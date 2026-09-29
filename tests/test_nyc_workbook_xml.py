"""Synthetic OOXML fixtures for the bounded NYC worksheet parser."""

from __future__ import annotations

from datetime import date
from io import BytesIO
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from zipfile import ZIP_DEFLATED, ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import nyc_workbook_xml as xml  # noqa: E402
from profile_nyc_rolling_snapshot import HEADER  # noqa: E402


def cell(column: int, row: int, value: str, *, kind: str = "inlineStr") -> str:
    label = ""
    current = column
    while current:
        current, digit = divmod(current - 1, 26)
        label = chr(65 + digit) + label
    if kind == "inlineStr":
        return f'<c r="{label}{row}" t="inlineStr"><is><t>{value}</t></is></c>'
    return f'<c r="{label}{row}" t="{kind}"><v>{value}</v></c>'


def synthetic_xlsx(
    *,
    rows: str | None = None,
    shared: str | None = None,
    sheet_count: int = 1,
    relationship_target: str = "worksheets/sheet1.xml",
    extra_relationship: str = "",
    extra_parts: dict[str, bytes] | None = None,
    date1904: str = "",
) -> bytes:
    if rows is None:
        header = "".join(cell(index, 1, name) for index, name in enumerate(HEADER, 1))
        rows = f'<row r="1">{header}</row><row r="2">{cell(21, 2, "09/15/2025")}</row>'
    workbook = (
        '<?xml version="1.0"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f"<workbookPr {date1904}/><sheets>"
        + "".join(
            f'<sheet name="Test{i}" sheetId="{i}" r:id="rId{i}"/>'
            for i in range(1, sheet_count + 1)
        )
        + "</sheets></workbook>"
    )
    relationships = (
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        f'<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="{relationship_target}"/>'
        + (
            '<Relationship Id="rIdShared" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings" Target="sharedStrings.xml"/>'
            if shared is not None
            else ""
        )
        + extra_relationship
        + "</Relationships>"
    )
    parts = {
        "[Content_Types].xml": b'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>',
        "_rels/.rels": b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rIdRoot" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>',
        "xl/workbook.xml": workbook.encode(),
        "xl/_rels/workbook.xml.rels": relationships.encode(),
        "xl/worksheets/sheet1.xml": (
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
            + rows
            + "</sheetData></worksheet>"
        ).encode(),
        **({"xl/sharedStrings.xml": shared.encode()} if shared is not None else {}),
        **(extra_parts or {}),
    }
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        for name, body in parts.items():
            archive.writestr(name, body)
    return buffer.getvalue()


def inspect(data: bytes, *, timer=lambda: 0.0) -> dict:
    return xml.inspect_workbook(BytesIO(data), timer=timer, start=0.0)


