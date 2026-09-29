"""Bounded, candidate-only scanner for the pinned NYC borough XLSX packages."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from io import BufferedIOBase
import time
from typing import Callable
from zipfile import BadZipFile, LargeZipFile, ZipFile

from defusedxml import ElementTree as DET

import nyc_workbook_xml as workbook
from profile_nyc_rolling_snapshot import HEADER


PROTOCOL = "nyc-borough-header-diagnostic-v1"
FIRST_ROWS = 25
HEADER_COLUMNS = len(HEADER)
Timer = Callable[[], float]


@dataclass(frozen=True)
class _Row:
    number: int
    ordinal: int
    values: tuple[str | int, ...]
    formula_cells: int
    beyond_21_count: int


def _string_index(cell) -> int:
    node = cell.find(workbook.NS + "v")
    value = "" if node is None else (node.text or "")
    if len(value) > workbook.MAX_STRING or not value.isascii() or not value.isdecimal():
        raise ValueError("Workbook shared string index is invalid")
    number = int(value)
    if number >= workbook.MAX_SHARED_STRINGS:
        raise ValueError("Workbook shared string index exceeds limit")
    return number


def _bounded_text(cell) -> None:
    """Validate text length without retaining the cell's value."""
    size = sum(len(element.text or "") for element in cell.iter())
    if size > workbook.MAX_STRING:
        raise ValueError("Workbook cell text exceeds limit")


def _late_cell_length_only(cell) -> None:
    """Enforce the size cap without combining, returning or retaining text."""
    count = 0
    for element in cell.iter():
        count += len(element.text or "")
        if count > workbook.MAX_STRING:
            raise ValueError("Workbook cell text exceeds limit")


def _row_values(row, number: int, ordinal: int) -> tuple[_Row | None, set[int]]:
    if len(row) > workbook.MAX_CELLS:
        raise ValueError("Workbook row cell cap exceeded")
    cells: dict[int, str | int] = {}
    requested: set[int] = set()
    formulas = 0
    extras = 0
    for cell in row:
        if cell.tag != workbook.NS + "c":
            raise ValueError("Workbook row contains unsupported element")
        column = workbook._column(cell.get("r", ""), number)
        if column in cells:
            raise ValueError("Workbook cell coordinate is duplicated")
        kind = cell.get("t", "n")
        if kind not in ("n", "s", "inlineStr", "str", "b"):
            raise ValueError("Workbook cell representation is unsupported")
        formula = cell.find(workbook.NS + "f") is not None
        if ordinal > FIRST_ROWS:
            if not formula:
                _late_cell_length_only(cell)
            cells[column] = ""
            continue
        if column > HEADER_COLUMNS:
            if not formula:
                _bounded_text(cell)
            cells[column] = ""
            extras += 1
            continue
        if formula:
            cells[column] = ""
            formulas += 1
        elif kind == "s":
            index = _string_index(cell)
            cells[column] = index
            requested.add(index)
        else:
            value, _ = workbook._cell(cell, ())
            cells[column] = value
    if ordinal > FIRST_ROWS:
        return None, requested
    ordered = tuple(cells.get(column, "") for column in range(1, HEADER_COLUMNS + 1))
    return _Row(number, ordinal, ordered, formulas, extras), requested


def _scan_sheet(
    archive: ZipFile, name: str, timer: Timer, start: float
) -> tuple[list[_Row], set[int], int]:
    if archive.getinfo(name).file_size > workbook.MAX_WORKSHEET_XML:
        raise ValueError("Workbook worksheet exceeds decoded cap")
    rows: list[_Row] = []
    requested: set[int] = set()
    ordinal = last_number = 0
    with archive.open(name) as raw:
        reader = workbook._LimitedReader(raw, workbook.MAX_WORKSHEET_XML, timer, start)
        try:
            events = DET.iterparse(
                reader,
                events=("start", "end"),
                forbid_dtd=True,
                forbid_entities=True,
                forbid_external=True,
            )
            root = sheet_data = None
            sheet_data_seen = False
            for event, element in events:
                if root is None:
                    if event != "start" or element.tag != workbook.NS + "worksheet":
                        raise ValueError("Workbook worksheet root is invalid")
                    root = element
                if event == "start":
                    if element.tag == workbook.NS + "sheetData":
                        if sheet_data_seen:
                            raise ValueError("Workbook has duplicate sheet data")
                        sheet_data = element
                        sheet_data_seen = True
                    continue
                if element.tag == workbook.NS + "sheetData":
                    sheet_data = None
                    continue
                if element.tag != workbook.NS + "row":
                    continue
                if sheet_data is None:
                    raise ValueError("Workbook row is outside sheet data")
                ordinal += 1
                if ordinal > workbook.MAX_ROWS:
                    raise ValueError("Workbook physical row cap exceeded")
                reference = element.get("r", "")
                if not reference.isascii() or not reference.isdecimal():
                    raise ValueError("Workbook row number is invalid")
                number = int(reference)
                if number <= last_number:
                    raise ValueError("Workbook rows are duplicate or nonmonotone")
                last_number = number
                candidate, indices = _row_values(element, number, ordinal)
                if candidate is not None:
                    rows.append(candidate)
                    requested.update(indices)
                element.clear()
                sheet_data.clear()
            if not sheet_data_seen:
                raise ValueError("Workbook sheet data is missing")
        except DET.ParseError as error:
            raise ValueError("Workbook worksheet XML is malformed") from error
    return rows, requested, ordinal


