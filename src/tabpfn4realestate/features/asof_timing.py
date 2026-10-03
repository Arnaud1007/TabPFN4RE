"""Typed time comparisons for exact and source-local OFF feature protocols."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from tabpfn4realestate.data.local_date_facts import DateOnlyEvent, event_day_end_utc
from tabpfn4realestate.data.schema import (
    Attribute,
    Property,
    SourceSnapshot,
    _utc,
)
from tabpfn4realestate.evaluation.local_dates import (
    DateOnlyAvailability,
    LocalDateOrigin,
    availability_cutoff_utc,
)


SourceTime = datetime | DateOnlyAvailability | DateOnlyEvent


@dataclass(frozen=True)
class _ReconciledProperty:
    """Exact property facts with a typed date-only end disclosure."""

    property_id: str
    country: str
    property_type: str
    source_id: str
    observed_at: datetime
    available_at: datetime
    living_area: Decimal | None
    living_area_unit: str | None
    living_area_state: str | None
    latitude: Decimal | None
    longitude: Decimal | None
    valid_from: datetime | None
    valid_to: datetime | None
    valid_to_available_at: DateOnlyAvailability | None

    @classmethod
    def from_exact(
        cls, row: Property, end: datetime, disclosure: DateOnlyAvailability
    ) -> _ReconciledProperty:
        return cls(
            row.property_id,
            row.country,
            row.property_type,
            row.source_id,
            row.observed_at,
            row.available_at,
            row.living_area,
            row.living_area_unit,
            row.living_area_state,
            row.latitude,
            row.longitude,
            row.valid_from,
            end,
            disclosure,
        )


@dataclass(frozen=True)
class _ReconciledAttribute:
    """Exact attribute facts with a typed date-only end disclosure."""

    property_id: str
    name: str
    value: str | int | Decimal | None
    observed_at: datetime
    available_at: datetime
    source_id: str
    unit: str | None
    missing_state: str | None
    valid_from: datetime | None
    valid_to: datetime | None
    valid_to_available_at: DateOnlyAvailability | None

    @classmethod
    def from_exact(
        cls, row: Attribute, end: datetime, disclosure: DateOnlyAvailability
    ) -> _ReconciledAttribute:
        return cls(
            row.property_id,
            row.name,
            row.value,
            row.observed_at,
            row.available_at,
            row.source_id,
            row.unit,
            row.missing_state,
            row.valid_from,
            end,
            disclosure,
        )


def time_cutoff_utc(value: SourceTime) -> datetime:
    """Use a date's conservative completed-day boundary for comparisons."""
    if isinstance(value, DateOnlyAvailability):
        return availability_cutoff_utc(value)
    if isinstance(value, DateOnlyEvent):
        return event_day_end_utc(value)
    if isinstance(value, datetime):
        return _utc(value)
    raise ValueError("Unsupported source time")


def typed_time_identity(value: SourceTime) -> dict[str, str]:
    if isinstance(value, (DateOnlyAvailability, DateOnlyEvent)):
        return {
            "kind": "local_date",
            "date": value.value.isoformat(),
            "zone": value.zone_key,
        }
    if isinstance(value, datetime):
        return {"kind": "timestamp", "utc": _utc(value).isoformat()}
    raise ValueError("Unsupported source time")


def time_sort_text(value: SourceTime) -> str:
    """Preserve the legacy exact-time tie break and make date ties stable."""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (DateOnlyAvailability, DateOnlyEvent)):
        return f"{value.value.isoformat()}|{value.zone_key}"
    raise ValueError("Unsupported source time")


@dataclass(frozen=True)
class _Boundary:
    effective_utc: datetime
    effective_exclusive: bool
    known_utc: datetime
    known_exclusive: bool
    allow_date_only: bool = False

    def effective_by(self, value: datetime) -> bool:
        instant = _utc(value)
        return (
            instant < self.effective_utc
            if self.effective_exclusive
            else instant <= self.effective_utc
        )

    def known_by(self, value: SourceTime) -> bool:
        if isinstance(value, (DateOnlyAvailability, DateOnlyEvent)):
            if not self.allow_date_only:
                raise ValueError("Exact protocol rejects date-only facts")
            return time_cutoff_utc(value) <= self.known_utc
        instant = time_cutoff_utc(value)
        return (
            instant < self.known_utc
            if self.known_exclusive
            else instant <= self.known_utc
        )

    def valid_through(self, end: datetime) -> bool:
        instant = _utc(end)
        return (
            self.effective_utc <= instant
            if self.effective_exclusive
            else self.effective_utc < instant
        )


def _exact_boundary(
    origin: datetime, source_snapshot: SourceSnapshot, known_at: datetime | None = None
) -> _Boundary:
    effective = _utc(origin)
    known = min(_utc(known_at or origin), _utc(source_snapshot.as_of))
    return _Boundary(effective, False, known, False)


def _local_boundary(
    origin: LocalDateOrigin, source_snapshot: SourceSnapshot, *, allow_date_only=False
) -> _Boundary:
    exclusive = origin.cutoff_exclusive_utc
    source_cap = _utc(source_snapshot.as_of)
    if source_cap < exclusive:
        return _Boundary(exclusive, True, source_cap, False, allow_date_only)
    return _Boundary(exclusive, True, exclusive, True, allow_date_only)
