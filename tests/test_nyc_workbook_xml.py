"""Synthetic OOXML fixtures for the bounded NYC worksheet parser."""

from __future__ import annotations

from datetime import date
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from zipfile import ZIP_DEFLATED, ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import nyc_workbook_xml as xml  # noqa: E402
from profile_nyc_rolling_snapshot import HEADER  # noqa: E402


TEST_PRINTER = b"opaque synthetic printer settings only"
TEST_PIN = (len(TEST_PRINTER), sha256(TEST_PRINTER).hexdigest())
PRINTER_PART = "xl/printerSettings/printerSettings1.bin"
PRINTER_MIME = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.printerSettings"
)
PRINTER_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/printerSettings"


def archive_parts(body: bytes) -> dict[str, bytes]:
    with ZipFile(BytesIO(body)) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def repack(parts: dict[str, bytes]) -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        for name, body in parts.items():
            archive.writestr(name, body)
    return buffer.getvalue()


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
    omit_parts: tuple[str, ...] = (),
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
        + '<Relationship Id="rIdShared" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings" Target="sharedStrings.xml"/>'
        + extra_relationship
        + "</Relationships>"
    )
    parts = {
        "[Content_Types].xml": (
            f'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="bin" ContentType="{PRINTER_MIME}"/></Types>'
        ).encode(),
        "_rels/.rels": b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rIdRoot" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/><Relationship Id="rIdCore" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/><Relationship Id="rIdApp" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/><Relationship Id="rIdCustom" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/custom-properties" Target="docProps/custom.xml"/></Relationships>',
        "docProps/app.xml": b"<Properties/>",
        "docProps/core.xml": b"<Properties/>",
        "docProps/custom.xml": b"<Properties/>",
        "xl/workbook.xml": workbook.encode(),
        "xl/_rels/workbook.xml.rels": relationships.encode(),
        "xl/sharedStrings.xml": (
            shared
            or '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"/>'
        ).encode(),
        "xl/styles.xml": b"<styleSheet/>",
        "xl/theme/theme1.xml": b"<theme/>",
        PRINTER_PART: TEST_PRINTER,
        "xl/worksheets/_rels/sheet1.xml.rels": (
            f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rIdPrinter" Type="{PRINTER_REL}" Target="../printerSettings/printerSettings1.bin"/></Relationships>'
        ).encode(),
        "xl/worksheets/sheet1.xml": (
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
            + rows
            + "</sheetData></worksheet>"
        ).encode(),
        **(extra_parts or {}),
    }
    return repack(
        {name: body for name, body in parts.items() if name not in omit_parts}
    )


def inspect(data: bytes, *, timer=lambda: 0.0) -> dict:
    return xml._inspect_workbook_with_pin(
        BytesIO(data), TEST_PIN, timer=timer, start=0.0
    )


def mutated(
    *,
    replace: dict[str, bytes] | None = None,
    remove: tuple[str, ...] = (),
    add: dict[str, bytes] | None = None,
) -> bytes:
    parts = archive_parts(synthetic_xlsx())
    return repack(
        {
            **{name: body for name, body in parts.items() if name not in remove},
            **(replace or {}),
            **(add or {}),
        }
    )


