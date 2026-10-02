"""Freeze label-free calendar membership for a synthetic US evaluation plan."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from hashlib import sha256
import json
import re
from typing import Sequence

from tabpfn4realestate.data.schema import _identifier


PROTOCOL = "us_synthetic_calendar_schedule_v1"
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_QUARTER_START_MONTHS = frozenset((1, 4, 7, 10))


def _day(value: date, name: str) -> None:
    if type(value) is not date:
        raise ValueError(f"{name} must be a source-local calendar date")


def _month_start(value: date, name: str) -> None:
    _day(value, name)
    if value.day != 1:
        raise ValueError(f"{name} must start on the first of a month")


def _digest(value: str, name: str) -> None:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        raise ValueError(f"{name} must be a lowercase SHA-256 digest")


def _add_months(start: date, months: int) -> date:
    """Shift a first-of-month boundary by whole calendar months."""
    month_index = (start.year - 1) * 12 + start.month - 1 + months
    if month_index < 0:
        raise ValueError("Calendar schedule predates supported dates")
    year_offset, month_offset = divmod(month_index, 12)
    try:
        return date(year_offset + 1, month_offset + 1, 1)
    except ValueError as error:
        raise ValueError("Calendar schedule exceeds supported dates") from error


@dataclass(frozen=True)
class CalendarOriginRef:
    """A transfer identity and its declared source-local origin date."""

    row_id: str
    property_id: str
    origin_date: date

    def __post_init__(self) -> None:
        _identifier(self.row_id, "row_id")
        _identifier(self.property_id, "property_id")
        _day(self.origin_date, "origin_date")


@dataclass(frozen=True)
class DevelopmentWindow:
    start: date
    end: date
    row_ids: tuple[str, ...]
    training_candidate_ids: tuple[str, ...]


@dataclass(frozen=True)
class ReservedWindow:
    start: date
    end: date
    row_ids: tuple[str, ...]


@dataclass(frozen=True)
class CalendarSchedule:
    protocol_id: str
    source_snapshot_sha256: str
    origin_policy_sha256: str
    history_start: date
    pre_development_row_ids: tuple[str, ...]
    development: tuple[DevelopmentWindow, ...]
    calibration: ReservedWindow
    final_test: ReservedWindow
    schedule_hash: str


def _validate_boundaries(
    history_start: date,
    calibration_start: date,
    test_start: date,
    protocol_id: str,
) -> tuple[date, date]:
    if protocol_id != PROTOCOL:
        raise ValueError("Only the synthetic calendar schedule protocol is supported")
    for name, value in (
        ("history_start", history_start),
        ("calibration_start", calibration_start),
        ("test_start", test_start),
    ):
        _month_start(value, name)
    if calibration_start.month not in _QUARTER_START_MONTHS:
        raise ValueError("Calibration must begin at a calendar quarter boundary")
    if test_start <= calibration_start:
        raise ValueError("Calibration and test intervals must be disjoint")
    development_start = _add_months(calibration_start, -12)
    earliest_history = _add_months(development_start, -24)
    if history_start > earliest_history:
        raise ValueError("Declared history must span at least 24 calendar months")
    return development_start, _add_months(test_start, 12)


def _index_rows(
    rows: Sequence[CalendarOriginRef], history_start: date, test_end: date
) -> tuple[CalendarOriginRef, ...]:
    indexed: dict[str, CalendarOriginRef] = {}
    for row in rows:
        if not isinstance(row, CalendarOriginRef):
            raise ValueError("Calendar origins must be CalendarOriginRef records")
        if row.row_id in indexed:
            raise ValueError("Calendar origin row IDs contain a duplicate")
        if not history_start <= row.origin_date < test_end:
            raise ValueError("Calendar origin lies outside the declared schedule")
        indexed[row.row_id] = row
    if not indexed:
        raise ValueError("Calendar schedule has empty origin metadata")
    return tuple(
        sorted(indexed.values(), key=lambda row: (row.origin_date, row.row_id))
    )


def _ids_between(
    rows: tuple[CalendarOriginRef, ...], start: date, end: date
) -> tuple[str, ...]:
    return tuple(row.row_id for row in rows if start <= row.origin_date < end)


def _schedule_hash(
    result: CalendarSchedule, rows: tuple[CalendarOriginRef, ...]
) -> str:
    payload = {
        "protocol_id": result.protocol_id,
        "source_snapshot_sha256": result.source_snapshot_sha256,
        "origin_policy_sha256": result.origin_policy_sha256,
        "history_start": result.history_start.isoformat(),
        "rows": [
            (row.row_id, row.property_id, row.origin_date.isoformat()) for row in rows
        ],
        "pre_development_row_ids": result.pre_development_row_ids,
        "development": [
            (
                window.start.isoformat(),
                window.end.isoformat(),
                window.row_ids,
                window.training_candidate_ids,
            )
            for window in result.development
        ],
        "calibration": (
            result.calibration.start.isoformat(),
            result.calibration.end.isoformat(),
            result.calibration.row_ids,
        ),
        "final_test": (
            result.final_test.start.isoformat(),
            result.final_test.end.isoformat(),
            result.final_test.row_ids,
        ),
    }
    return sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def build_calendar_schedule(
    rows: Sequence[CalendarOriginRef],
    *,
    history_start: date,
    calibration_start: date,
    test_start: date,
    source_snapshot_sha256: str,
    origin_policy_sha256: str,
    protocol_id: str = PROTOCOL,
) -> CalendarSchedule:
    """Freeze synthetic windows without opening any label or maturity value."""
    _digest(source_snapshot_sha256, "source_snapshot_sha256")
    _digest(origin_policy_sha256, "origin_policy_sha256")
    development_start, test_end = _validate_boundaries(
        history_start, calibration_start, test_start, protocol_id
    )
    indexed = _index_rows(rows, history_start, test_end)
    pre_development = _ids_between(indexed, history_start, development_start)
    if not pre_development:
        raise ValueError("Calendar schedule has empty pre-development history")
    quarters: list[DevelopmentWindow] = []
    for quarter in range(4):
        start = _add_months(development_start, quarter * 3)
        end = _add_months(start, 3)
        validation_ids = _ids_between(indexed, start, end)
        if not validation_ids:
            raise ValueError("Calendar schedule has an empty development window")
        candidates = tuple(row.row_id for row in indexed if row.origin_date < start)
        quarters.append(DevelopmentWindow(start, end, validation_ids, candidates))
    calibration_ids = _ids_between(indexed, calibration_start, test_start)
    test_ids = _ids_between(indexed, test_start, test_end)
    if not calibration_ids or not test_ids:
        raise ValueError("Calendar schedule has an empty calibration or test window")
    result = CalendarSchedule(
        protocol_id=protocol_id,
        source_snapshot_sha256=source_snapshot_sha256,
        origin_policy_sha256=origin_policy_sha256,
        history_start=history_start,
        pre_development_row_ids=pre_development,
        development=tuple(quarters),
        calibration=ReservedWindow(calibration_start, test_start, calibration_ids),
        final_test=ReservedWindow(test_start, test_end, test_ids),
        schedule_hash="",
    )
    return replace(result, schedule_hash=_schedule_hash(result, indexed))
