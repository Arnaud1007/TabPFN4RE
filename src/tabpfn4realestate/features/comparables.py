"""Point-in-time comparable eligibility, retrieval, and a simple price baseline."""

from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from math import asin, cos, isfinite, radians, sin, sqrt
from typing import Sequence

from tabpfn4realestate.data.schema import (
    Property,
    SourceSnapshot,
    Transaction,
    _instant,
    _utc,
    canonicalize_transactions,
)
from tabpfn4realestate.features.asof import (
    NoAvailablePropertyVersionError,
    _effective_at,
    _visible_property_version,
    select_property_version,
)


def _candidate_histories(
    candidate_properties: Sequence[Property],
) -> dict[str, tuple[Property, ...]]:
    grouped: dict[str, list[Property]] = {}
    for row in candidate_properties:
        grouped.setdefault(row.property_id, []).append(row)
    return {property_id: tuple(rows) for property_id, rows in grouped.items()}


def _candidate_at_sale(
    sale: Transaction,
    histories: dict[str, tuple[Property, ...]],
    subject: Property,
    source_snapshot: SourceSnapshot,
    origin: datetime,
) -> Property | None:
    versions = histories.get(sale.property_id)
    if versions is None or sale.property_id == subject.property_id:
        return None
    try:
        selected = select_property_version(
            sale.property_id,
            versions,
            sale.close_at,
            source_snapshot,
            known_at=origin,
        )
    except NoAvailablePropertyVersionError:
        return None
    if (
        _utc(selected.observed_at) > _utc(sale.close_at)
        or selected.country != subject.country
        or selected.property_type != subject.property_type
    ):
        return None
    return selected


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
    cutoff = min(_utc(origin), _utc(source_snapshot.as_of))
    if subject.source_id not in source_snapshot.source_ids:
        raise ValueError("Subject property source is absent from snapshot manifest")
    if not _effective_at(subject, origin, cutoff):
        raise ValueError(
            "Subject property version was unavailable or invalid at origin"
        )

    for candidate in candidate_properties:
        if (
            _utc(candidate.observed_at) <= cutoff
            and _utc(candidate.available_at) <= cutoff
            and candidate.source_id not in source_snapshot.source_ids
        ):
            raise ValueError(
                "Candidate property source is absent from snapshot manifest"
            )

    histories = _candidate_histories(candidate_properties)
    visible_sales = tuple(
        sale
        for sale in transactions
        if sale.source_id in source_snapshot.source_ids
        and _utc(sale.close_at) <= cutoff
        and _utc(sale.available_at) <= cutoff
    )
    canonical = canonicalize_transactions(visible_sales)
    return tuple(
        sorted(
            (
                sale
                for sale in canonical
                if sale.economic_transfer_id != subject_economic_transfer_id
                and sale.eligible_prior_sale
                and _candidate_at_sale(
                    sale, histories, subject, source_snapshot, origin
                )
                is not None
            ),
            key=lambda sale: (_utc(sale.close_at), sale.economic_transfer_id),
        )
    )


_SQFT_PER_SQM = Decimal("10.76391041671")
_EARTH_RADIUS_KM = 6371.0088


@dataclass(frozen=True)
class ComparableConfig:
    """Frozen retrieval settings; certification must fit choices on development data."""

    n_neighbors: int = 5
    sale_window_months: int = 12
    radii_km: tuple[float, ...] = (2.0, 10.0, 30.0)
    min_comparables: int = 3
    distance_scale_km: float = 1.0
    recency_scale_days: float = 365.0
    area_scale_ratio: float = 0.25

    def __post_init__(self) -> None:
        if any(
            type(value) is not int or value < 1
            for value in (
                self.n_neighbors,
                self.sale_window_months,
                self.min_comparables,
            )
        ):
            raise ValueError(
                "Comparable counts and sale window must be positive integers"
            )
        if self.min_comparables > self.n_neighbors:
            raise ValueError("min_comparables cannot exceed n_neighbors")
        if (
            not isinstance(self.radii_km, tuple)
            or not self.radii_km
            or any(
                type(radius) not in {int, float} or not isfinite(radius) or radius <= 0
                for radius in self.radii_km
            )
        ):
            raise ValueError("radii_km must contain positive finite distances")
        if any(left >= right for left, right in zip(self.radii_km, self.radii_km[1:])):
            raise ValueError("radii_km must increase strictly")
        if any(
            not isfinite(scale) or scale <= 0
            for scale in (
                self.distance_scale_km,
                self.recency_scale_days,
                self.area_scale_ratio,
            )
        ):
            raise ValueError("Comparable scales must be positive and finite")


