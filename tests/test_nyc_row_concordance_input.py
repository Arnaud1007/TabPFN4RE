"""Synthetic input-scanner tests for ADR 0033; never open captured NYC data."""

from __future__ import annotations

import sys
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import nyc_row_concordance_input as scanner  # noqa: E402
import nyc_workbook_xml_v3 as v3  # noqa: E402
from profile_nyc_rolling_snapshot import HEADER  # noqa: E402

from tests.test_nyc_workbook_xml import TEST_PIN, archive_parts, repack  # noqa: E402
from tests.test_nyc_workbook_xml_v3 import (  # noqa: E402
    RAW_HEADER,
    row,
    synthetic_xlsx,
)


def workbook(*, borough: str = "2", sale_row: int = 6, extra: str = "") -> bytes:
    values = tuple(
        (
            borough
            if index == 1
            else "0012"
            if index == 5
            else " 003 "
            if index == 6
            else "  "
            if index == 10
            else "PRIVATE ADDRESS"
            if index == 9
            else "987654321"
            if index == 20
            else "09/15/2025"
            if index == 21
            else f"v{index}"
        )
        for index in range(1, 22)
    )
    preamble = "".join(row(number, {}) for number in range(1, 5))
    header = row(5, dict(enumerate(RAW_HEADER, 1)))
    sale = row(sale_row, dict(enumerate(values, 1)))
    return synthetic_xlsx(rows=preamble + header + sale + extra)


def scan_workbook(body: bytes, expected: str = "2", on_row=None) -> dict:
    handle = BytesIO(body)
    callback = on_row or (lambda number, values: None)
    with (
        patch.object(scanner.base, "PRODUCTION_PRINTER_PIN", TEST_PIN),
        patch.object(
            scanner.v3,
            "inspect_workbook",
            side_effect=lambda source, **kwargs: v3._inspect_with_pin(
                source, TEST_PIN, **kwargs
            ),
        ),
    ):
        return scanner.scan_qualified_workbook(
            handle, expected, callback, timer=lambda: 0.0, start=0.0
        )


def csv_body(*records: tuple[str, ...], header: tuple[str, ...] = HEADER) -> bytes:
    import csv
    from io import StringIO

    output = StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(header)
    writer.writerows(records)
    return output.getvalue().encode("utf-8")


class WorkbookInputScannerTest(unittest.TestCase):
    def test_exact_raw_values_alias_and_source_row_are_preserved(self):
        found = []
        result = scan_workbook(
            workbook(sale_row=7), on_row=lambda n, v: found.append((n, v))
        )
        self.assertEqual(result["rows"], 1)
        self.assertEqual(result["physical_rows"], 6)
        self.assertEqual(found[0][0], 7)
        self.assertEqual(len(found[0][1]), 21)
        self.assertEqual(found[0][1][4:6], ("0012", " 003 "))
        self.assertEqual(found[0][1][9], "  ")
        self.assertEqual(found[0][1][19:21], ("987654321", "09/15/2025"))

    def test_wrong_borough_and_wrong_expected_code_fail(self):
        found = []
        with self.assertRaises(ValueError):
            scan_workbook(workbook(borough="3"), on_row=lambda n, v: found.append(n))
        self.assertEqual(found, [])
        with self.assertRaises(ValueError):
            scan_workbook(workbook(), expected="1")
        with self.assertRaises(ValueError):
            scan_workbook(workbook(), expected=[])

    def test_v3_structural_rejection_precedes_row_callback(self):
        found = []
        preamble = "".join(row(number, {}) for number in range(1, 5))
        bad = synthetic_xlsx(
            rows=preamble
            + row(5, dict(enumerate(HEADER, 1)))
            + row(6, {1: "2", 21: "09/15/2025"})
        )
        with self.assertRaises(ValueError):
            scan_workbook(bad, on_row=lambda n, v: found.append(n))
        self.assertEqual(found, [])
        parts = archive_parts(workbook())
        sheet = "xl/worksheets/sheet1.xml"
        for damaged in (
            parts[sheet][:-12],
            parts[sheet].replace(
                b"</sheetData>", b'<row r="7"><c r="V7"><f>1</f></c></row></sheetData>'
            ),
        ):
            with self.subTest(damaged=damaged[-20:]), self.assertRaises(ValueError):
                scan_workbook(
                    repack({**parts, sheet: damaged}),
                    on_row=lambda n, v: found.append(n),
                )
        self.assertEqual(found, [])

    def test_blank_styled_extra_cell_keeps_v3_data_row_semantics(self):
        preamble = "".join(row(number, {}) for number in range(1, 5))
        header = row(5, dict(enumerate(RAW_HEADER, 1)))
        sale = row(6, {1: "2", 21: "09/15/2025", 22: ""})
        found = []
        result = scan_workbook(
            synthetic_xlsx(rows=preamble + header + sale),
            on_row=lambda number, values: found.append((number, values)),
        )
        self.assertEqual(result["rows"], 1)
        self.assertEqual(found[0][0], 6)
        self.assertEqual(len(found[0][1]), 21)

    def test_workbook_rejects_cell_character_and_time_limits(self):
        with patch.object(scanner, "MAX_CELL_CHARACTERS", 10):
            with self.assertRaises(ValueError):
                scan_workbook(workbook())
        with self.assertRaises(TimeoutError):
            with (
                patch.object(scanner.base, "PRODUCTION_PRINTER_PIN", TEST_PIN),
                patch.object(
                    scanner.v3,
                    "inspect_workbook",
                    side_effect=lambda source, **kwargs: v3._inspect_with_pin(
                        source, TEST_PIN, **kwargs
                    ),
                ),
            ):
                scanner.scan_qualified_workbook(
                    BytesIO(workbook()),
                    "2",
                    lambda n, v: None,
                    timer=lambda: 181.0,
                    start=0.0,
                )


