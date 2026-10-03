"""Validate a candidate US market map against a pinned Census delineation.

This validates geography and conservative status only. It cannot admit a sale
source, a service area, a model or a G-US market.
"""

from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import re
from xml.etree import ElementTree
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
PINNED_CENSUS_SHA256 = (
    "952c4b1e78acbb54e6ec9412434b7602fedacbf021736351a63c181bdb753629"
)
PINNED_COUNTY_SHA256 = {
    "12": "8026e05146f65d9cb3749a699e2d56a572535d620bd88451b5eb6bf59ffb7ffb",
    "36": "da451828242610580fad16caf7f6699fbe58d27277e4468e0a2811f0aacf8f16",
}
COUNTY_USPS = {"12": "FL", "36": "NY"}
COUNTY_COUNTS = {"12": 67, "36": 62}
NAMESPACE = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
REGION_BY_STATE = {
    "08": "West",
    "12": "South",
    "17": "Midwest",
    "18": "Midwest",
    "34": "Northeast",
    "36": "Northeast",
    "53": "West",
}
REGIONS = {"Northeast", "Midwest", "South", "West"}
TOP_KEYS = {
    "schema_version",
    "selection_version",
    "selected_on",
    "status",
    "product_mode",
    "property_scope",
    "target_origin",
    "census_delineation",
    "census_county_references",
    "census_region_reference",
    "common_admission_blockers",
    "metro_candidates",
    "nonmetro_candidates",
}
METRO_KEYS = {
    "id",
    "region",
    "cbsa_code",
    "cbsa_title",
    "cbsa_county_count",
    "potential_source_counties",
    "source_cards",
    "scope_gap",
    "variation_hypothesis",
    "status",
}
NONMETRO_KEYS = {
    "id",
    "region",
    "state_fips",
    "county_fips",
    "rule",
    "source_cards",
    "scope_gap",
    "status",
}


def _xml_bytes(archive: ZipFile, name: str) -> bytes:
    if archive.getinfo(name).file_size > 2_000_000:
        raise ValueError("Census workbook component is oversized")
    with archive.open(name) as stream:
        return stream.read(2_000_001)


def _shared_strings(archive: ZipFile) -> list[str]:
    root = ElementTree.fromstring(_xml_bytes(archive, "xl/sharedStrings.xml"))
    return ["".join(node.itertext()) for node in root.findall(f"{NAMESPACE}si")]


def _row_cells(row: ElementTree.Element, shared: list[str]) -> dict[str, str]:
    cells = {}
    for cell in row.findall(f"{NAMESPACE}c"):
        column = re.match(r"[A-Z]+", cell.attrib.get("r", ""))
        if column is None:
            raise ValueError("Census workbook has a cell without a column")
        if cell.attrib.get("t") == "inlineStr":
            text = "".join(cell.find(f"{NAMESPACE}is").itertext())
        else:
            value = cell.find(f"{NAMESPACE}v")
            if value is None or value.text is None:
                continue
            text = (
                shared[int(value.text)] if cell.attrib.get("t") == "s" else value.text
            )
        cells[column.group()] = text
    return cells


def census_metros(body: bytes) -> dict[str, tuple[str, set[str]]]:
    """Read metro title and county membership from the official XLSX layout."""
    with ZipFile(BytesIO(body)) as archive:
        shared = _shared_strings(archive)
        sheet = ElementTree.fromstring(_xml_bytes(archive, "xl/worksheets/sheet1.xml"))
    result: dict[str, tuple[str, set[str]]] = {}
    for row in sheet.findall(f".//{NAMESPACE}sheetData/{NAMESPACE}row"):
        cells = _row_cells(row, shared)
        if cells.get("E") != "Metropolitan Statistical Area":
            continue
        code, title = cells["A"], cells["D"]
        county = cells["J"].zfill(2) + cells["K"].zfill(3)
        if code in result and result[code][0] != title:
            raise ValueError("Census CBSA has inconsistent titles")
        result.setdefault(code, (title, set()))[1].add(county)
    if not result:
        raise ValueError("Census workbook has no metropolitan rows")
    return result


