"""RED tests for the separate Manhattan-only v4 worksheet policy."""

from __future__ import annotations

from io import BytesIO
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import nyc_manhattan_formula_xml_v1 as diagnostic  # noqa: E402
import nyc_workbook_xml_v3 as v3  # noqa: E402
import nyc_workbook_xml_v4 as v4  # noqa: E402
from tests.test_nyc_manhattan_formula_xml_v1 import _before  # noqa: E402
from tests.test_nyc_workbook_xml import TEST_PIN  # noqa: E402
from tests.test_nyc_workbook_xml_v3 import (  # noqa: E402
    RAW_HEADER,
    row,
    synthetic_xlsx,
    workbook,
)


def inspected(body: bytes, borough: str, expected: dict | None = None) -> dict:
    return v4._inspect_with_pin(
        BytesIO(body),
        TEST_PIN,
        borough=borough,
        expected_formula=expected,
        timer=lambda: 0.0,
        start=0.0,
    )


class WorksheetV4Test(unittest.TestCase):
    def setUp(self):
        self.body = workbook(before=_before("<f>1+1</f><v>PRIVATE_PRICE</v>"))
        self.expected = diagnostic._diagnose_with_pin(
            BytesIO(self.body), TEST_PIN, timer=lambda: 0.0
        )["formula"]

    def test_exact_private_formula_only_qualifies_manhattan_structure(self):
        old = v3._inspect_with_pin(BytesIO(self.body), TEST_PIN, timer=lambda: 0.0)
        self.assertFalse(old["worksheet_qualified"])
        result = inspected(self.body, "Manhattan", self.expected)
        self.assertTrue(result["worksheet_qualified"])
        self.assertFalse(result["v3_worksheet_qualified"])
        self.assertEqual(result["formula_exception_count"], 1)
        self.assertEqual(result["formula_cells"], 1)
        self.assertEqual(result["label_status"], "unqualified")
        self.assertEqual(result["sale_labels_certified"], 0)
        self.assertNotIn("PRIVATE_PRICE", json.dumps(result))
        self.assertNotIn("1+1", json.dumps(result))

    def test_other_boroughs_keep_strict_v3_rule(self):
        clean = inspected(workbook(), "Bronx")
        self.assertTrue(clean["worksheet_qualified"])
        self.assertEqual(clean["formula_exception_count"], 0)
        formula = inspected(self.body, "Bronx")
        self.assertFalse(formula["worksheet_qualified"])
        self.assertFalse(formula["v3_worksheet_qualified"])
        with self.assertRaises(ValueError):
            inspected(workbook(), "Unknown")

    def test_missing_or_changed_private_formula_is_rejected(self):
        with self.assertRaises(ValueError):
            inspected(self.body, "Manhattan")
        changed = workbook(before=_before("<f>2+2</f><v>PRIVATE_PRICE</v>"))
        with self.assertRaises(ValueError):
            inspected(changed, "Manhattan", self.expected)
        changed_metadata = workbook(before=_before('<f t="shared" si="1"/>'))
        with self.assertRaises(ValueError):
            inspected(changed_metadata, "Manhattan", self.expected)

    def test_extra_or_relocated_formulas_fail(self):
        another = _before("<f>1+1</f>").replace(
            '<row r="2"></row>', '<row r="2"><c r="B2"><f>2</f></c></row>'
        )
        header_formula = synthetic_xlsx(
            rows=_before("<f>1+1</f>")
            + row(5, {**dict(enumerate(RAW_HEADER, 1)), 1: "2"}, formula=1)
            + row(6, {21: "09/15/2025"})
        )
        for body in (
            workbook(before=another),
            header_formula,
            workbook(after=row(7, {1: "2"}, formula=1), before=_before("<f>1+1</f>")),
            workbook(
                before=row(1, {22: "2"}, formula=22)
                + "".join(row(i, {}) for i in range(2, 5))
            ),
        ):
            with self.subTest(body_length=len(body)), self.assertRaises(ValueError):
                inspected(body, "Manhattan", self.expected)

    def test_header_date_extra_cell_and_malformed_tail_fail(self):
        bad_header = synthetic_xlsx(
            rows=_before("<f>1+1</f>")
            + row(5, {**dict(enumerate(RAW_HEADER, 1)), 1: "WRONG"})
            + row(6, {21: "09/15/2025"})
        )
        bad_date = workbook(
            before=_before("<f>1+1</f>"), after=row(7, {21: "09/15/2030"})
        )
        extra = workbook(before=_before("<f>1+1</f>"), after=row(7, {22: "EXTRA"}))
        malformed = synthetic_xlsx(
            rows=_before("<f>1+1</f>")
            + row(5, dict(enumerate(RAW_HEADER, 1)))
            + row(6, {21: "09/15/2025"})
            + "<row>"
        )
        for body in (bad_header, bad_date, extra, malformed):
            with self.subTest(body_length=len(body)), self.assertRaises(ValueError):
                inspected(body, "Manhattan", self.expected)


if __name__ == "__main__":
    unittest.main()
