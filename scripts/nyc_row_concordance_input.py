"""Bounded private input streams for the frozen NYC row-concordance diagnostic.

The callbacks receive raw source strings. They are valid for comparison only
after a scanner returns successfully; a later parse failure invalidates every
earlier callback from that scan. This module never interprets sale labels.
"""

from __future__ import annotations

import csv
import io
import time
from collections.abc import Callable
from typing import BinaryIO
from zipfile import BadZipFile, LargeZipFile, ZipFile

import nyc_workbook_xml as base
import nyc_workbook_xml_v3 as v3
from defusedxml import ElementTree as DET
from profile_nyc_rolling_snapshot import HEADER, MAX_CSV_BYTES

MAX_ROWS = base.MAX_ROWS
MAX_CELL_CHARACTERS = 32_000_000
ALLOWED_WORKBOOK_BOROUGHS = frozenset({"2", "3", "4", "5"})
RowCallback = Callable[[int, tuple[str, ...]], None]


class _CappedCsvRaw(io.RawIOBase):
    """Limit byte reads while leaving the caller-owned binary handle open."""

    def __init__(self, handle: BinaryIO, timer: base.Timer, start: float) -> None:
        self.handle = handle
        self.timer = timer
        self.start = start
        self.count = 0

    def readable(self) -> bool:
        return True

    def readinto(self, buffer: bytearray | memoryview) -> int:
        base._check_time(self.timer, self.start)
        size = min(len(buffer), MAX_CSV_BYTES - self.count + 1)
        chunk = self.handle.read(size)
        self.count += len(chunk)
        if self.count > MAX_CSV_BYTES:
            raise ValueError("NYC CSV exceeds byte cap")
        buffer[: len(chunk)] = chunk
        base._check_time(self.timer, self.start)
        return len(chunk)


def scan_pinned_csv(
    handle: BinaryIO,
    expected_rows: int,
    on_row: RowCallback,
    *,
    timer: base.Timer = time.monotonic,
    start: float | None = None,
) -> dict:
    """Read the exact API CSV schema to EOF and emit 1-based data ordinals."""
    if type(expected_rows) is not int or not 0 <= expected_rows <= MAX_ROWS:
        raise ValueError("NYC CSV expected row count is invalid")
    origin = timer() if start is None else start
    base._check_time(timer, origin)
    handle.seek(0)
    source = _CappedCsvRaw(handle, timer, origin)
    rows = 0
    characters = 0
    try:
        with io.TextIOWrapper(
            io.BufferedReader(source), encoding="utf-8-sig", newline=""
        ) as text:
            reader = csv.reader(text, strict=True)
            if tuple(next(reader, ())) != HEADER:
                raise ValueError("NYC CSV header differs from pinned schema")
            for record in reader:
                base._check_time(timer, origin)
                if len(record) != len(HEADER):
                    raise ValueError("NYC CSV row field count differs")
                if rows >= MAX_ROWS:
                    raise ValueError("NYC CSV row cap exceeded")
                if any(len(value) > base.MAX_STRING for value in record):
                    raise ValueError("NYC CSV field exceeds character cap")
                characters += sum(map(len, record))
                if characters > MAX_CELL_CHARACTERS:
                    raise ValueError("NYC CSV aggregate cell characters exceed cap")
                rows += 1
                on_row(rows, tuple(record))
    except (csv.Error, UnicodeError) as error:
        raise ValueError("NYC CSV is malformed") from error
    if rows != expected_rows:
        raise ValueError("NYC CSV row count differs from manifest")
    base._check_time(timer, origin)
    return {"rows": rows, "bytes_read": source.count}


