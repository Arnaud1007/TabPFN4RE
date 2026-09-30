"""Synthetic RED tests for the separate Manhattan formula diagnostic."""

from __future__ import annotations

from io import BytesIO
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import nyc_manhattan_formula_xml_v1 as diagnostic  # noqa: E402
import nyc_workbook_xml_v3 as v3  # noqa: E402
from tests.test_nyc_workbook_xml import TEST_PIN  # noqa: E402
from tests.test_nyc_workbook_xml_v3 import (  # noqa: E402
    RAW_HEADER,
    row,
    synthetic_xlsx,
    workbook,
)


def _before(formula: str, *, row_number: int = 1) -> str:
    preamble = []
    for number in range(1, 5):
        preamble.append(
            f'<row r="{number}"><c r="A{number}">{formula}</c></row>'
            if number == row_number
            else row(number, {})
        )
    return "".join(preamble)


def inspect(body: bytes) -> dict:
    return diagnostic._diagnose_with_pin(
        BytesIO(body), TEST_PIN, timer=lambda: 0.0, start=0.0
    )


class ManhattanFormulaXmlTest(unittest.TestCase):
    def test_one_preamble_formula_is_private_diagnosis_only(self):
        body = workbook(
            before=_before("<f>1+1</f><v>PRIVATE_CACHED_PRICE</v>", row_number=4)
        )
        prior = v3._inspect_with_pin(BytesIO(body), TEST_PIN, timer=lambda: 0.0)
        self.assertFalse(prior["worksheet_qualified"])
        result = inspect(body)
        self.assertEqual(result["protocol"], "nyc-manhattan-formula-diagnostic-v1")
        self.assertEqual(result["formula"]["coordinate"], "A4")
        self.assertEqual(result["formula"]["source_row"], 4)
        self.assertEqual(result["formula"]["physical_ordinal"], 4)
        self.assertEqual(result["formula"]["expression"], "1+1")
        self.assertTrue(result["formula"]["cached_value_present"])
        self.assertFalse(result["v3_worksheet_qualified"])
        self.assertEqual(result["sale_labels_certified"], 0)
        self.assertNotIn("PRIVATE_CACHED_PRICE", json.dumps(result))
        self.assertNotIn("PRIVATE_SALE_ADDRESS", json.dumps(result))

    def test_shared_formula_with_empty_expression_keeps_bounded_attributes(self):
        body = workbook(before=_before('<f t="shared" si="3" ref="A1:A4"/>'))
        result = inspect(body)
        self.assertEqual(result["formula"]["expression"], "")
        self.assertEqual(
            result["formula"]["attributes"],
            {"t": "shared", "si": "3", "ref": "A1:A4"},
        )
        self.assertFalse(result["formula"]["cached_value_present"])

    def test_no_or_wrong_zone_formula_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "one preamble formula"):
            inspect(workbook())
        formula_data = row(7, {1: "2"}, formula=1)
        with self.assertRaisesRegex(ValueError, "one preamble formula"):
            inspect(workbook(after=formula_data))

    def test_multiple_or_beyond_header_formula_is_rejected(self):
        before = _before("<f>1</f>").replace(
            '<row r="2"></row>', '<row r="2"><c r="B2"><f>2</f></c></row>'
        )
        with self.assertRaisesRegex(ValueError, "one preamble formula"):
            inspect(workbook(before=before))
        extra = row(1, {22: "2"}, formula=22) + "".join(
            row(number, {}) for number in range(2, 5)
        )
        with self.assertRaisesRegex(ValueError, "preamble structural"):
            inspect(workbook(before=extra))

    def test_duplicate_formula_nodes_or_oversized_expression_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "formula XML"):
            inspect(workbook(before=_before("<f>1</f><f>2</f>")))
        with self.assertRaisesRegex(ValueError, "formula XML"):
            inspect(workbook(before=_before(f"<f>{'x' * 513}</f>")))

    def test_changed_pin_and_malformed_tail_fail_closed(self):
        body = workbook(before=_before("<f>1</f>"))
        with self.assertRaises(ValueError):
            diagnostic._diagnose_with_pin(
                BytesIO(body), (TEST_PIN[0], "0" * 64), timer=lambda: 0.0
            )
        broken = synthetic_xlsx(
            rows=_before("<f>1</f>")
            + row(5, dict(enumerate(RAW_HEADER, 1)))
            + row(6, {21: "09/15/2025"})
            + "<row>"
        )
        with self.assertRaises(ValueError):
            inspect(broken)


if __name__ == "__main__":
    unittest.main()
