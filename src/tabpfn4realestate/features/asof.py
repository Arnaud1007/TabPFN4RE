"""Conservative OFF feature assembly with per-value source lineage."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
import hashlib
import json
from types import MappingProxyType
from typing import Mapping, Sequence

from tabpfn4realestate.data.local_date_facts import (
    DateOnlyEvent,
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
    _identifier,
    _instant,
    _utc,
)
from tabpfn4realestate.evaluation.local_dates import (
    DateOnlyAvailability,
    LocalDateOrigin,
)
from tabpfn4realestate.features.asof_timing import (
    _Boundary,
    _ReconciledAttribute,
    _ReconciledProperty,
    _exact_boundary,
    _local_boundary,
    time_cutoff_utc,
    time_sort_text,
    typed_time_identity,
)
from tabpfn4realestate.features.asof_prior import select_prior_sale


ASSEMBLER_POLICY_VERSION = "synthetic_off_asof_v2"
LOCAL_DATE_ASSEMBLER_POLICY_VERSION = "synthetic_off_local_date_asof_v1"
LOCAL_DATE_ASSEMBLER_POLICY_VERSION_V2 = "synthetic_off_local_date_asof_v2"


_ATTRIBUTE_TYPES = {
    "condition": str,
    "bedrooms": int,
    "year_built": int,
}
_FORBIDDEN = {"SalePrice", "F172", "F349", "F350"}

PropertyFact = Property | DatePublishedProperty | _ReconciledProperty
AttributeFact = Attribute | DatePublishedAttribute | _ReconciledAttribute


@dataclass(frozen=True)
class Lineage:
    source_id: str
    observed_at: datetime | DateOnlyEvent
    available_at: datetime | DateOnlyAvailability
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    valid_to_available_at: datetime | DateOnlyAvailability | None = None


@dataclass(frozen=True)
class FeatureSnapshot:
    property_id: str
    origin: datetime
    mode: str
    source_snapshot_id: str
    values: Mapping[str, str | int | Decimal]
    lineage: Mapping[str, Lineage]
    snapshot_hash: str


@dataclass(frozen=True)
class LocalDateFeatureSnapshot:
    property_id: str
    origin: LocalDateOrigin
    mode: str
    source_snapshot_id: str
    values: Mapping[str, str | int | Decimal]
    lineage: Mapping[str, Lineage]
    snapshot_hash: str


class NoAvailablePropertyVersionError(ValueError):
    """The known history has no structural version at the requested origin."""


def _validate_attribute(attribute: Attribute | DatePublishedAttribute) -> None:
    if attribute.name in _FORBIDDEN:
        raise ValueError(f"Forbidden feature: {attribute.name}")
    expected_type = _ATTRIBUTE_TYPES.get(attribute.name)
    if expected_type is None:
        raise ValueError(f"Unregistered feature: {attribute.name}")
    if attribute.unit is not None or (
        attribute.value is not None and type(attribute.value) is not expected_type
    ):
        raise ValueError(f"Invalid value or unit for {attribute.name}")
    if expected_type is int and attribute.value is not None and attribute.value < 0:
        raise ValueError(f"{attribute.name} cannot be negative")
    if (
        expected_type is str
        and attribute.value is not None
        and not attribute.value.strip()
    ):
        raise ValueError(f"{attribute.name} cannot be empty")


def _known_valid_to(
    row: PropertyFact | AttributeFact,
    boundary: _Boundary,
) -> tuple[datetime | None, datetime | DateOnlyAvailability | None]:
    if (
        row.valid_to is not None
        and row.valid_to_available_at is not None
        and boundary.known_by(row.valid_to_available_at)
    ):
        return row.valid_to, row.valid_to_available_at
    return None, None


def _visible_property_version(row: PropertyFact, boundary: _Boundary) -> PropertyFact:
    """Remove an end date that was not available by the source cutoff."""
    end, _ = _known_valid_to(row, boundary)
    if end is None and row.valid_to is not None:
        return replace(row, valid_to=None, valid_to_available_at=None)
    return row


def _effective_at(
    row: PropertyFact | AttributeFact,
    boundary: _Boundary,
) -> bool:
    if not boundary.known_by(row.observed_at) or not boundary.known_by(
        row.available_at
    ):
        return False
    if not boundary.effective_by(row.valid_from or row.observed_at):
        return False
    valid_to, _ = _known_valid_to(row, boundary)
    return valid_to is None or boundary.valid_through(valid_to)


def _version_lineage(
    row: PropertyFact | AttributeFact,
    boundary: _Boundary,
) -> Lineage:
    valid_to, valid_to_available_at = _known_valid_to(row, boundary)
    return Lineage(
        row.source_id,
        row.observed_at,
        row.available_at,
        row.valid_from,
        valid_to,
        valid_to_available_at,
    )


def _reconcile_attribute_copies(
    observations: Sequence[Attribute | DatePublishedAttribute], boundary: _Boundary
) -> tuple[AttributeFact, ...]:
    """Apply a disclosed end to every copy of one source observation."""
    grouped: dict[tuple[object, ...], list[Attribute | DatePublishedAttribute]] = {}
    for row in observations:
        if not boundary.known_by(row.observed_at) or not boundary.known_by(
            row.available_at
        ):
            continue
        key = (
            row.property_id,
            row.name,
            row.value,
            row.unit,
            row.missing_state,
            row.source_id,
            _utc(row.observed_at),
            _utc(row.valid_from or row.observed_at),
        )
        grouped.setdefault(key, []).append(row)

    reconciled: list[AttributeFact] = []
    for copies in grouped.values():
        base = min(copies, key=lambda row: time_cutoff_utc(row.available_at))
        result: AttributeFact = base
        known_ends: list[tuple[datetime, datetime | DateOnlyAvailability]] = []
        open_copies: list[datetime | DateOnlyAvailability] = []
        for row in copies:
            end, published = _known_valid_to(row, boundary)
            if end is None or published is None:
                open_copies.append(row.available_at)
            else:
                known_ends.append(
                    (end, max(row.available_at, published, key=time_cutoff_utc))
                )
        if known_ends:
            end_instants = {_utc(end) for end, _ in known_ends}
            if len(end_instants) != 1:
                raise ValueError(f"Ambiguous attribute version end: {base.name}")
            disclosed = min(
                (published for _, published in known_ends), key=time_cutoff_utc
            )
            if any(
                time_cutoff_utc(opened) >= time_cutoff_utc(disclosed)
                for opened in open_copies
            ):
                raise ValueError(f"Ambiguous attribute end retraction: {base.name}")
            if isinstance(base, Attribute) and isinstance(
                disclosed, DateOnlyAvailability
            ):
                result = _ReconciledAttribute.from_exact(
                    base, known_ends[0][0], disclosed
                )
            else:
                result = replace(
                    base,
                    valid_to=known_ends[0][0],
                    valid_to_available_at=disclosed,
                )
        reconciled.append(result)
    return tuple(reconciled)


def _reconcile_property_copies(
    observations: Sequence[Property | DatePublishedProperty], boundary: _Boundary
) -> tuple[PropertyFact, ...]:
    """Close identical source copies when their end becomes known."""
    grouped: dict[tuple[object, ...], list[Property | DatePublishedProperty]] = {}
    for row in observations:
        if not boundary.known_by(row.observed_at) or not boundary.known_by(
            row.available_at
        ):
            continue
        key = (
            row.property_id,
            row.country,
            row.property_type,
            row.source_id,
            _utc(row.observed_at),
            _utc(row.valid_from or row.observed_at),
            row.living_area,
            row.living_area_unit,
            row.living_area_state,
            row.latitude,
            row.longitude,
        )
        grouped.setdefault(key, []).append(row)

    reconciled: list[PropertyFact] = []
    for copies in grouped.values():
        base = min(
            copies,
            key=lambda row: (
                time_cutoff_utc(row.available_at),
                row.valid_from is not None,
                str(row.living_area),
                str(row.latitude),
                str(row.longitude),
                time_sort_text(row.available_at),
                row.observed_at.isoformat(),
                row.valid_from.isoformat() if row.valid_from else "",
            ),
        )
        result: PropertyFact = base
        known_ends: list[tuple[datetime, datetime | DateOnlyAvailability]] = []
        open_copies: list[datetime | DateOnlyAvailability] = []
        for row in copies:
            end, published = _known_valid_to(row, boundary)
            if end is None or published is None:
                open_copies.append(row.available_at)
            else:
                known_ends.append(
                    (end, max(row.available_at, published, key=time_cutoff_utc))
                )
        if known_ends:
            if len({_utc(end) for end, _ in known_ends}) != 1:
                raise ValueError("Ambiguous property version end")
            disclosed = min(
                (published for _, published in known_ends), key=time_cutoff_utc
            )
            if any(
                time_cutoff_utc(opened) >= time_cutoff_utc(disclosed)
                for opened in open_copies
            ):
                raise ValueError("Ambiguous property end retraction")
            if isinstance(base, Property) and isinstance(
                disclosed, DateOnlyAvailability
            ):
                result = _ReconciledProperty.from_exact(
                    base, _utc(known_ends[0][0]), disclosed
                )
            else:
                result = replace(
                    base,
                    valid_to=_utc(known_ends[0][0]),
                    valid_to_available_at=(
                        disclosed
                        if isinstance(disclosed, DateOnlyAvailability)
                        else _utc(disclosed)
                    ),
                )
        reconciled.append(_visible_property_version(result, boundary))
    return tuple(reconciled)


def select_property_version(
    property_id: str,
    versions: Sequence[Property],
    origin: datetime,
    source_snapshot: SourceSnapshot,
    *,
    known_at: datetime | None = None,
) -> Property:
    """Select the effective version using only information known by a cutoff."""
    _instant(origin, "origin")
    if any(type(row) is not Property for row in versions):
        raise ValueError("Exact protocol rejects date-only property facts")
    if known_at is not None:
        _instant(known_at, "known_at")
        if _utc(known_at) < _utc(origin):
            raise ValueError("known_at cannot precede the effective origin")
    selected = _select_property_version(
        property_id,
        versions,
        _exact_boundary(origin, source_snapshot, known_at),
        source_snapshot,
    )
    if type(selected) is not Property:
        raise ValueError("Exact protocol selected a non-exact property fact")
    return selected


def select_local_date_property_version(
    property_id: str,
    versions: Sequence[Property],
    origin: LocalDateOrigin,
    source_snapshot: SourceSnapshot,
) -> Property:
    """Select a version effective through a source-local origin date."""
    if not isinstance(origin, LocalDateOrigin):
        raise ValueError("origin must be a LocalDateOrigin")
    if any(type(row) is not Property for row in versions):
        raise ValueError("Local-date v1 rejects date-only property facts; use v2")
    selected = _select_property_version(
        property_id, versions, _local_boundary(origin, source_snapshot), source_snapshot
    )
    if type(selected) is not Property:
        raise ValueError("Local-date v1 selected a non-exact property fact")
    return selected


def _select_property_version(
    property_id: str,
    versions: Sequence[Property | DatePublishedProperty],
    boundary: _Boundary,
    source_snapshot: SourceSnapshot,
) -> PropertyFact:
    _identifier(property_id, "property_id")
    if not versions:
        raise ValueError("Property history is empty")
    for row in versions:
        if row.property_id != property_id:
            raise ValueError("Property history contains another property_id")

    for row in versions:
        if not boundary.known_by(row.observed_at) or not boundary.known_by(
            row.available_at
        ):
            continue
        if row.source_id not in source_snapshot.source_ids:
            raise ValueError("Property source is absent from snapshot manifest")
    visible = _reconcile_property_copies(versions, boundary)
    active = tuple(row for row in visible if _effective_at(row, boundary))
    for expired in visible:
        end, _ = _known_valid_to(expired, boundary)
        if end is None or boundary.valid_through(end):
            continue
        if any(
            contender is not expired
            and contender in active
            and _utc(contender.valid_from or contender.observed_at) < _utc(end)
            for contender in visible
        ):
            raise ValueError("Unresolved overlapping property versions")
    if not active:
        raise NoAvailablePropertyVersionError(
            "No property version is available and valid at origin"
        )
    if len(active) > 1:
        raise ValueError("Ambiguous overlapping property versions")
    return active[0]


def _reject_unresolved_expiries(
    observations: Sequence[AttributeFact], boundary: _Boundary
) -> None:
    grouped: dict[tuple[str, str, str], list[AttributeFact]] = {}
    for row in observations:
        grouped.setdefault((row.property_id, row.name, row.source_id), []).append(row)
    for rows in grouped.values():
        for expired in rows:
            end, _ = _known_valid_to(expired, boundary)
            if end is None or boundary.valid_through(end):
                continue
            if any(
                contender is not expired
                and _effective_at(contender, boundary)
                and _utc(contender.valid_from or contender.observed_at) < _utc(end)
                for contender in rows
            ):
                raise ValueError(
                    f"Unresolved overlapping attribute versions: {expired.name}"
                )


def _known_attribute_facts(
    row: AttributeFact, boundary: _Boundary
) -> tuple[object, ...]:
    return row.value, row.unit, row.missing_state, _version_lineage(row, boundary)


def _snapshot_hash(
    property_id: str,
    origin: datetime | LocalDateOrigin,
    source_snapshot: SourceSnapshot,
    values: Mapping[str, str | int | Decimal],
    lineage: Mapping[str, Lineage],
    *,
    local_policy_version: str | None = None,
) -> str:
    typed = local_policy_version == LOCAL_DATE_ASSEMBLER_POLICY_VERSION_V2
    features: list[dict[str, object]] = []
    for name in sorted(values):
        entry = lineage[name]
        feature = {
            "name": name,
            "value": str(values[name]),
            "source_id": entry.source_id,
            "observed_at": (
                typed_time_identity(entry.observed_at)
                if typed
                else _utc(entry.observed_at).isoformat()
            ),
            "available_at": (
                typed_time_identity(entry.available_at)
                if typed
                else _utc(entry.available_at).isoformat()
            ),
        }
        for field in ("valid_from", "valid_to", "valid_to_available_at"):
            value = getattr(entry, field)
            if value is not None:
                feature[field] = (
                    typed_time_identity(value) if typed else _utc(value).isoformat()
                )
        features.append(feature)
    payload = {
        "property_id": property_id,
        "mode": "OFF",
        "source_snapshot": {
            "snapshot_id": source_snapshot.snapshot_id,
            "source_ids": source_snapshot.source_ids,
            "as_of": _utc(source_snapshot.as_of).isoformat(),
        },
        "features": features,
    }
    if isinstance(origin, LocalDateOrigin):
        payload["origin_policy"] = {
            "assembler_policy_version": (
                local_policy_version or LOCAL_DATE_ASSEMBLER_POLICY_VERSION
            ),
            "protocol_id": origin.protocol_id,
            "policy_hash": origin.policy_hash,
            "origin_date": origin.origin_date.isoformat(),
            "close_date": origin.close_date.isoformat(),
            "zone_key": origin.zone_key,
            "cutoff_exclusive_utc": origin.cutoff_exclusive_utc.isoformat(),
        }
    else:
        payload["origin"] = _utc(origin).isoformat()
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def assemble_snapshot(
    property: Property,
    origin: datetime,
    mode: str,
    source_snapshot: SourceSnapshot,
    *,
    attributes: Sequence[Attribute] = (),
    listing_events: Sequence[ListingEvent] = (),
    transactions: Sequence[Transaction] = (),
    subject_transaction_id: str | None = None,
    subject_source_id: str | None = None,
    subject_economic_transfer_id: str | None = None,
) -> FeatureSnapshot:
    """Return source-backed features visible no later than a valuation origin."""
    _instant(origin, "origin")
    if (
        type(property) is not Property
        or any(type(row) is not Attribute for row in attributes)
        or any(type(row) is not Transaction for row in transactions)
    ):
        raise ValueError("Exact protocol rejects date-only facts")
    return _assemble_snapshot_core(
        property,
        origin,
        mode,
        source_snapshot,
        _exact_boundary(origin, source_snapshot),
        attributes=attributes,
        listing_events=listing_events,
        transactions=transactions,
        subject_transaction_id=subject_transaction_id,
        subject_source_id=subject_source_id,
        subject_economic_transfer_id=subject_economic_transfer_id,
    )


def assemble_local_date_snapshot(
    property: Property,
    origin: LocalDateOrigin,
    mode: str,
    source_snapshot: SourceSnapshot,
    *,
    attributes: Sequence[Attribute] = (),
    listing_events: Sequence[ListingEvent] = (),
    transactions: Sequence[Transaction] = (),
    subject_transaction_id: str | None = None,
    subject_source_id: str | None = None,
    subject_economic_transfer_id: str | None = None,
) -> LocalDateFeatureSnapshot:
    """Assemble timestamped source facts before the local date's exclusive end."""
    if not isinstance(origin, LocalDateOrigin):
        raise ValueError("origin must be a LocalDateOrigin")
    if (
        type(property) is not Property
        or any(type(row) is not Attribute for row in attributes)
        or any(type(row) is not Transaction for row in transactions)
    ):
        raise ValueError("Local-date v1 rejects date-only facts; use v2")
    return _assemble_snapshot_core(
        property,
        origin,
        mode,
        source_snapshot,
        _local_boundary(origin, source_snapshot),
        attributes=attributes,
        listing_events=listing_events,
        transactions=transactions,
        subject_transaction_id=subject_transaction_id,
        subject_source_id=subject_source_id,
        subject_economic_transfer_id=subject_economic_transfer_id,
    )


