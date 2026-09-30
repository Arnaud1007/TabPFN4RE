"""Inspect the exact pinned NYC borough worksheet schema without admitting labels."""

from __future__ import annotations

import time
from hashlib import sha256
from io import BufferedIOBase
from zipfile import BadZipFile, LargeZipFile, ZipFile

import nyc_workbook_xml as base
from defusedxml import ElementTree as DET
from profile_nyc_rolling_snapshot import HEADER

PROTOCOL = "nyc-borough-worksheet-inspection-v3"
RAW_HEADER = (*HEADER[:6], "EASEMENT", *HEADER[7:])
RAW_HEADER_SHA256 = sha256("\x1f".join(RAW_HEADER).encode("utf-8")).hexdigest()
EXPECTED_RAW_HEADER_SHA256 = (
    "4f8efb3fe379c1adb05938d397271d6c38002b6c2fdbe2224b3c4aa68d529e95"
)
HEADER_ROW_NUMBER = 5
HEADER_PHYSICAL_ORDINAL = 5
HEADER_LIKE_MIN_SCORE = 5
CONTENT_TYPES_NS = "{http://schemas.openxmlformats.org/package/2006/content-types}"
WORKSHEET_MIME = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"
)


def _empty_result() -> dict:
    return {
        "physical_rows": 0,
        "preamble_rows": 0,
        "data_rows": 0,
        "header_status": "missing",
        "header_lineage": None,
        "raw_header_sha256": None,
        "missing_or_unparseable_dates": 0,
        "out_of_period_dates": 0,
        "repeated_header_rows": 0,
        "formula_cells": 0,
        "formula_preamble": 0,
        "formula_header": 0,
        "formula_data": 0,
        "extra_preamble_cells": 0,
        "extra_header_cells": 0,
        "extra_data_cells": 0,
        "invalid_header_candidate_rows": 0,
        "date_min": None,
        "date_max": None,
    }


def _record_date(state: dict, value: str, system: str) -> None:
    parsed = base._date(value, system)
    if parsed is None:
        state["missing_or_unparseable_dates"] += 1
        return
    stamp = parsed.isoformat()
    state["date_min"] = min(state["date_min"], stamp) if state["date_min"] else stamp
    state["date_max"] = max(state["date_max"], stamp) if state["date_max"] else stamp
    if not base.START_DATE <= parsed <= base.END_DATE:
        state["out_of_period_dates"] += 1


def _worksheet(
    archive: ZipFile,
    sheet: str,
    shared: tuple[str, ...],
    system: str,
    timer: base.Timer,
    start: float,
) -> dict:
    if archive.getinfo(sheet).file_size > base.MAX_WORKSHEET_XML:
        raise ValueError("Workbook worksheet exceeds decoded cap")
    state = _empty_result()
    last_row = 0
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
            first = True
            depth = 0
            sheet_data = None
            sheet_data_seen = False
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
                state["physical_rows"] += 1
                ordinal = state["physical_rows"]
                if ordinal > base.MAX_ROWS:
                    raise ValueError("Workbook physical row cap exceeded")
                reference = element.get("r", "")
                if not reference.isascii() or not reference.isdecimal():
                    raise ValueError("Workbook row number is invalid")
                number = int(reference)
                if number <= last_row:
                    raise ValueError("Workbook rows are duplicate or nonmonotone")
                last_row = number
                cells, formulas, beyond_formula = _parse_row(element, number, shared)
                ordered = tuple(cells.get(i, "").strip() for i in range(1, 22))
                extra = (
                    sum(
                        bool(value.strip())
                        for column, value in cells.items()
                        if column > len(RAW_HEADER)
                    )
                    + beyond_formula
                )
                state["formula_cells"] += formulas
                zone = (
                    "preamble"
                    if ordinal < HEADER_PHYSICAL_ORDINAL
                    else "header"
                    if ordinal == HEADER_PHYSICAL_ORDINAL
                    else "data"
                )
                state[f"formula_{zone}"] += formulas
                score = sum(a == b for a, b in zip(ordered, RAW_HEADER))
                if ordinal == HEADER_PHYSICAL_ORDINAL:
                    state["extra_header_cells"] = extra
                    if (
                        number == HEADER_ROW_NUMBER
                        and ordered == RAW_HEADER
                        and extra == 0
                        and formulas == 0
                    ):
                        state["header_status"] = "exact_pinned_alias"
                        state["raw_header_sha256"] = RAW_HEADER_SHA256
                        state["header_lineage"] = {
                            "source_column": "G",
                            "source_column_index": 7,
                            "source_name": "EASEMENT",
                            "canonical_name": "EASE-MENT",
                        }
                    else:
                        state["header_status"] = "mismatch"
                elif ordinal < HEADER_PHYSICAL_ORDINAL:
                    state["preamble_rows"] += 1
                    state["extra_preamble_cells"] += extra
                if ordinal != HEADER_PHYSICAL_ORDINAL and ordinal <= 25:
                    state["invalid_header_candidate_rows"] += (
                        all(ordered) and score >= HEADER_LIKE_MIN_SCORE
                    )
                if ordinal > HEADER_PHYSICAL_ORDINAL and (
                    any(ordered) or extra or formulas
                ):
                    state["data_rows"] += 1
                    state["extra_data_cells"] += extra
                    if ordered in (RAW_HEADER, HEADER):
                        state["repeated_header_rows"] += 1
                    _record_date(state, cells.get(21, ""), system)
                element.clear()
                sheet_data.clear()
                depth -= 1
        except DET.ParseError as error:
            raise ValueError("Workbook worksheet XML is malformed") from error
    if not sheet_data_seen or depth != 0:
        raise ValueError("Workbook sheet data is missing or incomplete")
    state["worksheet_qualified"] = (
        state["header_status"] == "exact_pinned_alias"
        and state["data_rows"] > 0
        and not any(
            state[key]
            for key in (
                "missing_or_unparseable_dates",
                "out_of_period_dates",
                "repeated_header_rows",
                "formula_cells",
                "extra_preamble_cells",
                "extra_header_cells",
                "extra_data_cells",
                "invalid_header_candidate_rows",
            )
        )
    )
    return {**state, "label_status": "unqualified", "sale_labels_certified": 0}


