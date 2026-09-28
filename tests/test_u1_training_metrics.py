"""T05–T08: guarded fitting, split integrity, and shared scorecard behaviour."""

import math
from decimal import Decimal
from pathlib import Path
import sys
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tabpfn4realestate.evaluation.metrics import (  # noqa: E402
    PredictionRow,
    score_predictions,
    signed_percentage_error,
)
from tabpfn4realestate.evaluation.splits import validate_property_split  # noqa: E402
from tabpfn4realestate.models.guards import (  # noqa: E402
    GuardedCategoryEncoder,
    TrainingPartition,
)


def prediction_row(**changes):
    fields = {
        "row_id": "sale-1",
        "actual": Decimal("100"),
        "predicted": Decimal("110"),
        "actual_currency": "USD",
        "predicted_currency": "USD",
        "status": "estimated",
        "reason": None,
    }
    return PredictionRow(**(fields | changes))


class TrainingGuardTests(unittest.TestCase):
    def test_partition_rejects_or_copies_mutable_id_sets(self):
        train = {"train-1"}
        reserved = {"test-1"}
        try:
            partition = TrainingPartition(
                train_row_ids=train, reserved_row_ids=reserved
            )
        except (TypeError, ValueError):
            return
        reserved.remove("test-1")
        train.add("test-1")
        with self.assertRaises(ValueError):
            GuardedCategoryEncoder.fit(
                ("house",), row_ids=("test-1",), partition=partition
            )

    def test_partition_rejects_whitespace_padded_ids(self):
        for train_ids, reserved_ids in (
            (frozenset({" train-1"}), frozenset({"test-1"})),
            (frozenset({"train-1"}), frozenset({"test-1 "})),
        ):
            with self.subTest(train_ids=train_ids, reserved_ids=reserved_ids):
                with self.assertRaises(ValueError):
                    TrainingPartition(train_ids, reserved_ids)

    def test_reserved_row_id_is_rejected_during_fit(self):
        partition = TrainingPartition(
            train_row_ids=frozenset({"train-1"}),
            reserved_row_ids=frozenset({"test-1"}),
        )
        with self.assertRaises(ValueError):
            GuardedCategoryEncoder.fit(
                ("house", "condo"),
                row_ids=("train-1", "test-1"),
                partition=partition,
            )

    def test_validation_only_category_uses_unknown_without_refitting(self):
        partition = TrainingPartition(
            train_row_ids=frozenset({"train-1", "train-2"}),
            reserved_row_ids=frozenset({"test-1"}),
        )
        encoder = GuardedCategoryEncoder.fit(
            ("house", "condo"),
            row_ids=("train-1", "train-2"),
            partition=partition,
        )
        before = encoder.categories
        self.assertEqual(encoder.transform(("validation-only",)), (-1,))
        self.assertEqual(encoder.categories, before)
        self.assertNotIn("validation-only", encoder.categories)
        self.assertNotEqual(encoder.transform(("house",)), (-1,))

    def test_fit_rejects_unregistered_training_row(self):
        partition = TrainingPartition(
            train_row_ids=frozenset({"train-1"}),
            reserved_row_ids=frozenset({"test-1"}),
        )
        with self.assertRaises(ValueError):
            GuardedCategoryEncoder.fit(
                ("house",), row_ids=("unregistered",), partition=partition
            )

    def test_encoder_unknown_code_cannot_collide_with_known_categories(self):
        with self.assertRaises(ValueError):
            GuardedCategoryEncoder(categories=("house",), unknown_code=0)

    def test_encoder_rejects_or_copies_mutable_vocabulary(self):
        categories = ["house"]
        try:
            encoder = GuardedCategoryEncoder(categories=categories)
        except (TypeError, ValueError):
            return
        categories.append("condo")
        self.assertEqual(encoder.categories, ("house",))


class SplitValidationTests(unittest.TestCase):
    def test_property_ids_reject_surrounding_whitespace(self):
        for train, test in (
            ((" home-1",), ("home-2",)),
            (("home-1",), ("home-2 ",)),
        ):
            with self.subTest(train=train, test=test):
                with self.assertRaises(ValueError):
                    validate_property_split(train, test, "unseen_property")

    def test_unseen_property_protocol_rejects_overlap(self):
        with self.assertRaises(ValueError):
            validate_property_split(
                ("home-1", "home-2"), ("home-2", "home-3"), "unseen_property"
            )

    def test_future_sales_protocol_allows_genuine_prior_property_history(self):
        validate_property_split(
            ("home-1", "home-2"), ("home-2", "home-3"), "future_sales"
        )

    def test_unknown_protocol_is_rejected(self):
        with self.assertRaises(ValueError):
            validate_property_split(("home-1",), ("home-2",), "anything_goes")


