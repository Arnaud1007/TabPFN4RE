"""Synthetic US19/T09 split conformal checks; no source transaction data."""

from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
import sys
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tabpfn4realestate.evaluation.conformal import (  # noqa: E402
    CalibrationEvidence,
    CalibrationRow,
    IntervalEvaluationRow,
    SplitConformalCalibrator,
    score_intervals,
    split_conformal_radius,
)


UTC = timezone.utc
TRAINING_CUTOFF = datetime(2024, 1, 1, tzinfo=UTC)
CALIBRATION_CUTOFF = datetime(2024, 5, 1, tzinfo=UTC)
TEST_START = datetime(2024, 5, 2, tzinfo=UTC)
TEST_CLOSE = TEST_START + timedelta(days=90)
TEST_AVAILABLE = TEST_CLOSE + timedelta(days=1)
EVALUATION_AT = TEST_AVAILABLE + timedelta(days=1)
MODEL = "a" * 64
OTHER_MODEL = "b" * 64


def sample_rows(count: int = 1000) -> tuple[CalibrationRow, ...]:
    rows = []
    for index in range(count):
        origin = TRAINING_CUTOFF + timedelta(days=1 + index % 10)
        close = origin + timedelta(days=90)
        rows.append(
            CalibrationRow(
                row_id=f"cal-{index:04d}",
                origin=origin,
                close_at=close,
                available_at=close + timedelta(days=1),
                actual=Decimal("100"),
                predicted=Decimal("90") if index % 10 == 0 else Decimal("100"),
                currency="USD",
                predictor_digest=MODEL,
            )
        )
    return tuple(rows)


def fit_calibrator(
    rows: tuple[CalibrationRow, ...] | None = None,
    *,
    train_ids=frozenset({"train-1"}),
    calibration_ids=None,
    test_ids=frozenset({"test-1", "test-2", "test-3"}),
    **changes,
) -> SplitConformalCalibrator:
    rows = sample_rows() if rows is None else rows
    fields = {
        "training_row_ids": train_ids,
        "calibration_row_ids": frozenset(row.row_id for row in rows)
        if calibration_ids is None
        else calibration_ids,
        "test_row_ids": test_ids,
        "predictor_digest": MODEL,
        "training_cutoff": TRAINING_CUTOFF,
        "calibration_cutoff": CALIBRATION_CUTOFF,
        "test_start": TEST_START,
    }
    return SplitConformalCalibrator.fit(rows, **(fields | changes))


class RadiusTests(unittest.TestCase):
    def test_exact_one_based_rank_ties_and_order(self):
        scores = tuple(Decimal(value) for value in (9, 7, 8, 1, 2, 3, 4, 5, 6))
        self.assertEqual(split_conformal_radius(scores, Decimal("0.10")), Decimal(9))
        self.assertEqual(
            split_conformal_radius((Decimal(2),) * 9, Decimal("0.1")),
            Decimal(2),
        )
        self.assertEqual(
            split_conformal_radius(tuple(reversed(scores)), Decimal("0.1")),
            Decimal(9),
        )
        self.assertEqual(
            split_conformal_radius(
                (Decimal(4), Decimal(1), Decimal(3), Decimal(2)), Decimal("0.2")
            ),
            Decimal(4),
        )

    def test_insufficient_rank_and_invalid_inputs_fail(self):
        with self.assertRaisesRegex(ValueError, "insufficient"):
            split_conformal_radius((Decimal(1),) * 8, Decimal("0.1"))
        with self.assertRaisesRegex(ValueError, "insufficient"):
            split_conformal_radius((Decimal(1),) * 4, Decimal("0.1" + "9" * 60))
        for scores, alpha in (
            ((), Decimal("0.1")),
            ((Decimal(0),), Decimal(0)),
            ((Decimal(0),), Decimal(1)),
            ((Decimal(0),), Decimal("NaN")),
            ((Decimal(0),), 0.1),
            ((Decimal(-1),), Decimal("0.5")),
            ((Decimal("Infinity"),), Decimal("0.5")),
            ((1,), Decimal("0.5")),
        ):
            with self.subTest(scores=scores, alpha=alpha):
                with self.assertRaises(ValueError):
                    split_conformal_radius(scores, alpha)


