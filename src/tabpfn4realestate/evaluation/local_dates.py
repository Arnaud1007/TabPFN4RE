"""Conservative source-local calendar origins for date-only sale records.

This policy is independent of the synthetic exact-UTC-duration protocol. A
source adapter must separately prove that its dates mean closing and first
availability before this helper can support a certified historical split.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from functools import lru_cache
from hashlib import sha256
from importlib.resources import files
import json
from zoneinfo import ZoneInfo

import tzdata


PROTOCOL_ID = "us_local_date_90d_v1"
TZDATA_VERSION = "2026.4"
HORIZON_DAYS = 90


@dataclass(frozen=True)
class LocalDateOrigin:
    """One row's source-local valuation date and exclusive UTC cutoff."""

    close_date: date
    zone_key: str
    origin_date: date = field(init=False)
    cutoff_exclusive_utc: datetime = field(init=False)
    protocol_id: str = field(init=False)
    policy_hash: str = field(init=False)

    def __post_init__(self) -> None:
        if type(self.close_date) is not date:
            raise ValueError("close_date must be a source-local date")
        zone = _zone_from_pinned_data(self.zone_key)
        try:
            origin_date = self.close_date - timedelta(days=HORIZON_DAYS)
            next_date = origin_date + timedelta(days=1)
        except OverflowError as exc:
            raise ValueError("close_date is outside supported calendar range") from exc
        _first_midnight_utc(origin_date, zone)
        cutoff = _first_midnight_utc(next_date, zone)
        payload = {
            "calendar_rule": "source_local_close_minus_90_dates_end_of_origin_inclusive",
            "close_date": self.close_date.isoformat(),
            "origin_date": origin_date.isoformat(),
            "zone_key": self.zone_key,
            "cutoff_exclusive_utc": cutoff.isoformat(),
            "protocol_id": PROTOCOL_ID,
            "tzdata_version": TZDATA_VERSION,
        }
        policy_hash = sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        object.__setattr__(self, "origin_date", origin_date)
        object.__setattr__(self, "cutoff_exclusive_utc", cutoff)
        object.__setattr__(self, "protocol_id", PROTOCOL_ID)
        object.__setattr__(self, "policy_hash", policy_hash)


@dataclass(frozen=True)
class DateOnlyAvailability:
    """Publication known only to a date in a named source-local time zone."""

    value: date
    zone_key: str

    def __post_init__(self) -> None:
        if type(self.value) is not date:
            raise ValueError("Date-only availability must be a source-local date")
        _zone_from_pinned_data(self.zone_key)


def _zone_from_pinned_data(zone_key: str) -> ZoneInfo:
    if not isinstance(zone_key, str) or not zone_key or zone_key != zone_key.strip():
        raise ValueError("zone_key must be a nonempty IANA time-zone key")
    parts = zone_key.split("/")
    if any(
        part in {"", ".", ".."}
        or not part.isascii()
        or any(not (char.isalnum() or char in "._+-") for char in part)
        for part in parts
    ):
        raise ValueError("zone_key must be a normalized IANA time-zone key")
    if tzdata.__version__ != TZDATA_VERSION:
        raise RuntimeError("Installed tzdata differs from the frozen date policy")
    return _load_pinned_zone(zone_key)


@lru_cache(maxsize=64)
def _load_pinned_zone(zone_key: str) -> ZoneInfo:
    """Reuse immutable pinned zones after each caller validates key and version."""
    resource = files("tzdata.zoneinfo").joinpath(*zone_key.split("/"))
    if not resource.is_file():
        raise ValueError(f"Unknown IANA time zone: {zone_key}")
    with resource.open("rb") as stream:
        return ZoneInfo.from_file(stream, key=zone_key)


def _first_midnight_utc(day: date, zone: ZoneInfo) -> datetime:
    """Choose the first repeated midnight; reject a skipped midnight/date."""
    candidates: set[datetime] = set()
    for fold in (0, 1):
        local = datetime.combine(day, time.min, tzinfo=zone).replace(fold=fold)
        candidate = local.astimezone(timezone.utc)
        round_trip = candidate.astimezone(zone)
        if round_trip.date() == day and round_trip.time() == time.min:
            candidates.add(candidate)
    if not candidates:
        raise ValueError(f"Source-local midnight does not exist on {day}")
    return min(candidates)


def derive_local_date_origin(close_date: date, zone_key: str) -> LocalDateOrigin:
    """Place an origin 90 calendar dates before close, at that day's end.

    Exact instants at the next day's first midnight are excluded. This fail-closed
    version rejects days whose midnight does not exist, pending a source policy
    that explicitly resolves those rare dates.
    """
    return LocalDateOrigin(close_date, zone_key)


def source_local_day_start_utc(day: date, zone_key: str) -> datetime:
    """Return the pinned-zone first midnight as one comparable UTC instant."""
    if type(day) is not date:
        raise ValueError("day must be a source-local date")
    return _first_midnight_utc(day, _zone_from_pinned_data(zone_key))


def availability_cutoff_utc(available_at: datetime | DateOnlyAvailability) -> datetime:
    """Place a date-only publication conservatively at that local day's end."""
    if isinstance(available_at, datetime):
        if available_at.tzinfo is None or available_at.utcoffset() is None:
            raise ValueError("Timestamp availability must include a UTC offset")
        return available_at.astimezone(timezone.utc)
    if isinstance(available_at, DateOnlyAvailability):
        try:
            following_date = available_at.value + timedelta(days=1)
        except OverflowError as exc:
            raise ValueError("Availability date is outside supported range") from exc
        _first_midnight_utc(
            available_at.value, _zone_from_pinned_data(available_at.zone_key)
        )
        return source_local_day_start_utc(following_date, available_at.zone_key)
    raise ValueError("Availability must be a dated source fact or aware datetime")


def is_visible_at_date_origin(
    available_at: datetime | DateOnlyAvailability, origin: LocalDateOrigin
) -> bool:
    """Use source-local dates as dates and exact timestamps as UTC instants.

    Date-only availability is conservatively placed at the end of its own
    source-local date, which may be in a different time zone from the origin.
    """
    if not isinstance(origin, LocalDateOrigin):
        raise ValueError("origin must be a LocalDateOrigin")
    if isinstance(available_at, datetime):
        if available_at.tzinfo is None or available_at.utcoffset() is None:
            raise ValueError("Timestamp availability must include a UTC offset")
        return available_at.astimezone(timezone.utc) < origin.cutoff_exclusive_utc
    if isinstance(available_at, DateOnlyAvailability):
        zone = _zone_from_pinned_data(available_at.zone_key)
        _first_midnight_utc(available_at.value, zone)
        try:
            following_date = available_at.value + timedelta(days=1)
        except OverflowError as exc:
            raise ValueError("Availability date is outside supported range") from exc
        available_by = _first_midnight_utc(following_date, zone)
        return available_by <= origin.cutoff_exclusive_utc
    raise ValueError("Availability must be a dated source fact or aware datetime")
