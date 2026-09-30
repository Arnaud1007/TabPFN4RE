"""Synthetic RED tests for the frozen NYC v3 worksheet protocol."""

from __future__ import annotations

import sys
import unittest
from datetime import date
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import nyc_workbook_xml as v2  # noqa: E402
import nyc_workbook_xml_v3 as v3  # noqa: E402
from profile_nyc_rolling_snapshot import HEADER  # noqa: E402

from tests.test_nyc_workbook_xml import (  # noqa: E402
    TEST_PIN,
    archive_parts,
    cell,
    mutated,
    repack,
)
from tests.test_nyc_workbook_xml import (
    synthetic_xlsx as v2_synthetic_xlsx,
)

RAW_HEADER = (*HEADER[:6], "EASEMENT", *HEADER[7:])
RAW_FINGERPRINT = sha256("\x1f".join(RAW_HEADER).encode()).hexdigest()


def synthetic_xlsx(**kwargs) -> bytes:
    parts = archive_parts(v2_synthetic_xlsx(**kwargs))
    content_types = parts["[Content_Types].xml"]
    declaration = (
        b'<Override PartName="/xl/worksheets/sheet1.xml" '
        b'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
    )
    parts["[Content_Types].xml"] = content_types.replace(
        b"</Types>", declaration + b"</Types>"
    )
    return repack(parts)


def row(number: int, fields: dict[int, str], *, formula: int | None = None) -> str:
    values = []
    for column, value in sorted(fields.items()):
        if column == formula:
            values.append(
                f'<c r="{chr(64 + column)}{number}"><f>1+1</f><v>{value}</v></c>'
            )
        else:
            values.append(cell(column, number, value))
    return f'<row r="{number}">{"".join(values)}</row>'


def workbook(
    *,
    header: tuple[str, ...] = RAW_HEADER,
    header_row: int = 5,
    date: str = "09/15/2025",
    before: str = "",
    after: str = "",
    extra_header: str = "",
    date1904: str = "",
) -> bytes:
    preamble = before or "".join(row(number, {}) for number in range(1, header_row))
    heading = row(header_row, dict(enumerate(header, 1)))
    sale = row(header_row + 1, {9: "PRIVATE_SALE_ADDRESS", 20: "987654321", 21: date})
    return synthetic_xlsx(
        rows=preamble + heading + sale + extra_header + after,
        date1904=date1904,
    )


def inspect(body: bytes) -> dict:
    return v3._inspect_with_pin(BytesIO(body), TEST_PIN, timer=lambda: 0.0, start=0.0)


