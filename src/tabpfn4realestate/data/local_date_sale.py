"""A sale label whose closing time is known only to a source-local date."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Sequence

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


def canonicalize_local_date_sales(
    sales: Sequence[LocalDateSale],
) -> tuple[LocalDateSale, ...]:
    """Collapse only matching copies of one dated economic transfer."""
    by_transfer: dict[str, LocalDateSale] = {}
    by_source_transaction: dict[tuple[str, str], str] = {}
    for row in sales:
        if not isinstance(row, LocalDateSale):
            raise ValueError("Expected a local-date sale")
        source_key = (row.source_id, row.transaction_id)
        earlier_transfer = by_source_transaction.get(source_key)
        if (
            earlier_transfer is not None
            and earlier_transfer != row.economic_transfer_id
        ):
            raise ValueError("Source transaction identifies two economic transfers")
        by_source_transaction[source_key] = row.economic_transfer_id
        earlier = by_transfer.get(row.economic_transfer_id)
        if earlier is None:
            by_transfer[row.economic_transfer_id] = row
            continue
        comparable_fields = (
            "property_id",
            "close_date",
            "close_zone_key",
            "price",
            "currency",
            "scope",
            "consideration_type",
            "arm_length_status",
            "adjustment_flags",
        )
        if any(
            getattr(earlier, name) != getattr(row, name) for name in comparable_fields
        ):
            raise ValueError("Conflicting duplicate economic transfer; quarantine")
        if (
            availability_cutoff_utc(row.available_at),
            row.source_id,
            row.transaction_id,
        ) < (
            availability_cutoff_utc(earlier.available_at),
            earlier.source_id,
            earlier.transaction_id,
        ):
            by_transfer[row.economic_transfer_id] = row
    return tuple(by_transfer[key] for key in sorted(by_transfer))