def _parse_row(
    row, number: int, shared: tuple[str, ...]
) -> tuple[dict[int, str], int, int]:
    if len(row) > base.MAX_CELLS:
        raise ValueError("Workbook row cell cap exceeded")
    cells: dict[int, str] = {}
    formulas = 0
    beyond_formula = 0
    last_column = 0
    for item in row:
        column = base._column(item.get("r", ""), number)
        if column <= last_column:
            raise ValueError("Workbook cell coordinates are nonmonotone")
        last_column = column
        value, formula = base._cell(item, shared)
        cells[column] = value
        if formula:
            formulas += 1
            beyond_formula += column > len(RAW_HEADER)
    return cells, formulas, beyond_formula


def _check_worksheet_content_type(
    archive: ZipFile, sheet: str, timer: base.Timer, start: float
) -> None:
    root = base._xml_root(
        archive, "[Content_Types].xml", base.MAX_OTHER_XML, timer, start
    )
    declarations = [
        entry
        for entry in root
        if entry.get("PartName", "").casefold() == ("/" + sheet).casefold()
    ]
    if (
        len(declarations) != 1
        or declarations[0].tag != CONTENT_TYPES_NS + "Override"
        or declarations[0].get("PartName") != "/" + sheet
        or declarations[0].get("ContentType") != WORKSHEET_MIME
    ):
        raise ValueError("Workbook worksheet MIME differs from pin")


def _inspect_with_pin(
    handle: BufferedIOBase,
    pin: tuple[int, str],
    *,
    timer: base.Timer = time.monotonic,
    start: float | None = None,
) -> dict:
    """Test fixture entry; production always uses the pinned official binary."""
    if (
        base.HEADER_SHA256 != base.EXPECTED_HEADER_SHA256
        or RAW_HEADER_SHA256 != EXPECTED_RAW_HEADER_SHA256
    ):
        raise ValueError("Pinned NYC header definition changed")
    origin = timer() if start is None else start
    base._check_time(timer, origin)
    try:
        handle.seek(0)
        with ZipFile(handle) as archive:
            names = base._member_names(archive)
            base._check_printer_bytes(archive, pin, timer, origin)
            sheets = {
                name
                for name in names
                if name.startswith("xl/worksheets/") and name.endswith(".xml")
            }
            declared = base._content_types(archive, timer, origin)
            relationships = base._relationships(archive, names, timer, origin)
            base._check_root(relationships)
            sheet, system, shared_path = base._workbook(
                archive, relationships, timer, origin
            )
            base._check_printer_relationship(relationships, sheet)
            if sheets != {sheet} or declared != {sheet}:
                raise ValueError("Workbook has extra or missing worksheet parts")
            _check_worksheet_content_type(archive, sheet, timer, origin)
            strings = base._shared_strings(archive, shared_path, timer, origin)
            result = _worksheet(archive, sheet, strings, system, timer, origin)
            base._check_time(timer, origin)
            return {
                "protocol": PROTOCOL,
                "sheet_count": 1,
                "date_system": system,
                **result,
            }
    except (BadZipFile, LargeZipFile, EOFError, RuntimeError) as error:
        raise ValueError("Workbook ZIP is invalid") from error


def inspect_workbook(
    handle: BufferedIOBase,
    *,
    timer: base.Timer = time.monotonic,
    start: float | None = None,
) -> dict:
    """Production inspection with no configurable printer or header policy."""
    return _inspect_with_pin(
        handle, base.PRODUCTION_PRINTER_PIN, timer=timer, start=start
    )
