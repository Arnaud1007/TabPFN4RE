"""Point-in-time canaries for the repeated hour at a daylight-saving fallback."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone, tzinfo
from decimal import Decimal
from pathlib import Path
import sys
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tabpfn4realestate.data.schema import (  # noqa: E402
    Attribute,
    Property,
    SourceSnapshot,
    Transaction,
)
from tabpfn4realestate.evaluation.splits import (  # noqa: E402
    LabelMaturity,
    OriginRef,
    build_temporal_fold,
)
from tabpfn4realestate.features.asof import assemble_snapshot  # noqa: E402
from tabpfn4realestate.features.comparables import (  # noqa: E402
    ComparableConfig,
    comparable_price_per_area,
    eligible_comparable_sales,
    retrieve_comparables,
)
from tabpfn4realestate.models.guards import TrainingPartition  # noqa: E402
from tabpfn4realestate.models.off_baseline import (  # noqa: E402
    GuardedOffMedian,
    TrainingExample,
    label_row_id,
)


class FallbackEastern(tzinfo):
    """Model the two real instants at 01:30 on the 2024 US fallback day."""

    def utcoffset(self, value):
        return timedelta(hours=-5 if value is not None and value.fold else -4)

    def dst(self, value):
        return timedelta(hours=0 if value is not None and value.fold else 1)

    def tzname(self, value):
        return "EST" if value is not None and value.fold else "EDT"


class SeasonalEastern(tzinfo):
    """Minimal offsets for the two dates in the month-window regression."""

    def utcoffset(self, value):
        if value is not None and value.year == 2023:
            return timedelta(hours=-4)
        return timedelta(hours=-5 if value is not None and value.fold else -4)

    def dst(self, value):
        return timedelta(0)

    def tzname(self, value):
        return "synthetic-seasonal"


EASTERN = FallbackEastern()
FIRST_0130 = datetime(2024, 11, 3, 1, 30, tzinfo=EASTERN, fold=0)
SECOND_0130 = datetime(2024, 11, 3, 1, 30, tzinfo=EASTERN, fold=1)
PAST = datetime(2024, 1, 1, tzinfo=timezone.utc)


def property_record(property_id="home-1", **changes):
    fields = {
        "property_id": property_id,
        "country": "US",
        "property_type": "single_family",
        "source_id": "assessor",
        "observed_at": PAST,
        "available_at": PAST,
        "living_area": Decimal("1500"),
        "living_area_unit": "sqft",
        "latitude": Decimal("40.0000"),
        "longitude": Decimal("-75.0000"),
    }
    return Property(**(fields | changes))


def source_snapshot(as_of=FIRST_0130):
    return SourceSnapshot(
        snapshot_id="fallback-fixture",
        source_ids=("assessor", "sales"),
        as_of=as_of,
    )


def sale_record(property_id="home-1", **changes):
    fields = {
        "transaction_id": f"sale-{property_id}",
        "economic_transfer_id": f"transfer-{property_id}",
        "property_id": property_id,
        "close_at": FIRST_0130,
        "available_at": SECOND_0130,
        "price": Decimal("200000"),
        "currency": "USD",
        "source_id": "sales",
        "scope": "single_property",
        "consideration_type": "gross_recorded_sale",
        "arm_length_status": "confirmed",
        "adjustment_flags": (),
    }
    return Transaction(**(fields | changes))


def comparable_config():
    return ComparableConfig(
        n_neighbors=1,
        min_comparables=1,
        sale_window_months=12,
        radii_km=(5.0,),
    )


class FallbackAvailabilityTests(unittest.TestCase):
    def test_fixture_represents_distinct_instants_with_the_same_wall_time(self):
        self.assertEqual(FIRST_0130.astimezone(timezone.utc).hour, 5)
        self.assertEqual(SECOND_0130.astimezone(timezone.utc).hour, 6)
        self.assertLess(
            FIRST_0130.astimezone(timezone.utc),
            SECOND_0130.astimezone(timezone.utc),
        )

    def test_future_property_version_is_rejected(self):
        for field in ("observed_at", "available_at"):
            with self.subTest(field=field):
                property = property_record(**{field: SECOND_0130})
                with self.assertRaisesRegex(ValueError, "unavailable"):
                    assemble_snapshot(property, FIRST_0130, "OFF", source_snapshot())

    def test_future_attribute_is_absent(self):
        future = Attribute(
            property_id="home-1",
            name="condition",
            value="renovated",
            observed_at=PAST,
            available_at=SECOND_0130,
            source_id="assessor",
        )
        result = assemble_snapshot(
            property_record(),
            FIRST_0130,
            "OFF",
            source_snapshot(),
            attributes=(future,),
        )
        self.assertNotIn("condition", result.values)

    def test_late_published_subject_sale_is_not_prior_history(self):
        result = assemble_snapshot(
            property_record(),
            FIRST_0130,
            "OFF",
            source_snapshot(),
            transactions=(sale_record(),),
        )
        self.assertNotIn("prior_sale_price", result.values)

    def test_late_published_neighbor_sale_is_not_eligible(self):
        subject = property_record()
        neighbor = property_record("home-2", latitude=Decimal("40.0010"))
        late_sale = sale_record("home-2")
        eligible = eligible_comparable_sales(
            subject,
            FIRST_0130,
            source_snapshot(),
            candidate_properties=(neighbor,),
            transactions=(late_sale,),
        )
        self.assertEqual(eligible, ())

    def test_retrieval_excludes_late_published_neighbor_sale(self):
        subject = property_record()
        neighbor = property_record("home-2", latitude=Decimal("40.0010"))
        late_sale = sale_record("home-2")
        retrieved = retrieve_comparables(
            subject,
            FIRST_0130,
            source_snapshot(),
            candidate_properties=(neighbor,),
            transactions=(late_sale,),
            config=comparable_config(),
        )
        self.assertEqual(retrieved.comparables, ())
        self.assertEqual(retrieved.support, "low")

    def test_comparable_result_cannot_be_reused_one_fold_later(self):
        subject = property_record()
        neighbor = property_record("home-2", latitude=Decimal("40.0010"))
        already_visible = sale_record(
            "home-2",
            close_at=datetime(2024, 10, 1, tzinfo=timezone.utc),
            available_at=datetime(2024, 10, 2, tzinfo=timezone.utc),
        )
        manifest = source_snapshot()
        result = retrieve_comparables(
            subject,
            FIRST_0130,
            manifest,
            candidate_properties=(neighbor,),
            transactions=(already_visible,),
            config=comparable_config(),
        )
        self.assertEqual(len(result.comparables), 1)
        with self.assertRaisesRegex(ValueError, "different input context"):
            comparable_price_per_area(subject, SECOND_0130, manifest, result)
        with self.assertRaisesRegex(ValueError, "origin must be"):
            comparable_price_per_area(
                subject, FIRST_0130.replace(tzinfo=None), manifest, result
            )

    def test_equivalent_timezone_context_can_price_same_comparables(self):
        subject = property_record(observed_at=FIRST_0130, available_at=FIRST_0130)
        neighbor = property_record("home-2", latitude=Decimal("40.0010"))
        sale = sale_record(
            "home-2",
            close_at=datetime(2024, 10, 1, tzinfo=timezone.utc),
            available_at=datetime(2024, 10, 2, tzinfo=timezone.utc),
        )
        manifest = source_snapshot(SECOND_0130)
        result = retrieve_comparables(
            subject,
            SECOND_0130,
            manifest,
            candidate_properties=(neighbor,),
            transactions=(sale,),
            config=comparable_config(),
        )
        expected = comparable_price_per_area(subject, SECOND_0130, manifest, result)
        equivalent_subject = replace(
            subject,
            observed_at=FIRST_0130.astimezone(timezone.utc),
            available_at=FIRST_0130.astimezone(timezone.utc),
        )
        equivalent_manifest = replace(
            manifest, as_of=SECOND_0130.astimezone(timezone.utc)
        )
        self.assertEqual(
            comparable_price_per_area(
                equivalent_subject,
                SECOND_0130.astimezone(timezone.utc),
                equivalent_manifest,
                result,
            ),
            expected,
        )

    def test_synthetic_utc_horizon_ignores_input_timezone_representation(self):
        origin_utc = SECOND_0130.astimezone(timezone.utc) - timedelta(days=90)
        origin_offset = origin_utc.astimezone(timezone(timedelta(hours=-4)))
        available = SECOND_0130 + timedelta(hours=2)
        label = sale_record(close_at=SECOND_0130, available_at=available)
        cutoff = datetime(2024, 11, 4, tzinfo=timezone.utc)

        def build(origin):
            fold = build_temporal_fold(
                (
                    OriginRef(label_row_id(label), label.property_id, origin),
                    OriginRef(
                        "validation",
                        "other-home",
                        datetime(2024, 11, 5, tzinfo=timezone.utc),
                    ),
                ),
                (
                    LabelMaturity(
                        label_row_id(label), label.close_at, label.available_at
                    ),
                ),
                training_cutoff=cutoff,
                validation_start=datetime(2024, 11, 5, tzinfo=timezone.utc),
                validation_end=datetime(2024, 11, 6, tzinfo=timezone.utc),
            )
            row = TrainingExample(
                row_id=label_row_id(label),
                property=property_record(),
                origin=origin,
                source_snapshot=source_snapshot(origin),
                label=label,
            )
            partition = TrainingPartition(
                train_row_ids=frozenset({row.row_id}),
                reserved_row_ids=frozenset({"validation"}),
            )
            return fold, GuardedOffMedian.fit((row,), partition, training_cutoff=cutoff)

        utc_fold, utc_model = build(origin_utc)
        offset_fold, offset_model = build(origin_offset)
        self.assertEqual(utc_fold.split_hash, offset_fold.split_hash)
        self.assertEqual(utc_model.amount, offset_model.amount)
        self.assertEqual(
            utc_model.feature_snapshot_hashes, offset_model.feature_snapshot_hashes
        )
        with self.assertRaisesRegex(ValueError, "origin horizon"):
            build(SECOND_0130 - timedelta(days=90))

    def test_comparable_window_ignores_timezone_representation(self):
        local_origin = datetime(2024, 11, 3, 1, 30, tzinfo=SeasonalEastern(), fold=1)
        utc_origin = local_origin.astimezone(timezone.utc)
        subject = property_record()
        older_observation = datetime(2023, 1, 1, tzinfo=timezone.utc)
        neighbor = property_record(
            "home-2",
            latitude=Decimal("40.0010"),
            observed_at=older_observation,
            available_at=older_observation,
        )
        boundary_sale = sale_record(
            "home-2",
            close_at=datetime(2023, 11, 3, 6, tzinfo=timezone.utc),
            available_at=datetime(2023, 11, 4, tzinfo=timezone.utc),
        )
        local = retrieve_comparables(
            subject,
            local_origin,
            source_snapshot(local_origin),
            candidate_properties=(neighbor,),
            transactions=(boundary_sale,),
            config=comparable_config(),
        )
        utc = retrieve_comparables(
            subject,
            utc_origin,
            source_snapshot(utc_origin),
            candidate_properties=(neighbor,),
            transactions=(boundary_sale,),
            config=comparable_config(),
        )
        self.assertEqual(
            tuple(item.sale.economic_transfer_id for item in local.comparables),
            tuple(item.sale.economic_transfer_id for item in utc.comparables),
        )

    def test_equal_instant_timezone_representations_have_same_snapshot_hash(self):
        utc_origin = FIRST_0130.astimezone(timezone.utc)
        local = assemble_snapshot(
            property_record(), FIRST_0130, "OFF", source_snapshot()
        )
        utc = assemble_snapshot(
            property_record(), utc_origin, "OFF", source_snapshot(utc_origin)
        )
        self.assertEqual(dict(local.values), dict(utc.values))
        self.assertEqual(local.snapshot_hash, utc.snapshot_hash)

    def test_off_fit_rejects_label_published_in_second_fold(self):
        label = sale_record()
        train_origin = FIRST_0130 - timedelta(days=90)
        row = TrainingExample(
            row_id=label_row_id(label),
            property=property_record(),
            origin=train_origin,
            source_snapshot=source_snapshot(train_origin),
            label=label,
        )
        partition = TrainingPartition(
            train_row_ids=frozenset({row.row_id}),
            reserved_row_ids=frozenset({"reserved-row"}),
        )
        with self.assertRaisesRegex(ValueError, "unavailable"):
            GuardedOffMedian.fit((row,), partition, training_cutoff=FIRST_0130)

    def test_off_predict_excludes_second_fold_attribute(self):
        model = GuardedOffMedian(
            amount=Decimal("250000"),
            train_row_ids=("training-row",),
            feature_snapshot_hashes=("a" * 64,),
            training_cutoff=FIRST_0130 - timedelta(days=1),
        )
        future = Attribute(
            property_id="home-1",
            name="condition",
            value="renovated",
            observed_at=PAST,
            available_at=SECOND_0130,
            source_id="assessor",
        )
        prediction = model.predict(
            property_record(),
            FIRST_0130,
            source_snapshot(),
            attributes=(future,),
        )
        self.assertEqual(prediction.amount, Decimal("250000"))
        self.assertNotIn("condition", prediction.snapshot.values)


if __name__ == "__main__":
    unittest.main()
