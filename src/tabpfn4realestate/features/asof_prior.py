"""Identity-guarded retrieval of a subject property's last known sale."""

from __future__ import annotations

from datetime import datetime
from typing import Sequence

from tabpfn4realestate.data.local_date_facts import DateOnlyEvent
from tabpfn4realestate.data.local_date_sale import (
    LocalDateSale,
    canonicalize_local_date_sales,
)
from tabpfn4realestate.data.schema import (
    SourceSnapshot,
    Transaction,
    canonicalize_transactions,
)
from tabpfn4realestate.features.asof_timing import _Boundary, time_cutoff_utc


def select_prior_sale(
    property_id: str,
    transactions: Sequence[Transaction | LocalDateSale],
    boundary: _Boundary,
    source_snapshot: SourceSnapshot,
    *,
    subject_transaction_id: str | None,
    subject_source_id: str | None,
    subject_economic_transfer_id: str | None,
) -> tuple[Transaction | LocalDateSale, datetime | DateOnlyEvent] | None:
    """Return the latest eligible, visible transfer after identity checks."""
    if (subject_transaction_id is None) != (subject_source_id is None):
        raise ValueError("Subject raw transaction ID requires its source ID")
    subject_matches = (
        {
            sale.economic_transfer_id
            for sale in transactions
            if sale.property_id == property_id
            and sale.source_id == subject_source_id
            and sale.transaction_id == subject_transaction_id
        }
        if subject_transaction_id is not None
        else set()
    )
    if subject_transaction_id is not None and not subject_matches:
        raise ValueError("Subject transaction identity cannot be resolved")
    if len(subject_matches) > 1:
        raise ValueError("Subject transaction maps to multiple transfers")
    if (
        subject_matches
        and subject_economic_transfer_id is not None
        and subject_economic_transfer_id not in subject_matches
    ):
        raise ValueError("Subject economic transfer identity conflicts")
    excluded_transfer = (
        subject_economic_transfer_id
        if subject_economic_transfer_id is not None
        else next(iter(subject_matches), None)
    )
    prior: list[Transaction | LocalDateSale] = []
    for sale in transactions:
        if sale.property_id != property_id:
            continue
        if sale.source_id not in source_snapshot.source_ids:
            raise ValueError("Transaction source is absent from snapshot manifest")
        if sale.economic_transfer_id == excluded_transfer:
            continue
        close_event = (
            DateOnlyEvent(sale.close_date, sale.close_zone_key)
            if isinstance(sale, LocalDateSale)
            else sale.close_at
        )
        if boundary.known_by(close_event) and boundary.known_by(sale.available_at):
            prior.append(sale)
    exact = canonicalize_transactions(
        tuple(row for row in prior if isinstance(row, Transaction))
    )
    dated = canonicalize_local_date_sales(
        tuple(row for row in prior if isinstance(row, LocalDateSale))
    )
    if {row.economic_transfer_id for row in exact} & {
        row.economic_transfer_id for row in dated
    } or {(row.source_id, row.transaction_id) for row in exact} & {
        (row.source_id, row.transaction_id) for row in dated
    }:
        raise ValueError("Mixed-precision economic transfer needs reconciliation")
    eligible = tuple(row for row in exact if row.eligible_prior_sale) + tuple(
        row for row in dated if row.eligible_sale
    )
    if not eligible:
        return None

    def close_event(row: Transaction | LocalDateSale) -> datetime | DateOnlyEvent:
        return (
            DateOnlyEvent(row.close_date, row.close_zone_key)
            if isinstance(row, LocalDateSale)
            else row.close_at
        )

    latest = max(
        eligible,
        key=lambda row: (
            time_cutoff_utc(close_event(row)),
            time_cutoff_utc(row.available_at),
        ),
    )
    return latest, close_event(latest)
