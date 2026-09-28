"""Point-error formulas with explicit cohort counts; U1 accepts USD only."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
import math
from statistics import median
from typing import Sequence


def _positive_decimal(value: Decimal, name: str) -> None:
    if not isinstance(value, Decimal) or not value.is_finite() or value <= 0:
        raise ValueError(f"{name} must be a positive finite Decimal")
    representation = value.as_tuple()
    if len(representation.digits) > 64 or abs(representation.exponent) > 64:
        raise ValueError(f"{name} exceeds the supported Decimal representation budget")


def signed_percentage_error(actual: Decimal, predicted: Decimal) -> Decimal:
    """Positive means overvaluation; the result is a fraction, not percent units."""
    _positive_decimal(actual, "actual")
    _positive_decimal(predicted, "predicted")
    return (predicted - actual) / actual


@dataclass(frozen=True)
class PredictionRow:
    row_id: str
    actual: Decimal
    predicted: Decimal | None
    actual_currency: str
    predicted_currency: str | None
    status: str
    reason: str | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.row_id, str)
            or not self.row_id
            or self.row_id != self.row_id.strip()
        ):
            raise ValueError("row_id must be a canonical nonempty string")
        _positive_decimal(self.actual, "actual")
        if self.actual_currency != "USD":
            raise ValueError("U1 point metrics currently support USD only")
        if self.status == "estimated":
            _positive_decimal(self.predicted, "predicted")
            if self.predicted_currency != self.actual_currency:
                raise ValueError("Prediction currency does not match actual currency")
            if self.reason is not None:
                raise ValueError("Estimated row cannot have a failure reason")
        elif self.status in {"failed", "abstained"}:
            if self.predicted is not None or self.predicted_currency is not None:
                raise ValueError("Non-estimated row cannot contain a prediction")
            if not isinstance(self.reason, str) or not self.reason.strip():
                raise ValueError("Non-estimated row requires a reason")
        else:
            raise ValueError("Unknown prediction status")


@dataclass(frozen=True)
class Scorecard:
    eligible_count: int
    success_count: int
    failed_count: int
    abstained_count: int
    success_coverage: Decimal
    currency: str
    mdape: Decimal | None
    mape: Decimal | None
    within_5: Decimal | None
    within_10: Decimal | None
    within_20: Decimal | None
    p90_ape: Decimal | None
    p95_ape: Decimal | None
    median_signed_percentage_error: Decimal | None
    mae: Decimal | None
    rmse: float | None
    rmsle: float | None
    r2: Decimal | None


def _quantile(values: Sequence[Decimal], probability: Decimal) -> Decimal:
    """Linearly interpolated empirical quantile (type 7), including small n."""
    ordered = sorted(values)
    position = Decimal(len(ordered) - 1) * probability
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def score_predictions(rows: Sequence[PredictionRow]) -> Scorecard:
    """Score successful estimates and retain every eligible row in service counts."""
    if not rows:
        raise ValueError("Scorecard requires a nonempty eligible cohort")
    ids = [row.row_id for row in rows]
    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate prediction row ID")
    currencies = {row.actual_currency for row in rows}
    if len(currencies) != 1:
        raise ValueError("Metric cohort mixes currencies")
    estimated = [row for row in rows if row.status == "estimated"]
    failed_count = sum(row.status == "failed" for row in rows)
    abstained_count = sum(row.status == "abstained" for row in rows)
    counts = {
        "eligible_count": len(rows),
        "success_count": len(estimated),
        "failed_count": failed_count,
        "abstained_count": abstained_count,
        "success_coverage": Decimal(len(estimated)) / Decimal(len(rows)),
        "currency": next(iter(currencies)),
    }
    if not estimated:
        return Scorecard(
            **counts,
            **dict.fromkeys(
                (
                    "mdape",
                    "mape",
                    "within_5",
                    "within_10",
                    "within_20",
                    "p90_ape",
                    "p95_ape",
                    "median_signed_percentage_error",
                    "mae",
                    "rmse",
                    "rmsle",
                    "r2",
                )
            ),
        )

    count = Decimal(len(estimated))
    actuals = [row.actual for row in estimated]
    predictions = [row.predicted for row in estimated]
    signed = [
        signed_percentage_error(actual, predicted)
        for actual, predicted in zip(actuals, predictions, strict=True)
    ]
    absolute = [abs(error) for error in signed]
    exact_prices = [
        (Fraction(actual), Fraction(predicted))
        for actual, predicted in zip(actuals, predictions, strict=True)
    ]

    def within(numerator: int, denominator: int) -> Decimal:
        successes = sum(
            abs(predicted - actual) * denominator <= actual * numerator
            for actual, predicted in exact_prices
        )
        return Decimal(successes) / count

    dollar_errors = [
        predicted - actual
        for actual, predicted in zip(actuals, predictions, strict=True)
    ]
    actual_mean = sum(actuals) / count
    total_variation = sum((actual - actual_mean) ** 2 for actual in actuals)
    squared_error = sum(error**2 for error in dollar_errors)
    try:
        rmse = math.sqrt(float(squared_error / count))
        rmsle = math.sqrt(
            sum(
                (math.log1p(float(predicted)) - math.log1p(float(actual))) ** 2
                for actual, predicted in zip(actuals, predictions, strict=True)
            )
            / len(estimated)
        )
    except (OverflowError, ValueError) as error:
        raise ValueError("Metric input cannot be represented safely") from error
    if not math.isfinite(rmse) or not math.isfinite(rmsle):
        raise ValueError("Metric result is not finite")
    return Scorecard(
        **counts,
        mdape=median(absolute),
        mape=sum(absolute) / count,
        within_5=within(5, 100),
        within_10=within(10, 100),
        within_20=within(20, 100),
        p90_ape=_quantile(absolute, Decimal("0.90")),
        p95_ape=_quantile(absolute, Decimal("0.95")),
        median_signed_percentage_error=median(signed),
        mae=sum(abs(error) for error in dollar_errors) / count,
        rmse=rmse,
        rmsle=rmsle,
        r2=None if total_variation == 0 else 1 - squared_error / total_variation,
    )
