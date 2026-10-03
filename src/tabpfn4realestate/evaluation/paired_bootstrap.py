"""Synthetic paired comparison with property and space-time block resampling."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, localcontext
from fractions import Fraction
from hashlib import sha256
import json
import random
import re
from typing import Sequence

from tabpfn4realestate.data.schema import _identifier, _instant, _utc
from tabpfn4realestate.evaluation.metrics import PredictionRow


_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_METRIC_NAMES = ("mdape", "within_10", "signed_bias", "absolute_bias", "p90_ape")
_MIN_COMPONENTS = 20
_MIN_COMPONENTS_PER_MARKET = 2
_MAX_RESAMPLED_ROW_WORK = 100_000_000


@dataclass(frozen=True)
class ComparisonMeta:
    row_id: str
    property_id: str
    market_id: str
    geographic_block_id: str
    temporal_block_id: str
    origin: datetime

    def __post_init__(self) -> None:
        for name in (
            "row_id",
            "property_id",
            "market_id",
            "geographic_block_id",
            "temporal_block_id",
        ):
            _identifier(getattr(self, name), name)
        _instant(self.origin, "origin")


@dataclass(frozen=True)
class ResamplingUnit:
    market_id: str
    cells: tuple[tuple[str, str], ...]
    row_ids: tuple[str, ...]


@dataclass(frozen=True)
class MetricDelta:
    mdape: Decimal
    within_10: Decimal
    signed_bias: Decimal
    absolute_bias: Decimal
    p90_ape: Decimal


@dataclass(frozen=True)
class Interval:
    lower: Decimal
    upper: Decimal


@dataclass(frozen=True)
class MetricIntervals:
    mdape: Interval
    within_10: Interval
    signed_bias: Interval
    absolute_bias: Interval
    p90_ape: Interval


@dataclass(frozen=True)
class ComparisonScope:
    point: MetricDelta
    ci95: MetricIntervals | None
    replicates: tuple[MetricDelta, ...]


@dataclass(frozen=True)
class PairedBootstrapResult:
    protocol_id: str
    status: str
    row_count: int
    market_count: int
    component_count: int
    components: tuple[ResamplingUnit, ...]
    comparison_hash: str
    seed: int
    draws_requested: int
    draws_completed: int
    pooled: ComparisonScope
    equal_market: ComparisonScope


def _index_prediction_rows(
    rows: Sequence[PredictionRow], name: str
) -> dict[str, PredictionRow]:
    indexed: dict[str, PredictionRow] = {}
    for row in rows:
        if not isinstance(row, PredictionRow) or row.row_id in indexed:
            raise ValueError(f"{name} row IDs must be unique PredictionRow records")
        indexed[row.row_id] = row
    if not indexed:
        raise ValueError(f"{name} requires prediction rows")
    return indexed


def _index_metadata(rows: Sequence[ComparisonMeta]) -> dict[str, ComparisonMeta]:
    indexed: dict[str, ComparisonMeta] = {}
    for row in rows:
        if not isinstance(row, ComparisonMeta) or row.row_id in indexed:
            raise ValueError("metadata row IDs must be unique ComparisonMeta records")
        indexed[row.row_id] = row
    if not indexed:
        raise ValueError("metadata requires rows")
    return indexed


def _validate_pairs(
    metadata: dict[str, ComparisonMeta],
    baseline: dict[str, PredictionRow],
    challenger: dict[str, PredictionRow],
) -> None:
    if set(metadata) != set(baseline) or set(metadata) != set(challenger):
        raise ValueError("metadata and both prediction row IDs must match exactly")
    for row_id in metadata:
        left = baseline[row_id]
        right = challenger[row_id]
        if left.actual != right.actual:
            raise ValueError(f"Paired actual prices differ for {row_id}")
        if (
            left.actual_currency != right.actual_currency
            or left.actual_currency != "USD"
        ):
            raise ValueError(f"Paired currency differs or is unsupported for {row_id}")
        if left.status != "estimated" or right.status != "estimated":
            raise ValueError(f"Both paired predictions must be estimated for {row_id}")
        if left.predicted_currency != "USD" or right.predicted_currency != "USD":
            raise ValueError(f"Paired prediction currency differs for {row_id}")


def _components(metadata: dict[str, ComparisonMeta]) -> tuple[ResamplingUnit, ...]:
    cell_for = {
        row_id: (row.market_id, row.geographic_block_id, row.temporal_block_id)
        for row_id, row in metadata.items()
    }
    parents = {cell: cell for cell in cell_for.values()}

    def root(cell: tuple[str, str, str]) -> tuple[str, str, str]:
        while parents[cell] != cell:
            cell = parents[cell]
        return cell

    properties: dict[str, list[tuple[str, str, str]]] = {}
    for row_id, row in sorted(metadata.items()):
        properties.setdefault(row.property_id, []).append(cell_for[row_id])
    for _, property_cells in sorted(properties.items()):
        markets = {cell[0] for cell in property_cells}
        if len(markets) != 1:
            raise ValueError("A property cannot cross markets in the comparison")
        roots = sorted({root(cell) for cell in property_cells})
        for cell_root in roots[1:]:
            parents[cell_root] = roots[0]

    grouped_cells: dict[tuple[str, str, str], set[tuple[str, str, str]]] = {}
    grouped_rows: dict[tuple[str, str, str], list[str]] = {}
    for row_id, cell in cell_for.items():
        component = root(cell)
        grouped_cells.setdefault(component, set()).add(cell)
        grouped_rows.setdefault(component, []).append(row_id)
    units = (
        ResamplingUnit(
            market_id=component[0],
            cells=tuple(
                sorted((cell[1], cell[2]) for cell in grouped_cells[component])
            ),
            row_ids=tuple(sorted(grouped_rows[component])),
        )
        for component in grouped_rows
    )
    return tuple(
        sorted(units, key=lambda unit: (unit.market_id, unit.cells, unit.row_ids))
    )


def _quantile(values: Sequence[Fraction], probability: Fraction) -> Fraction:
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = position.numerator // position.denominator
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _metrics(
    row_ids: Sequence[str],
    signed_errors: dict[str, Fraction],
) -> tuple[Fraction, Fraction, Fraction, Fraction, Fraction]:
    signed = [signed_errors[row_id] for row_id in row_ids]
    absolute = [abs(value) for value in signed]
    bias = _quantile(signed, Fraction(1, 2))
    return (
        _quantile(absolute, Fraction(1, 2)),
        Fraction(sum(value <= Fraction(1, 10) for value in absolute), len(absolute)),
        bias,
        abs(bias),
        _quantile(absolute, Fraction(9, 10)),
    )


def _difference(
    row_ids: Sequence[str],
    baseline_errors: dict[str, Fraction],
    challenger_errors: dict[str, Fraction],
) -> tuple[Fraction, Fraction, Fraction, Fraction, Fraction]:
    left = _metrics(row_ids, baseline_errors)
    right = _metrics(row_ids, challenger_errors)
    return tuple(
        challenger - baseline for baseline, challenger in zip(left, right, strict=True)
    )


def _equal_market_difference(
    market_rows: dict[str, tuple[str, ...]],
    baseline_errors: dict[str, Fraction],
    challenger_errors: dict[str, Fraction],
) -> tuple[Fraction, Fraction, Fraction, Fraction, Fraction]:
    differences = tuple(
        _difference(rows, baseline_errors, challenger_errors)
        for _, rows in sorted(market_rows.items())
    )
    return tuple(
        sum(values, Fraction(0)) / len(differences)
        for values in zip(*differences, strict=True)
    )


def _decimal(value: Fraction) -> Decimal:
    with localcontext() as context:
        context.prec = 28
        return Decimal(value.numerator) / Decimal(value.denominator)


def _delta(values: tuple[Fraction, ...]) -> MetricDelta:
    return MetricDelta(*(_decimal(value) for value in values))


def _decimal_quantile(values: Sequence[Decimal], probability: Decimal) -> Decimal:
    ordered = sorted(values)
    with localcontext() as context:
        context.prec = 40
        position = Decimal(len(ordered) - 1) * probability
        lower = int(position)
        weight = position - lower
        return (
            ordered[lower] * (1 - weight)
            + ordered[min(lower + 1, len(ordered) - 1)] * weight
        )


def _intervals(replicates: tuple[MetricDelta, ...]) -> MetricIntervals:
    return MetricIntervals(
        *(
            Interval(
                _decimal_quantile(values, Decimal("0.025")),
                _decimal_quantile(values, Decimal("0.975")),
            )
            for values in (
                tuple(getattr(rep, name) for rep in replicates)
                for name in _METRIC_NAMES
            )
        )
    )


def _canonical_decimal(value: Decimal) -> str:
    if value == 0:
        return "0"
    rendered = format(value, "f")
    return rendered.rstrip("0").rstrip(".") if "." in rendered else rendered


def _predicted_amount(row: PredictionRow) -> Decimal:
    if row.predicted is None:
        raise ValueError(f"Prediction is not estimated for {row.row_id}")
    return row.predicted


def _signed_error(row: PredictionRow) -> Fraction:
    actual = Fraction(row.actual)
    return (Fraction(_predicted_amount(row)) - actual) / actual


def _comparison_hash(
    metadata: dict[str, ComparisonMeta],
    baseline: dict[str, PredictionRow],
    challenger: dict[str, PredictionRow],
    components: tuple[ResamplingUnit, ...],
    config: dict[str, str | int],
) -> str:
    payload = {
        "config": config,
        "rows": [
            (
                row_id,
                row.property_id,
                row.market_id,
                row.geographic_block_id,
                row.temporal_block_id,
                _utc(row.origin).isoformat(),
                _canonical_decimal(baseline[row_id].actual),
                _canonical_decimal(_predicted_amount(baseline[row_id])),
                _canonical_decimal(_predicted_amount(challenger[row_id])),
                "USD",
            )
            for row_id, row in sorted(metadata.items())
        ],
        "components": [
            (component.market_id, component.cells, component.row_ids)
            for component in components
        ],
    }
    return sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def compare_paired_blocks(
    metadata: Sequence[ComparisonMeta],
    baseline_rows: Sequence[PredictionRow],
    challenger_rows: Sequence[PredictionRow],
    *,
    split_hash: str,
    block_plan_hash: str,
    draws: int = 5000,
    seed: int = 42,
    protocol_id: str = "us_synthetic_paired_bootstrap_v1",
) -> PairedBootstrapResult:
    """Compare complete paired estimates; never infer a real certification claim."""
    if protocol_id != "us_synthetic_paired_bootstrap_v1":
        raise ValueError("Only the synthetic paired-bootstrap protocol is supported")
    for name, value in (
        ("split_hash", split_hash),
        ("block_plan_hash", block_plan_hash),
    ):
        if not isinstance(value, str) or not _SHA256.fullmatch(value):
            raise ValueError(f"{name} must be a SHA-256 digest")
    if type(draws) is not int or not 100 <= draws <= 5000:
        raise ValueError("draws must be an integer between 100 and 5000")
    if type(seed) is not int or not 0 <= seed < 2**32:
        raise ValueError("seed must be a 32-bit unsigned integer")
    if any(len(rows) > 100_000 for rows in (metadata, baseline_rows, challenger_rows)):
        raise ValueError("Paired comparison exceeds the registered 100,000-row budget")

    indexed_meta = _index_metadata(metadata)
    baseline = _index_prediction_rows(baseline_rows, "baseline")
    challenger = _index_prediction_rows(challenger_rows, "challenger")
    _validate_pairs(indexed_meta, baseline, challenger)
    components = _components(indexed_meta)
    market_units: dict[str, tuple[ResamplingUnit, ...]] = {
        market: tuple(unit for unit in components if unit.market_id == market)
        for market in sorted({unit.market_id for unit in components})
    }
    baseline_errors = {row_id: _signed_error(row) for row_id, row in baseline.items()}
    challenger_errors = {
        row_id: _signed_error(row) for row_id, row in challenger.items()
    }
    row_ids = tuple(sorted(indexed_meta))
    market_rows = {
        market: tuple(
            sorted(
                row.row_id for row in indexed_meta.values() if row.market_id == market
            )
        )
        for market in market_units
    }
    pooled_point = _delta(_difference(row_ids, baseline_errors, challenger_errors))
    equal_point = _delta(
        _equal_market_difference(market_rows, baseline_errors, challenger_errors)
    )
    config: dict[str, str | int] = {
        "protocol_id": protocol_id,
        "split_hash": split_hash,
        "block_plan_hash": block_plan_hash,
        "draws": draws,
        "seed": seed,
        "minimum_components": _MIN_COMPONENTS,
        "minimum_components_per_market": _MIN_COMPONENTS_PER_MARKET,
    }
    digest = _comparison_hash(indexed_meta, baseline, challenger, components, config)
    sufficient = len(components) >= _MIN_COMPONENTS and all(
        len(units) >= _MIN_COMPONENTS_PER_MARKET for units in market_units.values()
    )
    if not sufficient:
        return PairedBootstrapResult(
            protocol_id,
            "INCONCLUSIVE",
            len(row_ids),
            len(market_units),
            len(components),
            components,
            digest,
            seed,
            draws,
            0,
            ComparisonScope(pooled_point, None, ()),
            ComparisonScope(equal_point, None, ()),
        )

    worst_draw_rows = sum(
        len(units) * max(len(unit.row_ids) for unit in units)
        for units in market_units.values()
    )
    if worst_draw_rows * draws > _MAX_RESAMPLED_ROW_WORK:
        raise ValueError(
            "Paired comparison exceeds the registered resampling work budget"
        )

    generator = random.Random(seed)
    pooled_replicates: list[MetricDelta] = []
    equal_replicates: list[MetricDelta] = []
    for _ in range(draws):
        sampled_markets = {
            market: tuple(
                row_id
                for _ in units
                for row_id in units[generator.randrange(len(units))].row_ids
            )
            for market, units in market_units.items()
        }
        sampled_rows = tuple(
            row_id
            for market in sorted(sampled_markets)
            for row_id in sampled_markets[market]
        )
        pooled_replicates.append(
            _delta(_difference(sampled_rows, baseline_errors, challenger_errors))
        )
        equal_replicates.append(
            _delta(
                _equal_market_difference(
                    sampled_markets, baseline_errors, challenger_errors
                )
            )
        )
    pooled_draws = tuple(pooled_replicates)
    equal_draws = tuple(equal_replicates)
    return PairedBootstrapResult(
        protocol_id,
        "ESTIMABLE",
        len(row_ids),
        len(market_units),
        len(components),
        components,
        digest,
        seed,
        draws,
        draws,
        ComparisonScope(pooled_point, _intervals(pooled_draws), pooled_draws),
        ComparisonScope(equal_point, _intervals(equal_draws), equal_draws),
    )