class MetricContractTests(unittest.TestCase):
    def test_true_above_10_percent_is_not_rounded_into_boundary(self):
        score = score_predictions(
            (
                prediction_row(
                    actual=Decimal("1"),
                    predicted=Decimal("1.10000000000000000000000000001"),
                ),
            )
        )
        self.assertEqual(score.within_10, 0)

    def test_signed_percentage_error_and_exact_within_10_boundary(self):
        self.assertEqual(
            signed_percentage_error(Decimal("100"), Decimal("110")),
            Decimal("0.1"),
        )
        self.assertEqual(
            signed_percentage_error(Decimal("100"), Decimal("90")),
            Decimal("-0.1"),
        )
        score = score_predictions(
            (
                prediction_row(row_id="high", predicted=Decimal("110")),
                prediction_row(row_id="low", predicted=Decimal("90")),
            )
        )
        self.assertEqual(score.eligible_count, 2)
        self.assertEqual(score.success_count, 2)
        self.assertAlmostEqual(float(score.mdape), 0.1)
        self.assertAlmostEqual(float(score.mape), 0.1)
        self.assertEqual(score.within_5, 0)
        self.assertEqual(score.within_10, 1)
        self.assertEqual(score.within_20, 1)
        self.assertAlmostEqual(float(score.p90_ape), 0.1)
        self.assertAlmostEqual(float(score.p95_ape), 0.1)
        self.assertAlmostEqual(float(score.median_signed_percentage_error), 0)
        self.assertAlmostEqual(float(score.mae), 10)
        self.assertAlmostEqual(float(score.rmse), 10)
        self.assertIsNone(score.r2)
        expected_rmsle = math.sqrt(
            (
                (math.log1p(110) - math.log1p(100)) ** 2
                + (math.log1p(90) - math.log1p(100)) ** 2
            )
            / 2
        )
        self.assertAlmostEqual(float(score.rmsle), expected_rmsle)

    def test_nonconstant_target_r2_is_hand_checkable(self):
        score = score_predictions(
            (
                prediction_row(
                    row_id="one", actual=Decimal("100"), predicted=Decimal("110")
                ),
                prediction_row(
                    row_id="two", actual=Decimal("200"), predicted=Decimal("190")
                ),
            )
        )
        self.assertAlmostEqual(float(score.r2), 0.96)

    def test_nonpositive_prediction_is_model_output_failure(self):
        for value in (Decimal("0"), Decimal("-1")):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    score_predictions((prediction_row(predicted=value),))

    def test_extreme_decimal_representation_is_rejected_before_scoring(self):
        for field, value in (
            ("actual", Decimal("1e-10000000")),
            ("predicted", Decimal("1e10000000")),
            ("actual", Decimal("9" * 65)),
        ):
            with self.subTest(field=field, value=value.as_tuple().exponent):
                with self.assertRaises(ValueError):
                    prediction_row(**{field: value})

    def test_missing_prediction_requires_explicit_failure_or_abstention(self):
        with self.assertRaises(ValueError):
            score_predictions((prediction_row(predicted=None),))
        with self.assertRaises(ValueError):
            score_predictions(
                (prediction_row(predicted=None, status="failed", reason=None),)
            )

    def test_failures_and_abstentions_remain_in_cohort_counts(self):
        score = score_predictions(
            (
                prediction_row(row_id="estimated"),
                prediction_row(
                    row_id="failed",
                    predicted=None,
                    predicted_currency=None,
                    status="failed",
                    reason="model_output_error",
                ),
                prediction_row(
                    row_id="abstained",
                    predicted=None,
                    predicted_currency=None,
                    status="abstained",
                    reason="unsupported_property_type",
                ),
            )
        )
        self.assertEqual(score.eligible_count, 3)
        self.assertEqual(score.success_count, 1)
        self.assertEqual(score.failed_count, 1)
        self.assertEqual(score.abstained_count, 1)
        self.assertAlmostEqual(float(score.success_coverage), 1 / 3)

    def test_currency_mismatch_and_mixed_cohort_are_rejected(self):
        with self.assertRaises(ValueError):
            score_predictions((prediction_row(predicted_currency="EUR"),))
        with self.assertRaises(ValueError):
            score_predictions(
                (
                    prediction_row(row_id="usd"),
                    prediction_row(
                        row_id="eur", actual_currency="EUR", predicted_currency="EUR"
                    ),
                )
            )

    def test_non_ascii_and_unsupported_currency_codes_are_rejected(self):
        for currency in ("ÉUR", "ZZZ"):
            with self.subTest(currency=currency):
                with self.assertRaises(ValueError):
                    score_predictions(
                        (
                            prediction_row(
                                actual_currency=currency,
                                predicted_currency=currency,
                            ),
                        )
                    )

    def test_invalid_actual_and_duplicate_row_ids_are_rejected(self):
        with self.assertRaises(ValueError):
            score_predictions((prediction_row(actual=Decimal("0")),))
        with self.assertRaises(ValueError):
            score_predictions((prediction_row(), prediction_row()))


if __name__ == "__main__":
    unittest.main()
