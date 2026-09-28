"""Small immutable US source contract for synthetic U1 verification."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Sequence


def _identifier(value: str, name: str) -> None:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{name} must be a nonempty canonical string")


def _instant(value: datetime, name: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"{name} must be a timezone-aware datetime")
    if value.utcoffset() is None:
        raise ValueError(f"{name} must have a defined UTC offset")


def _utc(value: datetime) -> datetime:
    """Compare instants in UTC so a repeated local hour retains its fold."""
    return value.astimezone(timezone.utc)


def _matches_utc_horizon(origin: datetime, close: datetime, days: int) -> bool:
    """Check the synthetic exact-time horizon in UTC, independent of input zone."""
    _instant(origin, "origin")
    _instant(close, "close")
    return _utc(origin) + timedelta(days=days) == _utc(close)


def _decimal(value: Decimal, name: str) -> None:
    if not isinstance(value, Decimal) or not value.is_finite() or value <= 0:
        raise ValueError(f"{name} must be a positive finite Decimal")


_MISSING_STATES = {"unknown", "structurally_absent", "not_applicable"}


def _missing_state(value: object, state: str | None, name: str) -> None:
    if value is None and state not in _MISSING_STATES:
        raise ValueError(f"{name} requires an explicit missing state")
    if value is not None and state is not None:
        raise ValueError(f"{name} cannot have a missing state with a value")


@dataclass(frozen=True)
class Property:
    property_id: str
    country: str
    property_type: str
    source_id: str
    observed_at: datetime
    available_at: datetime
    living_area: Decimal | None = None
    living_area_unit: str | None = None
    living_area_state: str | None = None
    latitude: Decimal | None = None
    longitude: Decimal | None = None

    def __post_init__(self) -> None:
        for name in ("property_id", "property_type", "source_id"):
            _identifier(getattr(self, name), name)
        if self.country != "US":
            raise ValueError("U1 property contract supports US only")
        _instant(self.observed_at, "observed_at")
        _instant(self.available_at, "available_at")
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
class Transaction:
    transaction_id: str
    economic_transfer_id: str
    property_id: str
    close_at: datetime
    available_at: datetime
    price: Decimal
    currency: str
    source_id: str
    scope: str
    consideration_type: str
    arm_length_status: str
    adjustment_flags: tuple[str, ...]

    def __post_init__(self) -> None:
        for name in (
            "transaction_id",
            "economic_transfer_id",
            "property_id",
            "source_id",
        ):
            _identifier(getattr(self, name), name)
        _instant(self.close_at, "close_at")
        _instant(self.available_at, "available_at")
        _decimal(self.price, "price")
        if self.currency != "USD":
            raise ValueError("US transaction currency must be USD")
        if self.scope not in {
            "single_property",
            "partial_interest",
            "multi_property",
            "unknown",
        }:
            raise ValueError("Unsupported transaction scope")
        if self.consideration_type not in {
            "gross_recorded_sale",
            "nominal",
            "other",
            "unknown",
        }:
            raise ValueError("Unsupported consideration type")
        if self.arm_length_status not in {"confirmed", "excluded", "unknown"}:
            raise ValueError("Unsupported arm-length status")
        if not isinstance(self.adjustment_flags, tuple):
            raise ValueError("adjustment_flags must be an immutable tuple")
        if len(set(self.adjustment_flags)) != len(self.adjustment_flags):
            raise ValueError("adjustment_flags must be unique")
        for flag in self.adjustment_flags:
            _identifier(flag, "adjustment flag")

    @property
    def eligible_prior_sale(self) -> bool:
        return (
            self.scope == "single_property"
            and self.consideration_type == "gross_recorded_sale"
            and self.arm_length_status == "confirmed"
            and not self.adjustment_flags
        )


@dataclass(frozen=True)
class Attribute:
    property_id: str
    name: str
    value: str | int | Decimal | None
    observed_at: datetime
    available_at: datetime
    source_id: str
    unit: str | None = None
    missing_state: str | None = None

    def __post_init__(self) -> None:
        for name in ("property_id", "name", "source_id"):
            _identifier(getattr(self, name), name)
        _instant(self.observed_at, "observed_at")
        _instant(self.available_at, "available_at")
        if type(self.value) not in {str, int, Decimal, type(None)}:
            raise ValueError("attribute value must be a scalar")
        if isinstance(self.value, Decimal) and not self.value.is_finite():
            raise ValueError("attribute value must be finite")
        _missing_state(self.value, self.missing_state, "attribute value")


@dataclass(frozen=True)
class ListingEvent:
    listing_id: str
    property_id: str
    event_type: str
    event_at: datetime
    available_at: datetime
    source_id: str
    amount: Decimal | None = None

    def __post_init__(self) -> None:
        for name in ("listing_id", "property_id", "event_type", "source_id"):
            _identifier(getattr(self, name), name)
        _instant(self.event_at, "event_at")
        _instant(self.available_at, "available_at")
        if self.amount is not None:
            _decimal(self.amount, "amount")


@dataclass(frozen=True)
class SourceSnapshot:
    snapshot_id: str
    source_ids: tuple[str, ...]
    as_of: datetime

    def __post_init__(self) -> None:
        _identifier(self.snapshot_id, "snapshot_id")
        _instant(self.as_of, "as_of")
        if not isinstance(self.source_ids, tuple) or not self.source_ids:
            raise ValueError("source_ids must be a nonempty tuple")
        if len(set(self.source_ids)) != len(self.source_ids):
            raise ValueError("source_ids must be unique")
        for source_id in self.source_ids:
            _identifier(source_id, "source_id")


def canonicalize_transactions(
    transactions: Sequence[Transaction],
) -> tuple[Transaction, ...]:
    """Collapse only explicit economic duplicates with identical label facts."""
    by_transfer: dict[str, Transaction] = {}
    by_transaction_id: dict[tuple[str, str], str] = {}
    for row in transactions:
        source_key = (row.source_id, row.transaction_id)
        earlier_transfer = by_transaction_id.get(source_key)
        if (
            earlier_transfer is not None
            and earlier_transfer != row.economic_transfer_id
        ):
            raise ValueError("Conflicting transaction_id across economic transfers")
        by_transaction_id[source_key] = row.economic_transfer_id
        earlier = by_transfer.get(row.economic_transfer_id)
        if earlier is None:
            by_transfer[row.economic_transfer_id] = row
            continue
        shared_facts = (
            "property_id",
            "price",
            "currency",
            "scope",
            "consideration_type",
            "arm_length_status",
            "adjustment_flags",
        )
        if _utc(earlier.close_at) != _utc(row.close_at) or any(
            getattr(earlier, name) != getattr(row, name) for name in shared_facts
        ):
            raise ValueError("Conflicting duplicate economic transfer; quarantine")
        if (_utc(row.available_at), row.source_id, row.transaction_id) < (
            _utc(earlier.available_at),
            earlier.source_id,
            earlier.transaction_id,
        ):
            by_transfer[row.economic_transfer_id] = row
    return tuple(by_transfer[key] for key in sorted(by_transfer))