class V3HeaderAliasTest(unittest.TestCase):
    def test_exact_row_five_alias_accepts_structure_without_labels(self):
        result = inspect(workbook())
        self.assertEqual(result["protocol"], "nyc-borough-worksheet-inspection-v3")
        self.assertTrue(result["worksheet_qualified"])
        self.assertEqual(result["header_status"], "exact_pinned_alias")
        self.assertEqual(result["raw_header_sha256"], RAW_FINGERPRINT)
        self.assertEqual(
            result["header_lineage"],
            {
                "source_column": "G",
                "source_column_index": 7,
                "source_name": "EASEMENT",
                "canonical_name": "EASE-MENT",
            },
        )
        self.assertEqual(result["physical_rows"], 6)
        self.assertEqual(result["data_rows"], 1)
        self.assertEqual(result["date_min"], "2025-09-15")
        self.assertEqual(result["date_max"], "2025-09-15")
        self.assertEqual(result["label_status"], "unqualified")
        self.assertEqual(result["sale_labels_certified"], 0)
        self.assertNotIn("PRIVATE_SALE_ADDRESS", str(result))
        self.assertNotIn("987654321", str(result))

    def test_v2_result_is_still_a_header_mismatch(self):
        outcome = v2._inspect_workbook_with_pin(
            BytesIO(workbook()), TEST_PIN, timer=lambda: 0.0, start=0.0
        )
        self.assertFalse(outcome["qualified"])
        self.assertEqual(outcome["header_status"], "mismatch")

    def test_only_exact_g_alias_is_accepted(self):
        variants = (
            HEADER,
            (*HEADER[:6], "Easement", *HEADER[7:]),
            (*HEADER[:6], "EASE MENT", *HEADER[7:]),
            (*HEADER[:6], "EASEMENT", *HEADER[7:19], "SALE DATE", "SALE PRICE"),
        )
        for variant in variants:
            with self.subTest(variant=variant[6]):
                result = inspect(workbook(header=variant))
                self.assertFalse(result["worksheet_qualified"])
                self.assertEqual(result["label_status"], "unqualified")
        trimmed = (*HEADER[:6], " EASEMENT ", *HEADER[7:])
        self.assertTrue(inspect(workbook(header=trimmed))["worksheet_qualified"])

    def test_header_must_be_physical_and_source_row_five(self):
        result = inspect(workbook(header_row=4))
        self.assertFalse(result["worksheet_qualified"])
        sparse = row(1, {}) + row(2, {}) + row(3, {})
        result = inspect(workbook(before=sparse))
        self.assertFalse(result["worksheet_qualified"])

    def test_partial_header_like_preamble_is_not_a_second_complete_candidate(self):
        partial = row(1, {i: RAW_HEADER[i - 1] for i in range(1, 6)})
        preamble = partial + row(2, {}) + row(3, {}) + row(4, {})
        result = inspect(workbook(before=preamble))
        self.assertTrue(result["worksheet_qualified"])
        self.assertEqual(result["invalid_header_candidate_rows"], 0)

    def test_second_complete_header_like_row_blocks_qualification(self):
        preamble = row(1, dict(enumerate(HEADER, 1))) + "".join(
            row(i, {}) for i in range(2, 5)
        )
        result = inspect(workbook(before=preamble))
        self.assertFalse(result["worksheet_qualified"])
        self.assertEqual(result["invalid_header_candidate_rows"], 1)

    def test_extra_preamble_cell_blocks_qualification(self):
        preamble = row(1, {22: "unexpected"}) + "".join(row(i, {}) for i in range(2, 5))
        result = inspect(workbook(before=preamble))
        self.assertFalse(result["worksheet_qualified"])
        self.assertEqual(result["extra_preamble_cells"], 1)

    def test_formula_in_preamble_header_data_or_extra_column_blocks(self):
        header = row(5, dict(enumerate(RAW_HEADER, 1)))
        sale = row(6, {21: "09/15/2025"})
        cases = (
            row(1, {1: "2"}, formula=1) + row(2, {}) + row(3, {}) + row(4, {}),
            row(1, {22: "2"}, formula=22) + row(2, {}) + row(3, {}) + row(4, {}),
        )
        for preamble in cases:
            with self.subTest(preamble=preamble[:25]):
                result = inspect(synthetic_xlsx(rows=preamble + header + sale))
                self.assertFalse(result["worksheet_qualified"])
                self.assertGreater(result["formula_cells"], 0)
        for changed in (
            row(5, {**dict(enumerate(RAW_HEADER, 1)), 1: "2"}, formula=1),
            header + row(6, {21: "09/15/2025", 22: "2"}, formula=22),
        ):
            with self.subTest(changed=changed[:25]):
                rows = "".join(row(i, {}) for i in range(1, 5)) + changed
                if 'r="6"' not in changed:
                    rows += sale
                result = inspect(synthetic_xlsx(rows=rows))
                self.assertFalse(result["worksheet_qualified"])

    def test_date_boundaries_and_invalid_values(self):
        for value in ("09/01/2025", "08/31/2026"):
            with self.subTest(valid=value):
                self.assertTrue(inspect(workbook(date=value))["worksheet_qualified"])
        for value in ("08/31/2025", "09/01/2026", "not-a-date", ""):
            with self.subTest(invalid=value):
                self.assertFalse(inspect(workbook(date=value))["worksheet_qualified"])
        excel_1900_serial = (date(2025, 9, 1) - date(1899, 12, 30)).days
        for value in ("2025-09-01", str(excel_1900_serial)):
            with self.subTest(valid_other_format=value):
                self.assertTrue(inspect(workbook(date=value))["worksheet_qualified"])

    def test_repeated_header_and_extra_data_cell_reject(self):
        repeated = row(7, dict(enumerate(RAW_HEADER, 1)))
        self.assertFalse(
            inspect(workbook(extra_header=repeated))["worksheet_qualified"]
        )
        extra = row(7, {21: "09/16/2025", 22: "unexpected"})
        self.assertFalse(inspect(workbook(after=extra))["worksheet_qualified"])

    def test_package_anti_active_controls_are_inherited(self):
        body = mutated(add={"xl/vbaProject.bin": b"not-executable"})
        with self.assertRaises(ValueError):
            inspect(body)

    def test_worksheet_content_type_declaration_is_required(self):
        with self.assertRaises(ValueError):
            inspect(
                v2_synthetic_xlsx(
                    rows="".join(row(i, {}) for i in range(1, 5))
                    + row(5, dict(enumerate(RAW_HEADER, 1)))
                    + row(6, {21: "09/15/2025"})
                )
            )
        parts = archive_parts(workbook())
        mime = (
            b"application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"
        )
        parts["[Content_Types].xml"] = parts["[Content_Types].xml"].replace(
            mime, b"garbage.spreadsheetml.worksheet+xml"
        )
        with self.assertRaises(ValueError):
            inspect(repack(parts))
        parts = archive_parts(workbook())
        conflicting = (
            b'<Override PartName="/xl/worksheets/sheet1.xml" '
            b'ContentType="application/octet-stream"/>'
        )
        parts["[Content_Types].xml"] = parts["[Content_Types].xml"].replace(
            b"</Types>", conflicting + b"</Types>"
        )
        with self.assertRaises(ValueError):
            inspect(repack(parts))

    def test_missing_duplicate_and_nonmonotone_coordinates(self):
        missing = row(5, {i: name for i, name in enumerate(RAW_HEADER, 1) if i != 7})
        preamble = "".join(row(i, {}) for i in range(1, 5))
        sale = row(6, {21: "09/15/2025"})
        self.assertFalse(
            inspect(synthetic_xlsx(rows=preamble + missing + sale))[
                "worksheet_qualified"
            ]
        )
        duplicate = row(5, dict(enumerate(RAW_HEADER, 1))).replace(
            "</row>", cell(1, 5, "duplicate") + "</row>"
        )
        with self.assertRaises(ValueError):
            inspect(synthetic_xlsx(rows=preamble + duplicate + sale))
        with self.assertRaises(ValueError):
            inspect(synthetic_xlsx(rows=preamble + sale + row(5, {})))
        nonmonotone_cells = (
            '<row r="5">'
            + cell(2, 5, RAW_HEADER[1])
            + cell(1, 5, RAW_HEADER[0])
            + "".join(cell(i, 5, RAW_HEADER[i - 1]) for i in range(3, 22))
            + "</row>"
        )
        with self.assertRaises(ValueError):
            inspect(synthetic_xlsx(rows=preamble + nonmonotone_cells + sale))

    def test_shared_string_header_and_1904_serial_date(self):
        header = "".join(
            cell(i, 5, "0", kind="s") if i == 7 else cell(i, 5, name)
            for i, name in enumerate(RAW_HEADER, 1)
        )
        serial = (date(2025, 9, 1) - date(1904, 1, 1)).days
        rows = (
            "".join(row(i, {}) for i in range(1, 5))
            + f'<row r="5">{header}</row>'
            + row(6, {21: str(serial)})
        )
        shared = '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><si><t>EASEMENT</t></si></sst>'
        result = inspect(
            synthetic_xlsx(rows=rows, shared=shared, date1904='date1904="1"')
        )
        self.assertTrue(result["worksheet_qualified"])
        self.assertEqual(result["date_min"], "2025-09-01")

    def test_malformed_tail_and_dtd_reject_without_partial_result(self):
        parts = archive_parts(workbook())
        name = "xl/worksheets/sheet1.xml"
        for damaged in (
            parts[name][:-12],
            parts[name].replace(
                b"<worksheet ",
                b'<!DOCTYPE worksheet [<!ENTITY x "unsafe">]><worksheet ',
                1,
            ),
        ):
            with self.subTest(damaged=damaged[-20:]), self.assertRaises(ValueError):
                inspect(repack({**parts, name: damaged}))

    def test_rows_nested_under_extension_are_not_worksheet_data(self):
        parts = archive_parts(workbook())
        name = "xl/worksheets/sheet1.xml"
        nested = (
            parts[name]
            .replace(b"<sheetData>", b"<sheetData><extLst>")
            .replace(b"</sheetData>", b"</extLst></sheetData>")
        )
        with self.assertRaises(ValueError):
            inspect(repack({**parts, name: nested}))

    def test_formula_cached_value_is_never_returned(self):
        header = row(5, dict(enumerate(RAW_HEADER, 1)))
        sale = (
            '<row r="6"><c r="U6"><f>1+1</f><v>PRIVATE_CACHED_SALE_VALUE</v></c></row>'
        )
        preamble = "".join(row(i, {}) for i in range(1, 5))
        result = inspect(synthetic_xlsx(rows=preamble + header + sale))
        self.assertFalse(result["worksheet_qualified"])
        self.assertNotIn("PRIVATE_CACHED_SALE_VALUE", str(result))

    def test_elapsed_time_cap(self):
        with self.assertRaises(TimeoutError):
            v3._inspect_with_pin(
                BytesIO(workbook()), TEST_PIN, timer=lambda: 181.0, start=0.0
            )

    def test_header_fingerprint_and_production_printer_pin_cannot_be_overridden(self):
        with patch.object(v3, "EXPECTED_RAW_HEADER_SHA256", "0" * 64):
            with self.assertRaises(ValueError):
                inspect(workbook())
        with self.assertRaises(ValueError):
            v3.inspect_workbook(BytesIO(workbook()), timer=lambda: 0.0, start=0.0)


if __name__ == "__main__":
    unittest.main()