def _worksheet_rows(
    archive: ZipFile,
    sheet: str,
    shared: tuple[str, ...],
    expected_borough_code: str,
    on_row: RowCallback,
    timer: base.Timer,
    start: float,
) -> dict:
    if archive.getinfo(sheet).file_size > base.MAX_WORKSHEET_XML:
        raise ValueError("Workbook worksheet exceeds decoded cap")
    rows = 0
    physical_rows = 0
    last_source_row = 0
    characters = 0
    sheet_data_seen = False
    sheet_data = None
    depth = 0
    first = True
    with archive.open(sheet) as raw:
        source = base._LimitedReader(raw, base.MAX_WORKSHEET_XML, timer, start)
        try:
            events = DET.iterparse(
                source,
                events=("start", "end"),
                forbid_dtd=True,
                forbid_entities=True,
                forbid_external=True,
            )
            for event, element in events:
                if first:
                    if event != "start" or element.tag != base.NS + "worksheet":
                        raise ValueError("Workbook worksheet root is invalid")
                    first = False
                if event == "start":
                    depth += 1
                    if element.tag == base.NS + "sheetData":
                        if sheet_data_seen or depth != 2:
                            raise ValueError(
                                "Workbook sheet data is duplicated or nested"
                            )
                        sheet_data = element
                        sheet_data_seen = True
                    continue
                if element.tag == base.NS + "sheetData":
                    sheet_data = None
                    depth -= 1
                    continue
                if element.tag != base.NS + "row":
                    depth -= 1
                    continue
                if sheet_data is None or depth != 3:
                    raise ValueError("Workbook row is not direct sheet data")
                physical_rows += 1
                if physical_rows > MAX_ROWS:
                    raise ValueError("Workbook physical row cap exceeded")
                reference = element.get("r", "")
                if not reference.isascii() or not reference.isdecimal():
                    raise ValueError("Workbook row number is invalid")
                source_row = int(reference)
                if source_row <= last_source_row:
                    raise ValueError("Workbook rows are duplicate or nonmonotone")
                last_source_row = source_row
                cells, formulas, _ = v3._parse_row(element, source_row, shared)
                if formulas or any(
                    column > len(HEADER) and value.strip()
                    for column, value in cells.items()
                ):
                    raise ValueError("Workbook row has formula or extra cell")
                values = tuple(cells.get(column, "") for column in range(1, 22))
                if physical_rows == v3.HEADER_PHYSICAL_ORDINAL:
                    if (
                        source_row != v3.HEADER_ROW_NUMBER
                        or tuple(value.strip() for value in values) != v3.RAW_HEADER
                    ):
                        raise ValueError("Workbook header differs from pinned alias")
                elif physical_rows > v3.HEADER_PHYSICAL_ORDINAL and any(
                    value.strip() for value in values
                ):
                    if values[0].strip() != expected_borough_code:
                        raise ValueError("Workbook row borough differs from file")
                    characters += sum(map(len, values))
                    if characters > MAX_CELL_CHARACTERS:
                        raise ValueError(
                            "Workbook aggregate cell characters exceed cap"
                        )
                    rows += 1
                    on_row(source_row, values)
                element.clear()
                sheet_data.clear()
                depth -= 1
        except DET.ParseError as error:
            raise ValueError("Workbook worksheet XML is malformed") from error
    if not sheet_data_seen or depth != 0:
        raise ValueError("Workbook sheet data is missing or incomplete")
    return {"rows": rows, "physical_rows": physical_rows}


def scan_qualified_workbook(
    handle: BinaryIO,
    expected_borough_code: str,
    on_row: RowCallback,
    *,
    timer: base.Timer = time.monotonic,
    start: float | None = None,
) -> dict:
    """Qualify the same workbook with v3, then stream its exact 21 raw values."""
    if (
        type(expected_borough_code) is not str
        or expected_borough_code not in ALLOWED_WORKBOOK_BOROUGHS
    ):
        raise ValueError("Workbook expected borough code is out of scope")
    origin = timer() if start is None else start
    inspected = v3.inspect_workbook(handle, timer=timer, start=origin)
    if inspected.get("worksheet_qualified") is not True:
        raise ValueError("Workbook did not pass v3 structural qualification")
    base._check_time(timer, origin)
    try:
        handle.seek(0)
        with ZipFile(handle) as archive:
            names = base._member_names(archive)
            base._check_printer_bytes(
                archive, base.PRODUCTION_PRINTER_PIN, timer, origin
            )
            sheets = {
                name
                for name in names
                if name.startswith("xl/worksheets/") and name.endswith(".xml")
            }
            declared = base._content_types(archive, timer, origin)
            relationships = base._relationships(archive, names, timer, origin)
            base._check_root(relationships)
            sheet, _, shared_path = base._workbook(
                archive, relationships, timer, origin
            )
            base._check_printer_relationship(relationships, sheet)
            if sheets != {sheet} or declared != {sheet}:
                raise ValueError("Workbook worksheet inventory differs from pin")
            v3._check_worksheet_content_type(archive, sheet, timer, origin)
            shared = base._shared_strings(archive, shared_path, timer, origin)
            result = _worksheet_rows(
                archive, sheet, shared, expected_borough_code, on_row, timer, origin
            )
    except (BadZipFile, LargeZipFile, EOFError, RuntimeError) as error:
        raise ValueError("Workbook ZIP is invalid") from error
    if (
        result["rows"] != inspected["data_rows"]
        or result["physical_rows"] != inspected["physical_rows"]
    ):
        raise ValueError("Workbook row counts changed after v3 qualification")
    base._check_time(timer, origin)
    return result
