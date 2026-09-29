"""Bounded OOXML parser for synthetic and pinned NYC borough workbooks.

Only a small set of structural facts is returned. Cell values are never
included in public results, and sale prices are never interpreted here.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from io import BufferedIOBase
import posixpath
import re
import stat
import time
from typing import Callable
from urllib.parse import urlsplit
from zipfile import BadZipFile, LargeZipFile, ZipFile

from defusedxml import ElementTree as DET
from profile_nyc_rolling_snapshot import HEADER


PROTOCOL = "nyc-borough-worksheet-inspection-v1"
HEADER_SHA256 = sha256("\x1f".join(HEADER).encode("utf-8")).hexdigest()
EXPECTED_HEADER_SHA256 = (
    "66e69917e7320aa14485b0f6a3eee7b6ae1fc7b4632d93134a5ca53f326feb65"
)
NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
RNS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
PNS = "{http://schemas.openxmlformats.org/package/2006/relationships}"
MAX_WORKSHEET_XML = 32 * 1024 * 1024
MAX_SHARED_XML = 4 * 1024 * 1024
MAX_OTHER_XML = 1024 * 1024
MAX_ROWS = 150_000
MAX_CELLS = 64
MAX_SHARED_STRINGS = 100_000
MAX_STRING = 512
MAX_SECONDS = 180
MAX_ZIP_MEMBERS = 256
MAX_TOTAL_DECODED = 512 * 1024 * 1024
START_DATE = date(2025, 9, 1)
END_DATE = date(2026, 8, 31)
Timer = Callable[[], float]


def _check_time(timer: Timer, start: float) -> None:
    if timer() - start > MAX_SECONDS:
        raise TimeoutError("Workbook inspection exceeded elapsed-time cap")


class _LimitedReader:
    def __init__(self, stream: BufferedIOBase, limit: int, timer: Timer, start: float):
        self.stream = stream
        self.limit = limit
        self.timer = timer
        self.start = start
        self.count = 0

    def read(self, size: int = -1) -> bytes:
        _check_time(self.timer, self.start)
        bounded = min(65536, self.limit - self.count + 1)
        requested = bounded if size < 0 else min(size, bounded)
        body = self.stream.read(requested)
        self.count += len(body)
        if self.count > self.limit:
            raise ValueError("Workbook XML part exceeds decoded limit")
        _check_time(self.timer, self.start)
        return body


def _member_names(archive: ZipFile) -> set[str]:
    members = archive.infolist()
    if not 3 <= len(members) <= MAX_ZIP_MEMBERS:
        raise ValueError("Workbook ZIP member count is invalid")
    names: set[str] = set()
    seen: set[str] = set()
    total = 0
    for member in members:
        name = member.filename
        if (
            not name
            or name.startswith("/")
            or "\\" in name
            or ":" in name
            or any(ord(char) < 32 for char in name)
            or any(part in ("", ".", "..") for part in name.rstrip("/").split("/"))
        ):
            raise ValueError("Workbook ZIP member path is unsafe")
        normalized = name.rstrip("/")
        if normalized.casefold() in seen:
            raise ValueError("Workbook ZIP member is duplicated")
        seen.add(normalized.casefold())
        if name.lower().endswith(".rels") and not name.endswith(".rels"):
            raise ValueError("Workbook relationship part uses unsupported case")
        kind = (member.external_attr >> 16) & 0o170000
        if kind == stat.S_IFLNK or member.flag_bits & 1:
            raise ValueError("Workbook ZIP member is linked or encrypted")
        if member.is_dir() or kind == stat.S_IFDIR:
            if not member.is_dir() or member.file_size != 0:
                raise ValueError("Workbook ZIP directory entry is invalid")
            continue
        names.add(name)
        if member.compress_type not in (0, 8):
            raise ValueError("Workbook ZIP compression is unsupported")
        total += member.file_size
        if member.file_size > MAX_TOTAL_DECODED or total > MAX_TOTAL_DECODED:
            raise ValueError("Workbook ZIP exceeds decoded cap")
        lower = name.lower()
        if lower.endswith(".bin") or any(
            token in lower
            for token in (
                "vba",
                "activex",
                "externallink",
                "embedding",
                "connections.xml",
                "oleobject",
            )
        ):
            raise ValueError("Workbook contains an active or external part")
    if not {
        "[Content_Types].xml",
        "_rels/.rels",
        "xl/workbook.xml",
        "xl/_rels/workbook.xml.rels",
    }.issubset(names):
        raise ValueError("Workbook ZIP lacks required metadata")
    return names


def _xml_root(archive: ZipFile, name: str, limit: int, timer: Timer, start: float):
    info = archive.getinfo(name)
    if info.file_size > limit:
        raise ValueError("Workbook XML declared size exceeds limit")
    with archive.open(name) as raw:
        source = _LimitedReader(raw, limit, timer, start)
        body = b"".join(iter(lambda: source.read(65536), b""))
    try:
        return DET.fromstring(
            body, forbid_dtd=True, forbid_entities=True, forbid_external=True
        )
    except DET.ParseError as error:
        raise ValueError("Workbook XML is malformed") from error


def _source_part(rels_name: str) -> str:
    if rels_name == "_rels/.rels":
        return ""
    directory, basename = posixpath.split(rels_name)
    if not directory.endswith("/_rels") or not basename.endswith(".rels"):
        raise ValueError("Workbook relationship part path is invalid")
    return posixpath.join(
        directory.removesuffix("/_rels"), basename.removesuffix(".rels")
    )


def _target(source_part: str, target: str, names: set[str]) -> str:
    if (
        not target
        or target.startswith(("/", "\\"))
        or "\\" in target
        or "%" in target
        or any(ord(char) < 32 or ord(char) == 127 for char in target)
        or urlsplit(target).scheme
        or ":" in target
        or "?" in target
        or "#" in target
    ):
        raise ValueError("Workbook relationship target is unsafe")
    combined = posixpath.join(posixpath.dirname(source_part), target)
    parts: list[str] = []
    for part in combined.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            if not parts:
                raise ValueError("Workbook relationship escapes ZIP root")
            parts.pop()
        else:
            parts.append(part)
    resolved = "/".join(parts)
    if resolved not in names:
        raise ValueError("Workbook relationship target is missing")
    return resolved


def _relationships(
    archive: ZipFile, names: set[str], timer: Timer, start: float
) -> dict[str, dict[str, tuple[str, str]]]:
    result = {}
    for name in sorted(item for item in names if item.endswith(".rels")):
        root = _xml_root(archive, name, MAX_OTHER_XML, timer, start)
        if root.tag != PNS + "Relationships":
            raise ValueError("Workbook relationship XML has wrong root")
        source = _source_part(name)
        mapping = {}
        for relation in root:
            if relation.tag != PNS + "Relationship":
                raise ValueError("Workbook relationship XML has unknown item")
            identifier = relation.get("Id")
            kind = relation.get("Type", "")
            target = relation.get("Target", "")
            if (
                not identifier
                or identifier in mapping
                or relation.get("TargetMode") not in (None, "Internal")
            ):
                raise ValueError("Workbook relationship is duplicate or external")
            if any(
                token in kind.lower()
                for token in (
                    "externallink",
                    "vba",
                    "activex",
                    "connection",
                    "oleobject",
                )
            ):
                raise ValueError("Workbook relationship references an active part")
            mapping[identifier] = (kind, _target(source, target, names))
        result[source] = mapping
    return result


def _content_types(archive: ZipFile, timer: Timer, start: float) -> set[str]:
    root = _xml_root(archive, "[Content_Types].xml", MAX_OTHER_XML, timer, start)
    if (
        root.tag
        != "{http://schemas.openxmlformats.org/package/2006/content-types}Types"
    ):
        raise ValueError("Workbook content-type XML root is invalid")
    worksheet_parts: set[str] = set()
    for entry in root:
        metadata = " ".join(str(value).lower() for value in entry.attrib.values())
        if any(
            token in metadata
            for token in (
                "vba",
                "activex",
                "externallink",
                "connection",
                "oleobject",
                "macroenabled",
            )
        ):
            raise ValueError("Workbook content types reference an active part")
        if entry.get("ContentType", "").lower().endswith("spreadsheetml.worksheet+xml"):
            part = entry.get("PartName", "")
            if (
                entry.tag
                != "{http://schemas.openxmlformats.org/package/2006/content-types}Override"
                or not part.startswith("/")
                or part[1:] in worksheet_parts
            ):
                raise ValueError(
                    "Workbook worksheet content-type declaration is invalid"
                )
            worksheet_parts.add(part[1:])
    return worksheet_parts


def _workbook(
    archive: ZipFile, relationships: dict, timer: Timer, start: float
) -> tuple[str, str, str | None]:
    root = _xml_root(archive, "xl/workbook.xml", MAX_OTHER_XML, timer, start)
    if root.tag != NS + "workbook":
        raise ValueError("Workbook XML root is invalid")
    sheets = root.find(NS + "sheets")
    if sheets is None or len(sheets) != 1 or sheets[0].tag != NS + "sheet":
        raise ValueError("Workbook must contain exactly one data sheet")
    sheet_id = sheets[0].get(RNS + "id")
    mapping = relationships.get("xl/workbook.xml", {})
    if sum(kind.endswith("/worksheet") for kind, _ in mapping.values()) != 1:
        raise ValueError("Workbook has multiple worksheet relationships")
    if sheet_id not in mapping or not mapping[sheet_id][0].endswith("/worksheet"):
        raise ValueError("Workbook sheet relationship is invalid")
    sheet_path = mapping[sheet_id][1]
    shared = [
        path for kind, path in mapping.values() if kind.endswith("/sharedStrings")
    ]
    if len(shared) > 1:
        raise ValueError("Workbook shared strings are ambiguous")
    props = root.find(NS + "workbookPr")
    value = props.get("date1904") if props is not None else None
    if value in (None, "0", "false"):
        system = "1900_default" if value is None else "1900_explicit"
    elif value in ("1", "true"):
        system = "1904_explicit"
    else:
        raise ValueError("Workbook date system is unsupported")
    return sheet_path, system, shared[0] if shared else None


def _shared_strings(
    archive: ZipFile, name: str | None, timer: Timer, start: float
) -> tuple[str, ...]:
    if name is None:
        return ()
    if archive.getinfo(name).file_size > MAX_SHARED_XML:
        raise ValueError("Workbook shared strings exceed decoded cap")
    strings = []
    with archive.open(name) as raw:
        source = _LimitedReader(raw, MAX_SHARED_XML, timer, start)
        try:
            events = DET.iterparse(
                source,
                events=("start", "end"),
                forbid_dtd=True,
                forbid_entities=True,
                forbid_external=True,
            )
            first = True
            root_element = None
            for event, element in events:
                if first:
                    if event != "start" or element.tag != NS + "sst":
                        raise ValueError("Workbook shared strings root is invalid")
                    root_element = element
                    first = False
                if element.tag == NS + "si":
                    if event != "end":
                        continue
                    value = "".join(part.text or "" for part in element.iter(NS + "t"))
                    if len(value) > MAX_STRING or len(strings) >= MAX_SHARED_STRINGS:
                        raise ValueError("Workbook shared string exceeds limit")
                    strings.append(value)
                    element.clear()
                    root_element.clear()
        except DET.ParseError as error:
            raise ValueError("Workbook shared strings XML is malformed") from error
    return tuple(strings)


def _column(reference: str, row_number: int) -> int:
    match = re.fullmatch(r"([A-Z]{1,2})([1-9][0-9]*)", reference)
    if match is None or int(match.group(2)) != row_number:
        raise ValueError("Workbook cell reference is invalid")
    number = 0
    for character in match.group(1):
        number = number * 26 + ord(character) - 64
    if not 1 <= number <= MAX_CELLS:
        raise ValueError("Workbook cell column exceeds limit")
    return number


def _cell(cell, shared: tuple[str, ...]) -> tuple[str, bool]:
    if cell.tag != NS + "c":
        raise ValueError("Workbook row contains unsupported element")
    kind = cell.get("t", "n")
    if kind not in ("n", "s", "inlineStr", "str", "b"):
        raise ValueError("Workbook cell representation is unsupported")
    formula = cell.find(NS + "f") is not None
    if formula:
        return "", True
    if kind == "inlineStr":
        inline = cell.find(NS + "is")
        value = (
            ""
            if inline is None
            else "".join(part.text or "" for part in inline.iter(NS + "t"))
        )
    else:
        node = cell.find(NS + "v")
        value = "" if node is None else (node.text or "")
    if len(value) > MAX_STRING:
        raise ValueError("Workbook cell text exceeds limit")
    if kind == "s":
        if not value.isascii() or not value.isdecimal() or int(value) >= len(shared):
            raise ValueError("Workbook shared string index is invalid")
        value = shared[int(value)]
    return value, False


def _date(value: str, system: str) -> date | None:
    value = value.strip()
    if not value:
        return None
    if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    if re.fullmatch(r"[0-9]{2}/[0-9]{2}/[0-9]{4}", value):
        try:
            return datetime.strptime(value, "%m/%d/%Y").date()
        except ValueError:
            return None
    try:
        serial = Decimal(value)
    except InvalidOperation:
        return None
    if not serial.is_finite() or serial != serial.to_integral_value():
        return None
    if serial > 3_000_000 or serial < 0:
        return None
    number = int(serial)
    if system.startswith("1900") and number < 61:
        return None
    if system == "1904_explicit" and number < 0:
        return None
    base = date(1899, 12, 30) if system.startswith("1900") else date(1904, 1, 1)
    try:
        return base + timedelta(days=number)
    except OverflowError:
        return None


def _worksheet(
    archive: ZipFile,
    sheet: str,
    shared: tuple[str, ...],
    system: str,
    timer: Timer,
    start: float,
) -> dict:
    if archive.getinfo(sheet).file_size > MAX_WORKSHEET_XML:
        raise ValueError("Workbook worksheet exceeds decoded cap")
    state = {
        "physical_rows": 0,
        "preamble_rows": 0,
        "data_rows": 0,
        "header_status": "missing",
        "header_sha256": None,
        "missing_or_unparseable_dates": 0,
        "out_of_period_dates": 0,
        "repeated_header_rows": 0,
        "formula_cells": 0,
        "extra_data_cells": 0,
        "invalid_header_candidate_rows": 0,
        "date_min": None,
        "date_max": None,
    }
    last_row = 0
    with archive.open(sheet) as raw:
        source = _LimitedReader(raw, MAX_WORKSHEET_XML, timer, start)
        try:
            events = DET.iterparse(
                source,
                events=("start", "end"),
                forbid_dtd=True,
                forbid_entities=True,
                forbid_external=True,
            )
            first = True
            sheet_data = None
            sheet_data_seen = False
            for event, row in events:
                if first:
                    if event != "start" or row.tag != NS + "worksheet":
                        raise ValueError("Workbook worksheet root is invalid")
                    first = False
                if event == "start":
                    if row.tag == NS + "sheetData":
                        if sheet_data_seen:
                            raise ValueError("Workbook has duplicate sheet data")
                        sheet_data = row
                        sheet_data_seen = True
                    continue
                if row.tag == NS + "sheetData":
                    sheet_data = None
                    continue
                if row.tag != NS + "row":
                    continue
                if sheet_data is None:
                    raise ValueError("Workbook row is outside sheet data")
                state["physical_rows"] += 1
                if state["physical_rows"] > MAX_ROWS:
                    raise ValueError("Workbook physical row cap exceeded")
                reference = row.get("r", "")
                if not reference.isascii() or not reference.isdecimal():
                    raise ValueError("Workbook row number is invalid")
                number = int(reference)
                if number <= last_row:
                    raise ValueError("Workbook rows are duplicate or nonmonotone")
                last_row = number
                if len(row) > MAX_CELLS:
                    raise ValueError("Workbook row cell cap exceeded")
                cells: dict[int, str] = {}
                row_formula = 0
                extra_formula = 0
                for item in row:
                    column = _column(item.get("r", ""), number)
                    if column in cells:
                        raise ValueError("Workbook cell coordinate is duplicated")
                    value, formula = _cell(item, shared)
                    cells[column] = value
                    if formula:
                        row_formula += 1
                        if column <= 21:
                            state["formula_cells"] += 1
                        else:
                            extra_formula += 1
                ordered = tuple(cells.get(index, "").strip() for index in range(1, 22))
                extra = (
                    sum(
                        bool(value.strip())
                        for index, value in cells.items()
                        if index > 21
                    )
                    + extra_formula
                )
                if state["header_status"] != "exact" and state["physical_rows"] <= 25:
                    if ordered == HEADER and extra == 0:
                        state["header_status"] = "exact"
                        state["header_sha256"] = HEADER_SHA256
                    else:
                        state["preamble_rows"] += 1
                        if all(ordered):
                            state["invalid_header_candidate_rows"] += 1
                        if any(ordered) or extra:
                            state["header_status"] = "mismatch"
                            state["header_sha256"] = sha256(
                                "\x1f".join(ordered).encode()
                            ).hexdigest()
                elif state["header_status"] == "exact" and (
                    any(ordered) or extra or row_formula
                ):
                    state["data_rows"] += 1
                    state["extra_data_cells"] += extra
                    if ordered == HEADER:
                        state["repeated_header_rows"] += 1
                    parsed = _date(cells.get(21, ""), system)
                    if parsed is None:
                        state["missing_or_unparseable_dates"] += 1
                    else:
                        stamp = parsed.isoformat()
                        state["date_min"] = (
                            min(state["date_min"], stamp)
                            if state["date_min"]
                            else stamp
                        )
                        state["date_max"] = (
                            max(state["date_max"], stamp)
                            if state["date_max"]
                            else stamp
                        )
                        if not START_DATE <= parsed <= END_DATE:
                            state["out_of_period_dates"] += 1
                row.clear()
                sheet_data.clear()
        except DET.ParseError as error:
            raise ValueError("Workbook worksheet XML is malformed") from error
    state["qualified"] = (
        state["header_status"] == "exact"
        and state["data_rows"] > 0
        and not any(
            state[key]
            for key in (
                "missing_or_unparseable_dates",
                "out_of_period_dates",
                "repeated_header_rows",
                "formula_cells",
                "extra_data_cells",
                "invalid_header_candidate_rows",
            )
        )
    )
    return state


def inspect_workbook(
    handle: BufferedIOBase, *, timer: Timer = time.monotonic, start: float | None = None
) -> dict:
    """Inspect a workbook using a caller-owned seekable handle; no extraction."""
    if HEADER_SHA256 != EXPECTED_HEADER_SHA256:
        raise ValueError("Pinned NYC header definition changed")
    origin = timer() if start is None else start
    _check_time(timer, origin)
    try:
        handle.seek(0)
        with ZipFile(handle) as archive:
            names = _member_names(archive)
            sheet_members = {
                name
                for name in names
                if name.startswith("xl/worksheets/") and name.endswith(".xml")
            }
            declared_sheets = _content_types(archive, timer, origin)
            relationships = _relationships(archive, names, timer, origin)
            root = relationships.get("", {})
            if (
                len(root) != 1
                or not next(iter(root.values()))[0].endswith("/officeDocument")
                or next(iter(root.values()))[1] != "xl/workbook.xml"
            ):
                raise ValueError("Workbook root relationship is invalid")
            sheet, system, shared_path = _workbook(
                archive, relationships, timer, origin
            )
            if sheet_members != {sheet} or (
                declared_sheets and declared_sheets != {sheet}
            ):
                raise ValueError("Workbook has extra or missing worksheet parts")
            strings = _shared_strings(archive, shared_path, timer, origin)
            outcome = _worksheet(archive, sheet, strings, system, timer, origin)
            _check_time(timer, origin)
            return {
                "protocol": PROTOCOL,
                "sheet_count": 1,
                "date_system": system,
                **outcome,
            }
    except (BadZipFile, LargeZipFile, EOFError, RuntimeError) as error:
        raise ValueError("Workbook ZIP is invalid") from error