class CalibrationTests(unittest.TestCase):
    def test_fit_is_immutable_reproducible_and_order_independent(self):
        rows = sample_rows()
        first = fit_calibrator(rows)
        second = fit_calibrator(tuple(reversed(rows)))
        self.assertEqual(first, second)
        self.assertEqual(len(first.calibration_id), 64)
        self.assertEqual(first.radius80, Decimal(0))
        self.assertGreater(first.radius90, first.radius80)
        with self.assertRaises(FrozenInstanceError):
            first.radius90 = Decimal(0)
        with self.assertRaises(FrozenInstanceError):
            rows[0].actual = Decimal(1)
        changed = (
            tuple(replace(rows[0], actual=Decimal("101")) for _ in (0,)) + rows[1:]
        )
        self.assertNotEqual(
            first.calibration_id, fit_calibrator(changed).calibration_id
        )

    def test_minimum_size_and_exact_pairwise_disjoint_membership(self):
        rows = sample_rows()
        with self.assertRaisesRegex(ValueError, "1,000"):
            fit_calibrator(rows[:-1])
        for changes in (
            {"train_ids": frozenset({rows[0].row_id})},
            {"test_ids": frozenset({rows[0].row_id})},
            {"calibration_ids": frozenset(row.row_id for row in rows[:-1])},
            {"calibration_ids": frozenset(row.row_id for row in rows) | {"extra"}},
            {"calibration_ids": frozenset({"train-1"})},
        ):
            with self.subTest(changes=changes):
                with self.assertRaises(ValueError):
                    fit_calibrator(rows, **changes)
        with self.assertRaises(ValueError):
            fit_calibrator(rows + (rows[0],))

    def test_temporal_origin_horizon_and_label_availability(self):
        rows = sample_rows()
        bad_changes = (
            {
                "origin": TRAINING_CUTOFF,
                "close_at": TRAINING_CUTOFF + timedelta(days=90),
            },
            {"close_at": rows[0].close_at + timedelta(days=1)},
            {"available_at": CALIBRATION_CUTOFF + timedelta(microseconds=1)},
            {"available_at": rows[0].close_at - timedelta(seconds=1)},
            {"origin": rows[0].origin.replace(tzinfo=None)},
        )
        for changes in bad_changes:
            with self.subTest(changes=changes):
                with self.assertRaises(ValueError):
                    fit_calibrator((replace(rows[0], **changes),) + rows[1:])
        for changes in (
            {"training_cutoff": CALIBRATION_CUTOFF},
            {"calibration_cutoff": TEST_START + timedelta(seconds=1)},
            {"test_start": TEST_START.replace(tzinfo=None)},
        ):
            with self.subTest(changes=changes):
                with self.assertRaises(ValueError):
                    fit_calibrator(rows, **changes)

    def test_rejects_invalid_prices_currency_and_model_digest(self):
        rows = sample_rows()
        for changes in (
            {"actual": Decimal(0)},
            {"predicted": Decimal("NaN")},
            {"predicted": 100.0},
            {"currency": "EUR"},
            {"predictor_digest": OTHER_MODEL},
        ):
            with self.subTest(changes=changes):
                with self.assertRaises(ValueError):
                    fit_calibrator((replace(rows[0], **changes),) + rows[1:])
        with self.assertRaises(ValueError):
            fit_calibrator(rows, predictor_digest="mutable-default")

    def test_intervals_are_positive_nested_and_bound_to_model(self):
        fitted = fit_calibrator()
        bounds = fitted.intervals(Decimal("100"), predictor_digest=MODEL)
        self.assertEqual(bounds.lower80, bounds.upper80)
        self.assertLess(bounds.lower90, bounds.lower80)
        self.assertGreater(bounds.upper90, bounds.upper80)
        self.assertGreater(bounds.lower90, 0)
        tiny_bounds = fitted.intervals(Decimal("1E-20"), predictor_digest=MODEL)
        self.assertGreater(tiny_bounds.lower90, 0)
        with self.assertRaisesRegex(ValueError, "predictor"):
            fitted.intervals(Decimal("100"), predictor_digest=OTHER_MODEL)
        for invalid in (0, Decimal("NaN"), Decimal("Infinity"), 100.0):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    fitted.intervals(invalid, predictor_digest=MODEL)
        with self.assertRaises(ValueError):
            replace(fitted, radius90=Decimal("1000")).intervals(
                Decimal("100"), predictor_digest=MODEL
            )

    def test_loaded_calibrator_must_preserve_interval_and_identity_invariants(self):
        fitted = fit_calibrator()
        for changes in (
            {"radius80": Decimal("-0.01")},
            {"radius90": Decimal("NaN")},
            {"radius80": fitted.radius90 + Decimal(1)},
            {"calibration_id": "mutable"},
            {"predictor_digest": OTHER_MODEL, "calibration_id": "bad"},
        ):
            with self.subTest(changes=changes):
                with self.assertRaises(ValueError):
                    replace(fitted, **changes)
        with self.assertRaisesRegex(ValueError, "[Cc]alibration"):
            replace(fitted, radius90=fitted.radius90 + Decimal("0.1"))
        altered = replace(
            fitted.evidence[0], factor=fitted.evidence[0].factor + Fraction(1, 100)
        )
        with self.assertRaisesRegex(ValueError, "calibration_id"):
            replace(fitted, evidence=(altered,) + fitted.evidence[1:])

    def test_residual_evidence_has_a_bounded_exact_ratio(self):
        row = sample_rows(1)[0]
        with self.assertRaises(ValueError):
            CalibrationEvidence(
                row.row_id,
                row.origin,
                row.close_at,
                row.available_at,
                Fraction(10**500),
            )

    def test_exact_calibration_tie_is_inside_outward_interval(self):
        rows = tuple(replace(row, predicted=Decimal("90")) for row in sample_rows())
        fitted = fit_calibrator(rows)
        bounds = fitted.intervals(Decimal("90"), predictor_digest=MODEL)
        self.assertLessEqual(bounds.lower90, Decimal("90"))
        self.assertGreaterEqual(bounds.upper90, Decimal("100"))
        self.assertGreaterEqual(bounds.upper80, Decimal("100"))
        lower_tie = fitted.intervals(Decimal("100"), predictor_digest=MODEL)
        self.assertLessEqual(lower_tie.lower90, Decimal("90"))
        self.assertLessEqual(lower_tie.lower80, Decimal("90"))

    def test_distinct_64_digit_prices_do_not_collapse_to_zero_residual(self):
        actual = Decimal("2." + "0" * 60 + "1")
        rows = tuple(
            replace(row, actual=actual, predicted=Decimal("2")) for row in sample_rows()
        )
        fitted = fit_calibrator(rows)
        self.assertGreater(fitted.radius90, 0)
        bounds = fitted.intervals(Decimal("2"), predictor_digest=MODEL)
        self.assertGreater(bounds.upper90, Decimal("2"))
        self.assertGreaterEqual(bounds.upper90, actual)

    def test_unrepresentable_endpoint_fails_explicitly(self):
        rows = tuple(
            replace(row, actual=Decimal("1E64"), predicted=Decimal("1E-64"))
            for row in sample_rows()
        )
        fitted = fit_calibrator(rows)
        with self.assertRaisesRegex(ValueError, "representation budget"):
            fitted.intervals(Decimal("1E-64"), predictor_digest=MODEL)