def _assemble_snapshot_core(
    property: PropertyFact,
    origin: datetime | LocalDateOrigin,
    mode: str,
    source_snapshot: SourceSnapshot,
    boundary: _Boundary,
    *,
    attributes: Sequence[Attribute | DatePublishedAttribute],
    listing_events: Sequence[ListingEvent],
    transactions: Sequence[Transaction | LocalDateSale],
    subject_transaction_id: str | None,
    subject_source_id: str | None,
    subject_economic_transfer_id: str | None,
    local_policy_version: str | None = None,
) -> FeatureSnapshot | LocalDateFeatureSnapshot:
    if mode == "ON":
        raise NotImplementedError("ON requires authorised historical listing snapshots")
    if mode != "OFF":
        raise ValueError(f"Unsupported information mode: {mode}")
    if property.source_id not in source_snapshot.source_ids:
        raise ValueError("Property source is absent from snapshot manifest")
    if not _effective_at(property, boundary):
        raise NoAvailablePropertyVersionError(
            "Property version is unavailable or not valid at origin"
        )

    property_lineage = _version_lineage(property, boundary)
    values: dict[str, str | int | Decimal] = {"property_type": property.property_type}
    lineage: dict[str, Lineage] = {"property_type": property_lineage}
    if property.living_area is not None:
        values.update(
            living_area=property.living_area,
            living_area_unit=property.living_area_unit,
        )
        lineage.update(
            living_area=property_lineage,
            living_area_unit=property_lineage,
        )
    else:
        values["living_area_state"] = property.living_area_state
        lineage["living_area_state"] = property_lineage

    validated_attributes: list[Attribute | DatePublishedAttribute] = []
    for observation in attributes:
        if observation.property_id != property.property_id:
            raise ValueError("Attribute property_id does not match requested property")
        if observation.source_id not in source_snapshot.source_ids:
            raise ValueError("Attribute source is absent from snapshot manifest")
        _validate_attribute(observation)
        validated_attributes.append(observation)
    reconciled = _reconcile_attribute_copies(validated_attributes, boundary)
    _reject_unresolved_expiries(reconciled, boundary)
    candidates: dict[str, list[AttributeFact]] = {}
    for observation in reconciled:
        if not _effective_at(observation, boundary):
            continue
        candidates.setdefault(observation.name, []).append(observation)
    chosen: dict[str, AttributeFact] = {}
    for name, eligible in candidates.items():
        if len(eligible) > 1 and any(
            row.valid_from is not None or row.valid_to is not None for row in eligible
        ):
            if any(
                _known_attribute_facts(row, boundary)
                != _known_attribute_facts(eligible[0], boundary)
                for row in eligible[1:]
            ):
                raise ValueError(f"Ambiguous overlapping attribute versions: {name}")
        for observation in eligible:
            earlier = chosen.get(name)
            if earlier is None or _utc(observation.observed_at) > _utc(
                earlier.observed_at
            ):
                chosen[name] = observation
                continue
            if _utc(observation.observed_at) != _utc(earlier.observed_at):
                continue
            if (
                observation.value != earlier.value
                or observation.unit != earlier.unit
                or observation.missing_state != earlier.missing_state
            ):
                raise ValueError(f"Ambiguous attribute: {name}")
            if (time_cutoff_utc(observation.available_at), observation.source_id) < (
                time_cutoff_utc(earlier.available_at),
                earlier.source_id,
            ):
                chosen[name] = observation
    for name, observation in chosen.items():
        output_name = name if observation.value is not None else f"{name}_state"
        values[output_name] = (
            observation.value
            if observation.value is not None
            else observation.missing_state
        )
        lineage[output_name] = _version_lineage(observation, boundary)

    prior = select_prior_sale(
        property.property_id,
        transactions,
        boundary,
        source_snapshot,
        subject_transaction_id=subject_transaction_id,
        subject_source_id=subject_source_id,
        subject_economic_transfer_id=subject_economic_transfer_id,
    )
    if prior is not None:
        latest, close_event = prior
        values["prior_sale_price"] = latest.price
        lineage["prior_sale_price"] = Lineage(
            latest.source_id, close_event, latest.available_at
        )

    # OFF never reads listing_events; its events cannot affect this snapshot.
    del listing_events
    snapshot_type = (
        LocalDateFeatureSnapshot
        if isinstance(origin, LocalDateOrigin)
        else FeatureSnapshot
    )
    return snapshot_type(
        property_id=property.property_id,
        origin=origin,
        mode="OFF",
        source_snapshot_id=source_snapshot.snapshot_id,
        values=MappingProxyType(values),
        lineage=MappingProxyType(lineage),
        snapshot_hash=_snapshot_hash(
            property.property_id,
            origin,
            source_snapshot,
            values,
            lineage,
            local_policy_version=local_policy_version,
        ),
    )


