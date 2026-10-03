"""Synthetic calendar-date labels train only under a verified maturity plan."""

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
import sys
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


from tabpfn4realestate.data.local_date_sale import LocalDateSale  # noqa: E402
from tabpfn4realestate.data.schema import Property, SourceSnapshot  # noqa: E402
from tabpfn4realestate.evaluation.calendar_schedule import (  # noqa: E402
    CalendarOriginRef,
    build_calendar_schedule,
)
from tabpfn4realestate.evaluation.chronological_plan import (  # noqa: E402
    ChronologicalMaturityRef,
    build_chronological_plan,
    origin_policy_hash,
)
from tabpfn4realestate.evaluation.local_dates import (  # noqa: E402
    DateOnlyAvailability,
    derive_local_date_origin,
)
from tabpfn4realestate.evaluation.metrics import PredictionRow, score_predictions  # noqa: E402
from tabpfn4realestate.models.local_date_median import (  # noqa: E402
    CalendarTrainingExample,
    GuardedLocalDateMedian,
)


UTC = timezone.utc
ZONE = "America/New_York"
SOURCE_HASH = "a" * 64
FIT_CUTOFFS = tuple(
    datetime(year, month, 1, tzinfo=UTC)
    for year, month in ((2023, 1), (2023, 4), (2023, 7), (2023, 10), (2024, 1))
)
ORIGINS = tuple(
    CalendarOriginRef(row_id, f"property-{row_id}", origin_date)
    for row_id, origin_date in (
        ("history", date(2021, 1, 1)),
        ("q1", date(2023, 1, 1)),
        ("q2", date(2023, 4, 1)),
        ("q3", date(2023, 7, 1)),
        ("q4", date(2023, 10, 1)),
        ("calibration", date(2024, 1, 1)),
        ("test", date(2024, 4, 1)),
    )
)
ZONES = {row.row_id: ZONE for row in ORIGINS}


def fixture_plan(*, late_q4=False):
    schedule = build_calendar_schedule(
        ORIGINS,
        history_start=date(2021, 1, 1),
        calibration_start=date(2024, 1, 1),
        test_start=date(2024, 4, 1),
        source_snapshot_sha256=SOURCE_HASH,
        origin_policy_sha256=origin_policy_hash(ORIGINS, ZONES),
    )
    maturity = tuple(
        ChronologicalMaturityRef(
            row.row_id,
            row.origin_date + timedelta(days=90),
            DateOnlyAvailability(
                date(2024, 1, 2)
                if late_q4 and row.row_id == "q4"
                else row.origin_date + timedelta(days=90),
                ZONE,
            ),
        )
        for row in ORIGINS[:5]
    )
    plan = build_chronological_plan(
        schedule, ORIGINS, ZONES, maturity, fit_cutoffs_utc=FIT_CUTOFFS
    )
    return plan, maturity


def example(row, amount, *, available_at=None):
    close_date = row.origin_date + timedelta(days=90)
    label = LocalDateSale(
        transaction_id=f"deed-{row.row_id}",
        economic_transfer_id=row.row_id,
        property_id=row.property_id,
        close_date=close_date,
        close_zone_key=ZONE,
        available_at=available_at or DateOnlyAvailability(close_date, ZONE),
        price=Decimal(amount),
        currency="USD",
        source_id="synthetic-county",
        scope="single_property",
        consideration_type="gross_recorded_sale",
        arm_length_status="confirmed",
        adjustment_flags=(),
    )
    property = Property(
        property_id=row.property_id,
        country="US",
        property_type="single_family",
        source_id="synthetic-county",
        observed_at=datetime(2020, 1, 1, tzinfo=UTC),
        available_at=datetime(2020, 1, 2, tzinfo=UTC),
        living_area=Decimal("1500"),
        living_area_unit="sqft",
    )
    origin = derive_local_date_origin(close_date, ZONE)
    snapshot = SourceSnapshot(
        f"source-{row.row_id}", ("synthetic-county",), origin.cutoff_exclusive_utc
    )
    return CalendarTrainingExample(row.row_id, property, origin, snapshot, label)


def fit_examples(plan, maturity, examples):
    return GuardedLocalDateMedian.fit(
        examples,
        plan,
        ORIGINS,
        ZONES,
        maturity,
        source_snapshot_sha256=SOURCE_HASH,
    )


