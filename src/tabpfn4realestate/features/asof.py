"""Conservative OFF feature assembly with per-value source lineage."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
import hashlib
import json
from types import MappingProxyType
from typing import Mapping, Sequence

from tabpfn4realestate.data.schema import (
    Attribute,
    ListingEvent,
    Property,
    SourceSnapshot,
    Transaction,
    canonicalize_transactions,
    _instant,
    _utc,
)


ASSEMBLER_POLICY_VERSION = "synthetic_off_asof_v2"


_ATTRIBUTE_TYPES = {
    "condition": str,
    "bedrooms": int,
    "year_built": int,
}
_FORBIDDEN = {"SalePrice", "F172", "F349", "F350"}


@dataclass(frozen=True)
class Lineage:
    source_id: str
    observed_at: datetime
    available_at: datetime
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    valid_to_available_at: datetime | None = None


@dataclass(frozen=True)
class FeatureSnapshot:
    property_id: str
    origin: datetime
    mode: str
    source_snapshot_id: str
    values: Mapping[str, str | int | Decimal]
    lineage: Mapping[str, Lineage]
    snapshot_hash: str


def _validate_attribute(attribute: Attribute) -> None:
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
    row: Property | Attribute, cutoff: datetime
) -> tuple[datetime | None, datetime | None]:
    if (
        row.valid_to is not None
        and row.valid_to_available_at is not None
        and _utc(row.valid_to_available_at) <= cutoff
    ):
        return row.valid_to, row.valid_to_available_at
    return None, None


def _effective_at(
    row: Property | Attribute, origin: datetime, cutoff: datetime
) -> bool:
    if _utc(row.observed_at) > cutoff or _utc(row.available_at) > cutoff:
        return False
    if _utc(row.valid_from or row.observed_at) > _utc(origin):
        return False
    valid_to, _ = _known_valid_to(row, cutoff)
    return valid_to is None or _utc(origin) < _utc(valid_to)


def _version_lineage(row: Property | Attribute, cutoff: datetime) -> Lineage:
    valid_to, valid_to_available_at = _known_valid_to(row, cutoff)
    return Lineage(
        row.source_id,
        row.observed_at,
        row.available_at,
        row.valid_from,
        valid_to,
        valid_to_available_at,
    )


def _reconcile_attribute_copies(
    observations: Sequence[Attribute], cutoff: datetime
) -> tuple[Attribute, ...]:
    """Apply a disclosed end to every copy of one source observation."""
    grouped: dict[tuple[object, ...], list[Attribute]] = {}
    for row in observations:
        if _utc(row.observed_at) > cutoff or _utc(row.available_at) > cutoff:
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

    reconciled: list[Attribute] = []
    for copies in grouped.values():
        base = min(copies, key=lambda row: _utc(row.available_at))
        known_ends: list[tuple[datetime, datetime]] = []
        open_copies: list[datetime] = []
        for row in copies:
            end, published = _known_valid_to(row, cutoff)
            if end is None or published is None:
                open_copies.append(row.available_at)
            else:
                known_ends.append((end, max(row.available_at, published, key=_utc)))
        if known_ends:
            end_instants = {_utc(end) for end, _ in known_ends}
            if len(end_instants) != 1:
                raise ValueError(f"Ambiguous attribute version end: {base.name}")
            disclosed = min((published for _, published in known_ends), key=_utc)
            if any(_utc(opened) >= _utc(disclosed) for opened in open_copies):
                raise ValueError(f"Ambiguous attribute end retraction: {base.name}")
            base = replace(
                base,
                valid_to=known_ends[0][0],
                valid_to_available_at=disclosed,
            )
        reconciled.append(base)
    return tuple(reconciled)


def _reject_unresolved_expiries(
    observations: Sequence[Attribute], origin: datetime, cutoff: datetime
) -> None:
    grouped: dict[tuple[str, str, str], list[Attribute]] = {}
    for row in observations:
        grouped.setdefault((row.property_id, row.name, row.source_id), []).append(row)
    for rows in grouped.values():
        for expired in rows:
            end, _ = _known_valid_to(expired, cutoff)
            if end is None or _utc(origin) < _utc(end):
                continue
            if any(
                contender is not expired
                and _effective_at(contender, origin, cutoff)
                and _utc(contender.valid_from or contender.observed_at) < _utc(end)
                for contender in rows
            ):
                raise ValueError(
                    f"Unresolved overlapping attribute versions: {expired.name}"
                )


def _known_attribute_facts(row: Attribute, cutoff: datetime) -> tuple[object, ...]:
    return row.value, row.unit, row.missing_state, _version_lineage(row, cutoff)


def _snapshot_hash(
    property_id: str,
    origin: datetime,
    source_snapshot: SourceSnapshot,
    values: Mapping[str, str | int | Decimal],
    lineage: Mapping[str, Lineage],
) -> str:
    features: list[dict[str, str]] = []
    for name in sorted(values):
        entry = lineage[name]
        feature = {
            "name": name,
            "value": str(values[name]),
            "source_id": entry.source_id,
            "observed_at": _utc(entry.observed_at).isoformat(),
            "available_at": _utc(entry.available_at).isoformat(),
        }
        for field in ("valid_from", "valid_to", "valid_to_available_at"):
            value = getattr(entry, field)
            if value is not None:
                feature[field] = _utc(value).isoformat()
        features.append(feature)
    payload = {
        "property_id": property_id,
        "origin": _utc(origin).isoformat(),
        "mode": "OFF",
        "source_snapshot": {
            "snapshot_id": source_snapshot.snapshot_id,
            "source_ids": source_snapshot.source_ids,
            "as_of": _utc(source_snapshot.as_of).isoformat(),
        },
        "features": features,
    }
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
    if mode == "ON":
        raise NotImplementedError("ON requires authorised historical listing snapshots")
    if mode != "OFF":
        raise ValueError(f"Unsupported information mode: {mode}")
    cutoff = min(_utc(origin), _utc(source_snapshot.as_of))
    if property.source_id not in source_snapshot.source_ids:
        raise ValueError("Property source is absent from snapshot manifest")
    if not _effective_at(property, origin, cutoff):
        raise ValueError("Property version is unavailable or not valid at origin")

    property_lineage = _version_lineage(property, cutoff)
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

    validated_attributes: list[Attribute] = []
    for observation in attributes:
        if observation.property_id != property.property_id:
            raise ValueError("Attribute property_id does not match requested property")
        if observation.source_id not in source_snapshot.source_ids:
            raise ValueError("Attribute source is absent from snapshot manifest")
        _validate_attribute(observation)
        validated_attributes.append(observation)
    reconciled = _reconcile_attribute_copies(validated_attributes, cutoff)
    _reject_unresolved_expiries(reconciled, origin, cutoff)
    candidates: dict[str, list[Attribute]] = {}
    for observation in reconciled:
        if not _effective_at(observation, origin, cutoff):
            continue
        candidates.setdefault(observation.name, []).append(observation)
    chosen: dict[str, Attribute] = {}
    for name, eligible in candidates.items():
        if len(eligible) > 1 and any(
            row.valid_from is not None or row.valid_to is not None for row in eligible
        ):
            if any(
                _known_attribute_facts(row, cutoff)
                != _known_attribute_facts(eligible[0], cutoff)
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
            if (_utc(observation.available_at), observation.source_id) < (
                _utc(earlier.available_at),
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
        lineage[output_name] = _version_lineage(observation, cutoff)

    if (subject_transaction_id is None) != (subject_source_id is None):
        raise ValueError("Subject raw transaction ID requires its source ID")
    subject_matches = (
        {
            sale.economic_transfer_id
            for sale in transactions
            if sale.property_id == property.property_id
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
    prior = []
    for sale in transactions:
        if sale.property_id != property.property_id:
            continue
        if sale.source_id not in source_snapshot.source_ids:
            raise ValueError("Transaction source is absent from snapshot manifest")
        if sale.economic_transfer_id == excluded_transfer:
            continue
        if _utc(sale.close_at) <= cutoff and _utc(sale.available_at) <= cutoff:
            prior.append(sale)
    if prior:
        canonical = canonicalize_transactions(prior)
        eligible = tuple(sale for sale in canonical if sale.eligible_prior_sale)
        if eligible:
            latest = max(
                eligible,
                key=lambda row: (_utc(row.close_at), _utc(row.available_at)),
            )
            values["prior_sale_price"] = latest.price
            lineage["prior_sale_price"] = Lineage(
                latest.source_id, latest.close_at, latest.available_at
            )

    # OFF never reads listing_events; its events cannot affect this snapshot.
    del listing_events
    return FeatureSnapshot(
        property_id=property.property_id,
        origin=origin,
        mode="OFF",
        source_snapshot_id=source_snapshot.snapshot_id,
        values=MappingProxyType(values),
        lineage=MappingProxyType(lineage),
        snapshot_hash=_snapshot_hash(
            property.property_id, origin, source_snapshot, values, lineage
        ),
    )
