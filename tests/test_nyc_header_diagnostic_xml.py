"""Synthetic-only tests for private NYC XLSX header triage."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import nyc_header_diagnostic_xml as diagnostic  # noqa: E402
import nyc_workbook_xml as workbook  # noqa: E402
from profile_nyc_rolling_snapshot import HEADER  # noqa: E402
from tests.test_nyc_workbook_xml import (
    TEST_PIN,
    archive_parts,
    cell,
    repack,
    synthetic_xlsx,
)  # noqa: E402


def sheet(rows: str) -> bytes:
    return (
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
        + rows
        + "</sheetData></worksheet>"
    ).encode()


def edited_sheet(rows: str) -> bytes:
    parts = archive_parts(synthetic_xlsx())
    return repack({**parts, "xl/worksheets/sheet1.xml": sheet(rows)})


def header_row(number: int, names=HEADER) -> str:
    return (
        f'<row r="{number}">'
        + "".join(cell(index, number, name) for index, name in enumerate(names, 1))
        + "</row>"
    )


def scan(body: bytes) -> dict:
    return diagnostic._scan_with_pin(
        BytesIO(body), TEST_PIN, timer=lambda: 0.0, start=0.0
    )


class HeaderDiagnosticXmlTest(unittest.TestCase):
    def test_exact_and_changed_header_candidate(self):
        exact = scan(synthetic_xlsx())
        self.assertEqual(exact["status"], "candidate_found")
        self.assertEqual(exact["candidate"]["cells"], list(HEADER))
        self.assertEqual(exact["candidate"]["score"], 21)
        self.assertEqual(exact["candidate"]["physical_ordinal"], 1)
        self.assertEqual(
            exact["candidate"]["fingerprint_sha256"], workbook.HEADER_SHA256
        )
        changed = ("DIFFERENT", *HEADER[1:])
        result = scan(edited_sheet(header_row(1, changed)))
        self.assertEqual(result["candidate"]["score"], 20)
        self.assertEqual(result["candidate"]["cells"][0], "DIFFERENT")
        self.assertNotEqual(
            result["candidate"]["fingerprint_sha256"], workbook.HEADER_SHA256
        )

    def test_position_aware_missing_cells_extra_cells_and_no_sale_value(self):
        positions = (1, 3, 5, 7, 9)
        cells = "".join(cell(index, 1, HEADER[index - 1]) for index in positions)
        cells += cell(22, 1, "PRIVATE_PRICE_LIKE_VALUE")
        result = scan(edited_sheet(f'<row r="1">{cells}</row>'))
        candidate = result["candidate"]
        self.assertEqual(candidate["score"], 5)
        self.assertEqual(candidate["nonempty_count"], 5)
        self.assertEqual(candidate["beyond_21_count"], 1)
        self.assertEqual(candidate["cells"][1], "")
        self.assertNotIn("PRIVATE_PRICE_LIKE_VALUE", str(result))

    def test_tie_low_score_and_formula_high_row(self):
        tied = scan(edited_sheet(header_row(1) + header_row(2)))
        self.assertEqual(tied["status"], "no_unique_candidate")
        self.assertNotIn("candidate", tied)
        low = scan(edited_sheet(f'<row r="1">{cell(1, 1, HEADER[0])}</row>'))
        self.assertEqual(low["status"], "no_unique_candidate")
        header = header_row(1).replace(
            cell(21, 1, HEADER[20]),
            '<c r="U1"><f>1+1</f><v>PRIVATE_CACHED_FORMULA</v></c>',
        )
        formula = scan(edited_sheet(header))
        self.assertEqual(formula["status"], "rejected_formula_candidate")
        self.assertEqual(formula["formula_cells"], 1)
        self.assertEqual(formula["candidate_score"], 20)
        self.assertNotIn("candidate", formula)
        self.assertNotIn("PRIVATE_CACHED_FORMULA", str(formula))
        self.assertNotIn("fingerprint_sha256", str(formula))

    def test_formula_cache_and_post_25_values_are_never_extracted(self):
        formula = header_row(1).replace(
            cell(21, 1, HEADER[20]),
            '<c r="U1"><f>1+1</f><v>PRIVATE_CACHED_FORMULA</v></c>',
        )
        rows = formula + "".join(f'<row r="{number}"/>' for number in range(2, 26))
        rows += f'<row r="26">{cell(1, 26, "PRIVATE_POST_25")}</row>'
        with patch.object(
            diagnostic, "_bounded_text", side_effect=AssertionError("value extracted")
        ) as extractor:
            result = scan(edited_sheet(rows))
        extractor.assert_not_called()
        self.assertEqual(result["status"], "rejected_formula_candidate")
        self.assertNotIn("PRIVATE_CACHED_FORMULA", str(result))
        self.assertNotIn("PRIVATE_POST_25", str(result))

    def test_overlong_formula_cache_does_not_change_formula_rejection(self):
        formula = header_row(1).replace(
            cell(21, 1, HEADER[20]),
            f'<c r="U1"><f>1+1</f><v>{"PRIVATE_CACHED" * 100}</v></c>',
        )
        result = scan(edited_sheet(formula))
        self.assertEqual(result["status"], "rejected_formula_candidate")
        self.assertNotIn("candidate", result)
        self.assertNotIn("PRIVATE_CACHED", str(result))

    def test_beyond_u_formula_cache_is_never_inspected_and_is_counted(self):
        beyond = '<c r="V1"><f>2+2</f><v>' + "PRIVATE_CACHE" * 100 + "</v></c>"
        row = header_row(1).replace("</row>", beyond + "</row>")
        with patch.object(
            diagnostic,
            "_bounded_text",
            side_effect=AssertionError("formula cache read"),
        ) as extractor:
            result = scan(edited_sheet(row))
        extractor.assert_not_called()
        self.assertEqual(result["status"], "candidate_found")
        self.assertEqual(result["candidate"]["beyond_21_count"], 1)
        self.assertNotIn("PRIVATE_CACHE", str(result))

    def test_overlong_nonformula_post_25_cell_rejects(self):
        rows = header_row(1) + "".join(
            f'<row r="{number}"/>' for number in range(2, 26)
        )
        rows += f'<row r="26">{cell(1, 26, "X" * 513)}</row>'
        with self.assertRaises(ValueError):
            scan(edited_sheet(rows))

    def test_selective_shared_strings_and_post_25_redaction(self):
        shared = (
            '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            + "".join(f"<si><t>{name}</t></si>" for name in HEADER)
            + "<si><t>PRIVATE_UNREQUESTED_ADDRESS</t></si></sst>"
        )
        rows = (
            '<row r="1">'
            + "".join(
                cell(index, 1, str(index - 1), kind="s") for index in range(1, 22)
            )
            + "</row>"
        )
        rows += "".join(f'<row r="{number}"/>' for number in range(2, 26))
        rows += f'<row r="26">{cell(9, 26, "PRIVATE_POST_25_ADDRESS")}{cell(20, 26, "987654321")}</row>'
        result = scan(synthetic_xlsx(rows=rows, shared=shared))
        self.assertEqual(result["status"], "candidate_found")
        self.assertEqual(result["physical_rows"], 26)
        self.assertEqual(result["candidate"]["cells"], list(HEADER))
        self.assertNotIn("PRIVATE_UNREQUESTED_ADDRESS", str(result))
        self.assertNotIn("PRIVATE_POST_25_ADDRESS", str(result))
        self.assertNotIn("987654321", str(result))

    def test_malformed_or_oversized_tail_rejects(self):
        rows = header_row(1) + "".join(
            f'<row r="{number}"/>' for number in range(2, 26)
        )
        malformed = sheet(rows) + b"<bad"
        body = repack(
            {**archive_parts(synthetic_xlsx()), "xl/worksheets/sheet1.xml": malformed}
        )
        with self.assertRaises(ValueError):
            scan(body)
        with patch.object(workbook, "MAX_WORKSHEET_XML", 64):
            with self.assertRaises(ValueError):
                scan(edited_sheet(rows))
        dtd = b'<!DOCTYPE x [<!ENTITY e "secret">]>' + sheet(rows)
        with self.assertRaises(Exception):
            scan(
                repack(
                    {**archive_parts(synthetic_xlsx()), "xl/worksheets/sheet1.xml": dtd}
                )
            )

    def test_bad_row_and_cell_coordinates_reject(self):
        for rows in (
            '<row r="1"/><row r="1"/>',
            '<row r="2"/><row r="1"/>',
            '<row r="1"><c r="A1"/><c r="A1"/></row>',
            '<row r="1"><c r="BM1"/></row>',
        ):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                scan(edited_sheet(rows))

    def test_empty_rows_trimmed_strings_and_fingerprint_frozen_to_winner(self):
        self.assertEqual(scan(edited_sheet(""))["status"], "no_unique_candidate")
        first = header_row(1, ("  " + HEADER[0] + "  ", *HEADER[1:]))
        late = f'<row r="26">{cell(1, 26, "PRIVATE_LATE_ADDRESS")}</row>'
        result = scan(edited_sheet(first + late))
        self.assertEqual(result["candidate"]["cells"], list(HEADER))
        self.assertEqual(
            result["candidate"]["fingerprint_sha256"], workbook.HEADER_SHA256
        )
        self.assertNotIn("PRIVATE_LATE_ADDRESS", str(result))

    def test_shared_index_and_xml_structure_fail_closed(self):
        shared = '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><si><t>ONE</t></si></sst>'
        for index in ("1", "-1", "1.0", "1e999999", "100000"):
            rows = f'<row r="1">{cell(1, 1, index, kind="s")}</row>'
            with self.subTest(index=index), self.assertRaises(ValueError):
                scan(synthetic_xlsx(rows=rows, shared=shared))
        with self.assertRaises(ValueError):
            scan(edited_sheet('<row r="1"/><sheetData/>'))
        with self.assertRaises(ValueError):
            scan(edited_sheet('<row r="1"><v>UNSUPPORTED</v></row>'))
        with self.assertRaises(ValueError):
            scan(edited_sheet(f'<row r="1">{cell(1, 1, "X" * 513)}</row>'))
        with self.assertRaises(TimeoutError):
            diagnostic._scan_with_pin(
                BytesIO(synthetic_xlsx()), TEST_PIN, timer=lambda: 181.0, start=0.0
            )

    def test_invalid_shared_string_tail_and_unselected_oversize(self):
        rows = f'<row r="1">{cell(1, 1, "0", kind="s")}</row>'
        valid = '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><si><t>ONE</t></si>'
        oversized = valid + f"<si><t>{'Z' * 513}</t></si></sst>"
        with self.assertRaises(ValueError):
            scan(synthetic_xlsx(rows=rows, shared=oversized))
        malformed = valid + "<si><t>PRIVATE_ADDRESS</t></si></sst><bad"
        with self.assertRaises(ValueError):
            scan(synthetic_xlsx(rows=rows, shared=malformed))


if __name__ == "__main__":
    unittest.main()
