"""A guarded, deliberately simple OFF baseline for synthetic U1 integration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
import re
from statistics import median
from types import MappingProxyType

from tabpfn4realestate.data.schema import (
    Attribute,
    ListingEvent,
    Property,
    SourceSnapshot,
    Transaction,
    _instant,
    _matches_utc_horizon,
    _utc,
)
from tabpfn4realestate.features.asof import FeatureSnapshot, assemble_snapshot
from tabpfn4realestate.models.guards import (
    FeatureDefinition,
    TrainingPartition,
    validate_feature_columns,
)


CORE_OFF_FEATURES = MappingProxyType(
    {
        name: FeatureDefinition(name)
        for name in (
            "property_type",
            "living_area",
            "living_area_unit",
            "living_area_state",
            "condition",
            "condition_state",
            "bedrooms",
            "bedrooms_state",
            "year_built",
            "year_built_state",
            "prior_sale_price",
        )
    }
)


def label_row_id(label: Transaction) -> str:
    """Group all source records of one economic transfer in the same split."""
    return label.economic_transfer_id


@dataclass(frozen=True)
class TrainingExample:
    row_id: str
    property: Property
    origin: datetime
    source_snapshot: SourceSnapshot
    label: Transaction
    attributes: tuple[Attribute, ...] = ()
    transactions: tuple[Transaction, ...] = ()
    listing_events: tuple[ListingEvent, ...] = ()

    def __post_init__(self) -> None:
        if any(
            not isinstance(records, tuple)
            for records in (self.attributes, self.transactions, self.listing_events)
        ):
            raise ValueError("Training event collections must be immutable tuples")


@dataclass(frozen=True)
class OffPrediction:
    amount: Decimal
    snapshot: FeatureSnapshot


def _checked_snapshot(snapshot: FeatureSnapshot, source: SourceSnapshot) -> None:
    validate_feature_columns(tuple(snapshot.values), CORE_OFF_FEATURES, mode="OFF")
    if set(snapshot.values) != set(snapshot.lineage):
        raise ValueError("Feature values and lineage do not match")
    cutoff = min(_utc(snapshot.origin), _utc(source.as_of))
    if snapshot.source_snapshot_id != source.snapshot_id:
        raise ValueError("Feature source snapshot does not match request")
    if any(
        entry.source_id not in source.source_ids
        or _utc(entry.observed_at) > cutoff
        or _utc(entry.available_at) > cutoff
        for entry in snapshot.lineage.values()
    ):
        raise ValueError("OFF feature has invalid source or future lineage")


def _predict_off_median(
    amount: Decimal,
    training_cutoff: datetime,
    property: Property,
    origin: datetime,
    source_snapshot: SourceSnapshot,
    *,
    attributes: tuple[Attribute, ...],
    transactions: tuple[Transaction, ...],
    listing_events: tuple[ListingEvent, ...],
    subject_economic_transfer_id: str | None,
) -> OffPrediction:
    _instant(origin, "origin")
    if _utc(origin) < _utc(training_cutoff):
        raise ValueError("Prediction origin predates model training cutoff")
    snapshot = assemble_snapshot(
        property,
        origin,
        "OFF",
        source_snapshot,
        attributes=attributes,
        transactions=transactions,
        listing_events=listing_events,
        subject_economic_transfer_id=subject_economic_transfer_id,
    )
    _checked_snapshot(snapshot, source_snapshot)
    return OffPrediction(amount, snapshot)


@dataclass(frozen=True)
class GuardedOffMedian:
    amount: Decimal
    train_row_ids: tuple[str, ...]
    feature_snapshot_hashes: tuple[str, ...]
    training_cutoff: datetime

    def save(self, path: Path) -> str:
        """Publish the synthetic baseline bundle once; return its digest."""
        from tabpfn4realestate.models.bundle import save_off_median_bundle

        return save_off_median_bundle(self, path)

    @classmethod
    def load(cls, path: Path, *, expected_sha256: str) -> ServingOffMedian:
        """Read the serving view of a trusted synthetic bundle."""
        from tabpfn4realestate.models.bundle import load_off_median_bundle

        return load_off_median_bundle(path, expected_sha256=expected_sha256)

    def __post_init__(self) -> None:
        _instant(self.training_cutoff, "training_cutoff")
        if (
            not isinstance(self.amount, Decimal)
            or not self.amount.is_finite()
            or self.amount <= 0
        ):
            raise ValueError("OFF baseline amount must be a positive finite Decimal")
        if (
            not isinstance(self.train_row_ids, tuple)
            or not isinstance(self.feature_snapshot_hashes, tuple)
            or not self.train_row_ids
            or len(self.train_row_ids) != len(self.feature_snapshot_hashes)
            or len(set(self.train_row_ids)) != len(self.train_row_ids)
        ):
            raise ValueError("OFF baseline training manifest is invalid")
        if any(
            not isinstance(row_id, str) or not row_id or row_id != row_id.strip()
            for row_id in self.train_row_ids
        ):
            raise ValueError("OFF baseline training row ID is invalid")
        if any(
            not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None
            for value in self.feature_snapshot_hashes
        ):
            raise ValueError("OFF baseline feature hash is invalid")

    @classmethod
    def fit(
        cls,
        examples: tuple[TrainingExample, ...],
        partition: TrainingPartition,
        *,
        training_cutoff: datetime,
    ) -> GuardedOffMedian:
        _instant(training_cutoff, "training_cutoff")
        if not examples:
            raise ValueError("OFF baseline needs training examples")
        row_ids = tuple(row.row_id for row in examples)
        if len(set(row_ids)) != len(row_ids):
            raise ValueError("Training row IDs must be unique")
        if set(row_ids) & partition.reserved_row_ids or not set(row_ids).issubset(
            partition.train_row_ids
        ):
            raise ValueError(
                "OFF baseline fit includes reserved or unregistered row IDs"
            )
        if any(row.row_id != label_row_id(row.label) for row in examples):
            raise ValueError("Training row ID does not match label identity")
        transfers = tuple(row.label.economic_transfer_id for row in examples)
        if len(set(transfers)) != len(transfers):
            raise ValueError("Duplicate economic transfer in training labels")
        prices: list[Decimal] = []
        hashes: list[str] = []
        for row in examples:
            if row.label.property_id != row.property.property_id:
                raise ValueError("Training label property does not match subject")
            if row.label.source_id not in row.source_snapshot.source_ids:
                raise ValueError("Training label source is absent from manifest")
            if not _matches_utc_horizon(row.origin, row.label.close_at, 90):
                raise ValueError("Training label does not match 90-day origin")
            if (
                _utc(row.label.available_at) <= _utc(row.origin)
                or _utc(row.label.close_at) > _utc(training_cutoff)
                or _utc(row.label.available_at) > _utc(training_cutoff)
                or not row.label.eligible_prior_sale
            ):
                raise ValueError("Training label is unavailable or ineligible")
            snapshot = assemble_snapshot(
                row.property,
                row.origin,
                "OFF",
                row.source_snapshot,
                attributes=row.attributes,
                transactions=row.transactions,
                listing_events=row.listing_events,
                subject_economic_transfer_id=row.label.economic_transfer_id,
            )
            _checked_snapshot(snapshot, row.source_snapshot)
            prices.append(row.label.price)
            hashes.append(snapshot.snapshot_hash)
        return cls(median(prices), row_ids, tuple(hashes), training_cutoff)

    def predict(
        self,
        property: Property,
        origin: datetime,
        source_snapshot: SourceSnapshot,
        *,
        attributes: tuple[Attribute, ...] = (),
        transactions: tuple[Transaction, ...] = (),
        listing_events: tuple[ListingEvent, ...] = (),
        subject_economic_transfer_id: str | None = None,
    ) -> OffPrediction:
        return _predict_off_median(
            self.amount,
            self.training_cutoff,
            property,
            origin,
            source_snapshot,
            attributes=attributes,
            transactions=transactions,
            listing_events=listing_events,
            subject_economic_transfer_id=subject_economic_transfer_id,
        )


@dataclass(frozen=True)
class ServingOffMedian:
    """Serving view without training row identifiers or row-level feature hashes."""

    amount: Decimal
    training_cutoff: datetime
    train_count: int
    feature_snapshot_hashes_sha256: str

    def __post_init__(self) -> None:
        _instant(self.training_cutoff, "training_cutoff")
        if (
            not isinstance(self.amount, Decimal)
            or not self.amount.is_finite()
            or self.amount <= 0
        ):
            raise ValueError("OFF baseline amount must be a positive finite Decimal")
        if type(self.train_count) is not int or self.train_count <= 0:
            raise ValueError("OFF baseline train count must be a positive integer")
        if (
            type(self.feature_snapshot_hashes_sha256) is not str
            or re.fullmatch(r"[0-9a-f]{64}", self.feature_snapshot_hashes_sha256)
            is None
        ):
            raise ValueError("OFF baseline feature manifest hash is invalid")

    @classmethod
    def load(cls, path: Path, *, expected_sha256: str) -> ServingOffMedian:
        from tabpfn4realestate.models.bundle import load_off_median_bundle

        return load_off_median_bundle(path, expected_sha256=expected_sha256)

    def predict(
        self,
        property: Property,
        origin: datetime,
        source_snapshot: SourceSnapshot,
        *,
        attributes: tuple[Attribute, ...] = (),
        transactions: tuple[Transaction, ...] = (),
        listing_events: tuple[ListingEvent, ...] = (),
        subject_economic_transfer_id: str | None = None,
    ) -> OffPrediction:
        return _predict_off_median(
            self.amount,
            self.training_cutoff,
            property,
            origin,
            source_snapshot,
            attributes=attributes,
            transactions=transactions,
            listing_events=listing_events,
            subject_economic_transfer_id=subject_economic_transfer_id,
        )
