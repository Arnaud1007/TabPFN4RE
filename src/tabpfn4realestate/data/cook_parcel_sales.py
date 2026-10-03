"""Lossless Cook parcel-sale source observations, without sale-label promotion."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
import math
import re
from typing import Mapping


SELECT_FIELDS = (
    "row_id",
    "pin",
    "year",
    "township_code",
    "nbhd",
    "class",
    "sale_date",
    "is_mydec_date",
    "sale_price",
    "doc_no",
    "deed_type",
    "mydec_deed_type",
    "is_multisale",
    "num_parcels_sale",
    "sale_type",
    "sale_filter_same_sale_within_365",
    "sale_filter_less_than_10k",
    "sale_filter_deed_type",
)
_FIELD_SET = frozenset(SELECT_FIELDS)
_HEX64 = re.compile(r"[0-9a-f]{64}\Z")
_PIN = re.compile(r"[0-9]{14}\Z")
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?)?\Z")
_RECORD_FIELDS = frozenset(
    {
        "raw_fields",
        "row_id",
        "pin_state",
        "pin",
        "price_state",
        "price",
        "recorded_date_state",
        "recorded_date",
        "capture_sha256",
        "response_sha256",
        "row_sha256",
        "observed_at",
        "currency",
        "source_audit_only",
    }
)

type_raw_scalar = str | int | float | bool | None


def _encoded(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _sha256(value: object) -> str:
    return sha256(_encoded(value)).hexdigest()


def _validate_scalar(value: object) -> None:
    if type(value) not in {str, int, float, bool, type(None)}:
        raise ValueError("Source row contains a non-scalar or unsupported value")
    if type(value) is float and not math.isfinite(value):
        raise ValueError("Source row contains a nonfinite value")


def _value(raw: Mapping[str, type_raw_scalar], field: str) -> tuple[str, object]:
    if field not in raw:
        return "missing", None
    if raw[field] is None:
        return "null", None
    return "present", raw[field]


def _pin(raw: Mapping[str, type_raw_scalar]) -> tuple[str, str | None]:
    state, value = _value(raw, "pin")
    if state != "present":
        return state, None
    if type(value) is str and _PIN.fullmatch(value):
        return "valid", value
    return "malformed", None


def _price(raw: Mapping[str, type_raw_scalar]) -> tuple[str, Decimal | None]:
    state, value = _value(raw, "sale_price")
    if state != "present":
        return state, None
    if type(value) is not str:
        return "malformed", None
    try:
        parsed = Decimal(value)
    except InvalidOperation:
        return "malformed", None
    if not parsed.is_finite():
        return "malformed", None
    return ("positive" if parsed > 0 else "nonpositive"), parsed


def _recorded_date(raw: Mapping[str, type_raw_scalar]) -> tuple[str, date | None]:
    state, value = _value(raw, "sale_date")
    if state != "present":
        return state, None
    if type(value) is not str or not _DATE.fullmatch(value):
        return "malformed", None
    try:
        parsed = (
            date.fromisoformat(value)
            if len(value) == 10
            else datetime.fromisoformat(value.replace("Z", "+00:00")).date()
        )
    except ValueError:
        return "malformed", None
    return "valid", parsed


def _validate_hash(value: str, name: str) -> None:
    if type(value) is not str or not _HEX64.fullmatch(value):
        raise ValueError(f"{name} must be a lowercase SHA-256 digest")


def _validate_utc(value: datetime) -> None:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
        or value.utcoffset().total_seconds() != 0
    ):
        raise ValueError("Observation time must be a timezone-aware UTC datetime")


@dataclass(frozen=True)
class CookParcelSaleObservation:
    """One published source row. It is not one dwelling or economic transfer."""

    raw_fields: tuple[tuple[str, type_raw_scalar], ...]
    row_id: str
    pin_state: str
    pin: str | None
    price_state: str
    price: Decimal | None
    recorded_date_state: str
    recorded_date: date | None
    capture_sha256: str
    response_sha256: str
    row_sha256: str
    observed_at: datetime
    currency: str = "USD"
    source_audit_only: bool = True

    def __post_init__(self) -> None:
        if self.currency != "USD" or self.source_audit_only is not True:
            raise ValueError("Cook source observation must remain USD and audit-only")

    def to_record(self) -> dict[str, object]:
        """Return a fresh JSON-safe source record with no certified label fields."""
        return {
            "raw_fields": dict(self.raw_fields),
            "row_id": self.row_id,
            "pin_state": self.pin_state,
            "pin": self.pin,
            "price_state": self.price_state,
            "price": str(self.price) if self.price is not None else None,
            "recorded_date_state": self.recorded_date_state,
            "recorded_date": self.recorded_date.isoformat()
            if self.recorded_date is not None
            else None,
            "capture_sha256": self.capture_sha256,
            "response_sha256": self.response_sha256,
            "row_sha256": self.row_sha256,
            "observed_at": self.observed_at.astimezone(timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            "currency": self.currency,
            "source_audit_only": self.source_audit_only,
        }

    @classmethod
    def from_record(cls, record: Mapping[str, object]) -> CookParcelSaleObservation:
        """Reparse raw fields and reject changed lineage or derived values."""
        if not isinstance(record, Mapping) or set(record) != _RECORD_FIELDS:
            raise ValueError("Source observation record has invalid fields")
        raw = record["raw_fields"]
        instant = record["observed_at"]
        if not isinstance(raw, dict) or type(instant) is not str:
            raise ValueError("Source observation record has invalid values")
        try:
            observed_at = datetime.fromisoformat(instant.replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError("Source observation time is malformed") from error
        parsed = parse_cook_row(
            raw,
            capture_sha256=record["capture_sha256"],
            response_sha256=record["response_sha256"],
            row_sha256=record["row_sha256"],
            observed_at=observed_at,
        )
        try:
            matching = _encoded(parsed.to_record()) == _encoded(record)
        except (TypeError, ValueError) as error:
            raise ValueError("Source observation record is malformed") from error
        if not matching:
            raise ValueError("Source observation record differs from source row")
        return parsed


def parse_cook_row(
    row: Mapping[str, object],
    *,
    capture_sha256: str,
    response_sha256: str,
    row_sha256: str,
    observed_at: datetime,
) -> CookParcelSaleObservation:
    """Preserve a verified Cook row with source-only states and lineage."""
    if not isinstance(row, Mapping) or any(type(key) is not str for key in row):
        raise ValueError("Cook source row must be an object with string keys")
    if set(row) - _FIELD_SET:
        raise ValueError("Cook source row has unrequested fields")
    for value in row.values():
        _validate_scalar(value)
    row_id = row.get("row_id")
    if type(row_id) is not str or not row_id or row_id != row_id.strip():
        raise ValueError("Cook source row ID is invalid")
    for name, value in (
        ("capture_sha256", capture_sha256),
        ("response_sha256", response_sha256),
        ("row_sha256", row_sha256),
    ):
        _validate_hash(value, name)
    _validate_utc(observed_at)
    selected = {field: row[field] for field in SELECT_FIELDS if field in row}
    if _sha256(selected) != row_sha256:
        raise ValueError("Cook source row hash mismatch")
    pin_state, pin = _pin(selected)
    price_state, price = _price(selected)
    recorded_date_state, recorded_date = _recorded_date(selected)
    return CookParcelSaleObservation(
        raw_fields=tuple(selected.items()),
        row_id=row_id,
        pin_state=pin_state,
        pin=pin,
        price_state=price_state,
        price=price,
        recorded_date_state=recorded_date_state,
        recorded_date=recorded_date,
        capture_sha256=capture_sha256,
        response_sha256=response_sha256,
        row_sha256=row_sha256,
        observed_at=observed_at,
    )
