"""Read one pinned Manhattan preamble formula without evaluating workbook cells."""

from __future__ import annotations

import time
from io import BufferedIOBase
from zipfile import ZipFile

from defusedxml import ElementTree as DET

import nyc_workbook_xml as base
import nyc_workbook_xml_v3 as v3


PROTOCOL = "nyc-manhattan-formula-diagnostic-v1"
SHEET = "xl/worksheets/sheet1.xml"
MAX_FORMULA_ATTRIBUTES = 8


def _require_v3(result: dict) -> None:
    if result["formula_cells"] != 1 or result["formula_preamble"] != 1:
        raise ValueError("Expected exactly one preamble formula")
    if (
        result["header_status"] != "exact_pinned_alias"
        or result["preamble_rows"] != 4
        or result["data_rows"] < 1
        or result["worksheet_qualified"]
        or any(
            result[name]
            for name in (
                "formula_header",
                "formula_data",
                "extra_preamble_cells",
                "extra_header_cells",
                "extra_data_cells",
                "invalid_header_candidate_rows",
                "missing_or_unparseable_dates",
                "out_of_period_dates",
                "repeated_header_rows",
            )
        )
    ):
        raise ValueError("Manhattan preamble structural condition differs")


def _attributes(formula) -> dict[str, str]:
    if len(formula) != 0 or len(formula.attrib) > MAX_FORMULA_ATTRIBUTES:
        raise ValueError("Preamble formula XML is unsupported")
    attributes = dict(formula.attrib)
    if any(
        len(name) > 64 or len(value) > base.MAX_STRING
        for name, value in attributes.items()
    ):
        raise ValueError("Preamble formula XML exceeds bounds")
    return attributes


def _row_formulas(row, ordinal: int) -> list[dict]:
    if len(row) > base.MAX_CELLS:
        raise ValueError("Preamble row cell cap exceeded")
    number_text = row.get("r", "")
    if not number_text.isascii() or not number_text.isdecimal():
        raise ValueError("Preamble row number is invalid")
    number = int(number_text)
    found = []
    previous_column = 0
    for cell in row:
        coordinate = cell.get("r", "")
        column = base._column(coordinate, number)
        if column <= previous_column:
            raise ValueError("Preamble cell coordinates are nonmonotone")
        previous_column = column
        formulas = cell.findall(base.NS + "f")
        if len(formulas) > 1:
            raise ValueError("Preamble formula XML is duplicated")
        if not formulas:
            continue
        formula = formulas[0]
        expression = formula.text or ""
        if len(expression) > base.MAX_STRING:
            raise ValueError("Preamble formula XML exceeds bounds")
        found.append(
            {
                "source_row": number,
                "physical_ordinal": ordinal,
                "coordinate": coordinate,
                "attributes": _attributes(formula),
                "expression": expression,
                "cached_value_present": cell.find(base.NS + "v") is not None,
            }
        )
    return found


def _extract(handle: BufferedIOBase, timer: base.Timer, start: float) -> dict:
    handle.seek(0)
    with ZipFile(handle) as archive:
        if archive.getinfo(SHEET).file_size > base.MAX_WORKSHEET_XML:
            raise ValueError("Preamble worksheet exceeds decoded cap")
        with archive.open(SHEET) as raw:
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
                found = []
                ordinal = 0
                for event, element in events:
                    if first:
                        if event != "start" or element.tag != base.NS + "worksheet":
                            raise ValueError("Preamble worksheet root differs")
                        first = False
                    if event == "start":
                        depth += 1
                        if element.tag == base.NS + "sheetData":
                            sheet_data = element
                        continue
                    if element.tag == base.NS + "row":
                        if sheet_data is None or depth != 3:
                            raise ValueError("Preamble row is not direct sheet data")
                        ordinal += 1
                        if ordinal > 4:
                            break
                        found.extend(_row_formulas(element, ordinal))
                        element.clear()
                        sheet_data.clear()
                    depth -= 1
            except DET.ParseError as error:
                raise ValueError("Preamble worksheet XML is malformed") from error
    if len(found) != 1:
        raise ValueError("Expected exactly one bounded preamble formula")
    return found[0]


def _diagnose_with_pin(
    handle: BufferedIOBase,
    pin: tuple[int, str],
    *,
    timer: base.Timer = time.monotonic,
    start: float | None = None,
) -> dict:
    """Synthetic-fixture entry with an explicit printer-settings pin."""
    origin = timer() if start is None else start
    inspected = v3._inspect_with_pin(handle, pin, timer=timer, start=origin)
    _require_v3(inspected)
    formula = _extract(handle, timer, origin)
    base._check_time(timer, origin)
    return {
        "protocol": PROTOCOL,
        "formula": formula,
        "v3_worksheet_qualified": False,
        "sale_labels_certified": 0,
    }


def diagnose_workbook(
    handle: BufferedIOBase,
    *,
    timer: base.Timer = time.monotonic,
    start: float | None = None,
) -> dict:
    """Production entry pinned to the captured official workbook package."""
    return _diagnose_with_pin(
        handle, base.PRODUCTION_PRINTER_PIN, timer=timer, start=start
    )