class WorkbookXmlTest(unittest.TestCase):
    def test_valid_text_dates_and_header(self):
        result = inspect(synthetic_xlsx())
        self.assertTrue(result["qualified"])
        self.assertEqual(result["data_rows"], 1)
        self.assertEqual(result["date_min"], "2025-09-15")
        self.assertEqual(result["date_max"], "2025-09-15")
        self.assertEqual(result["header_sha256"], xml.HEADER_SHA256)
        self.assertEqual(result["date_system"], "1900_default")
        header = "".join(cell(index, 1, name) for index, name in enumerate(HEADER, 1))
        iso = inspect(
            synthetic_xlsx(
                rows=f'<row r="1">{header}</row><row r="2">{cell(21, 2, "2026-08-31")}</row>'
            )
        )
        self.assertTrue(iso["qualified"])
        self.assertEqual(iso["date_max"], "2026-08-31")

    def test_shared_strings_preamble_blank_rows_and_serial_dates(self):
        shared = (
            '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            + "".join(f"<si><t>{name}</t></si>" for name in HEADER)
            + "</sst>"
        )
        header = "".join(cell(i, 3, str(i - 1), kind="s") for i in range(1, 22))
        rows = f'<row r="1"><c r="A1" t="inlineStr"><is><t>preamble</t></is></c></row><row r="2"/><row r="3">{header}</row><row r="4">{cell(21, 4, "45915", kind="n")}</row><row r="5"/>'
        result = inspect(synthetic_xlsx(rows=rows, shared=shared))
        self.assertEqual(result["preamble_rows"], 2)
        self.assertEqual(result["physical_rows"], 5)
        self.assertEqual(result["data_rows"], 1)
        self.assertTrue(result["qualified"])

    def test_header_mismatch_and_repeat_disqualify_without_echoing_values(self):
        bad = "".join(
            cell(i, 1, "PRIVATE_ADDRESS" if i == 9 else name)
            for i, name in enumerate(HEADER, 1)
        )
        result = inspect(
            synthetic_xlsx(
                rows=f'<row r="1">{bad}</row><row r="2">{cell(21, 2, "2025-09-01")}</row>'
            )
        )
        self.assertFalse(result["qualified"])
        self.assertEqual(result["header_status"], "mismatch")
        self.assertNotIn("PRIVATE_ADDRESS", str(result))
        header = "".join(cell(i, 1, name) for i, name in enumerate(HEADER, 1))
        repeated = "".join(cell(i, 3, name) for i, name in enumerate(HEADER, 1))
        result = inspect(
            synthetic_xlsx(
                rows=f'<row r="1">{header}</row><row r="2">{cell(21, 2, "2025-09-01")}</row><row r="3">{repeated}</row>'
            )
        )
        self.assertFalse(result["qualified"])
        self.assertEqual(result["repeated_header_rows"], 1)

    def test_dates_and_formula_traps(self):
        header = "".join(cell(i, 1, name) for i, name in enumerate(HEADER, 1))
        cases = ["09/31/2025", "10/11/25", "60", "60.5", "", "2026-09-01"]
        for value in cases:
            with self.subTest(value=value):
                rows = f'<row r="1">{header}</row><row r="2">{cell(21, 2, value, kind="n" if value and value[0].isdigit() and "/" not in value and "-" not in value else "inlineStr")}</row>'
                result = inspect(synthetic_xlsx(rows=rows))
                self.assertFalse(result["qualified"])
        rows = f'<row r="1">{header}</row><row r="2"><c r="U2"><f>PRIVATE_FORMULA</f><v>44440</v></c></row>'
        result = inspect(synthetic_xlsx(rows=rows))
        self.assertEqual(result["formula_cells"], 1)
        self.assertFalse(result["qualified"])
        self.assertNotIn("PRIVATE_FORMULA", str(result))

    def test_reject_external_traversal_and_active_parts(self):
        malicious = [
            "https://evil.example/a",
            "../../escape.xml",
            r"..\escape.xml",
            "%2e%2e/x",
            "//server/share",
        ]
        for target in malicious:
            with self.subTest(target=target), self.assertRaises(ValueError):
                inspect(synthetic_xlsx(relationship_target=target))
        with self.assertRaises(ValueError):
            inspect(
                synthetic_xlsx(
                    extra_relationship='<Relationship Id="rIdBad" Type="test" Target="http://example.invalid" TargetMode="External"/>'
                )
            )
        with self.assertRaises(ValueError):
            inspect(
                synthetic_xlsx(
                    extra_relationship='<Relationship Id="rIdBad" Type="test" Target="worksheets/sheet1.xml" TargetMode="external"/>'
                )
            )
        uppercase_rels = b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="bad" Type="test" Target="https://example.invalid" TargetMode="External"/></Relationships>'
        with self.assertRaises(ValueError):
            inspect(
                synthetic_xlsx(extra_parts={"xl/_rels/other.xml.RELS": uppercase_rels})
            )
        with self.assertRaises(ValueError):
            inspect(synthetic_xlsx(extra_parts={"xl/WORKBOOK.xml": b"<duplicate/>"}))
        with self.assertRaises(ValueError):
            inspect(synthetic_xlsx(extra_parts={"xl/vbaProject.bin": b"not-a-macro"}))

    def test_reject_extra_sheet_dtd_and_duplicate_row_or_cell(self):
        with self.assertRaises(ValueError):
            inspect(synthetic_xlsx(sheet_count=2))
        with self.assertRaises(ValueError):
            inspect(
                synthetic_xlsx(extra_parts={"xl/worksheets/sheet2.xml": b"<unused/>"})
            )
        extra_type = b'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/other/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>'
        with self.assertRaises(ValueError):
            inspect(
                synthetic_xlsx(
                    extra_parts={
                        "[Content_Types].xml": extra_type,
                        "xl/other/sheet2.xml": b"<unused/>",
                    }
                )
            )
        duplicated_data = b'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData/><sheetData/></worksheet>'
        with self.assertRaises(ValueError):
            inspect(
                synthetic_xlsx(
                    extra_parts={"xl/worksheets/sheet1.xml": duplicated_data}
                )
            )
        with self.assertRaises(ValueError):
            inspect(
                synthetic_xlsx(
                    extra_relationship='<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/>',
                    extra_parts={
                        "xl/worksheets/sheet2.xml": b'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"/>'
                    },
                )
            )
        with self.assertRaises(ValueError):
            inspect(
                synthetic_xlsx(
                    extra_parts={
                        "xl/workbook.xml": b'<!DOCTYPE x [<!ENTITY e "evil">]><workbook>&e;</workbook>'
                    }
                )
            )
        for rows in (
            '<row r="1"/><row r="1"/>',
            '<row r="1"><c r="A1"/><c r="A1"/></row>',
        ):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                inspect(synthetic_xlsx(rows=rows))

    def test_1904_serial_and_extra_or_formula_cells(self):
        header = "".join(cell(i, 1, name) for i, name in enumerate(HEADER, 1))
        serial = (date(2025, 9, 15) - date(1904, 1, 1)).days
        rows = f'<row r="1">{header}</row><row r="2">{cell(21, 2, str(serial), kind="n")}</row>'
        outcome = inspect(synthetic_xlsx(rows=rows, date1904='date1904="1"'))
        self.assertEqual(outcome["date_system"], "1904_explicit")
        self.assertTrue(outcome["qualified"])
        extra = f'<row r="1">{header}</row><row r="2">{cell(21, 2, str(serial), kind="n")}{cell(22, 2, "PRIVATE_NOT_A_SALE")}</row>'
        outcome = inspect(synthetic_xlsx(rows=extra))
        self.assertFalse(outcome["qualified"])
        self.assertNotIn("PRIVATE_NOT_A_SALE", str(outcome))
        formula = f'<row r="1">{header}</row><row r="2">{cell(21, 2, str(serial), kind="n")}<c r="V2"><f>1+2</f><v>3</v></c></row>'
        self.assertFalse(inspect(synthetic_xlsx(rows=formula))["qualified"])

    def test_invalid_header_candidate_and_root_parts(self):
        bad = "".join(
            cell(i, 1, "WRONG" if i == 9 else name) for i, name in enumerate(HEADER, 1)
        )
        good = "".join(cell(i, 2, name) for i, name in enumerate(HEADER, 1))
        result = inspect(
            synthetic_xlsx(
                rows=f'<row r="1">{bad}</row><row r="2">{good}</row><row r="3">{cell(21, 3, "2025-09-15")}</row>'
            )
        )
        self.assertEqual(result["invalid_header_candidate_rows"], 1)
        self.assertFalse(result["qualified"])
        with self.assertRaises(ValueError):
            inspect(
                synthetic_xlsx(
                    extra_parts={
                        "xl/worksheets/sheet1.xml": b'<root><row r="1"/></root>'
                    }
                )
            )
        outside = b'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><row r="1"/><sheetData/></worksheet>'
        with self.assertRaises(ValueError):
            inspect(synthetic_xlsx(extra_parts={"xl/worksheets/sheet1.xml": outside}))
        with self.assertRaises(ValueError):
            inspect(synthetic_xlsx(shared="<root><si><t>bad</t></si></root>"))
        active_type = b'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Override PartName="/xl/vbaProject.bin" ContentType="application/vnd.ms-office.vbaProject"/></Types>'
        with self.assertRaises(ValueError):
            inspect(synthetic_xlsx(extra_parts={"[Content_Types].xml": active_type}))

    def test_metadata_over_64k_is_fully_parsed_and_tail_checked(self):
        opening = b'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        valid = opening + b" " * 70000 + b"</Types>"
        self.assertTrue(
            inspect(synthetic_xlsx(extra_parts={"[Content_Types].xml": valid}))[
                "qualified"
            ]
        )
        invalid = opening + b"</Types>" + b" " * 70000 + b"<unexpected/>"
        with self.assertRaises(ValueError):
            inspect(synthetic_xlsx(extra_parts={"[Content_Types].xml": invalid}))
        forbidden_suffix = (
            opening
            + b"</Types>"
            + b" " * 70000
            + b'<!DOCTYPE x [<!ENTITY private "do not expand">]>'
        )
        with self.assertRaises(ValueError):
            inspect(
                synthetic_xlsx(extra_parts={"[Content_Types].xml": forbidden_suffix})
            )

    def test_huge_scientific_date_rejected_before_integer_conversion(self):
        class GuardedDecimal:
            def is_finite(self):
                return True

            def to_integral_value(self):
                return self

            def __eq__(self, other):
                return True

            def __gt__(self, other):
                return True

            def __int__(self):
                raise AssertionError("huge Decimal must not be materialized as int")

        with patch.object(xml, "Decimal", return_value=GuardedDecimal()):
            self.assertIsNone(xml._date("1e999999999", "1900_default"))
        self.assertIsNone(xml._date("1e999999999", "1900_default"))

    def test_patched_small_limits_apply_to_physical_rows_and_xml(self):
        with patch.object(xml, "MAX_ROWS", 1):
            with self.assertRaises(ValueError):
                inspect(synthetic_xlsx())
        with patch.object(xml, "MAX_WORKSHEET_XML", 10):
            with self.assertRaises(ValueError):
                inspect(synthetic_xlsx())
        with patch.object(xml, "MAX_SHARED_STRINGS", 0):
            with self.assertRaises(ValueError):
                inspect(
                    synthetic_xlsx(
                        shared='<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><si><t>x</t></si></sst>'
                    )
                )
        with patch.object(xml, "MAX_SHARED_XML", 10):
            with self.assertRaises(ValueError):
                inspect(
                    synthetic_xlsx(
                        shared='<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"/>'
                    )
                )

    def test_safe_explicit_zip_directory_is_not_a_data_sheet(self):
        outcome = inspect(synthetic_xlsx(extra_parts={"xl/": b""}))
        self.assertTrue(outcome["qualified"])

    def test_ten_thousand_physical_rows_stream_under_registered_cap(self):
        header = "".join(cell(i, 1, name) for i, name in enumerate(HEADER, 1))
        rows = f'<row r="1">{header}</row>' + "".join(
            f'<row r="{index}">{cell(21, index, "2025-09-15")}</row>'
            for index in range(2, 10002)
        )
        result = inspect(synthetic_xlsx(rows=rows))
        self.assertTrue(result["qualified"])
        self.assertEqual(result["physical_rows"], 10001)
        self.assertEqual(result["data_rows"], 10000)

    def test_limits_and_bad_zip(self):
        with self.assertRaises(ValueError):
            inspect(b"not a zip")
        with self.assertRaises(ValueError):
            inspect(
                synthetic_xlsx(
                    rows='<row r="1">'
                    + "".join(cell(i, 1, "x") for i in range(1, 66))
                    + "</row>"
                )
            )
        with self.assertRaises(ValueError):
            inspect(
                synthetic_xlsx(
                    shared='<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><si><t>'
                    + "x" * 513
                    + "</t></si></sst>"
                )
            )
        with self.assertRaises(TimeoutError):
            inspect(synthetic_xlsx(), timer=lambda: 181.0)


if __name__ == "__main__":
    unittest.main()
