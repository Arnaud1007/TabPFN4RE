"""A sale label whose closing time is known only to a source-local date."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

from tabpfn4realestate.data.schema import _decimal, _identifier
from tabpfn4realestate.evaluation.local_dates import (
    DateOnlyAvailability,
    availability_cutoff_utc,
    source_local_day_start_utc,
)


@dataclass(frozen=True)
class LocalDateSale:
    transaction_id: str
    economic_transfer_id: str
    property_id: str
    close_date: date
    close_zone_key: str
    available_at: datetime | DateOnlyAvailability
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
        if type(self.close_date) is not date:
            raise ValueError("close_date must retain source-local date precision")
        try:
            next_day = self.close_date + timedelta(days=1)
        except OverflowError as error:
            raise ValueError(
                "close_date is outside supported calendar range"
            ) from error
        close_day_end = source_local_day_start_utc(next_day, self.close_zone_key)
        if availability_cutoff_utc(self.available_at) < close_day_end:
            raise ValueError(
                "Sale label cannot be available before the close date ended"
            )
        _decimal(self.price, "price")
        if self.currency != "USD":
            raise ValueError("US sale currency must be USD")
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
    def eligible_sale(self) -> bool:
        return (
            self.scope == "single_property"
            and self.consideration_type == "gross_recorded_sale"
            and self.arm_length_status == "confirmed"
            and not self.adjustment_flags
        )