def assemble_snapshot_from_versions(
    property_id: str,
    versions: Sequence[Property],
    origin: datetime,
    mode: str,
    source_snapshot: SourceSnapshot,
    *,
    attributes: Sequence[Attribute] = (),
    listing_events: Sequence[ListingEvent] = (),
    transactions: Sequence[Transaction] = (),
    subject_transaction_id: str | None = None,
    subject_source_id: str | None = None,
    subject_economic_transfer_id: str | None = None,
) -> FeatureSnapshot:
    """Assemble after resolving the property's visible structural history."""
    selected = select_property_version(property_id, versions, origin, source_snapshot)
    return assemble_snapshot(
        selected,
        origin,
        mode,
        source_snapshot,
        attributes=attributes,
        listing_events=listing_events,
        transactions=transactions,
        subject_transaction_id=subject_transaction_id,
        subject_source_id=subject_source_id,
        subject_economic_transfer_id=subject_economic_transfer_id,
    )


def assemble_local_date_snapshot_from_versions(
    property_id: str,
    versions: Sequence[Property],
    origin: LocalDateOrigin,
    mode: str,
    source_snapshot: SourceSnapshot,
    *,
    attributes: Sequence[Attribute] = (),
    listing_events: Sequence[ListingEvent] = (),
    transactions: Sequence[Transaction] = (),
    subject_transaction_id: str | None = None,
    subject_source_id: str | None = None,
    subject_economic_transfer_id: str | None = None,
) -> LocalDateFeatureSnapshot:
    """Resolve timestamped structural versions at a local calendar origin."""
    selected = select_local_date_property_version(
        property_id, versions, origin, source_snapshot
    )
    return assemble_local_date_snapshot(
        selected,
        origin,
        mode,
        source_snapshot,
        attributes=attributes,
        listing_events=listing_events,
        transactions=transactions,
        subject_transaction_id=subject_transaction_id,
        subject_source_id=subject_source_id,
        subject_economic_transfer_id=subject_economic_transfer_id,
    )