class CsvInputScannerTest(unittest.TestCase):
    def setUp(self):
        self.record = tuple(f"v{i}" for i in range(1, 22))

    def test_strict_header_fields_ordinals_and_handle_stays_open(self):
        body = b"\xef\xbb\xbf" + csv_body(self.record, self.record)
        handle = BytesIO(body)
        found = []
        result = scanner.scan_pinned_csv(
            handle,
            2,
            lambda n, v: found.append((n, v)),
            timer=lambda: 0.0,
            start=0.0,
        )
        self.assertEqual(result["rows"], 2)
        self.assertEqual(result["bytes_read"], len(body))
        self.assertEqual([n for n, _ in found], [1, 2])
        self.assertEqual(found[0][1], self.record)
        self.assertFalse(handle.closed)

    def test_csv_keeps_leading_zeros_outer_spaces_and_embedded_newline(self):
        record = (
            *self.record[:4],
            "0012",
            " 003 ",
            *self.record[6:9],
            "",
            *self.record[10:19],
            "12,000",
            "09/15/2025\n",
        )
        seen = []
        result = scanner.scan_pinned_csv(
            BytesIO(csv_body(record)),
            1,
            lambda n, v: seen.append(v),
            timer=lambda: 0.0,
            start=0.0,
        )
        self.assertEqual(result["rows"], 1)
        self.assertEqual(seen, [record])

    def test_wrong_header_field_count_and_row_count_fail(self):
        for body in (
            csv_body(self.record, header=RAW_HEADER),
            csv_body(self.record[:-1]),
            csv_body((*self.record, "extra")),
        ):
            with self.subTest(body=body[:30]), self.assertRaises(ValueError):
                scanner.scan_pinned_csv(
                    BytesIO(body),
                    1,
                    lambda n, v: None,
                    timer=lambda: 0.0,
                    start=0.0,
                )
        with self.assertRaises(ValueError):
            scanner.scan_pinned_csv(
                BytesIO(csv_body(self.record)),
                2,
                lambda n, v: None,
                timer=lambda: 0.0,
                start=0.0,
            )

    def test_invalid_utf8_bad_csv_and_bad_expected_count_fail(self):
        for body in (csv_body() + b"\xff", csv_body() + b'"unterminated'):
            with self.subTest(body=body[-15:]), self.assertRaises(ValueError):
                scanner.scan_pinned_csv(
                    BytesIO(body),
                    1,
                    lambda n, v: None,
                    timer=lambda: 0.0,
                    start=0.0,
                )
        for expected in (-1, 150001, True):
            with self.subTest(expected=expected), self.assertRaises(ValueError):
                scanner.scan_pinned_csv(
                    BytesIO(csv_body()),
                    expected,
                    lambda n, v: None,
                    timer=lambda: 0.0,
                    start=0.0,
                )

    def test_byte_row_field_character_and_time_limits(self):
        body = csv_body(self.record)
        with patch.object(scanner, "MAX_CSV_BYTES", len(body) - 1):
            with self.assertRaises(ValueError):
                scanner.scan_pinned_csv(
                    BytesIO(body),
                    1,
                    lambda n, v: None,
                    timer=lambda: 0.0,
                    start=0.0,
                )
        with patch.object(scanner, "MAX_ROWS", 0):
            with self.assertRaises(ValueError):
                scanner.scan_pinned_csv(
                    BytesIO(body),
                    0,
                    lambda n, v: None,
                    timer=lambda: 0.0,
                    start=0.0,
                )
        too_long = ("x" * 513, *self.record[1:])
        with self.assertRaises(ValueError):
            scanner.scan_pinned_csv(
                BytesIO(csv_body(too_long)),
                1,
                lambda n, v: None,
                timer=lambda: 0.0,
                start=0.0,
            )
        with patch.object(scanner, "MAX_CELL_CHARACTERS", 10):
            with self.assertRaises(ValueError):
                scanner.scan_pinned_csv(
                    BytesIO(body),
                    1,
                    lambda n, v: None,
                    timer=lambda: 0.0,
                    start=0.0,
                )
        with self.assertRaises(TimeoutError):
            scanner.scan_pinned_csv(
                BytesIO(body),
                1,
                lambda n, v: None,
                timer=lambda: 181.0,
                start=0.0,
            )


if __name__ == "__main__":
    unittest.main()
