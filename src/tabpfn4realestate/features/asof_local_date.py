"""Versioned local-date OFF assembly admitting typed date publications."""

from __future__ import annotations

from typing import Sequence

from tabpfn4realestate.data.local_date_facts import (
    DatePublishedAttribute,
    DatePublishedProperty,
)
from tabpfn4realestate.data.local_date_sale import LocalDateSale
from tabpfn4realestate.data.schema import (
    Attribute,
    ListingEvent,
    Property,
    SourceSnapshot,
    Transaction,
)
from tabpfn4realestate.evaluation.local_dates import LocalDateOrigin
from tabpfn4realestate.features.asof import (
    LOCAL_DATE_ASSEMBLER_POLICY_VERSION_V2,
    LocalDateFeatureSnapshot,
    _assemble_snapshot_core,
    _select_property_version,
)
from tabpfn4realestate.features.asof_timing import _local_boundary


def assemble_local_date_snapshot_v2(
    property: Property | DatePublishedProperty,
    origin: LocalDateOrigin,
    mode: str,
    source_snapshot: SourceSnapshot,
    *,
    attributes: Sequence[Attribute | DatePublishedAttribute] = (),
    listing_events: Sequence[ListingEvent] = (),
    transactions: Sequence[Transaction | LocalDateSale] = (),
    subject_transaction_id: str | None = None,
    subject_source_id: str | None = None,
    subject_economic_transfer_id: str | None = None,
) -> LocalDateFeatureSnapshot:
    """Resolve source-local date publications at their completed-day cutoff."""
    if not isinstance(origin, LocalDateOrigin):
        raise ValueError("origin must be a LocalDateOrigin")
    if not isinstance(property, (Property, DatePublishedProperty)):
        raise ValueError("Unsupported property fact")
    if any(
        not isinstance(row, (Attribute, DatePublishedAttribute)) for row in attributes
    ):
        raise ValueError("Unsupported attribute fact")
    if any(not isinstance(row, (Transaction, LocalDateSale)) for row in transactions):
        raise ValueError("Unsupported sale fact")
    return _assemble_snapshot_core(
        property,
        origin,
        mode,
        source_snapshot,
        _local_boundary(origin, source_snapshot, allow_date_only=True),
        attributes=attributes,
        listing_events=listing_events,
        transactions=transactions,
        subject_transaction_id=subject_transaction_id,
        subject_source_id=subject_source_id,
        subject_economic_transfer_id=subject_economic_transfer_id,
        local_policy_version=LOCAL_DATE_ASSEMBLER_POLICY_VERSION_V2,
    )


def assemble_local_date_snapshot_from_versions_v2(
    property_id: str,
    versions: Sequence[Property | DatePublishedProperty],
    origin: LocalDateOrigin,
    mode: str,
    source_snapshot: SourceSnapshot,
    *,
    attributes: Sequence[Attribute | DatePublishedAttribute] = (),
    listing_events: Sequence[ListingEvent] = (),
    transactions: Sequence[Transaction | LocalDateSale] = (),
    subject_transaction_id: str | None = None,
    subject_source_id: str | None = None,
    subject_economic_transfer_id: str | None = None,
) -> LocalDateFeatureSnapshot:
    """Select an as-of structural version before assembling its features."""
    if not isinstance(origin, LocalDateOrigin):
        raise ValueError("origin must be a LocalDateOrigin")
    if any(not isinstance(row, (Property, DatePublishedProperty)) for row in versions):
        raise ValueError("Unsupported property fact")
    selected = _select_property_version(
        property_id,
        versions,
        _local_boundary(origin, source_snapshot, allow_date_only=True),
        source_snapshot,
    )
    return _assemble_snapshot_core(
        selected,
        origin,
        mode,
        source_snapshot,
        _local_boundary(origin, source_snapshot, allow_date_only=True),
        attributes=attributes,
        listing_events=listing_events,
        transactions=transactions,
        subject_transaction_id=subject_transaction_id,
        subject_source_id=subject_source_id,
        subject_economic_transfer_id=subject_economic_transfer_id,
        local_policy_version=LOCAL_DATE_ASSEMBLER_POLICY_VERSION_V2,
    )
