"""Synthetic, disjoint split conformal intervals for the frozen US OFF predictor.

Ordinary marginal coverage requires exchangeability; this module does not claim a
guarantee for shifted housing markets. Fit uses disjoint calibration sale labels;
reserved evaluation labels do not enter fit.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import (
    Context,
    Decimal,
    DecimalException,
    ROUND_CEILING,
    ROUND_FLOOR,
    localcontext,
)
from fractions import Fraction
from hashlib import sha256
import json
from typing import Sequence

from tabpfn4realestate.data.schema import (
    _identifier,
    _instant,
    _matches_utc_horizon,
    _utc,
)
from tabpfn4realestate.evaluation.metrics import _quantile


_ARITHMETIC_CONTEXT = Context(prec=50, Emax=999, Emin=-999)
_LOG_CONTEXT = Context(prec=150, Emax=999, Emin=-999)
_ENDPOINT_FLOOR_CONTEXT = Context(prec=60, Emax=999, Emin=-999, rounding=ROUND_FLOOR)
_ENDPOINT_CEILING_CONTEXT = Context(
    prec=60, Emax=999, Emin=-999, rounding=ROUND_CEILING
)
_ALPHA80 = Decimal("0.20")
_ALPHA90 = Decimal("0.10")


def _price(value: Decimal, name: str) -> None:
    if not isinstance(value, Decimal) or not value.is_finite() or value <= 0:
        raise ValueError(f"{name} must be a positive finite Decimal")
    parts = value.as_tuple()
    if len(parts.digits) > 64 or abs(value.adjusted()) > 64:
        raise ValueError(f"{name} exceeds the supported Decimal representation budget")


def _digest(value: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError("predictor_digest must be a lowercase SHA-256 digest")


def _ids(values: frozenset[str], name: str) -> None:
    if not isinstance(values, frozenset) or not values:
        raise ValueError(f"{name} must be a nonempty immutable ID set")
    for value in values:
        _identifier(value, name)


def _rank(n: int, alpha: Decimal) -> int:
    numerator, denominator = alpha.as_integer_ratio()
    numerator_remaining = (n + 1) * (denominator - numerator)
    rank = (numerator_remaining + denominator - 1) // denominator
    if rank > n:
        raise ValueError("insufficient calibration support for requested alpha")
    return rank


def split_conformal_radius(scores: Sequence[Decimal], alpha: Decimal) -> Decimal:
    """Return the finite 1-based ceil((n+1)(1-alpha)) order statistic."""
    if not isinstance(alpha, Decimal) or not alpha.is_finite() or not 0 < alpha < 1:
        raise ValueError("alpha must be a finite Decimal strictly between zero and one")
    parts = alpha.as_tuple()
    if len(parts.digits) > 64 or abs(parts.exponent) > 64:
        raise ValueError("alpha exceeds the supported Decimal representation budget")
    if not isinstance(scores, Sequence) or not scores:
        raise ValueError("scores must be a nonempty sequence")
    if any(
        not isinstance(score, Decimal) or not score.is_finite() or score < 0
        for score in scores
    ):
        raise ValueError("scores must contain nonnegative finite Decimals")
    return sorted(scores)[_rank(len(scores), alpha) - 1]


def _factor_radius(factors: Sequence[Fraction], alpha: Decimal) -> Fraction:
    return sorted(factors)[_rank(len(factors), alpha) - 1]


def _log_radius(factor: Fraction) -> Decimal:
    with localcontext(_LOG_CONTEXT):
        ratio = Decimal(factor.numerator) / Decimal(factor.denominator)
        radius = ratio.ln()
    if factor > 1 and radius <= 0:
        raise ValueError(
            "Calibration log precision cannot represent a positive residual"
        )
    return radius


def _outward_decimal(value: Fraction, *, upper: bool) -> Decimal:
    context = _ENDPOINT_CEILING_CONTEXT if upper else _ENDPOINT_FLOOR_CONTEXT
    with localcontext(context):
        return Decimal(value.numerator) / Decimal(value.denominator)


@dataclass(frozen=True)
class CalibrationRow:
    row_id: str
    origin: datetime
    close_at: datetime
    available_at: datetime
    actual: Decimal
    predicted: Decimal
    currency: str
    predictor_digest: str

    def __post_init__(self) -> None:
        _identifier(self.row_id, "row_id")
        for name in ("origin", "close_at", "available_at"):
            _instant(getattr(self, name), name)
        if not _matches_utc_horizon(self.origin, self.close_at, 90):
            raise ValueError("Calibration row needs an exact 90-day close origin")
        if _utc(self.available_at) < _utc(self.close_at):
            raise ValueError("Sale label cannot be available before close")
        _price(self.actual, "actual")
        _price(self.predicted, "predicted")
        if self.currency != "USD":
            raise ValueError("Synthetic US calibration supports USD only")
        _digest(self.predictor_digest)


@dataclass(frozen=True)
class CalibrationEvidence:
    """A dated, exact multiplicative residual without a raw sale price."""

    row_id: str
    origin: datetime
    close_at: datetime
    available_at: datetime
    factor: Fraction

    def __post_init__(self) -> None:
        _identifier(self.row_id, "row_id")
        for name in ("origin", "close_at", "available_at"):
            _instant(getattr(self, name), name)
        if not _matches_utc_horizon(self.origin, self.close_at, 90):
            raise ValueError("Calibration evidence needs an exact 90-day origin")
        if _utc(self.available_at) < _utc(self.close_at):
            raise ValueError("Calibration evidence cannot precede sale close")
        if not isinstance(self.factor, Fraction) or self.factor < 1:
            raise ValueError("Calibration evidence needs an exact factor >= 1")
        if (
            self.factor.numerator.bit_length() > 1024
            or self.factor.denominator.bit_length() > 1024
        ):
            raise ValueError("Calibration evidence factor exceeds the supported budget")


def _identity(
    *,
    predictor_digest: str,
    training_row_ids: frozenset[str],
    calibration_row_ids: frozenset[str],
    test_row_ids: frozenset[str],
    training_cutoff: datetime,
    calibration_cutoff: datetime,
    test_start: datetime,
    evidence: tuple[CalibrationEvidence, ...],
    factor80: Fraction,
    factor90: Fraction,
    radius80: Decimal,
    radius90: Decimal,
) -> str:
    payload = {
        "protocol": "us_synthetic_off_90d_split_conformal_v2",
        "predictor_digest": predictor_digest,
        "training_row_ids": sorted(training_row_ids),
        "calibration_row_ids": sorted(calibration_row_ids),
        "test_row_ids": sorted(test_row_ids),
        "training_cutoff": _utc(training_cutoff).isoformat(),
        "calibration_cutoff": _utc(calibration_cutoff).isoformat(),
        "test_start": _utc(test_start).isoformat(),
        "evidence": [
            (
                row.row_id,
                _utc(row.origin).isoformat(),
                _utc(row.close_at).isoformat(),
                _utc(row.available_at).isoformat(),
                row.factor.numerator,
                row.factor.denominator,
            )
            for row in evidence
        ],
        "factor80": (factor80.numerator, factor80.denominator),
        "factor90": (factor90.numerator, factor90.denominator),
        "radius80": str(radius80),
        "radius90": str(radius90),
    }
    return sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True)
class IntervalBounds:
    lower80: Decimal
    upper80: Decimal
    lower90: Decimal
    upper90: Decimal
    predictor_digest: str
    calibration_id: str

    def __post_init__(self) -> None:
        for name in ("lower80", "upper80", "lower90", "upper90"):
            _price(getattr(self, name), name)
        if not self.lower90 <= self.lower80 <= self.upper80 <= self.upper90:
            raise ValueError("80% interval must nest within 90% interval")
        _digest(self.predictor_digest)
        _digest(self.calibration_id)


@dataclass(frozen=True)
class SplitConformalCalibrator:
    predictor_digest: str
    training_row_ids: frozenset[str]
    calibration_row_ids: frozenset[str]
    test_row_ids: frozenset[str]
    training_cutoff: datetime
    calibration_cutoff: datetime
    test_start: datetime
    evidence: tuple[CalibrationEvidence, ...]
    factor80: Fraction
    factor90: Fraction
    radius80: Decimal
    radius90: Decimal
    calibration_id: str

    def __post_init__(self) -> None:
        _digest(self.predictor_digest)
        _digest(self.calibration_id)
        for name, values in (
            ("training_row_ids", self.training_row_ids),
            ("calibration_row_ids", self.calibration_row_ids),
            ("test_row_ids", self.test_row_ids),
        ):
            _ids(values, name)
        if (
            self.training_row_ids & self.calibration_row_ids
            or self.training_row_ids & self.test_row_ids
            or self.calibration_row_ids & self.test_row_ids
        ):
            raise ValueError("Training, calibration and test row IDs must be disjoint")
        for name, value in (
            ("training_cutoff", self.training_cutoff),
            ("calibration_cutoff", self.calibration_cutoff),
            ("test_start", self.test_start),
        ):
            _instant(value, name)
        if (
            not _utc(self.training_cutoff)
            < _utc(self.calibration_cutoff)
            < _utc(self.test_start)
        ):
            raise ValueError("Training, calibration and test cutoffs are out of order")
        if (
            not isinstance(self.evidence, tuple)
            or len(self.evidence) < 1000
            or any(not isinstance(row, CalibrationEvidence) for row in self.evidence)
        ):
            raise ValueError(
                "Calibration needs at least 1,000 immutable residual records"
            )
        evidence_ids = tuple(row.row_id for row in self.evidence)
        if (
            evidence_ids != tuple(sorted(evidence_ids))
            or len(set(evidence_ids)) != len(evidence_ids)
            or set(evidence_ids) != self.calibration_row_ids
        ):
            raise ValueError("Calibration evidence must match sorted reserved row IDs")
        for row in self.evidence:
            if (
                not _utc(self.training_cutoff)
                < _utc(row.origin)
                < _utc(self.calibration_cutoff)
            ):
                raise ValueError("Calibration evidence origin precedes predictor fit")
            if _utc(row.available_at) > _utc(self.calibration_cutoff):
                raise ValueError("Calibration evidence label was unavailable at fit")
        if not isinstance(self.factor80, Fraction) or not isinstance(
            self.factor90, Fraction
        ):
            raise ValueError("Calibration factors must be exact fractions")
        factors = tuple(row.factor for row in self.evidence)
        if self.factor80 != _factor_radius(factors, _ALPHA80) or self.factor90 != (
            _factor_radius(factors, _ALPHA90)
        ):
            raise ValueError("Calibration factors differ from residual evidence")
        if any(
            not isinstance(radius, Decimal) or not radius.is_finite() or radius < 0
            for radius in (self.radius80, self.radius90)
        ):
            raise ValueError("Conformal radii must be nonnegative finite Decimals")
        if self.radius80 != _log_radius(self.factor80) or self.radius90 != _log_radius(
            self.factor90
        ):
            raise ValueError("Calibration log radii differ from exact factors")
        if self.calibration_id != _identity(
            predictor_digest=self.predictor_digest,
            training_row_ids=self.training_row_ids,
            calibration_row_ids=self.calibration_row_ids,
            test_row_ids=self.test_row_ids,
            training_cutoff=self.training_cutoff,
            calibration_cutoff=self.calibration_cutoff,
            test_start=self.test_start,
            evidence=self.evidence,
            factor80=self.factor80,
            factor90=self.factor90,
            radius80=self.radius80,
            radius90=self.radius90,
        ):
            raise ValueError("calibration_id does not match the frozen evidence")

    @classmethod
    def fit(
        cls,
        rows: Sequence[CalibrationRow],
        *,
        training_row_ids: frozenset[str],
        calibration_row_ids: frozenset[str],
        test_row_ids: frozenset[str],
        predictor_digest: str,
        training_cutoff: datetime,
        calibration_cutoff: datetime,
        test_start: datetime,
    ) -> SplitConformalCalibrator:
        """Fit only after predictor freeze and before the first evaluation origin."""
        _digest(predictor_digest)
        for name, values in (
            ("training_row_ids", training_row_ids),
            ("calibration_row_ids", calibration_row_ids),
            ("test_row_ids", test_row_ids),
        ):
            _ids(values, name)
        if (
            training_row_ids & calibration_row_ids
            or training_row_ids & test_row_ids
            or calibration_row_ids & test_row_ids
        ):
            raise ValueError("Training, calibration and test row IDs must be disjoint")
        for name, value in (
            ("training_cutoff", training_cutoff),
            ("calibration_cutoff", calibration_cutoff),
            ("test_start", test_start),
        ):
            _instant(value, name)
        if not _utc(training_cutoff) < _utc(calibration_cutoff) < _utc(test_start):
            raise ValueError("Training, calibration and test cutoffs are out of order")
        if not isinstance(rows, Sequence) or len(rows) < 1000:
            raise ValueError("Split calibration requires at least 1,000 valid rows")
        if any(not isinstance(row, CalibrationRow) for row in rows):
            raise ValueError("Calibration requires validated CalibrationRow records")
        row_ids = tuple(row.row_id for row in rows)
        if len(set(row_ids)) != len(row_ids) or set(row_ids) != calibration_row_ids:
            raise ValueError(
                "Calibration rows must match exact unique reserved membership"
            )
        for row in rows:
            if row.predictor_digest != predictor_digest:
                raise ValueError("Calibration row has a different predictor identity")
            if not _utc(training_cutoff) < _utc(row.origin) < _utc(calibration_cutoff):
                raise ValueError("Calibration origin must follow predictor fit")
            if _utc(row.available_at) > _utc(calibration_cutoff):
                raise ValueError("Calibration label is unavailable at calibration fit")
        ordered = sorted(rows, key=lambda row: row.row_id)
        # The exact factor is exp(|log(actual) - log(predicted)|), so its
        # ordering matches the specified log-residual order statistic.
        evidence = tuple(
            CalibrationEvidence(
                row_id=row.row_id,
                origin=row.origin,
                close_at=row.close_at,
                available_at=row.available_at,
                factor=max(
                    Fraction(row.actual) / Fraction(row.predicted),
                    Fraction(row.predicted) / Fraction(row.actual),
                ),
            )
            for row in ordered
        )
        factors = tuple(row.factor for row in evidence)
        factor80 = _factor_radius(factors, _ALPHA80)
        factor90 = _factor_radius(factors, _ALPHA90)
        try:
            radius80 = _log_radius(factor80)
            radius90 = _log_radius(factor90)
        except DecimalException as error:
            raise ValueError("Calibration arithmetic failed") from error
        calibration_id = _identity(
            predictor_digest=predictor_digest,
            training_row_ids=training_row_ids,
            calibration_row_ids=calibration_row_ids,
            test_row_ids=test_row_ids,
            training_cutoff=training_cutoff,
            calibration_cutoff=calibration_cutoff,
            test_start=test_start,
            evidence=evidence,
            factor80=factor80,
            factor90=factor90,
            radius80=radius80,
            radius90=radius90,
        )
        return cls(
            predictor_digest,
            training_row_ids,
            calibration_row_ids,
            test_row_ids,
            training_cutoff,
            calibration_cutoff,
            test_start,
            evidence,
            factor80,
            factor90,
            radius80,
            radius90,
            calibration_id,
        )

    def intervals(self, predicted: Decimal, *, predictor_digest: str) -> IntervalBounds:
        _digest(predictor_digest)
        if predictor_digest != self.predictor_digest:
            raise ValueError("Intervals require the frozen predictor identity")
        _price(predicted, "predicted")
        try:
            point = Fraction(predicted)

            def endpoints(factor: Fraction) -> tuple[Decimal, Decimal]:
                if factor == 1:
                    return predicted, predicted
                # Directed rounding keeps an exact calibration tie inside.
                return (
                    _outward_decimal(point / factor, upper=False),
                    _outward_decimal(point * factor, upper=True),
                )

            lower80, upper80 = endpoints(self.factor80)
            lower90, upper90 = endpoints(self.factor90)
            return IntervalBounds(
                lower80=lower80,
                upper80=upper80,
                lower90=lower90,
                upper90=upper90,
                predictor_digest=self.predictor_digest,
                calibration_id=self.calibration_id,
            )
        except DecimalException as error:
            raise ValueError("Interval arithmetic overflow or underflow") from error


@dataclass(frozen=True)
class IntervalEvaluationRow:
    row_id: str
    origin: datetime
    close_at: datetime
    available_at: datetime
    actual: Decimal
    currency: str
    status: str
    predicted: Decimal | None
    bounds: IntervalBounds | None
    reason: str | None = None

    def __post_init__(self) -> None:
        _identifier(self.row_id, "row_id")
        _instant(self.origin, "origin")
        _instant(self.close_at, "close_at")
        _instant(self.available_at, "available_at")
        if not _matches_utc_horizon(self.origin, self.close_at, 90):
            raise ValueError("Evaluation row needs an exact 90-day close origin")
        if _utc(self.available_at) < _utc(self.close_at):
            raise ValueError("Evaluation label cannot be available before close")
        _price(self.actual, "actual")
        if self.currency != "USD":
            raise ValueError("Synthetic US interval scoring supports USD only")
        if self.status == "estimated":
            _price(self.predicted, "predicted")
            if not isinstance(self.bounds, IntervalBounds) or self.reason is not None:
                raise ValueError("Estimated row needs bounds and no failure reason")
        elif self.status in {"abstained", "failed"}:
            if (
                self.predicted is not None
                or self.bounds is not None
                or not isinstance(self.reason, str)
                or not self.reason.strip()
            ):
                raise ValueError("Non-estimated row needs a reason and no prediction")
        else:
            raise ValueError("Unknown interval prediction status")


@dataclass(frozen=True)
class IntervalScorecard:
    calibration_id: str
    eligible_count: int
    success_count: int
    failed_count: int
    abstained_count: int
    success_coverage: Decimal
    coverage80: Decimal | None
    coverage90: Decimal | None
    mean_relative_width80: Decimal | None
    mean_relative_width90: Decimal | None
    p90_relative_width80: Decimal | None
    p90_relative_width90: Decimal | None


def score_intervals(
    rows: Sequence[IntervalEvaluationRow],
    *,
    calibrator: SplitConformalCalibrator,
    evaluation_at: datetime,
) -> IntervalScorecard:
    """Score later reserved labels; failed rows remain in the service denominator."""
    if not isinstance(calibrator, SplitConformalCalibrator):
        raise ValueError("Expected a frozen SplitConformalCalibrator")
    _instant(evaluation_at, "evaluation_at")
    if _utc(evaluation_at) < _utc(calibrator.test_start):
        raise ValueError("Evaluation occurs before the reserved test start")
    if not isinstance(rows, Sequence) or not rows:
        raise ValueError("Interval evaluation needs the reserved cohort")
    if any(not isinstance(row, IntervalEvaluationRow) for row in rows):
        raise ValueError("Interval evaluation needs validated rows")
    row_ids = tuple(row.row_id for row in rows)
    if len(set(row_ids)) != len(row_ids) or set(row_ids) != calibrator.test_row_ids:
        raise ValueError("Evaluation rows must match exact distinct test membership")
    if any(_utc(row.origin) < _utc(calibrator.test_start) for row in rows):
        raise ValueError("Evaluation origin precedes the reserved test start")
    if any(_utc(row.available_at) > _utc(evaluation_at) for row in rows):
        raise ValueError("Evaluation label has not matured by evaluation_at")
    if any(
        row.status == "estimated"
        and (
            row.bounds.calibration_id != calibrator.calibration_id
            or row.bounds.predictor_digest != calibrator.predictor_digest
        )
        for row in rows
    ):
        raise ValueError("Interval provenance differs from the frozen calibration")
    if any(
        row.status == "estimated"
        and row.bounds
        != calibrator.intervals(
            row.predicted, predictor_digest=calibrator.predictor_digest
        )
        for row in rows
    ):
        raise ValueError("Interval bounds differ from the saved prediction")
    estimated = tuple(row for row in rows if row.status == "estimated")
    count = len(estimated)

    def coverage(lower: str, upper: str) -> Decimal | None:
        if not count:
            return None
        return Decimal(
            sum(
                getattr(row.bounds, lower) <= row.actual <= getattr(row.bounds, upper)
                for row in estimated
            )
        ) / Decimal(count)

    def relative_widths(lower: str, upper: str) -> tuple[Decimal, ...]:
        if not count:
            return ()
        with localcontext(_ARITHMETIC_CONTEXT):
            return tuple(
                (getattr(row.bounds, upper) - getattr(row.bounds, lower)) / row.actual
                for row in estimated
            )

    widths80 = relative_widths("lower80", "upper80")
    widths90 = relative_widths("lower90", "upper90")

    def mean_width(widths: tuple[Decimal, ...]) -> Decimal | None:
        if not count:
            return None
        with localcontext(_ARITHMETIC_CONTEXT):
            return sum(widths) / Decimal(count)

    def p90_width(widths: tuple[Decimal, ...]) -> Decimal | None:
        if not count:
            return None
        with localcontext(_ARITHMETIC_CONTEXT):
            return _quantile(widths, Decimal("0.90"))

    return IntervalScorecard(
        calibration_id=calibrator.calibration_id,
        eligible_count=len(rows),
        success_count=count,
        failed_count=sum(row.status == "failed" for row in rows),
        abstained_count=sum(row.status == "abstained" for row in rows),
        success_coverage=Decimal(count) / Decimal(len(rows)),
        coverage80=coverage("lower80", "upper80"),
        coverage90=coverage("lower90", "upper90"),
        mean_relative_width80=mean_width(widths80),
        mean_relative_width90=mean_width(widths90),
        p90_relative_width80=p90_width(widths80),
        p90_relative_width90=p90_width(widths90),
    )