def gazetteer_counties(body: bytes, state_fips: str, usps: str) -> set[str]:
    """Parse the complete 2023 county universe for one state."""
    try:
        lines = body.decode("utf-8-sig").splitlines()
    except UnicodeDecodeError as exc:
        raise ValueError("County Gazetteer text is invalid UTF-8") from exc
    if not lines or lines[0].split("\t")[:4] != ["USPS", "GEOID", "ANSICODE", "NAME"]:
        raise ValueError("County Gazetteer header differs")
    counties: set[str] = set()
    for line in lines[1:]:
        cells = line.split("\t")
        if len(cells) < 4 or cells[0] != usps or not cells[3].strip():
            raise ValueError("County Gazetteer state or GEOID differs")
        geoid = cells[1]
        if re.fullmatch(r"[0-9]{5}", geoid) is None or geoid[:2] != state_fips:
            raise ValueError("County Gazetteer state or GEOID differs")
        if geoid in counties:
            raise ValueError("County Gazetteer has a duplicate GEOID")
        counties.add(geoid)
    if not counties:
        raise ValueError("County Gazetteer has no counties")
    return counties


def _check_county_references(references: object) -> None:
    if not isinstance(references, dict) or set(references) != set(COUNTY_USPS):
        raise ValueError("County Gazetteer references differ")
    for state, reference in references.items():
        expected_url = (
            "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/"
            f"2023_Gazetteer/2023_gaz_counties_{state}.txt"
        )
        if (
            not isinstance(reference, dict)
            or set(reference) != {"url", "sha256", "vintage", "usps", "county_count"}
            or reference["url"] != expected_url
            or reference["sha256"] != PINNED_COUNTY_SHA256[state]
            or reference["vintage"] != "2023"
            or reference["usps"] != COUNTY_USPS[state]
            or type(reference["county_count"]) is not int
            or reference["county_count"] != COUNTY_COUNTS[state]
        ):
            raise ValueError("County Gazetteer reference pin differs")


def _check_source_cards(cards: object, root: Path) -> None:
    if not isinstance(cards, list) or not cards:
        raise ValueError("Candidate needs a source card")
    for card in cards:
        if not isinstance(card, str):
            raise ValueError("Candidate source card path is invalid")
        path = Path(card)
        source_dir = (root / "data/source_cards").resolve()
        resolved = (root / path).resolve()
        if (
            path.is_absolute()
            or len(path.parts) != 3
            or path.parts[:2] != ("data", "source_cards")
            or path.suffix != ".yaml"
            or (root / path).is_symlink()
            or resolved.parent != source_dir
            or not resolved.is_file()
        ):
            raise ValueError("Candidate source card is missing or outside source_cards")


def _check_metro(market: dict, census: dict, root: Path) -> None:
    if (
        not isinstance(market, dict)
        or set(market) != METRO_KEYS
        or market["status"] != "candidate_not_supported"
    ):
        raise ValueError("Metro candidate status or schema is invalid")
    code = market["cbsa_code"]
    if code not in census:
        raise ValueError("Candidate CBSA is not metropolitan in Census file")
    title, counties = census[code]
    if market["cbsa_title"] != title:
        raise ValueError("Candidate Census title differs")
    if market["cbsa_county_count"] != len(counties):
        raise ValueError("Candidate Census county count differs")
    source_counties = market["potential_source_counties"]
    if not isinstance(source_counties, list) or not source_counties:
        raise ValueError("Candidate needs potential source counties")
    if any(
        not isinstance(value, str) or re.fullmatch(r"[0-9]{5}", value) is None
        for value in source_counties
    ):
        raise ValueError("Candidate source county format is invalid")
    if (
        len(source_counties) != len(set(source_counties))
        or not set(source_counties) <= counties
    ):
        raise ValueError("Candidate source county is outside Census CBSA or repeated")
    if market["region"] not in REGIONS or any(
        REGION_BY_STATE.get(value[:2]) != market["region"] for value in source_counties
    ):
        raise ValueError("Candidate Census region differs from source state")
    if not market["scope_gap"] or not market["variation_hypothesis"]:
        raise ValueError("Candidate lacks scope or variation rationale")
    _check_source_cards(market["source_cards"], root)


