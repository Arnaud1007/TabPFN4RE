"""Point-in-time comparable candidate filter; distance ranking follows in U2."""

from __future__ import annotations

from datetime import datetime
from typing import Sequence

from tabpfn4realestate.data.schema import (
    Property,
    SourceSnapshot,
    Transaction,
    _instant,
    canonicalize_transactions,
)


def eligible_comparable_sales(
    subject: Property,
    origin: datetime,
    source_snapshot: SourceSnapshot,
    *,
    candidate_properties: Sequence[Property],
    transactions: Sequence[Transaction],
    subject_economic_transfer_id: str | None = None,
) -> tuple[Transaction, ...]:
    """Return eligible, visible, non-subject transfers in deterministic order."""
    _instant(origin, "origin")
    cutoff = min(origin, source_snapshot.as_of)
    if subject.source_id not in source_snapshot.source_ids:
        raise ValueError("Subject property source is absent from snapshot manifest")
    if subject.observed_at > cutoff or subject.available_at > cutoff:
        raise ValueError("Subject property version was unavailable at origin")

    candidates: dict[str, Property] = {}
    for property in candidate_properties:
        if property.source_id not in source_snapshot.source_ids:
            raise ValueError(
                "Candidate property source is absent from snapshot manifest"
            )
        if property.property_id in candidates:
            raise ValueError("Duplicate candidate property identity")
        candidates[property.property_id] = property

    eligible_property_ids = {
        property_id
        for property_id, property in candidates.items()
        if property_id != subject.property_id
        and property.country == subject.country
        and property.property_type == subject.property_type
        and property.observed_at <= cutoff
        and property.available_at <= cutoff
    }
    visible_sales = tuple(
        sale
        for sale in transactions
        if sale.source_id in source_snapshot.source_ids
        and sale.close_at <= cutoff
        and sale.available_at <= cutoff
    )
    canonical = canonicalize_transactions(visible_sales)
    return tuple(
        sorted(
            (
                sale
                for sale in canonical
                if sale.property_id in eligible_property_ids
                and sale.economic_transfer_id != subject_economic_transfer_id
                and sale.eligible_prior_sale
            ),
            key=lambda sale: (sale.close_at, sale.economic_transfer_id),
        )
    )
