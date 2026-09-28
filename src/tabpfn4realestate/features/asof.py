"""Conservative OFF feature assembly with per-value source lineage."""

from __future__ import annotations

from dataclasses import dataclass
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


def _snapshot_hash(
    property_id: str,
    origin: datetime,
    source_snapshot: SourceSnapshot,
    values: Mapping[str, str | int | Decimal],
    lineage: Mapping[str, Lineage],
) -> str:
    payload = {
        "property_id": property_id,
        "origin": _utc(origin).isoformat(),
        "mode": "OFF",
        "source_snapshot": {
            "snapshot_id": source_snapshot.snapshot_id,
            "source_ids": source_snapshot.source_ids,
            "as_of": _utc(source_snapshot.as_of).isoformat(),
        },
        "features": [
            {
                "name": name,
                "value": str(values[name]),
                "source_id": lineage[name].source_id,
                "observed_at": _utc(lineage[name].observed_at).isoformat(),
                "available_at": _utc(lineage[name].available_at).isoformat(),
            }
            for name in sorted(values)
        ],
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
    if _utc(property.observed_at) > cutoff or _utc(property.available_at) > cutoff:
        raise ValueError("Property version was unavailable at origin")

    property_lineage = Lineage(
        property.source_id, property.observed_at, property.available_at
    )
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

    chosen: dict[str, Attribute] = {}
    for observation in attributes:
        if observation.property_id != property.property_id:
            raise ValueError("Attribute property_id does not match requested property")
        if observation.source_id not in source_snapshot.source_ids:
            raise ValueError("Attribute source is absent from snapshot manifest")
        _validate_attribute(observation)
        if (
            _utc(observation.observed_at) > cutoff
            or _utc(observation.available_at) > cutoff
        ):
            continue
        earlier = chosen.get(observation.name)
        if earlier is None or _utc(observation.observed_at) > _utc(earlier.observed_at):
            chosen[observation.name] = observation
        elif _utc(observation.observed_at) == _utc(earlier.observed_at):
            if (
                observation.value != earlier.value
                or observation.unit != earlier.unit
                or observation.missing_state != earlier.missing_state
            ):
                raise ValueError(f"Ambiguous attribute: {observation.name}")
            if (_utc(observation.available_at), observation.source_id) < (
                _utc(earlier.available_at),
                earlier.source_id,
            ):
                chosen[observation.name] = observation
    for name, observation in chosen.items():
        output_name = name if observation.value is not None else f"{name}_state"
        values[output_name] = (
            observation.value
            if observation.value is not None
            else observation.missing_state
        )
        lineage[output_name] = Lineage(
            observation.source_id, observation.observed_at, observation.available_at
        )

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
