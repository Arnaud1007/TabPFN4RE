"""A proposed market map must be geography-checked without admitting service."""

from copy import deepcopy
from contextlib import redirect_stdout
from hashlib import sha256
from io import StringIO
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import validate_us_market_scope as scope  # noqa: E402
from validate_us_market_scope import census_metros, validate_manifest  # noqa: E402

NY_NONMETRO = (
    "36003 36009 36011 36013 36017 36019 36021 36023 36025 36031 36033 "
    "36035 36037 36039 36041 36049 36057 36077 36089 36097 36099 36101 "
    "36105 36121 36123"
).split()
FL_NONMETRO = (
    "12007 12013 12023 12027 12029 12037 12043 12045 12047 12049 12051 "
    "12059 12063 12067 12077 12079 12087 12093 12107 12121 12123 12125"
).split()


def candidate_fixture():
    document = json.loads((ROOT / "data/us_market_candidates.json").read_text())
    census = {}
    for market in document["metro_candidates"]:
        counties = set(market["potential_source_counties"])
        while len(counties) < market["cbsa_county_count"]:
            counties.add(f"99{len(counties):03d}")
        census[market["cbsa_code"]] = (market["cbsa_title"], counties)
    return document, census


def nonmetro_fixture():
    document, census = candidate_fixture()
    ny_selected = {
        county
        for market in document["metro_candidates"]
        for county in market["potential_source_counties"]
        if county.startswith("36")
    }
    fl_selected = {
        county
        for market in document["metro_candidates"]
        for county in market["potential_source_counties"]
        if county.startswith("12")
    }
    ny_extra = {"36007"} | {f"36{number:03d}" for number in range(900, 926)}
    fl_extra = {"12017"} | {f"12{number:03d}" for number in range(900, 940)}
    census["99990"] = ("Other NY metro", ny_extra)
    census["99991"] = ("Other FL metro", fl_extra)
    universes = {
        "36": set(NY_NONMETRO) | ny_selected | ny_extra,
        "12": set(FL_NONMETRO) | fl_selected | fl_extra,
    }
    assert len(universes["36"]) == 62
    assert len(universes["12"]) == 67
    return document, census, universes


