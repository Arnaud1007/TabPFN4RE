"""Bind synthetic calendar membership to source-local label maturity.

This checks training-side timing only. It does not qualify a source, open
reserved outcomes, or declare a real US evaluation protocol.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
import json
from typing import Mapping, Sequence

from tabpfn4realestate.data.schema import _identifier, _instant
from tabpfn4realestate.evaluation.calendar_schedule import (
    CalendarOriginRef,
    CalendarSchedule,
    build_calendar_schedule,
)
from tabpfn4realestate.evaluation.local_dates import (
    DateOnlyAvailability,
    TZDATA_VERSION,
    availability_cutoff_utc,
    derive_local_date_origin,
    source_local_day_start_utc,
)


PROTOCOL_ID = "us_synthetic_chronological_plan_v1"


def _hash(payload: object) -> str:
    return sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _index_origins(
    origins: Sequence[CalendarOriginRef], zones: Mapping[str, str]
) -> tuple[CalendarOriginRef, ...]:
    if not isinstance(zones, Mapping):
        raise ValueError("origin_zones must map each row ID to a source-local zone")
    indexed: dict[str, CalendarOriginRef] = {}
    for row in origins:
        if not isinstance(row, CalendarOriginRef) or row.row_id in indexed:
            raise ValueError("Calendar origins must have unique row IDs")
        indexed[row.row_id] = row
    if not indexed or set(zones) != set(indexed):
        raise ValueError("Every origin needs exactly one source-local zone")
    return tuple(
        sorted(indexed.values(), key=lambda row: (row.origin_date, row.row_id))
    )


def _policy_rows(
    origins: Sequence[CalendarOriginRef], zones: Mapping[str, str]
) -> tuple[tuple[str, str, str, str, str], ...]:
    result = []
    for row in _index_origins(origins, zones):
        try:
            close_date = row.origin_date + timedelta(days=90)
        except OverflowError as error:
            raise ValueError("Origin is outside supported calendar range") from error
        policy = derive_local_date_origin(close_date, zones[row.row_id])
        result.append(
            (
                row.row_id,
                row.property_id,
                row.origin_date.isoformat(),
                policy.zone_key,
                policy.policy_hash,
            )
        )
    return tuple(result)


def origin_policy_hash(
    origins: Sequence[CalendarOriginRef], zones: Mapping[str, str]
) -> str:
    """Bind each declared origin to its pinned source-local calendar policy."""
    return _hash({"tzdata": TZDATA_VERSION, "rows": _policy_rows(origins, zones)})


@dataclass(frozen=True)
class ChronologicalMaturityRef:
    """Training-side close and publication metadata, without sale price."""

    row_id: str
    close_date: date
    available_at: datetime | DateOnlyAvailability

    def __post_init__(self) -> None:
        _identifier(self.row_id, "row_id")
        if type(self.close_date) is not date:
            raise ValueError("close_date must be a source-local date")
        availability_cutoff_utc(self.available_at)


@dataclass(frozen=True)
class BoundDevelopmentWindow:
    fit_cutoff_utc: datetime
    validation_row_ids: tuple[str, ...]
    train_row_ids: tuple[str, ...]
    immature_row_ids: tuple[str, ...]


@dataclass(frozen=True)
class FrozenFinalFit:
    fit_cutoff_utc: datetime
    train_row_ids: tuple[str, ...]
    immature_row_ids: tuple[str, ...]


@dataclass(frozen=True)
class ChronologicalPlan:
    protocol_id: str
    schedule: CalendarSchedule
    development: tuple[BoundDevelopmentWindow, ...]
    final_fit: FrozenFinalFit
    plan_hash: str


def _verified_schedule(
    schedule: CalendarSchedule,
    origins: tuple[CalendarOriginRef, ...],
    zones: Mapping[str, str],
) -> None:
    if not isinstance(schedule, CalendarSchedule):
        raise ValueError("A frozen calendar schedule is required")
    if schedule.origin_policy_sha256 != origin_policy_hash(origins, zones):
        raise ValueError("Schedule origin policy does not match source-local zones")
    rebuilt = build_calendar_schedule(
        origins,
        history_start=schedule.history_start,
        calibration_start=schedule.calibration.start,
        test_start=schedule.final_test.start,
        source_snapshot_sha256=schedule.source_snapshot_sha256,
        origin_policy_sha256=schedule.origin_policy_sha256,
        protocol_id=schedule.protocol_id,
    )
    if rebuilt != schedule:
        raise ValueError("Calendar schedule membership or hash was changed")


def _training_maturity(
    schedule: CalendarSchedule,
    origins: tuple[CalendarOriginRef, ...],
    zones: Mapping[str, str],
    maturity: Sequence[ChronologicalMaturityRef],
) -> dict[str, ChronologicalMaturityRef]:
    candidates = {
        row.row_id: row
        for row in origins
        if row.origin_date < schedule.calibration.start
    }
    indexed: dict[str, ChronologicalMaturityRef] = {}
    for label in maturity:
        if not isinstance(label, ChronologicalMaturityRef) or label.row_id in indexed:
            raise ValueError("Training maturity records must be unique")
        row = candidates.get(label.row_id)
        if row is None:
            raise ValueError("Maturity supplied for a reserved or unknown row")
        origin = derive_local_date_origin(label.close_date, zones[label.row_id])
        if origin.origin_date != row.origin_date:
            raise ValueError("Sale close date does not match the local 90-day origin")
        try:
            next_close_day = label.close_date + timedelta(days=1)
        except OverflowError as error:
            raise ValueError(
                "Close date is outside supported calendar range"
            ) from error
        close_day_end = source_local_day_start_utc(next_close_day, zones[label.row_id])
        if availability_cutoff_utc(label.available_at) < close_day_end:
            raise ValueError(
                "A sale label cannot be available before its close date ended"
            )
        indexed[label.row_id] = label
    if set(indexed) != set(candidates):
        raise ValueError(
            "Every pre-calibration origin needs training maturity metadata"
        )
    return indexed


def _fit_cutoffs(
    schedule: CalendarSchedule,
    zones: Mapping[str, str],
    cutoffs: Sequence[datetime],
) -> tuple[datetime, ...]:
    if len(cutoffs) != 5:
        raise ValueError("Four development and one final UTC fit cutoff are required")
    starts = (
        *(window.start for window in schedule.development),
        schedule.calibration.start,
    )
    verified = []
    for cutoff, start in zip(cutoffs, starts, strict=True):
        _instant(cutoff, "fit_cutoff_utc")
        if cutoff.utcoffset() != timedelta(0):
            raise ValueError("fit_cutoff_utc must use a zero UTC offset")
        normalized = cutoff.astimezone(timezone.utc)
        if any(
            normalized > source_local_day_start_utc(start, zone)
            for zone in set(zones.values())
        ):
            raise ValueError(
                "A fit cutoff occurs after a source-local validation start"
            )
        verified.append(normalized)
    if any(left >= right for left, right in zip(verified, verified[1:], strict=False)):
        raise ValueError("Fit cutoffs must be strictly increasing")
    return tuple(verified)


def _partition(
    candidates: Sequence[str],
    maturity: Mapping[str, ChronologicalMaturityRef],
    cutoff: datetime,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    train = tuple(
        row_id
        for row_id in candidates
        if availability_cutoff_utc(maturity[row_id].available_at) <= cutoff
    )
    if not train:
        raise ValueError("Fit interval has no matured training labels")
    train_ids = set(train)
    immature = tuple(row_id for row_id in candidates if row_id not in train_ids)
    return train, immature


def _maturity_payload(
    maturity: Mapping[str, ChronologicalMaturityRef],
) -> list[tuple[str, str, str, str | None]]:
    result = []
    for row_id in sorted(maturity):
        label = maturity[row_id]
        available = label.available_at
        if isinstance(available, DateOnlyAvailability):
            result.append(
                (
                    row_id,
                    label.close_date.isoformat(),
                    available.value.isoformat(),
                    available.zone_key,
                )
            )
        else:
            result.append(
                (
                    row_id,
                    label.close_date.isoformat(),
                    availability_cutoff_utc(available).isoformat(),
                    None,
                )
            )
    return result


def build_chronological_plan(
    schedule: CalendarSchedule,
    origins: Sequence[CalendarOriginRef],
    origin_zones: Mapping[str, str],
    training_maturity: Sequence[ChronologicalMaturityRef],
    *,
    fit_cutoffs_utc: Sequence[datetime],
) -> ChronologicalPlan:
    """Freeze four training folds and the pre-calibration final fit set."""
    ordered = _index_origins(origins, origin_zones)
    _verified_schedule(schedule, ordered, origin_zones)
    maturity = _training_maturity(schedule, ordered, origin_zones, training_maturity)
    cutoffs = _fit_cutoffs(schedule, origin_zones, fit_cutoffs_utc)
    development = []
    for window, cutoff in zip(schedule.development, cutoffs[:4], strict=True):
        train, immature = _partition(window.training_candidate_ids, maturity, cutoff)
        development.append(
            BoundDevelopmentWindow(cutoff, window.row_ids, train, immature)
        )
    final_candidates = tuple(
        row.row_id for row in ordered if row.origin_date < schedule.calibration.start
    )
    final_train, final_immature = _partition(final_candidates, maturity, cutoffs[4])
    final_fit = FrozenFinalFit(cutoffs[4], final_train, final_immature)
    payload = {
        "protocol_id": PROTOCOL_ID,
        "schedule_hash": schedule.schedule_hash,
        "source_snapshot_sha256": schedule.source_snapshot_sha256,
        "origin_policy_sha256": schedule.origin_policy_sha256,
        "tzdata_version": TZDATA_VERSION,
        "cutoffs_utc": [value.isoformat() for value in cutoffs],
        "training_maturity": _maturity_payload(maturity),
        "development": [
            (fold.validation_row_ids, fold.train_row_ids, fold.immature_row_ids)
            for fold in development
        ],
        "final_fit": (final_fit.train_row_ids, final_fit.immature_row_ids),
    }
    return ChronologicalPlan(
        PROTOCOL_ID, schedule, tuple(development), final_fit, _hash(payload)
    )
