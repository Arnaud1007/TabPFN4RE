"""Application-owned OFF baseline canaries using canonical, as-of records."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
import sys
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tabpfn4realestate.data.schema import (  # noqa: E402
    Attribute,
    ListingEvent,
    Property,
    SourceSnapshot,
    Transaction,
)
from tabpfn4realestate.models.guards import TrainingPartition  # noqa: E402
from tabpfn4realestate.models.off_baseline import (  # noqa: E402
    GuardedOffMedian,
    TrainingExample,
    label_row_id,
)


ORIGIN = datetime(2024, 3, 1, 12, tzinfo=timezone.utc)
TRAIN_ORIGIN = ORIGIN - timedelta(days=200)
CLOSE = TRAIN_ORIGIN + timedelta(days=90)
TRAINING_CUTOFF = CLOSE + timedelta(days=10)


def property_record(**changes):
    fields = {
        "property_id": "home-1",
        "country": "US",
        "property_type": "single_family",
        "source_id": "assessor",
        "observed_at": ORIGIN - timedelta(days=365),
        "available_at": ORIGIN - timedelta(days=364),
        "living_area": Decimal("1500"),
        "living_area_unit": "sqft",
    }
    return Property(**(fields | changes))


def label_record(**changes):
    fields = {
        "transaction_id": "sale-1",
        "economic_transfer_id": "transfer-sale-1",
        "property_id": "home-1",
        "close_at": CLOSE,
        "available_at": CLOSE + timedelta(days=10),
        "price": Decimal("100000"),
        "currency": "USD",
        "source_id": "sales",
        "scope": "single_property",
        "consideration_type": "gross_recorded_sale",
        "arm_length_status": "confirmed",
        "adjustment_flags": (),
    }
    return Transaction(**(fields | changes))


def source_snapshot(**changes):
    fields = {
        "snapshot_id": "asof-origin",
        "source_ids": ("assessor", "sales", "listings"),
        "as_of": ORIGIN,
    }
    return SourceSnapshot(**(fields | changes))


def attribute_record(**changes):
    fields = {
        "property_id": "home-1",
        "name": "condition",
        "value": "good",
        "observed_at": ORIGIN - timedelta(days=10),
        "available_at": ORIGIN - timedelta(days=9),
        "source_id": "assessor",
    }
    return Attribute(**(fields | changes))


def listing_record(**changes):
    fields = {
        "listing_id": "listing-1",
        "property_id": "home-1",
        "event_type": "asking_price",
        "event_at": ORIGIN - timedelta(days=2),
        "available_at": ORIGIN - timedelta(days=1),
        "source_id": "listings",
        "amount": Decimal("120000"),
    }
    return ListingEvent(**(fields | changes))


def example(
    transaction_id="sale-1",
    property_id="home-1",
    price="100000",
    row_id=None,
    **changes,
):
    property = property_record(property_id=property_id)
    default_label = label_record(
        transaction_id=transaction_id,
        economic_transfer_id=f"transfer-{transaction_id}",
        property_id=property_id,
        price=Decimal(price),
    )
    label = changes.get("label", default_label)
    fields = {
        "row_id": label_row_id(label) if row_id is None else row_id,
        "property": property,
        "origin": TRAIN_ORIGIN,
        "source_snapshot": source_snapshot(as_of=TRAIN_ORIGIN),
        "label": label,
        "attributes": (),
        "transactions": (),
        "listing_events": (),
    }
    return TrainingExample(**(fields | changes))


def partition():
    return TrainingPartition(
        train_row_ids=frozenset(
            {
                example().row_id,
                example(transaction_id="sale-2", property_id="home-2").row_id,
            }
        ),
        reserved_row_ids=frozenset({example(transaction_id="sale-reserved").row_id}),
    )


class GuardedOffMedianTests(unittest.TestCase):
    def test_direct_construction_rejects_invalid_amount(self):
        for amount in (
            Decimal("0"),
            Decimal("-1"),
            Decimal("NaN"),
            Decimal("Infinity"),
        ):
            with self.subTest(amount=str(amount)):
                with self.assertRaises(ValueError):
                    GuardedOffMedian(
                        amount=amount,
                        train_row_ids=("transfer-1",),
                        feature_snapshot_hashes=("a" * 64,),
                        training_cutoff=TRAINING_CUTOFF,
                    )

    def test_direct_construction_rejects_invalid_training_manifest(self):
        invalid = (
            {"train_row_ids": (), "feature_snapshot_hashes": ()},
            {"train_row_ids": ("transfer-1",), "feature_snapshot_hashes": ()},
            {
                "train_row_ids": ("transfer-1", "transfer-2"),
                "feature_snapshot_hashes": ("a" * 64,),
            },
            {
                "train_row_ids": ("transfer-1", "transfer-1"),
                "feature_snapshot_hashes": ("a" * 64, "b" * 64),
            },
            {
                "train_row_ids": ("transfer-1",),
                "feature_snapshot_hashes": ("not-a-hash",),
            },
        )
        for change in invalid:
            with self.subTest(change=change):
                fields = {
                    "amount": Decimal("100000"),
                    "train_row_ids": ("transfer-1",),
                    "feature_snapshot_hashes": ("a" * 64,),
                    "training_cutoff": TRAINING_CUTOFF,
                }
                with self.assertRaises(ValueError):
                    GuardedOffMedian(**(fields | change))

    def fit_two(self):
        return GuardedOffMedian.fit(
            (example(), example("sale-2", "home-2", "200000")),
            partition(),
            training_cutoff=TRAINING_CUTOFF,
        )

    def test_two_matured_labels_fit_and_predict_training_median(self):
        model = self.fit_two()
        prediction = model.predict(
            property_record(property_id="home-3"), ORIGIN, source_snapshot()
        )
        self.assertEqual(prediction.amount, Decimal("150000"))
        self.assertEqual(prediction.snapshot.property_id, "home-3")
        self.assertEqual(prediction.snapshot.mode, "OFF")

    def test_fit_rejects_reserved_row_id(self):
        with self.assertRaises(ValueError):
            GuardedOffMedian.fit(
                (example("sale-reserved"),),
                partition(),
                training_cutoff=TRAINING_CUTOFF,
            )

    def test_label_row_id_groups_cross_feed_copies_of_same_transfer(self):
        reserved = label_record(
            transaction_id="sale-reserved",
            economic_transfer_id="transfer-reserved",
        )
        copy = label_record(
            transaction_id="sale-reserved-copy",
            source_id="assessor",
            economic_transfer_id="transfer-reserved",
        )
        self.assertEqual(label_row_id(reserved), label_row_id(copy))

    def test_cross_feed_copy_of_reserved_transfer_is_rejected_by_split(self):
        reserved = label_record(
            transaction_id="sale-reserved",
            economic_transfer_id="transfer-reserved",
        )
        copy = label_record(
            transaction_id="sale-reserved-copy",
            source_id="assessor",
            economic_transfer_id="transfer-reserved",
        )
        with self.assertRaises(ValueError):
            transfer_partition = TrainingPartition(
                train_row_ids=frozenset({label_row_id(copy)}),
                reserved_row_ids=frozenset({label_row_id(reserved)}),
            )
            GuardedOffMedian.fit(
                (example(label=copy),),
                transfer_partition,
                training_cutoff=TRAINING_CUTOFF,
            )

    def test_training_cutoff_is_required(self):
        with self.assertRaises(TypeError):
            GuardedOffMedian.fit((example(),), partition())

    def test_predict_rejects_origin_before_model_training_cutoff(self):
        model = self.fit_two()
        earlier_origin = TRAINING_CUTOFF - timedelta(microseconds=1)
        with self.assertRaises(ValueError):
            model.predict(
                property_record(),
                earlier_origin,
                source_snapshot(as_of=earlier_origin),
            )

    def test_relabeling_reserved_transaction_with_training_row_id_is_rejected(self):
        reserved_label = label_record(
            transaction_id="sale-reserved",
            economic_transfer_id="transfer-sale-reserved",
        )
        with self.assertRaises(ValueError):
            GuardedOffMedian.fit(
                (
                    example(
                        label=reserved_label,
                        row_id=label_row_id(label_record()),
                    ),
                ),
                partition(),
                training_cutoff=TRAINING_CUTOFF,
            )

    def test_label_source_must_appear_in_source_snapshot_manifest(self):
        out_of_manifest = example(label=label_record(source_id="external"))
        external_partition = TrainingPartition(
            train_row_ids=frozenset({label_row_id(out_of_manifest.label)}),
            reserved_row_ids=frozenset(
                {example(transaction_id="sale-reserved").row_id}
            ),
        )
        with self.assertRaises(ValueError):
            GuardedOffMedian.fit(
                (out_of_manifest,),
                external_partition,
                training_cutoff=TRAINING_CUTOFF,
            )

    def test_one_economic_transfer_cannot_count_as_two_training_labels(self):
        first = example()
        duplicate_label = label_record(
            transaction_id="sale-1-copy",
            source_id="assessor",
            economic_transfer_id=first.label.economic_transfer_id,
        )
        duplicate = example(label=duplicate_label)
        duplicate_partition = TrainingPartition(
            train_row_ids=frozenset({first.row_id, duplicate.row_id}),
            reserved_row_ids=frozenset(
                {example(transaction_id="sale-reserved").row_id}
            ),
        )
        with self.assertRaises(ValueError):
            GuardedOffMedian.fit(
                (first, duplicate),
                duplicate_partition,
                training_cutoff=TRAINING_CUTOFF,
            )

    def test_label_availability_after_training_cutoff_is_rejected(self):
        late_label = label_record(
            available_at=TRAINING_CUTOFF + timedelta(microseconds=1)
        )
        with self.assertRaises(ValueError):
            GuardedOffMedian.fit(
                (example(label=late_label),),
                partition(),
                training_cutoff=TRAINING_CUTOFF,
            )

    def test_label_availability_at_exact_training_cutoff_is_accepted(self):
        model = GuardedOffMedian.fit(
            (example(),), partition(), training_cutoff=TRAINING_CUTOFF
        )
        self.assertEqual(model.amount, Decimal("100000"))

    def test_label_property_mismatch_and_ineligible_label_are_rejected(self):
        invalid_labels = (
            label_record(property_id="home-9"),
            label_record(arm_length_status="unknown"),
        )
        for label in invalid_labels:
            with self.subTest(label=label):
                with self.assertRaises(ValueError):
                    GuardedOffMedian.fit(
                        (example(label=label),),
                        partition(),
                        training_cutoff=TRAINING_CUTOFF,
                    )

    def test_training_example_rejects_mutable_event_collections(self):
        for field, value in (
            ("attributes", [attribute_record()]),
            ("transactions", [label_record()]),
            ("listing_events", [listing_record()]),
        ):
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    example(**{field: value})

    def test_fit_rejects_target_forbidden_alias_and_unknown_attributes(self):
        for name in (
            "SalePrice",
            "F172",
            "rendement_locatif",
            "mystery_field",
        ):
            with self.subTest(name=name):
                forbidden = attribute_record(name=name)
                with self.assertRaises(ValueError):
                    GuardedOffMedian.fit(
                        (example(attributes=(forbidden,)),),
                        partition(),
                        training_cutoff=TRAINING_CUTOFF,
                    )

    def test_fit_uses_fixed_feature_policy_without_caller_definitions(self):
        with self.assertRaises(TypeError):
            GuardedOffMedian.fit(
                (example(),),
                partition(),
                training_cutoff=TRAINING_CUTOFF,
                definitions={"SalePrice": object()},
            )

    def test_subject_label_cannot_reenter_as_prior_sale(self):
        model = self.fit_two()
        subject_label = label_record()
        later_origin = subject_label.available_at + timedelta(seconds=1)
        later_source = source_snapshot(as_of=later_origin)
        prediction = model.predict(
            property_record(),
            later_origin,
            later_source,
            transactions=(subject_label,),
            subject_economic_transfer_id=subject_label.economic_transfer_id,
        )
        self.assertNotIn("prior_sale_price", prediction.snapshot.values)
        self.assertNotIn("prior_sale_price", prediction.snapshot.lineage)

    def test_future_and_late_published_inputs_do_not_enter_off_snapshot(self):
        model = self.fit_two()
        visible_condition = attribute_record()
        future_attribute = attribute_record(
            name="bedrooms",
            value=3,
            observed_at=ORIGIN + timedelta(seconds=1),
            available_at=ORIGIN + timedelta(days=1),
        )
        late_sale = label_record(
            transaction_id="old-sale",
            economic_transfer_id="old-transfer",
            close_at=ORIGIN - timedelta(days=30),
            available_at=ORIGIN + timedelta(days=1),
        )
        prediction = model.predict(
            property_record(),
            ORIGIN,
            source_snapshot(),
            attributes=(visible_condition, future_attribute),
            transactions=(late_sale,),
        )
        self.assertEqual(prediction.snapshot.values["condition"], "good")
        self.assertNotIn("bedrooms", prediction.snapshot.values)
        self.assertNotIn("prior_sale_price", prediction.snapshot.values)
        self.assertEqual(
            prediction.snapshot.lineage["condition"].available_at,
            visible_condition.available_at,
        )

    def test_source_snapshot_cutoff_excludes_later_available_attribute(self):
        model = self.fit_two()
        cutoff = ORIGIN - timedelta(days=1)
        later = attribute_record(available_at=cutoff + timedelta(hours=1))
        prediction = model.predict(
            property_record(),
            ORIGIN,
            source_snapshot(as_of=cutoff),
            attributes=(later,),
        )
        self.assertNotIn("condition", prediction.snapshot.values)
        self.assertNotIn("condition", prediction.snapshot.lineage)

    def test_listing_event_never_changes_off_estimate_or_snapshot(self):
        model = self.fit_two()
        without = model.predict(property_record(), ORIGIN, source_snapshot())
        with_listing = model.predict(
            property_record(),
            ORIGIN,
            source_snapshot(),
            listing_events=(listing_record(),),
        )
        self.assertEqual(with_listing.amount, without.amount)
        self.assertEqual(with_listing.snapshot.values, without.snapshot.values)
        self.assertEqual(
            with_listing.snapshot.snapshot_hash, without.snapshot.snapshot_hash
        )


if __name__ == "__main__":
    unittest.main()
