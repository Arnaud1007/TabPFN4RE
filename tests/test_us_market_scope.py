"""A proposed market map must be geography-checked without admitting service."""

from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from validate_us_market_scope import census_metros, validate_manifest  # noqa: E402


def candidate_fixture():
    document = json.loads((ROOT / "data/us_market_candidates.json").read_text())
    census = {}
    for market in document["metro_candidates"]:
        counties = set(market["potential_source_counties"])
        while len(counties) < market["cbsa_county_count"]:
            counties.add(f"99{len(counties):03d}")
        census[market["cbsa_code"]] = (market["cbsa_title"], counties)
    return document, census


class MarketScopeTests(unittest.TestCase):
    def test_all_candidates_validate_without_service_claim(self):
        document, census = candidate_fixture()
        result = validate_manifest(document, census, ROOT)
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

    def test_supported_status_is_rejected(self):
        document, census = candidate_fixture()
        document["metro_candidates"][0]["status"] = "supported"
        with self.assertRaisesRegex(ValueError, "candidate status"):
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
                census_metros(workbook), {"12345": ("Example, ST", {"36001"})}
            )


if __name__ == "__main__":
    unittest.main()
