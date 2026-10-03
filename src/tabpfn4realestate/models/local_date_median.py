"""Guarded calendar-date OFF median for synthetic US integration checks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from hashlib import sha256
import json
import re
from statistics import median
from typing import Mapping, Sequence

from tabpfn4realestate.data.local_date_sale import LocalDateSale
from tabpfn4realestate.data.local_date_facts import (
    DatePublishedAttribute,
    DatePublishedProperty,
)
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
from tabpfn4realestate.evaluation.calendar_schedule import CalendarOriginRef
from tabpfn4realestate.evaluation.chronological_plan import (
    ChronologicalMaturityRef,
    ChronologicalPlan,
    build_chronological_plan,
    origin_policy_hash,
)
from tabpfn4realestate.evaluation.local_dates import (
    DateOnlyAvailability,
    LocalDateOrigin,
    availability_cutoff_utc,
    derive_local_date_origin,
)
from tabpfn4realestate.features.asof import (
    LOCAL_DATE_ASSEMBLER_POLICY_VERSION,
    LOCAL_DATE_ASSEMBLER_POLICY_VERSION_V2,
    LocalDateFeatureSnapshot,
    assemble_local_date_snapshot,
)
from tabpfn4realestate.features.asof_local_date import assemble_local_date_snapshot_v2
from tabpfn4realestate.features.asof_timing import _local_boundary
from tabpfn4realestate.models.guards import validate_feature_columns
from tabpfn4realestate.models.off_baseline import CORE_OFF_FEATURES


_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


@dataclass(frozen=True)
class CalendarTrainingExample:
    row_id: str
    property: Property | DatePublishedProperty
    origin: LocalDateOrigin
    source_snapshot: SourceSnapshot
    label: LocalDateSale
    attributes: tuple[Attribute | DatePublishedAttribute, ...] = ()
    transactions: tuple[Transaction | LocalDateSale, ...] = ()
    listing_events: tuple[ListingEvent, ...] = ()

    def __post_init__(self) -> None:
        _identifier(self.row_id, "row_id")
        if not isinstance(
            self.property, (Property, DatePublishedProperty)
        ) or not isinstance(self.source_snapshot, SourceSnapshot):
            raise ValueError("Calendar example needs a property and source manifest")
        if not isinstance(self.origin, LocalDateOrigin) or not isinstance(
            self.label, LocalDateSale
        ):
            raise ValueError("Calendar example needs a local origin and date-only sale")
        if any(
            not isinstance(records, tuple)
            for records in (self.attributes, self.transactions, self.listing_events)
        ):
            raise ValueError("Training event collections must be immutable tuples")


@dataclass(frozen=True)
class LocalDateOffPrediction:
    amount: Decimal
    snapshot: LocalDateFeatureSnapshot


def _check_snapshot(
    snapshot: LocalDateFeatureSnapshot,
    source: SourceSnapshot,
    *,
    feature_policy_version: str = LOCAL_DATE_ASSEMBLER_POLICY_VERSION,
) -> None:
    validate_feature_columns(tuple(snapshot.values), CORE_OFF_FEATURES, mode="OFF")
    if set(snapshot.values) != set(snapshot.lineage):
        raise ValueError("Feature values and lineage do not match")
    if snapshot.source_snapshot_id != source.snapshot_id:
        raise ValueError("Feature source snapshot does not match request")
    boundary = _local_boundary(
        snapshot.origin,
        source,
        allow_date_only=feature_policy_version
        == LOCAL_DATE_ASSEMBLER_POLICY_VERSION_V2,
    )
    if any(
        entry.source_id not in source.source_ids
        or not boundary.known_by(entry.observed_at)
        or not boundary.known_by(entry.available_at)
        or (
            entry.valid_to_available_at is not None
            and not boundary.known_by(entry.valid_to_available_at)
        )
        for entry in snapshot.lineage.values()
    ):
        raise ValueError("OFF feature has invalid source or future lineage")


def _training_row_record(
    row: CalendarTrainingExample, snapshot: LocalDateFeatureSnapshot
) -> dict[str, object]:
    """Bind accepted label facts and feature snapshots to a replayable digest."""
    label = row.label
    publication = (
        {
            "kind": "local_date",
            "date": label.available_at.value.isoformat(),
            "zone": label.available_at.zone_key,
        }
        if isinstance(label.available_at, DateOnlyAvailability)
        else {"kind": "timestamp", "utc": _utc(label.available_at).isoformat()}
    )
    return {
        "row_id": row.row_id,
        "feature_snapshot_sha256": snapshot.snapshot_hash,
        "source_snapshot": {
            "snapshot_id": row.source_snapshot.snapshot_id,
            "source_ids": row.source_snapshot.source_ids,
            "as_of_utc": _utc(row.source_snapshot.as_of).isoformat(),
        },
        "label": {
            "transaction_id": label.transaction_id,
            "economic_transfer_id": label.economic_transfer_id,
            "property_id": label.property_id,
            "close_date": label.close_date.isoformat(),
            "close_zone_key": label.close_zone_key,
            "available_at": publication,
            "price": str(label.price),
            "currency": label.currency,
            "source_id": label.source_id,
            "scope": label.scope,
            "consideration_type": label.consideration_type,
            "arm_length_status": label.arm_length_status,
            "adjustment_flags": label.adjustment_flags,
        },
    }


def _verified_plan(
    plan: ChronologicalPlan,
    origins: Sequence[CalendarOriginRef],
    zones: Mapping[str, str],
    maturity: Sequence[ChronologicalMaturityRef],
    source_snapshot_sha256: str,
) -> dict[str, tuple[CalendarOriginRef, ChronologicalMaturityRef]]:
    if not isinstance(plan, ChronologicalPlan):
        raise ValueError("A frozen chronological plan is required")
    if (
        not isinstance(source_snapshot_sha256, str)
        or _SHA256.fullmatch(source_snapshot_sha256) is None
    ):
        raise ValueError("source_snapshot_sha256 must be a lowercase SHA-256 digest")
    if plan.schedule.source_snapshot_sha256 != source_snapshot_sha256:
        raise ValueError("Source snapshot digest differs from frozen schedule")
    if plan.schedule.origin_policy_sha256 != origin_policy_hash(origins, zones):
        raise ValueError("Origin policy differs from frozen schedule")
    cutoffs = (
        *(window.fit_cutoff_utc for window in plan.development),
        plan.final_fit.fit_cutoff_utc,
    )
    rebuilt = build_chronological_plan(
        plan.schedule, origins, zones, maturity, fit_cutoffs_utc=cutoffs
    )
    if rebuilt != plan:
        raise ValueError("Chronological plan membership or hash was changed")
    origin_by_id = {row.row_id: row for row in origins}
    maturity_by_id = {row.row_id: row for row in maturity}
    return {
        row_id: (origin_by_id[row_id], maturity_by_id[row_id])
        for row_id in plan.final_fit.train_row_ids
    }


@dataclass(frozen=True)
class GuardedLocalDateMedian:
    amount: Decimal
    train_row_ids: tuple[str, ...]
    feature_snapshot_hashes: tuple[str, ...]
    training_cutoff: datetime
    plan_hash: str
    schedule_hash: str
    origin_policy_sha256: str
    source_snapshot_sha256: str
    training_rows_sha256: str
    allowed_source_ids: tuple[str, ...]
    feature_policy_version: str = LOCAL_DATE_ASSEMBLER_POLICY_VERSION
    # Descriptive only. Provenance claims require independent artifact replay.
    source_binding_kind: str = "caller_declared_synthetic_v1"

    def __post_init__(self) -> None:
        _instant(self.training_cutoff, "training_cutoff")
        if (
            not isinstance(self.amount, Decimal)
            or not self.amount.is_finite()
            or self.amount <= 0
        ):
            raise ValueError("Calendar median amount must be positive and finite")
        if (
            not isinstance(self.train_row_ids, tuple)
            or not self.train_row_ids
            or tuple(sorted(set(self.train_row_ids))) != self.train_row_ids
            or not isinstance(self.feature_snapshot_hashes, tuple)
            or len(self.feature_snapshot_hashes) != len(self.train_row_ids)
        ):
            raise ValueError("Calendar training manifest is invalid")
        for row_id in self.train_row_ids:
            _identifier(row_id, "training row ID")
        for digest in (
            self.plan_hash,
            self.schedule_hash,
            self.origin_policy_sha256,
            self.source_snapshot_sha256,
            self.training_rows_sha256,
            *self.feature_snapshot_hashes,
        ):
            if not isinstance(digest, str) or _SHA256.fullmatch(digest) is None:
                raise ValueError("Calendar model digest is invalid")
        if (
            not isinstance(self.allowed_source_ids, tuple)
            or not self.allowed_source_ids
            or tuple(sorted(set(self.allowed_source_ids))) != self.allowed_source_ids
        ):
            raise ValueError("Calendar model source contract is invalid")
        for source_id in self.allowed_source_ids:
            _identifier(source_id, "source ID")
        if self.feature_policy_version not in {
            LOCAL_DATE_ASSEMBLER_POLICY_VERSION,
            LOCAL_DATE_ASSEMBLER_POLICY_VERSION_V2,
        }:
            raise ValueError("Unsupported local-date feature policy")
        if self.source_binding_kind not in {
            "caller_declared_synthetic_v1",
            "synthetic_capture_bytes_v1",
        }:
            raise ValueError("Unsupported synthetic source binding")

    @classmethod
    def fit(
        cls,
        examples: tuple[CalendarTrainingExample, ...],
        plan: ChronologicalPlan,
        origins: Sequence[CalendarOriginRef],
        zones: Mapping[str, str],
        maturity: Sequence[ChronologicalMaturityRef],
        *,
        source_snapshot_sha256: str,
        feature_policy_version: str = LOCAL_DATE_ASSEMBLER_POLICY_VERSION,
    ) -> GuardedLocalDateMedian:
        if feature_policy_version not in {
            LOCAL_DATE_ASSEMBLER_POLICY_VERSION,
            LOCAL_DATE_ASSEMBLER_POLICY_VERSION_V2,
        }:
            raise ValueError("Unsupported local-date feature policy")
        if not isinstance(examples, tuple) or not examples:
            raise ValueError("Calendar fit needs immutable training examples")
        membership = _verified_plan(
            plan, origins, zones, maturity, source_snapshot_sha256
        )
        if len(examples) != len(membership) or {row.row_id for row in examples} != set(
            membership
        ):
            raise ValueError("Calendar fit must use exact matured training membership")
        if any(not isinstance(row, CalendarTrainingExample) for row in examples):
            raise ValueError("Calendar fit needs validated examples")
        by_id = {row.row_id: row for row in examples}
        if len(by_id) != len(examples):
            raise ValueError("Duplicate economic transfer in calendar fit")
        source_transactions = {
            (row.label.source_id, row.label.transaction_id) for row in examples
        }
        if len(source_transactions) != len(examples):
            raise ValueError("Duplicate source transaction in calendar fit")

        prices: list[Decimal] = []
        hashes: list[str] = []
        training_rows: list[dict[str, object]] = []
        source_ids: set[str] = set()
        cutoff = _utc(plan.final_fit.fit_cutoff_utc)
        for row_id in sorted(by_id):
            row = by_id[row_id]
            origin_ref, maturity_ref = membership[row_id]
            if (
                row.label.economic_transfer_id != row_id
                or row.property.property_id != origin_ref.property_id
            ):
                raise ValueError(
                    "Training label or property identity differs from plan"
                )
            if row.label.property_id != row.property.property_id:
                raise ValueError("Training label property does not match subject")
            if row.label.source_id not in row.source_snapshot.source_ids:
                raise ValueError("Training label source is absent from manifest")
            if not row.label.eligible_sale:
                raise ValueError("Training label is not an eligible gross sale")
            if (
                row.label.close_date != maturity_ref.close_date
                or row.label.available_at != maturity_ref.available_at
                or row.label.close_zone_key != zones[row_id]
                or row.origin
                != derive_local_date_origin(row.label.close_date, zones[row_id])
                or row.origin.origin_date != origin_ref.origin_date
            ):
                raise ValueError("Sale timing differs from the frozen local origin")
            if availability_cutoff_utc(row.label.available_at) > cutoff:
                raise ValueError("Training sale label has not matured by fit cutoff")
            assembler = (
                assemble_local_date_snapshot_v2
                if feature_policy_version == LOCAL_DATE_ASSEMBLER_POLICY_VERSION_V2
                else assemble_local_date_snapshot
            )
            snapshot = assembler(
                row.property,
                row.origin,
                "OFF",
                row.source_snapshot,
                attributes=row.attributes,
                transactions=row.transactions,
                listing_events=row.listing_events,
                subject_economic_transfer_id=row.label.economic_transfer_id,
            )
            _check_snapshot(
                snapshot,
                row.source_snapshot,
                feature_policy_version=feature_policy_version,
            )
            prices.append(row.label.price)
            hashes.append(snapshot.snapshot_hash)
            training_rows.append(_training_row_record(row, snapshot))
            source_ids.add(row.label.source_id)
            source_ids.update(entry.source_id for entry in snapshot.lineage.values())
        training_rows_sha256 = sha256(
            json.dumps(training_rows, sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            )
        ).hexdigest()
        return cls(
            median(prices),
            tuple(sorted(by_id)),
            tuple(hashes),
            cutoff,
            plan.plan_hash,
            plan.schedule.schedule_hash,
            plan.schedule.origin_policy_sha256,
            source_snapshot_sha256,
            training_rows_sha256,
            tuple(sorted(source_ids)),
            feature_policy_version,
        )

    def predict(
        self,
        property: Property | DatePublishedProperty,
        origin: LocalDateOrigin,
        source_snapshot: SourceSnapshot,
        *,
        attributes: tuple[Attribute | DatePublishedAttribute, ...] = (),
        transactions: tuple[Transaction | LocalDateSale, ...] = (),
        listing_events: tuple[ListingEvent, ...] = (),
    ) -> LocalDateOffPrediction:
        if not isinstance(origin, LocalDateOrigin):
            raise ValueError("Prediction origin must use the local-date protocol")
        if origin.cutoff_exclusive_utc <= _utc(self.training_cutoff):
            raise ValueError("Prediction origin predates model fit cutoff")
        if not set(source_snapshot.source_ids).issubset(self.allowed_source_ids):
            raise ValueError("Prediction source is outside training source contract")
        assembler = (
            assemble_local_date_snapshot_v2
            if self.feature_policy_version == LOCAL_DATE_ASSEMBLER_POLICY_VERSION_V2
            else assemble_local_date_snapshot
        )
        snapshot = assembler(
            property,
            origin,
            "OFF",
            source_snapshot,
            attributes=attributes,
            transactions=transactions,
            listing_events=listing_events,
        )
        _check_snapshot(
            snapshot,
            source_snapshot,
            feature_policy_version=self.feature_policy_version,
        )
        return LocalDateOffPrediction(self.amount, snapshot)