def eval_row(
    row_id: str,
    actual: Decimal,
    status: str,
    predicted: Decimal | None = None,
    bounds=None,
    reason: str | None = None,
) -> IntervalEvaluationRow:
    return IntervalEvaluationRow(
        row_id=row_id,
        origin=TEST_START,
        close_at=TEST_CLOSE,
        available_at=TEST_AVAILABLE,
        actual=actual,
        currency="USD",
        status=status,
        predicted=predicted,
        bounds=bounds,
        reason=reason,
    )


class IntervalScoreTests(unittest.TestCase):
    def test_coverage_width_and_all_eligible_denominators(self):
        fitted = fit_calibrator()
        bounds = fitted.intervals(Decimal("100"), predictor_digest=MODEL)
        rows = (
            eval_row("test-1", Decimal("100"), "estimated", Decimal("100"), bounds),
            eval_row("test-2", Decimal("200"), "estimated", Decimal("100"), bounds),
            eval_row("test-3", Decimal("100"), "abstained", reason="low support"),
        )
        result = score_intervals(rows, calibrator=fitted, evaluation_at=EVALUATION_AT)
        self.assertEqual((result.eligible_count, result.success_count), (3, 2))
        self.assertEqual((result.failed_count, result.abstained_count), (0, 1))
        self.assertEqual(result.success_coverage, Decimal(2) / Decimal(3))
        self.assertEqual(result.coverage80, Decimal("0.5"))
        self.assertEqual(result.coverage90, Decimal("0.5"))
        self.assertEqual(result.mean_relative_width80, Decimal(0))
        self.assertGreater(result.mean_relative_width90, Decimal(0))
        self.assertGreater(result.p90_relative_width90, result.mean_relative_width90)
        self.assertEqual(result.calibration_id, fitted.calibration_id)

    def test_eval_cohort_is_separate_and_exact(self):
        fitted = fit_calibrator()
        good = eval_row("test-1", Decimal("100"), "failed", reason="model failed")
        for rows in (
            (good,),
            (good, good),
            (replace(good, row_id="cal-0000"),),
            (
                replace(
                    good,
                    origin=TRAINING_CUTOFF,
                    close_at=TRAINING_CUTOFF + timedelta(days=90),
                    available_at=TRAINING_CUTOFF + timedelta(days=91),
                ),
            ),
        ):
            with self.subTest(rows=rows):
                with self.assertRaises(ValueError):
                    score_intervals(
                        rows, calibrator=fitted, evaluation_at=EVALUATION_AT
                    )

    def test_scoring_rejects_other_calibration_and_model_provenance(self):
        fitted = fit_calibrator(test_ids=frozenset({"test-1"}))
        bounds = fitted.intervals(Decimal("100"), predictor_digest=MODEL)
        row = eval_row("test-1", Decimal("100"), "estimated", Decimal("100"), bounds)
        for changed_bounds in (
            replace(bounds, calibration_id="c" * 64),
            replace(bounds, predictor_digest=OTHER_MODEL),
        ):
            with self.subTest(bounds=changed_bounds):
                with self.assertRaises(ValueError):
                    score_intervals(
                        (replace(row, bounds=changed_bounds),),
                        calibrator=fitted,
                        evaluation_at=EVALUATION_AT,
                    )

    def test_scoring_rejects_widened_bounds_and_wrong_saved_point(self):
        fitted = fit_calibrator(test_ids=frozenset({"test-1"}))
        bounds = fitted.intervals(Decimal("100"), predictor_digest=MODEL)
        row = eval_row("test-1", Decimal("100"), "estimated", Decimal("100"), bounds)
        with self.assertRaisesRegex(ValueError, "saved prediction"):
            score_intervals(
                (replace(row, bounds=replace(bounds, lower90=bounds.lower90 / 2)),),
                calibrator=fitted,
                evaluation_at=EVALUATION_AT,
            )
        with self.assertRaisesRegex(ValueError, "saved prediction"):
            score_intervals(
                (replace(row, predicted=Decimal("101")),),
                calibrator=fitted,
                evaluation_at=EVALUATION_AT,
            )

    def test_scoring_rejects_immature_or_mistimed_test_labels(self):
        fitted = fit_calibrator(test_ids=frozenset({"test-1"}))
        failure = eval_row("test-1", Decimal("100"), "failed", reason="timeout")
        with self.assertRaisesRegex(ValueError, "mature"):
            score_intervals(
                (failure,),
                calibrator=fitted,
                evaluation_at=TEST_AVAILABLE - timedelta(microseconds=1),
            )
        with self.assertRaises(ValueError):
            score_intervals(
                (failure,), calibrator=fitted, evaluation_at=TRAINING_CUTOFF
            )
        for changes in (
            {"close_at": TEST_CLOSE + timedelta(days=1)},
            {"available_at": TEST_CLOSE - timedelta(microseconds=1)},
            {"available_at": TEST_AVAILABLE.replace(tzinfo=None)},
        ):
            with self.subTest(changes=changes):
                with self.assertRaises(ValueError):
                    replace(failure, **changes)

    def test_all_failed_has_no_interval_metric_and_bad_rows_rejected(self):
        fitted = fit_calibrator(test_ids=frozenset({"test-1"}))
        failure = eval_row("test-1", Decimal("100"), "failed", reason="timeout")
        result = score_intervals(
            (failure,), calibrator=fitted, evaluation_at=EVALUATION_AT
        )
        self.assertEqual(result.success_count, 0)
        self.assertIsNone(result.coverage90)
        self.assertIsNone(result.mean_relative_width90)
        self.assertIsNone(result.p90_relative_width90)
        for changes in (
            {"actual": Decimal(0)},
            {"actual": 100.0},
            {"currency": "EUR"},
            {"status": "estimated", "reason": None},
            {"status": "unknown"},
        ):
            with self.subTest(changes=changes):
                with self.assertRaises(ValueError):
                    score_intervals(
                        (replace(failure, **changes),),
                        calibrator=fitted,
                        evaluation_at=EVALUATION_AT,
                    )


if __name__ == "__main__":
    unittest.main()