@dataclass(frozen=True)
class RankedComparable:
    property: Property
    sale: Transaction
    distance_km: float
    score: float
    weight: float


@dataclass(frozen=True)
class ComparableResult:
    subject: Property
    origin: datetime
    source_snapshot: SourceSnapshot
    comparables: tuple[RankedComparable, ...]
    support: str
    radius_km: float
    sale_window_months: int


def _square_feet(property: Property) -> Decimal | None:
    if property.living_area is None:
        return None
    if property.living_area_unit == "sqft":
        return property.living_area
    return property.living_area * _SQFT_PER_SQM


def _months_before(origin: datetime, months: int) -> datetime:
    year, month = divmod(origin.year * 12 + origin.month - 1 - months, 12)
    if year < 1:
        raise ValueError("Sale window precedes supported calendar dates")
    day = min(origin.day, monthrange(year, month + 1)[1])
    return origin.replace(year=year, month=month + 1, day=day)


def _distance_km(subject: Property, candidate: Property) -> float:
    if subject.latitude is None or subject.longitude is None:
        raise ValueError("Subject coordinates are required for comparable retrieval")
    if candidate.latitude is None or candidate.longitude is None:
        raise ValueError("Candidate coordinates are required for distance calculation")
    lat1, lon1 = radians(float(subject.latitude)), radians(float(subject.longitude))
    lat2, lon2 = radians(float(candidate.latitude)), radians(float(candidate.longitude))
    half_chord = (
        sin((lat2 - lat1) / 2) ** 2
        + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * _EARTH_RADIUS_KM * asin(sqrt(min(1.0, half_chord)))


def retrieve_comparables(
    subject: Property,
    origin: datetime,
    source_snapshot: SourceSnapshot,
    *,
    candidate_properties: Sequence[Property],
    transactions: Sequence[Transaction],
    config: ComparableConfig,
    subject_economic_transfer_id: str | None = None,
) -> ComparableResult:
    """Rank visible neighboring sales without inspecting their target prices."""
    _instant(origin, "origin")
    if subject.latitude is None or subject.longitude is None:
        raise ValueError("Subject coordinates are required for comparable retrieval")
    eligible = eligible_comparable_sales(
        subject,
        origin,
        source_snapshot,
        candidate_properties=candidate_properties,
        transactions=transactions,
        subject_economic_transfer_id=subject_economic_transfer_id,
    )
    cutoff = min(_utc(origin), _utc(source_snapshot.as_of))
    visible_subject = _visible_property_version(subject, cutoff)
    subject_area = _square_feet(subject)
    if subject_area is None:
        return ComparableResult(
            visible_subject,
            origin,
            source_snapshot,
            (),
            "low",
            config.radii_km[-1],
            config.sale_window_months,
        )
    histories = _candidate_histories(candidate_properties)
    latest_by_property: dict[str, Transaction] = {}
    window_start = _months_before(_utc(origin), config.sale_window_months)
    for sale in eligible:
        if _utc(sale.close_at) < window_start:
            continue
        previous = latest_by_property.get(sale.property_id)
        if previous is None or (
            _utc(sale.close_at),
            _utc(sale.available_at),
            sale.economic_transfer_id,
        ) > (
            _utc(previous.close_at),
            _utc(previous.available_at),
            previous.economic_transfer_id,
        ):
            latest_by_property[sale.property_id] = sale

    ranked: list[RankedComparable] = []
    for sale in latest_by_property.values():
        property = _candidate_at_sale(sale, histories, subject, source_snapshot, origin)
        if property is None:
            raise ValueError("Eligible comparable lost its property version")
        candidate_area = _square_feet(property)
        if (
            candidate_area is None
            or property.latitude is None
            or property.longitude is None
        ):
            continue
        distance = _distance_km(subject, property)
        recency_days = (_utc(origin) - _utc(sale.close_at)).total_seconds() / 86400
        area_difference = float(abs(candidate_area.ln() - subject_area.ln()))
        score = (
            distance / config.distance_scale_km
            + recency_days / config.recency_scale_days
            + area_difference / config.area_scale_ratio
        )
        ranked.append(
            RankedComparable(property, sale, distance, score, 1 / (1 + score))
        )
    ranked.sort(key=lambda item: (item.score, item.sale.economic_transfer_id))

    selected: tuple[RankedComparable, ...] = ()
    selected_radius = config.radii_km[-1]
    for radius in config.radii_km:
        selected = tuple(item for item in ranked if item.distance_km <= radius)[
            : config.n_neighbors
        ]
        selected_radius = radius
        if len(selected) >= config.min_comparables:
            break
    support = "supported" if len(selected) >= config.min_comparables else "low"
    return ComparableResult(
        visible_subject,
        origin,
        source_snapshot,
        selected,
        support,
        selected_radius,
        config.sale_window_months,
    )


def retrieve_comparables_from_versions(
    subject_property_id: str,
    subject_versions: Sequence[Property],
    origin: datetime,
    source_snapshot: SourceSnapshot,
    *,
    candidate_properties: Sequence[Property],
    transactions: Sequence[Transaction],
    config: ComparableConfig,
    subject_economic_transfer_id: str | None = None,
) -> ComparableResult:
    """Resolve the subject at origin and each candidate at its sale date."""
    subject = select_property_version(
        subject_property_id, subject_versions, origin, source_snapshot
    )
    return retrieve_comparables(
        subject,
        origin,
        source_snapshot,
        candidate_properties=candidate_properties,
        transactions=transactions,
        config=config,
        subject_economic_transfer_id=subject_economic_transfer_id,
    )


def comparable_price_per_area(
    subject: Property,
    origin: datetime,
    source_snapshot: SourceSnapshot,
    result: ComparableResult,
) -> Decimal | None:
    """Weighted median USD per square foot times subject area, if support suffices."""
    _instant(origin, "origin")
    visible_subject = _visible_property_version(
        subject, min(_utc(origin), _utc(source_snapshot.as_of))
    )
    if (
        replace(
            visible_subject,
            observed_at=result.subject.observed_at,
            available_at=result.subject.available_at,
        )
        != result.subject
        or _utc(origin) != _utc(result.origin)
        or replace(source_snapshot, as_of=result.source_snapshot.as_of)
        != result.source_snapshot
        or _utc(subject.observed_at) != _utc(result.subject.observed_at)
        or _utc(subject.available_at) != _utc(result.subject.available_at)
        or _utc(source_snapshot.as_of) != _utc(result.source_snapshot.as_of)
    ):
        raise ValueError("Comparable result belongs to a different input context")
    subject_area = _square_feet(subject)
    if subject_area is None or result.support != "supported":
        return None
    priced = []
    for item in result.comparables:
        area = _square_feet(item.property)
        if area is None:
            raise ValueError("Ranked comparable is missing a living area")
        priced.append(
            (item.sale.price / area, item.sale.economic_transfer_id, item.weight)
        )
    priced.sort()
    threshold = sum(weight for _, _, weight in priced) / 2
    accumulated = 0.0
    for price_per_sqft, _, weight in priced:
        accumulated += weight
        if accumulated >= threshold:
            return price_per_sqft * subject_area
    raise AssertionError("Positive comparable weights must reach the median threshold")