def _check_nonmetro(area: dict, root: Path) -> None:
    if (
        not isinstance(area, dict)
        or set(area) != NONMETRO_KEYS
        or area["status"] != "candidate_not_supported"
    ):
        raise ValueError("Nonmetro candidate status or schema is invalid")
    if (
        not isinstance(area["state_fips"], str)
        or REGION_BY_STATE.get(area["state_fips"]) != area["region"]
    ):
        raise ValueError("Nonmetro candidate region differs from state")
    if (
        not isinstance(area["rule"], str)
        or "outside every Metropolitan Statistical Area" not in area["rule"]
    ):
        raise ValueError("Nonmetro candidate rule lacks metro exclusion")
    if not area["scope_gap"]:
        raise ValueError("Nonmetro candidate needs an admission gap")
    counties = area["county_fips"]
    if (
        not isinstance(counties, list)
        or not counties
        or any(
            not isinstance(code, str)
            or re.fullmatch(r"[0-9]{5}", code) is None
            or code[:2] != area["state_fips"]
            for code in counties
        )
        or counties != sorted(set(counties))
    ):
        raise ValueError("Nonmetro county list is invalid")
    _check_source_cards(area["source_cards"], root)


def validate_manifest(
    document: dict,
    census: dict,
    root: Path,
    *,
    county_universes: dict[str, set[str]] | None = None,
) -> dict:
    """Validate geography and conservative claims, never data admission."""
    if (
        not isinstance(document, dict)
        or set(document) != TOP_KEYS
        or document["schema_version"] != 2
    ):
        raise ValueError("Market candidate manifest schema differs")
    if (
        document["status"] != "candidate_inventory_not_service_area"
        or document["product_mode"] != "OFF"
        or document["property_scope"] != "existing_single_family"
        or document["target_origin"] != "90_calendar_days_before_verified_close"
    ):
        raise ValueError("Market candidate manifest claims unsupported service")
    if (
        not isinstance(document["census_delineation"], dict)
        or set(document["census_delineation"]) != {"url", "sha256", "vintage"}
        or document["census_delineation"]["sha256"] != PINNED_CENSUS_SHA256
    ):
        raise ValueError("Manifest Census pin differs")
    _check_county_references(document["census_county_references"])
    if not isinstance(document["metro_candidates"], list) or not isinstance(
        document["nonmetro_candidates"], list
    ):
        raise ValueError("Market candidate lists are invalid")
    if (
        len(document["metro_candidates"]) != 8
        or len(document["nonmetro_candidates"]) != 2
    ):
        raise ValueError("Market candidate floors differ")
    for market in document["metro_candidates"]:
        if (
            not isinstance(market, dict)
            or set(market) != METRO_KEYS
            or not isinstance(market["cbsa_code"], str)
            or not isinstance(market["id"], str)
        ):
            raise ValueError("Metro candidate status or schema is invalid")
    for area in document["nonmetro_candidates"]:
        if (
            not isinstance(area, dict)
            or set(area) != NONMETRO_KEYS
            or not isinstance(area["state_fips"], str)
            or not isinstance(area["id"], str)
        ):
            raise ValueError("Nonmetro candidate status or schema is invalid")
    metro_codes = [item["cbsa_code"] for item in document["metro_candidates"]]
    ids = [
        item["id"]
        for item in document["metro_candidates"] + document["nonmetro_candidates"]
    ]
    if len(set(metro_codes)) != 8 or len(set(ids)) != 10:
        raise ValueError("Market candidate has a duplicate CBSA or ID")
    states = [item["state_fips"] for item in document["nonmetro_candidates"]]
    if set(states) != set(COUNTY_USPS):
        raise ValueError("Nonmetro candidate states are not distinct")
    for market in document["metro_candidates"]:
        _check_metro(market, census, root)
    for area in document["nonmetro_candidates"]:
        _check_nonmetro(area, root)
    if county_universes is not None:
        if not isinstance(county_universes, dict) or set(county_universes) != set(
            COUNTY_USPS
        ):
            raise ValueError("Nonmetro county universes are incomplete")
        metropolitan = set().union(*(entry[1] for entry in census.values()))
        for area in document["nonmetro_candidates"]:
            state = area["state_fips"]
            universe = county_universes[state]
            if (
                not isinstance(universe, set)
                or len(universe) != COUNTY_COUNTS[state]
                or any(
                    not isinstance(code, str)
                    or re.fullmatch(r"[0-9]{5}", code) is None
                    or not code.startswith(state)
                    for code in universe
                )
            ):
                raise ValueError("Nonmetro county universe differs")
            state_metros = {code for code in metropolitan if code.startswith(state)}
            if not state_metros <= universe:
                raise ValueError("Metropolitan county is absent from county universe")
            expected = sorted(universe - metropolitan)
            if area["county_fips"] != expected:
                raise ValueError("Nonmetro county membership differs from Census")
    regions = Counter(item["region"] for item in document["metro_candidates"])
    if set(regions) != REGIONS or any(count != 2 for count in regions.values()):
        raise ValueError("Market candidate Census-region balance differs")
    if (
        not isinstance(document["common_admission_blockers"], list)
        or len(document["common_admission_blockers"]) < 5
    ):
        raise ValueError("Market candidate admission blockers are incomplete")
    return {
        "status": (
            "PASS_CANDIDATE_MEMBERSHIP_CONSISTENCY_ONLY"
            if county_universes is not None
            else "PASS_CANDIDATE_STRUCTURE_ONLY"
        ),
        "metro_candidates": 8,
        "metro_regions": dict(sorted(regions.items())),
        "nonmetro_candidates": 2,
        "nonmetro_membership_verified": False,
        "nonmetro_counties": (
            {
                area["state_fips"]: len(area["county_fips"])
                for area in document["nonmetro_candidates"]
            }
            if county_universes is not None
            else None
        ),
        "supported_markets": 0,
        "certified_sale_labels": 0,
        "g_us_status": "PENDING",
    }