def _select_strings(
    archive: ZipFile, name: str | None, requested: set[int], timer: Timer, start: float
) -> dict[int, str]:
    if name is None:
        if requested:
            raise ValueError("Workbook shared strings part is missing")
        return {}
    if archive.getinfo(name).file_size > workbook.MAX_SHARED_XML:
        raise ValueError("Workbook shared strings exceed decoded cap")
    selected: dict[int, str] = {}
    index = 0
    with archive.open(name) as raw:
        reader = workbook._LimitedReader(raw, workbook.MAX_SHARED_XML, timer, start)
        try:
            events = DET.iterparse(
                reader,
                events=("start", "end"),
                forbid_dtd=True,
                forbid_entities=True,
                forbid_external=True,
            )
            root = None
            for event, element in events:
                if root is None:
                    if event != "start" or element.tag != workbook.NS + "sst":
                        raise ValueError("Workbook shared strings root is invalid")
                    root = element
                if element.tag != workbook.NS + "si" or event != "end":
                    continue
                if index >= workbook.MAX_SHARED_STRINGS:
                    raise ValueError("Workbook shared string count exceeds limit")
                if index in requested:
                    value = "".join(
                        part.text or "" for part in element.iter(workbook.NS + "t")
                    )
                    if len(value) > workbook.MAX_STRING:
                        raise ValueError("Workbook shared string exceeds limit")
                    selected[index] = value
                elif (
                    sum(
                        len(part.text or "") for part in element.iter(workbook.NS + "t")
                    )
                    > workbook.MAX_STRING
                ):
                    raise ValueError("Workbook shared string exceeds limit")
                index += 1
                element.clear()
                root.clear()
        except DET.ParseError as error:
            raise ValueError("Workbook shared strings XML is malformed") from error
    if selected.keys() != requested:
        raise ValueError("Workbook shared string index is missing")
    return selected


def _candidate(rows: list[_Row], strings: dict[int, str]) -> dict:
    scored = []
    for row in rows:
        values = tuple(
            (strings[value] if type(value) is int else value).strip()
            for value in row.values
        )
        score = sum(
            actual == expected for actual, expected in zip(values, HEADER, strict=True)
        )
        scored.append((score, row, values))
    if not scored:
        return {"status": "no_unique_candidate"}
    best = max(score for score, _, _ in scored)
    winners = [(row, values) for score, row, values in scored if score == best]
    if best < 5 or len(winners) != 1:
        return {"status": "no_unique_candidate"}
    row, values = winners[0]
    if row.formula_cells:
        return {
            "status": "rejected_formula_candidate",
            "candidate_score": best,
            "source_row_number": row.number,
            "physical_ordinal": row.ordinal,
            "nonempty_count": sum(bool(value) for value in values),
            "formula_cells": row.formula_cells,
            "beyond_21_count": row.beyond_21_count,
        }
    fingerprint = sha256("\x1f".join(values).encode("utf-8")).hexdigest()
    return {
        "status": "candidate_found",
        "candidate": {
            "cells": list(values),
            "source_row_number": row.number,
            "physical_ordinal": row.ordinal,
            "score": best,
            "nonempty_count": sum(bool(value) for value in values),
            "formula_cells": row.formula_cells,
            "beyond_21_count": row.beyond_21_count,
            "fingerprint_sha256": fingerprint,
        },
    }


def _scan_with_pin(
    handle: BufferedIOBase,
    pin: tuple[int, str],
    *,
    timer: Timer = time.monotonic,
    start: float | None = None,
) -> dict:
    """Test-only fixture entry; production entry always uses the frozen pin."""
    if workbook.HEADER_SHA256 != workbook.EXPECTED_HEADER_SHA256:
        raise ValueError("Pinned NYC header definition changed")
    origin = timer() if start is None else start
    workbook._check_time(timer, origin)
    try:
        handle.seek(0)
        with ZipFile(handle) as archive:
            names = workbook._member_names(archive)
            workbook._check_printer_bytes(archive, pin, timer, origin)
            declared = workbook._content_types(archive, timer, origin)
            relationships = workbook._relationships(archive, names, timer, origin)
            workbook._check_root(relationships)
            sheet, system, shared_path = workbook._workbook(
                archive, relationships, timer, origin
            )
            workbook._check_printer_relationship(relationships, sheet)
            sheet_members = {
                name
                for name in names
                if name.startswith("xl/worksheets/") and name.endswith(".xml")
            }
            if sheet_members != {sheet} or (declared and declared != {sheet}):
                raise ValueError("Workbook worksheet inventory differs")
            rows, requested, physical_rows = _scan_sheet(archive, sheet, timer, origin)
            strings = _select_strings(archive, shared_path, requested, timer, origin)
            workbook._check_time(timer, origin)
            return {
                "protocol": PROTOCOL,
                "sheet_count": 1,
                "date_system": system,
                "physical_rows": physical_rows,
                **_candidate(rows, strings),
            }
    except (BadZipFile, LargeZipFile, EOFError, RuntimeError) as error:
        raise ValueError("Workbook ZIP is invalid") from error


def scan_workbook(
    handle: BufferedIOBase, *, timer: Timer = time.monotonic, start: float | None = None
) -> dict:
    """Production scan with no request, CLI or environment policy override."""
    return _scan_with_pin(
        handle, workbook.PRODUCTION_PRINTER_PIN, timer=timer, start=start
    )