class V2PrinterPolicyTest(unittest.TestCase):
    def test_exact_inventory_and_optional_calc_chain(self):
        self.assertTrue(inspect(synthetic_xlsx())["qualified"])
        self.assertTrue(
            inspect(mutated(add={"xl/calcChain.xml": b"<calcChain/>"}))["qualified"]
        )
        for name in ("xl/opaque.dat", "xl/second.bin", "xl/"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                inspect(mutated(add={name: b"opaque"}))

    def test_pinned_binary_size_digest_path_and_case(self):
        for replacement in (b"X" * len(TEST_PRINTER), TEST_PRINTER + b"x"):
            with (
                self.subTest(replacement=replacement[:2]),
                self.assertRaises(ValueError),
            ):
                inspect(mutated(replace={PRINTER_PART: replacement}))
        for wrong in (
            "xl/printerSettings/other.bin",
            "xl/printerSettings/PrinterSettings1.bin",
        ):
            with self.subTest(path=wrong), self.assertRaises(ValueError):
                inspect(mutated(remove=(PRINTER_PART,), add={wrong: TEST_PRINTER}))
        with self.assertRaises(ValueError):
            inspect(mutated(remove=(PRINTER_PART,)))

    def test_exact_default_mime_and_no_override(self):
        original = archive_parts(synthetic_xlsx())["[Content_Types].xml"]
        cases = (
            original.replace(
                b'<Default Extension="bin" ContentType="'
                + PRINTER_MIME.encode()
                + b'"/>',
                b"",
            ),
            original.replace(
                b"</Types>",
                b'<Default Extension="bin" ContentType="'
                + PRINTER_MIME.encode()
                + b'"/></Types>',
            ),
            original.replace(PRINTER_MIME.encode(), b"application/octet-stream"),
            original.replace(
                b"</Types>",
                b'<Override PartName="/'
                + PRINTER_PART.encode()
                + b'" ContentType="'
                + PRINTER_MIME.encode()
                + b'"/></Types>',
            ),
            original.replace(b'Extension="bin"', b'Extension="BIN"'),
            original.replace(
                b"</Types>",
                b'<Override PartName="/xl/other.bin" ContentType="application/octet-stream"/></Types>',
            ),
            original.replace(
                b"</Types>",
                b'<Override PartName="/xl/printerSettings/printerSettings1%2ebin" ContentType="application/octet-stream"/></Types>',
            ),
            original.replace(
                b"</Types>",
                b'<Default Extension="b%69n" ContentType="application/octet-stream"/></Types>',
            ),
            original.replace(
                b"</Types>",
                b'<Override PartName="/xl/other/../styles.xml" ContentType="application/xml"/></Types>',
            ),
            original.replace(
                b"</Types>",
                b'<Override PartName="/xl/printerSettings/printerSettings1.bin?alias" ContentType="application/octet-stream"/></Types>',
            ),
            original.replace(
                b"</Types>",
                b'<Default Extension="dat" ContentType="'
                + PRINTER_MIME.encode()
                + b'"/></Types>',
            ),
        )
        for body in cases:
            with self.subTest(body=body[-75:]), self.assertRaises(ValueError):
                inspect(mutated(replace={"[Content_Types].xml": body}))

    def test_single_literal_printer_relationship(self):
        name = "xl/worksheets/_rels/sheet1.xml.rels"
        original = archive_parts(synthetic_xlsx())[name]
        entry = f'<Relationship Id="rIdPrinter" Type="{PRINTER_REL}" Target="../printerSettings/printerSettings1.bin"/>'.encode()
        changes = (
            original.replace(entry, b""),
            original.replace(
                b"</Relationships>",
                entry.replace(b"rIdPrinter", b"rIdOther") + b"</Relationships>",
            ),
            original.replace(
                b"/>" + b"</Relationships>", b' TargetMode="External"/></Relationships>'
            ),
            original.replace(
                b"../printerSettings/printerSettings1.bin", b"../../outside.bin"
            ),
            original.replace(
                b"../printerSettings/printerSettings1.bin",
                b"../printerSettings/./printerSettings1.bin",
            ),
            original.replace(PRINTER_REL.encode(), b"http://example.invalid/wrong"),
            original.replace(
                b"</Relationships>",
                f'<Relationship Id="rIdOtherPrinter" Type="{PRINTER_REL}" Target="../styles.xml"/></Relationships>'.encode(),
            ),
        )
        for body in changes:
            with self.subTest(body=body[-90:]), self.assertRaises(ValueError):
                inspect(mutated(replace={name: body}))
        workbook_rels = archive_parts(synthetic_xlsx())["xl/_rels/workbook.xml.rels"]
        extra_incoming = workbook_rels.replace(
            b"</Relationships>",
            f'<Relationship Id="rIdExtraPrinter" Type="{PRINTER_REL}" Target="printerSettings/printerSettings1.bin"/></Relationships>'.encode(),
        )
        with self.assertRaises(ValueError):
            inspect(mutated(replace={"xl/_rels/workbook.xml.rels": extra_incoming}))
        with self.assertRaises(ValueError):
            inspect(
                mutated(
                    add={
                        "xl/printerSettings/_rels/printerSettings1.bin.rels": b"<Relationships/>"
                    }
                )
            )
        wrong_source = mutated(
            replace={
                name: original.replace(entry, b""),
                "xl/_rels/workbook.xml.rels": extra_incoming,
            }
        )
        with self.assertRaises(ValueError):
            inspect(wrong_source)

    def test_binary_zip_crc_is_verified_to_eof(self):
        parts = archive_parts(synthetic_xlsx())
        buffer = BytesIO()
        with ZipFile(buffer, "w") as archive:
            for name, body in parts.items():
                archive.writestr(name, body)
        changed = buffer.getvalue().replace(TEST_PRINTER, b"X" + TEST_PRINTER[1:], 1)
        with self.assertRaises(ValueError):
            inspect(changed)

    def test_four_full_root_relationships_literal_targets(self):
        name = "_rels/.rels"
        original = archive_parts(synthetic_xlsx())[name]
        for body in (
            original.replace(
                b'<Relationship Id="rIdCore" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>',
                b"",
            ),
            original.replace(
                b"</Relationships>",
                b'<Relationship Id="extra" Type="http://example.invalid/extra" Target="docProps/core.xml"/></Relationships>',
            ),
            original.replace(
                b'Target="docProps/core.xml"', b'Target="docProps/./core.xml"'
            ),
            original.replace(
                b'Target="xl/workbook.xml"', b'Target="xl/./workbook.xml"'
            ),
            original.replace(b"metadata/core-properties", b"metadata/other-properties"),
            original.replace(b'Id="rIdCore"', b'Id="rIdRoot"'),
            original.replace(
                b'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/custom-properties" Target="docProps/custom.xml"',
                b'Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/custom.xml"',
            ),
        ):
            with self.subTest(body=body[-80:]), self.assertRaises(ValueError):
                inspect(mutated(replace={name: body}))

    def test_test_policy_is_internal_only(self):
        self.assertEqual(xml.PROTOCOL, "nyc-borough-worksheet-inspection-v2")
        self.assertEqual(
            xml.PRODUCTION_PRINTER_PIN,
            (5024, "7d3c762f37f75bbe2ff459ab52b55b2e7be8a8603e2ad227248f6d4519a0f96b"),
        )


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
        declaration = (
            f'<Default Extension="bin" ContentType="{PRINTER_MIME}"/>'.encode()
        )
        valid = opening + declaration + b" " * 70000 + b"</Types>"
        self.assertTrue(
            inspect(synthetic_xlsx(extra_parts={"[Content_Types].xml": valid}))[
                "qualified"
            ]
        )
        invalid = opening + declaration + b"</Types>" + b" " * 70000 + b"<unexpected/>"
        with self.assertRaises(ValueError):
            inspect(synthetic_xlsx(extra_parts={"[Content_Types].xml": invalid}))
        forbidden_suffix = (
            opening
            + declaration
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

    def test_explicit_zip_directory_is_rejected_by_frozen_inventory(self):
        with self.assertRaises(ValueError):
            inspect(synthetic_xlsx(extra_parts={"xl/": b""}))

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