class LocalDateMedianTests(unittest.TestCase):
    def test_sale_label_keeps_local_date_precision_and_rejects_premature_publication(
        self,
    ):
        label = example(ORIGINS[0], "100").label
        with self.assertRaises(ValueError):
            replace(label, close_date=datetime(2021, 4, 1, tzinfo=UTC))
        with self.assertRaises(ValueError):
            replace(
                label,
                available_at=DateOnlyAvailability(
                    label.close_date - timedelta(days=1), ZONE
                ),
            )
        with self.assertRaises(ValueError):
            replace(label, available_at=datetime(2021, 4, 1, 12, tzinfo=UTC))

    def test_sale_label_rejects_invalid_price_currency_and_transaction_semantics(self):
        label = example(ORIGINS[0], "100").label
        self.assertTrue(label.eligible_sale)
        for change in (
            {"price": Decimal("0")},
            {"currency": "EUR"},
            {"scope": "parcel_guess"},
            {"consideration_type": "assessment"},
            {"arm_length_status": "assumed"},
            {"adjustment_flags": ("duplicate", "duplicate")},
        ):
            with self.subTest(change=change), self.assertRaises(ValueError):
                replace(label, **change)
        for change in (
            {"scope": "multi_property"},
            {"consideration_type": "nominal"},
            {"arm_length_status": "unknown"},
            {"adjustment_flags": ("concession_unknown",)},
        ):
            with self.subTest(change=change):
                self.assertFalse(replace(label, **change).eligible_sale)

    def test_fit_uses_exact_matured_membership_and_predicts_after_fit_cutoff(self):
        plan, maturity = fixture_plan()
        examples = tuple(
            example(row, str(100 + index * 10)) for index, row in enumerate(ORIGINS[:5])
        )
        model = fit_examples(plan, maturity, examples)
        self.assertEqual(model.amount, Decimal("120"))
        self.assertEqual(model.train_row_ids, plan.final_fit.train_row_ids)
        self.assertEqual(model.plan_hash, plan.plan_hash)
        future = example(ORIGINS[6], "200")
        prediction = model.predict(
            future.property, future.origin, future.source_snapshot
        )
        self.assertEqual(prediction.amount, Decimal("120"))
        self.assertEqual(prediction.snapshot.origin, future.origin)

    def test_reserved_and_immature_labels_cannot_enter_fit(self):
        plan, maturity = fixture_plan()
        trained = tuple(example(row, "100") for row in ORIGINS[:5])
        with self.assertRaises(ValueError):
            fit_examples(plan, maturity, (*trained, example(ORIGINS[5], "999")))
        late_plan, late_maturity = fixture_plan(late_q4=True)
        with self.assertRaises(ValueError):
            fit_examples(late_plan, late_maturity, trained)
        self.assertNotIn("q4", late_plan.final_fit.train_row_ids)

    def test_source_deed_id_cannot_label_two_economic_transfers(self):
        plan, maturity = fixture_plan()
        trained = list(example(row, "100") for row in ORIGINS[:5])
        trained[1] = replace(
            trained[1],
            label=replace(
                trained[1].label,
                transaction_id=trained[0].label.transaction_id,
            ),
        )
        with self.assertRaisesRegex(ValueError, "source transaction"):
            fit_examples(plan, maturity, tuple(trained))

    def test_close_date_zone_and_maturity_must_match_frozen_plan(self):
        plan, maturity = fixture_plan()
        trained = list(example(row, "100") for row in ORIGINS[:5])
        forged_label = replace(
            trained[0].label,
            close_date=date(2021, 4, 2),
            available_at=DateOnlyAvailability(date(2021, 4, 2), ZONE),
        )
        forged = replace(trained[0], label=forged_label)
        with self.assertRaises(ValueError):
            fit_examples(plan, maturity, (forged, *trained[1:]))
        wrong_zone = replace(
            trained[0],
            origin=derive_local_date_origin(
                trained[0].label.close_date, "America/Chicago"
            ),
        )
        with self.assertRaises(ValueError):
            fit_examples(plan, maturity, (wrong_zone, *trained[1:]))

    def test_plan_and_source_snapshot_hash_are_bound_to_fit(self):
        plan, maturity = fixture_plan()
        trained = tuple(example(row, "100") for row in ORIGINS[:5])
        with self.assertRaises(ValueError):
            GuardedLocalDateMedian.fit(
                trained, plan, ORIGINS, ZONES, maturity, source_snapshot_sha256="b" * 64
            )
        forged = replace(
            plan, final_fit=replace(plan.final_fit, train_row_ids=("history",))
        )
        with self.assertRaises(ValueError):
            fit_examples(forged, maturity, trained)

    def test_training_digest_changes_when_an_eligible_label_changes(self):
        plan, maturity = fixture_plan()
        trained = tuple(
            example(row, str(100 + index * 10)) for index, row in enumerate(ORIGINS[:5])
        )
        original = fit_examples(plan, maturity, trained)
        changed = replace(
            trained[0], label=replace(trained[0].label, price=Decimal("999999"))
        )
        revised = fit_examples(plan, maturity, (changed, *trained[1:]))
        self.assertNotEqual(original.training_rows_sha256, revised.training_rows_sha256)
        self.assertEqual(
            original.source_snapshot_sha256, revised.source_snapshot_sha256
        )

    def test_model_constructor_rejects_invalid_amount_and_manifest(self):
        plan, maturity = fixture_plan()
        model = fit_examples(
            plan, maturity, tuple(example(row, "100") for row in ORIGINS[:5])
        )
        with self.assertRaises(ValueError):
            replace(model, amount=Decimal("-1"))
        with self.assertRaises(ValueError):
            replace(model, training_rows_sha256="invalid")
        with self.assertRaises(ValueError):
            replace(model, train_row_ids=("duplicate",) * len(model.train_row_ids))

    def test_unused_manifest_source_is_not_accepted_for_prediction(self):
        plan, maturity = fixture_plan()
        trained = tuple(example(row, "100") for row in ORIGINS[:5])
        amended = tuple(
            replace(
                row,
                source_snapshot=replace(
                    row.source_snapshot, source_ids=("synthetic-county", "unused-feed")
                ),
            )
            for row in trained
        )
        model = fit_examples(plan, maturity, amended)
        self.assertEqual(model.allowed_source_ids, ("synthetic-county",))
        future = example(ORIGINS[6], "200")
        other = replace(future.source_snapshot, source_ids=("unused-feed",))
        with self.assertRaises(ValueError):
            model.predict(future.property, future.origin, other)

    def test_replay_and_score_have_stable_snapshot_identity(self):
        plan, maturity = fixture_plan()
        trained = tuple(example(row, "100") for row in ORIGINS[:5])
        first = fit_examples(plan, maturity, trained)
        second = fit_examples(plan, maturity, tuple(reversed(trained)))
        self.assertEqual(first, second)
        future = example(ORIGINS[6], "200")
        prediction = first.predict(
            future.property, future.origin, future.source_snapshot
        )
        score = score_predictions(
            (
                PredictionRow(
                    row_id="test",
                    actual=Decimal("200"),
                    predicted=prediction.amount,
                    actual_currency="USD",
                    predicted_currency="USD",
                    status="estimated",
                ),
            )
        )
        self.assertEqual(score.mdape, Decimal("0.5"))
        self.assertEqual(score.success_coverage, Decimal("1"))

    def test_two_hundred_development_rows_replay_through_calendar_fit_and_score(self):
        history = tuple(
            CalendarOriginRef(
                f"h{index:03d}",
                f"property-h{index:03d}",
                date(2021, 1, 1) + timedelta(days=index * 3),
            )
            for index in range(200)
        )
        origins = (*history, *ORIGINS[1:])
        zones = {row.row_id: ZONE for row in origins}
        schedule = build_calendar_schedule(
            origins,
            history_start=date(2021, 1, 1),
            calibration_start=date(2024, 1, 1),
            test_start=date(2024, 4, 1),
            source_snapshot_sha256=SOURCE_HASH,
            origin_policy_sha256=origin_policy_hash(origins, zones),
        )
        maturity = tuple(
            ChronologicalMaturityRef(
                row.row_id,
                row.origin_date + timedelta(days=90),
                DateOnlyAvailability(row.origin_date + timedelta(days=90), ZONE),
            )
            for row in origins[:-2]
        )
        plan = build_chronological_plan(
            schedule, origins, zones, maturity, fit_cutoffs_utc=FIT_CUTOFFS
        )
        training = tuple(
            example(row, str(100000 + index * 100))
            for index, row in enumerate(origins[:-2])
        )
        self.assertEqual(len(training), 204)
        model = GuardedLocalDateMedian.fit(
            training,
            plan,
            origins,
            zones,
            maturity,
            source_snapshot_sha256=SOURCE_HASH,
        )
        replay = GuardedLocalDateMedian.fit(
            tuple(reversed(training)),
            plan,
            origins,
            zones,
            maturity,
            source_snapshot_sha256=SOURCE_HASH,
        )
        self.assertEqual(model, replay)
        self.assertEqual(len(model.train_row_ids), 204)
        held_out = example(origins[-1], "150000")
        prediction = model.predict(
            held_out.property, held_out.origin, held_out.source_snapshot
        )
        score = score_predictions(
            (
                PredictionRow(
                    row_id=held_out.row_id,
                    actual=held_out.label.price,
                    predicted=prediction.amount,
                    actual_currency="USD",
                    predicted_currency="USD",
                    status="estimated",
                ),
            )
        )
        self.assertEqual(score.eligible_count, 1)
        self.assertEqual(score.success_count, 1)
        self.assertEqual(
            score.mdape,
            abs(prediction.amount - held_out.label.price) / held_out.label.price,
        )


if __name__ == "__main__":
    unittest.main()
