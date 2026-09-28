"""Distinguish operational repeat-property tests from unseen-property tests."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from typing import Sequence

from tabpfn4realestate.data.schema import _identifier, _instant


@dataclass(frozen=True)
class OriginRef:
    """Outcome-free row metadata; row_id is the canonical economic transfer ID."""

    row_id: str
    property_id: str
    origin: datetime

    def __post_init__(self) -> None:
        _identifier(self.row_id, "row_id")
        _identifier(self.property_id, "property_id")
        _instant(self.origin, "origin")


@dataclass(frozen=True)
class LabelMaturity:
    """Training-side label timing, never supplied for a reserved validation row."""

    row_id: str
    close_at: datetime
    available_at: datetime

    def __post_init__(self) -> None:
        _identifier(self.row_id, "row_id")
        _instant(self.close_at, "close_at")
        _instant(self.available_at, "available_at")
        if _utc(self.available_at) < _utc(self.close_at):
            raise ValueError("A sale label cannot be available before close")


@dataclass(frozen=True)
class TemporalFold:
    protocol_id: str
    training_cutoff: datetime
    validation_start: datetime
    validation_end: datetime
    train_row_ids: tuple[str, ...]
    validation_row_ids: tuple[str, ...]
    immature_row_ids: tuple[str, ...]
    split_hash: str


def _utc(value: datetime) -> datetime:
    return value.astimezone(timezone.utc)


def _utc_iso(value: datetime) -> str:
    return _utc(value).isoformat()


def _validate_fold_bounds(
    training_cutoff: datetime,
    validation_start: datetime,
    validation_end: datetime,
    horizon_days: int,
    protocol_id: str,
) -> None:
    for name, value in (
        ("training_cutoff", training_cutoff),
        ("validation_start", validation_start),
        ("validation_end", validation_end),
    ):
        _instant(value, name)
    _identifier(protocol_id, "protocol_id")
    if type(horizon_days) is not int or horizon_days <= 0:
        raise ValueError("horizon_days must be a positive integer")
    if _utc(training_cutoff) > _utc(validation_start) or _utc(validation_start) >= _utc(
        validation_end
    ):
        raise ValueError("Temporal fold boundaries are out of order")


def _index_origins(origins: Sequence[OriginRef]) -> dict[str, OriginRef]:
    indexed: dict[str, OriginRef] = {}
    for row in origins:
        if not isinstance(row, OriginRef) or row.row_id in indexed:
            raise ValueError("Origin rows must be unique OriginRef records")
        indexed[row.row_id] = row
    if not indexed:
        raise ValueError("Temporal fold needs origin rows")
    return indexed


def _index_training_maturity(
    labels: Sequence[LabelMaturity],
    origins: dict[str, OriginRef],
    training_candidate_ids: set[str],
    horizon_days: int,
) -> dict[str, LabelMaturity]:
    indexed: dict[str, LabelMaturity] = {}
    for label in labels:
        if not isinstance(label, LabelMaturity) or label.row_id in indexed:
            raise ValueError("Training maturity records must be unique")
        if label.row_id not in training_candidate_ids:
            raise ValueError("Maturity supplied for a reserved or unknown row")
        expected_close = origins[label.row_id].origin + timedelta(days=horizon_days)
        if _utc(label.close_at) != _utc(expected_close):
            raise ValueError(
                "Sale close date does not match the registered origin horizon"
            )
        indexed[label.row_id] = label
    if set(indexed) != training_candidate_ids:
        raise ValueError(
            "Every pre-cutoff origin needs training-side maturity metadata"
        )
    return indexed


def _fold_hash(
    fold: TemporalFold,
    origins: Sequence[OriginRef],
    training_maturity: Sequence[LabelMaturity],
    horizon_days: int,
) -> str:
    payload = {
        "protocol_id": fold.protocol_id,
        "horizon_days": horizon_days,
        "training_cutoff": _utc_iso(fold.training_cutoff),
        "validation_start": _utc_iso(fold.validation_start),
        "validation_end": _utc_iso(fold.validation_end),
        "origins": [
            (row.row_id, row.property_id, _utc_iso(row.origin))
            for row in sorted(origins, key=lambda item: item.row_id)
        ],
        "training_maturity": [
            (label.row_id, _utc_iso(label.close_at), _utc_iso(label.available_at))
            for label in sorted(training_maturity, key=lambda item: item.row_id)
        ],
        "train_row_ids": fold.train_row_ids,
        "validation_row_ids": fold.validation_row_ids,
        "immature_row_ids": fold.immature_row_ids,
    }
    return sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def build_temporal_fold(
    origins: Sequence[OriginRef],
    training_maturity: Sequence[LabelMaturity],
    *,
    training_cutoff: datetime,
    validation_start: datetime,
    validation_end: datetime,
    horizon_days: int = 90,
    protocol_id: str = "us_synthetic_rolling_v1",
) -> TemporalFold:
    """Freeze an origin-based fold without opening validation-row labels."""
    _validate_fold_bounds(
        training_cutoff, validation_start, validation_end, horizon_days, protocol_id
    )
    origin_by_id = _index_origins(origins)
    start_utc = _utc(validation_start)
    end_utc = _utc(validation_end)
    cutoff_utc = _utc(training_cutoff)
    validation_ids = tuple(
        row.row_id
        for row in sorted(origins, key=lambda item: (_utc(item.origin), item.row_id))
        if start_utc <= _utc(row.origin) < end_utc
    )
    if not validation_ids:
        raise ValueError("Validation interval contains no origins")
    training_candidate_ids = {
        row.row_id for row in origins if _utc(row.origin) < cutoff_utc
    }
    maturity_by_id = _index_training_maturity(
        training_maturity, origin_by_id, training_candidate_ids, horizon_days
    )

    train_ids = tuple(
        sorted(
            row_id
            for row_id, label in maturity_by_id.items()
            if _utc(label.available_at) <= cutoff_utc
        )
    )
    if not train_ids:
        raise ValueError("Temporal fold has no matured training labels")
    immature_ids = tuple(sorted(training_candidate_ids - set(train_ids)))
    fold = TemporalFold(
        protocol_id,
        training_cutoff,
        validation_start,
        validation_end,
        train_ids,
        validation_ids,
        immature_ids,
        "",
    )
    return replace(
        fold, split_hash=_fold_hash(fold, origins, training_maturity, horizon_days)
    )


def validate_property_split(
    train_property_ids: Sequence[str],
    test_property_ids: Sequence[str],
    protocol: str,
) -> None:
    if protocol not in {"unseen_property", "future_sales"}:
        raise ValueError(f"Unknown property split protocol: {protocol}")
    if not train_property_ids or not test_property_ids:
        raise ValueError("Both split partitions need property IDs")
    if any(
        not isinstance(value, str) or not value or value != value.strip()
        for value in (*train_property_ids, *test_property_ids)
    ):
        raise ValueError("Property IDs must be nonempty strings")
    if protocol == "unseen_property" and set(train_property_ids) & set(
        test_property_ids
    ):
        raise ValueError("Unseen-property split contains a repeat property")
