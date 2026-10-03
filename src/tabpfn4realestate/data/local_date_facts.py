"""US facts whose first publication is known only to a source-local date."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

from tabpfn4realestate.data.schema import (
    _decimal,
    _identifier,
    _instant,
    _missing_state,
    _utc,
)
from tabpfn4realestate.evaluation.local_dates import (
    DateOnlyAvailability,
    availability_cutoff_utc,
    source_local_day_start_utc,
)


@dataclass(frozen=True)
class DateOnlyEvent:
    """An event date with no evidenced time of day."""

    value: date
    zone_key: str

    def __post_init__(self) -> None:
        if type(self.value) is not date:
            raise ValueError("Event must retain source-local date precision")
        source_local_day_start_utc(self.value, self.zone_key)


def event_day_end_utc(event: DateOnlyEvent) -> datetime:
    if not isinstance(event, DateOnlyEvent):
        raise ValueError("Expected a source-local date event")
    try:
        following = event.value + timedelta(days=1)
    except OverflowError as error:
        raise ValueError("Event date is outside supported calendar range") from error
    return source_local_day_start_utc(following, event.zone_key)


def _date_publication(value: DateOnlyAvailability, name: str) -> None:
    if not isinstance(value, DateOnlyAvailability):
        raise ValueError(f"{name} must retain source-local publication date")
    availability_cutoff_utc(value)


def _validity(
    observed_at: datetime,
    valid_from: datetime | None,
    valid_to: datetime | None,
    valid_to_available_at: datetime | DateOnlyAvailability | None,
) -> None:
    if valid_from is not None:
        _instant(valid_from, "valid_from")
    if valid_to is None:
        if valid_to_available_at is not None:
            raise ValueError("valid_to_available_at requires valid_to")
        return
    _instant(valid_to, "valid_to")
    if valid_to_available_at is None:
        raise ValueError("valid_to requires valid_to_available_at")
    if isinstance(valid_to_available_at, datetime):
        _instant(valid_to_available_at, "valid_to_available_at")
    else:
        _date_publication(valid_to_available_at, "valid_to_available_at")
    if _utc(valid_to) <= _utc(valid_from or observed_at):
        raise ValueError("valid_to must follow the effective start")


@dataclass(frozen=True)
class DatePublishedProperty:
    property_id: str
    country: str
    property_type: str
    source_id: str
    observed_at: datetime
    available_at: DateOnlyAvailability
    living_area: Decimal | None = None
    living_area_unit: str | None = None
    living_area_state: str | None = None
    latitude: Decimal | None = None
    longitude: Decimal | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    valid_to_available_at: datetime | DateOnlyAvailability | None = None

    def __post_init__(self) -> None:
        for name in ("property_id", "property_type", "source_id"):
            _identifier(getattr(self, name), name)
        if self.country != "US":
            raise ValueError("Date-published property contract supports US only")
        _instant(self.observed_at, "observed_at")
        _date_publication(self.available_at, "available_at")
        _validity(
            self.observed_at,
            self.valid_from,
            self.valid_to,
            self.valid_to_available_at,
        )
        _missing_state(self.living_area, self.living_area_state, "living_area")
        if self.living_area is None:
            if self.living_area_unit is not None:
                raise ValueError("living_area_unit requires living_area")
        else:
            _decimal(self.living_area, "living_area")
            if self.living_area_unit not in {"sqft", "sqm"}:
                raise ValueError("living_area_unit must be sqft or sqm")
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("latitude and longitude must be supplied together")
        for name, value, limit in (
            ("latitude", self.latitude, Decimal("90")),
            ("longitude", self.longitude, Decimal("180")),
        ):
            if value is not None and (
                not isinstance(value, Decimal)
                or not value.is_finite()
                or abs(value) > limit
            ):
                raise ValueError(f"{name} must be a finite decimal within range")


@dataclass(frozen=True)
class DatePublishedAttribute:
    property_id: str
    name: str
    value: str | int | Decimal | None
    observed_at: datetime
    available_at: DateOnlyAvailability
    source_id: str
    unit: str | None = None
    missing_state: str | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    valid_to_available_at: datetime | DateOnlyAvailability | None = None

    def __post_init__(self) -> None:
        for name in ("property_id", "name", "source_id"):
            _identifier(getattr(self, name), name)
        _instant(self.observed_at, "observed_at")
        _date_publication(self.available_at, "available_at")
        _validity(
            self.observed_at,
            self.valid_from,
            self.valid_to,
            self.valid_to_available_at,
        )
        if type(self.value) not in {str, int, Decimal, type(None)}:
            raise ValueError("attribute value must be a scalar")
        if isinstance(self.value, Decimal) and not self.value.is_finite():
            raise ValueError("attribute value must be finite")
        _missing_state(self.value, self.missing_state, "attribute value")