def read_pinned_counties(path: Path, state: str) -> tuple[set[str], str]:
    with path.open("rb") as stream:
        body = stream.read(64_001)
    digest = sha256(body).hexdigest()
    if len(body) > 64_000 or digest != PINNED_COUNTY_SHA256[state]:
        raise ValueError("Official County Gazetteer bytes differ from independent pin")
    counties = gazetteer_counties(body, state, COUNTY_USPS[state])
    if len(counties) != COUNTY_COUNTS[state]:
        raise ValueError("Official County Gazetteer county count differs")
    return counties, digest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest", type=Path, default=ROOT / "data/us_market_candidates.json"
    )
    parser.add_argument(
        "--census", type=Path, default=ROOT / "data/raw/census/list1_2023.xlsx"
    )
    parser.add_argument(
        "--fl-counties",
        type=Path,
        default=ROOT / "data/raw/census/2023_gaz_counties_12.txt",
    )
    parser.add_argument(
        "--ny-counties",
        type=Path,
        default=ROOT / "data/raw/census/2023_gaz_counties_36.txt",
    )
    args = parser.parse_args()
    with args.census.open("rb") as stream:
        body = stream.read(2_000_001)
    if len(body) > 2_000_000 or sha256(body).hexdigest() != PINNED_CENSUS_SHA256:
        raise ValueError("Official Census workbook bytes differ from independent pin")
    with args.manifest.open("rb") as stream:
        manifest_bytes = stream.read(64_001)
    if len(manifest_bytes) > 64_000:
        raise ValueError("Market candidate manifest is oversized")
    document = json.loads(manifest_bytes)
    county_universes = {}
    county_digests = {}
    for state, path in {"12": args.fl_counties, "36": args.ny_counties}.items():
        county_universes[state], county_digests[state] = read_pinned_counties(
            path, state
        )
    validated = validate_manifest(
        document, census_metros(body), ROOT, county_universes=county_universes
    )
    result = {
        **validated,
        "status": "PASS_CANDIDATE_GEOGRAPHY_ONLY",
        "nonmetro_membership_verified": True,
        "census_sha256": sha256(body).hexdigest(),
        "county_universe_sha256": county_digests,
        "county_universe_counts": {
            state: len(counties) for state, counties in county_universes.items()
        },
        "manifest_sha256": sha256(manifest_bytes).hexdigest(),
    }
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