class MarketScopeTests(unittest.TestCase):
    def test_manifest_materializes_official_nonmetro_counties(self):
        document, _ = candidate_fixture()
        areas = {area["state_fips"]: area for area in document["nonmetro_candidates"]}
        self.assertEqual(areas["36"]["county_fips"], NY_NONMETRO)
        self.assertEqual(areas["12"]["county_fips"], FL_NONMETRO)
        self.assertEqual(len(areas["36"]["county_fips"]), 25)
        self.assertEqual(len(areas["12"]["county_fips"]), 22)
        self.assertIn("36009", areas["36"]["county_fips"])  # micropolitan
        self.assertIn("12007", areas["12"]["county_fips"])  # outside every CBSA

    def test_gazetteer_reader_requires_unique_county_geoid_and_state(self):
        header = b"USPS\tGEOID\tANSICODE\tNAME\n"
        rows = b"NY\t36001\t1\tAlbany County\nNY\t36003\t2\tAllegany County\n"
        self.assertEqual(
            scope.gazetteer_counties(header + rows, "36", "NY"), {"36001", "36003"}
        )
        with self.assertRaisesRegex(ValueError, "duplicate"):
            scope.gazetteer_counties(
                header + rows + rows[: rows.index(b"\n") + 1], "36", "NY"
            )
        with self.assertRaisesRegex(ValueError, "state or GEOID"):
            scope.gazetteer_counties(
                header + b"FL\t12001\t1\tAlachua County\n", "36", "NY"
            )

    def test_pinned_county_reader_rejects_changed_bytes(self):
        body = b"USPS\tGEOID\tANSICODE\tNAME\nNY\t36001\t1\tAlbany County\n"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "counties.txt"
            path.write_bytes(body)
            with (
                patch.object(
                    scope, "PINNED_COUNTY_SHA256", {"36": sha256(body).hexdigest()}
                ),
                patch.object(scope, "COUNTY_COUNTS", {"36": 1}),
            ):
                self.assertEqual(scope.read_pinned_counties(path, "36")[0], {"36001"})
                path.write_bytes(body + b"NY\t36003\t2\tAllegany County\n")
                with self.assertRaisesRegex(ValueError, "independent pin"):
                    scope.read_pinned_counties(path, "36")

    def test_nonmetro_membership_uses_all_metros_and_complete_county_universe(self):
        document, census, universes = nonmetro_fixture()
        result = validate_manifest(document, census, ROOT, county_universes=universes)
        self.assertEqual(result["status"], "PASS_CANDIDATE_MEMBERSHIP_CONSISTENCY_ONLY")
        self.assertFalse(result["nonmetro_membership_verified"])
        self.assertEqual(result["nonmetro_counties"], {"12": 22, "36": 25})
        self.assertEqual(result["supported_markets"], 0)
        self.assertEqual(result["certified_sale_labels"], 0)
        self.assertEqual(result["g_us_status"], "PENDING")

    def test_nonmetro_list_mutations_are_rejected(self):
        document, census, universes = nonmetro_fixture()
        for mutated in (
            NY_NONMETRO[1:],
            sorted(NY_NONMETRO + ["36007"]),
            NY_NONMETRO + ["36009"],
            NY_NONMETRO + ["12007"],
            NY_NONMETRO + [36003],
            list(reversed(NY_NONMETRO)),
        ):
            with (
                self.subTest(mutated=mutated),
                self.assertRaisesRegex(ValueError, "Nonmetro county"),
            ):
                changed = deepcopy(document)
                changed["nonmetro_candidates"][0]["county_fips"] = mutated
                validate_manifest(changed, census, ROOT, county_universes=universes)

    def test_nonmetro_universe_cannot_omit_an_unselected_metro(self):
        document, census, universes = nonmetro_fixture()
        universes["36"].remove("36007")
        universes["36"].add("36999")
        with self.assertRaisesRegex(ValueError, "Metropolitan county is absent"):
            validate_manifest(document, census, ROOT, county_universes=universes)

    def test_incomplete_supplied_universe_cannot_be_verified(self):
        document, census, universes = nonmetro_fixture()
        universes["36"].remove("36003")
        document["nonmetro_candidates"][0]["county_fips"].remove("36003")
        with self.assertRaisesRegex(ValueError, "county universe differs"):
            validate_manifest(document, census, ROOT, county_universes=universes)

    def test_nonmetro_source_pin_and_state_cannot_change(self):
        document, census = candidate_fixture()
        document["census_county_references"]["36"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "reference pin"):
            validate_manifest(document, census, ROOT)
        document, census = candidate_fixture()
        document["nonmetro_candidates"][0]["state_fips"] = "34"
        with self.assertRaisesRegex(ValueError, "states are not distinct"):
            validate_manifest(document, census, ROOT)

    def test_non_object_manifest_is_rejected_explicitly(self):
        with self.assertRaisesRegex(ValueError, "schema differs"):
            validate_manifest(None, {}, ROOT)

    def test_all_candidates_validate_without_service_claim(self):
        document, census = candidate_fixture()
        result = validate_manifest(document, census, ROOT)
        self.assertEqual(result["status"], "PASS_CANDIDATE_STRUCTURE_ONLY")
        self.assertEqual(result["metro_candidates"], 8)
        self.assertEqual(result["nonmetro_candidates"], 2)
        self.assertEqual(result["certified_sale_labels"], 0)

    def test_wrong_census_title_is_rejected(self):
        document, census = candidate_fixture()
        document["metro_candidates"][0]["cbsa_title"] = "invented metro"
        with self.assertRaisesRegex(ValueError, "Census title"):
            validate_manifest(document, census, ROOT)

    def test_county_outside_cbsa_is_rejected(self):
        document, census = candidate_fixture()
        document["metro_candidates"][0]["potential_source_counties"] = ["99999"]
        with self.assertRaisesRegex(ValueError, "outside Census CBSA"):
            validate_manifest(document, census, ROOT)

    def test_non_text_county_is_rejected_explicitly(self):
        document, census = candidate_fixture()
        document["metro_candidates"][0]["potential_source_counties"] = [12345]
        with self.assertRaisesRegex(ValueError, "source county format"):
            validate_manifest(document, census, ROOT)

    def test_supported_status_is_rejected(self):
        document, census = candidate_fixture()
        document["metro_candidates"][0]["status"] = "supported"
        with self.assertRaisesRegex(ValueError, "candidate status"):
            validate_manifest(document, census, ROOT)

    def test_manifest_cannot_claim_support_or_add_unreviewed_fields(self):
        document, census = candidate_fixture()
        document["status"] = "supported"
        with self.assertRaisesRegex(ValueError, "unsupported service"):
            validate_manifest(document, census, ROOT)
        document["status"] = "candidate_inventory_not_service_area"
        document["national_accuracy"] = "5%"
        with self.assertRaisesRegex(ValueError, "schema differs"):
            validate_manifest(document, census, ROOT)

    def test_region_balance_and_nonmetro_state_are_checked(self):
        document, census = candidate_fixture()
        document["metro_candidates"][0]["region"] = "West"
        with self.assertRaisesRegex(ValueError, "region differs"):
            validate_manifest(document, census, ROOT)
        document, census = candidate_fixture()
        document["nonmetro_candidates"][1]["state_fips"] = "36"
        with self.assertRaisesRegex(ValueError, "states are not distinct"):
            validate_manifest(document, census, ROOT)

    def test_census_count_and_nonmetro_rule_are_checked(self):
        document, census = candidate_fixture()
        document["metro_candidates"][0]["cbsa_county_count"] = 1
        with self.assertRaisesRegex(ValueError, "county count"):
            validate_manifest(document, census, ROOT)
        document, census = candidate_fixture()
        document["nonmetro_candidates"][0]["rule"] = "all New York counties"
        with self.assertRaisesRegex(ValueError, "metro exclusion"):
            validate_manifest(document, census, ROOT)

    def test_unsafe_source_card_path_is_rejected(self):
        document, census = candidate_fixture()
        document["metro_candidates"][0]["source_cards"] = [
            "data/source_cards/../us_market_candidates.json"
        ]
        with self.assertRaisesRegex(ValueError, "source card"):
            validate_manifest(document, census, ROOT)

    def test_missing_candidate_and_wrong_pin_are_rejected(self):
        document, census = candidate_fixture()
        document["metro_candidates"].pop()
        with self.assertRaisesRegex(ValueError, "floors differ"):
            validate_manifest(document, census, ROOT)
        document, census = candidate_fixture()
        document["census_delineation"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "Census pin"):
            validate_manifest(document, census, ROOT)

    def test_duplicate_metro_and_missing_source_card_are_rejected(self):
        document, census = candidate_fixture()
        duplicate = deepcopy(document)
        duplicate["metro_candidates"][1]["cbsa_code"] = duplicate["metro_candidates"][
            0
        ]["cbsa_code"]
        with self.assertRaisesRegex(ValueError, "duplicate CBSA"):
            validate_manifest(duplicate, census, ROOT)
        document["metro_candidates"][0]["source_cards"] = [
            "data/source_cards/does_not_exist.yaml"
        ]
        with self.assertRaisesRegex(ValueError, "source card"):
            validate_manifest(document, census, ROOT)

    def test_census_reader_uses_metropolitan_rows_and_shared_strings(self):
        shared = (
            '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            "<si><t>Example, ST</t></si>"
            "<si><t>Metropolitan Statistical Area</t></si>"
            "<si><t>Micropolitan Statistical Area</t></si>"
            "</sst>"
        )
        sheet = (
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            "<sheetData>"
            '<row r="1"><c r="A1" t="inlineStr"><is><t>12345</t></is></c>'
            '<c r="D1" t="s"><v>0</v></c><c r="E1" t="s"><v>1</v></c>'
            '<c r="J1"><v>36</v></c><c r="K1"><v>001</v></c></row>'
            '<row r="2"><c r="A2"><v>99999</v></c>'
            '<c r="D2" t="s"><v>0</v></c><c r="E2" t="s"><v>2</v></c>'
            '<c r="J2"><v>36</v></c><c r="K2"><v>003</v></c></row>'
            "</sheetData></worksheet>"
        )
        with tempfile.TemporaryDirectory() as directory:
            workbook = Path(directory) / "census.xlsx"
            with ZipFile(workbook, "w") as archive:
                archive.writestr("xl/sharedStrings.xml", shared)
                archive.writestr("xl/worksheets/sheet1.xml", sheet)
            self.assertEqual(
                census_metros(workbook.read_bytes()),
                {"12345": ("Example, ST", {"36001"})},
            )

    def test_cli_rejects_wrong_workbook_hash_before_parse(self):
        with tempfile.TemporaryDirectory() as directory:
            workbook = Path(directory) / "census.xlsx"
            workbook.write_bytes(b"not a Census workbook")
            with patch.object(
                sys,
                "argv",
                ["validate_us_market_scope", "--census", str(workbook)],
            ):
                with self.assertRaisesRegex(ValueError, "independent pin"):
                    scope.main()

    def test_cli_passes_hash_checked_county_sets_to_validation(self):
        _, census = candidate_fixture()
        with tempfile.TemporaryDirectory() as directory:
            workbook = Path(directory) / "census.xlsx"
            workbook.write_bytes(b"fixture")
            county_paths = {}
            county_hashes = {}
            for state, usps in (("12", "FL"), ("36", "NY")):
                path = Path(directory) / f"counties_{state}.txt"
                body = (
                    f"USPS\tGEOID\tANSICODE\tNAME\n"
                    f"{usps}\t{state}001\t1\tExample County\n"
                ).encode()
                path.write_bytes(body)
                county_paths[state] = path
                county_hashes[state] = sha256(body).hexdigest()
            capture = StringIO()
            with (
                patch.object(
                    scope, "PINNED_CENSUS_SHA256", sha256(b"fixture").hexdigest()
                ),
                patch.object(scope, "PINNED_COUNTY_SHA256", county_hashes),
                patch.object(scope, "COUNTY_COUNTS", {"12": 1, "36": 1}),
                patch.object(scope, "census_metros", return_value=census),
                patch.object(
                    sys,
                    "argv",
                    [
                        "scope",
                        "--census",
                        str(workbook),
                        "--fl-counties",
                        str(county_paths["12"]),
                        "--ny-counties",
                        str(county_paths["36"]),
                    ],
                ),
                redirect_stdout(capture),
            ):
                with patch.object(
                    scope, "validate_manifest", return_value={"supported_markets": 0}
                ) as validator:
                    scope.main()
            self.assertEqual(
                validator.call_args.kwargs["county_universes"],
                {"12": {"12001"}, "36": {"36001"}},
            )
            result = json.loads(capture.getvalue())
            self.assertEqual(result["supported_markets"], 0)
            self.assertTrue(result["nonmetro_membership_verified"])
            self.assertEqual(result["county_universe_sha256"], county_hashes)


if __name__ == "__main__":
    unittest.main()
