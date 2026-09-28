"""Behavioural checks for the first canonical and point-in-time data contract."""

import unittest
from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tabpfn4realestate.data.schema import (  # noqa: E402
    Attribute,
    ListingEvent,
    Property,
    SourceSnapshot,
    Transaction,
    canonicalize_transactions,
)
from tabpfn4realestate.features.asof import assemble_snapshot  # noqa: E402


ORIGIN = datetime(2024, 6, 30, 12, tzinfo=timezone.utc)


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


def source_snapshot(**changes):
    fields = {
        "snapshot_id": "snapshot-1",
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
        "available_at": ORIGIN - timedelta(days=1),
        "source_id": "assessor",
    }
    return Attribute(**(fields | changes))


def transaction_record(**changes):
    fields = {
        "transaction_id": "sale-1",
        "economic_transfer_id": "transfer-1",
        "property_id": "home-1",
        "close_at": ORIGIN - timedelta(days=10),
        "available_at": ORIGIN - timedelta(days=1),
        "price": Decimal("400000"),
        "currency": "USD",
        "source_id": "sales",
        "scope": "single_property",
        "consideration_type": "gross_recorded_sale",
        "arm_length_status": "confirmed",
        "adjustment_flags": (),
    }
    return Transaction(**(fields | changes))


def listing_record(**changes):
    fields = {
        "listing_id": "listing-1",
        "property_id": "home-1",
        "event_type": "asking_price",
        "event_at": ORIGIN - timedelta(days=7),
        "available_at": ORIGIN - timedelta(days=6),
        "source_id": "listings",
        "amount": Decimal("450000"),
    }
    return ListingEvent(**(fields | changes))


class CanonicalRecordTests(unittest.TestCase):
    def test_records_are_immutable(self):
        records = (
            property_record(),
            transaction_record(),
            attribute_record(),
            listing_record(),
            source_snapshot(),
        )
        for record in records:
            with self.subTest(record=type(record).__name__):
                with self.assertRaises(FrozenInstanceError):
                    record.source_id = "changed"

    def test_event_and_availability_instants_must_be_timezone_aware(self):
        naive = ORIGIN.replace(tzinfo=None)
        for factory, change in (
            (property_record, {"observed_at": naive}),
            (property_record, {"available_at": naive}),
            (transaction_record, {"available_at": naive}),
            (transaction_record, {"close_at": naive}),
            (attribute_record, {"observed_at": naive}),
            (listing_record, {"event_at": naive}),
            (source_snapshot, {"as_of": naive}),
        ):
            with self.subTest(factory=factory.__name__, change=change):
                with self.assertRaises(ValueError):
                    factory(**change)

    def test_money_and_area_units_are_validated(self):
        with self.assertRaises(ValueError):
            property_record(living_area_unit="acres")
        with self.assertRaises(ValueError):
            transaction_record(price=400000)
        with self.assertRaises(ValueError):
            listing_record(amount=450000)
        with self.assertRaises(ValueError):
            transaction_record(currency="EUR")

    def test_identity_identifiers_reject_surrounding_whitespace(self):
        for factory, change in (
            (property_record, {"property_id": " home-1"}),
            (property_record, {"source_id": "assessor "}),
            (transaction_record, {"transaction_id": "sale-1 "}),
            (transaction_record, {"economic_transfer_id": " transfer-1"}),
            (attribute_record, {"property_id": "home-1 "}),
            (listing_record, {"listing_id": " listing-1"}),
            (source_snapshot, {"snapshot_id": "snapshot-1 "}),
            (source_snapshot, {"source_ids": ("assessor ", "sales")}),
        ):
            with self.subTest(factory=factory.__name__, change=change):
                with self.assertRaises(ValueError):
                    factory(**change)

    def test_missing_state_is_explicit_and_distinct_from_zero(self):
        missing = attribute_record(name="bedrooms", value=None, missing_state="unknown")
        zero = attribute_record(name="bedrooms", value=0)
        self.assertEqual(missing.missing_state, "unknown")
        self.assertEqual(zero.value, 0)
        with self.assertRaises(ValueError):
            attribute_record(name="bedrooms", value=None, missing_state="invented")

    def test_identical_cross_feed_transfer_has_one_canonical_label(self):
        first = transaction_record()
        duplicate = transaction_record(
            transaction_id="sale-1-copy", source_id="assessor"
        )
        result = canonicalize_transactions((first, duplicate))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].economic_transfer_id, "transfer-1")
        self.assertEqual(result[0].price, Decimal("400000"))

    def test_conflicting_cross_feed_transfer_is_quarantined_not_doubled(self):
        first = transaction_record()
        conflict = transaction_record(
            transaction_id="sale-1-copy", source_id="assessor", price=Decimal("410000")
        )
        with self.assertRaises(ValueError):
            canonicalize_transactions((first, conflict))

    def test_unsupported_arm_length_status_is_rejected(self):
        with self.assertRaises(ValueError):
            transaction_record(arm_length_status="perhaps")

    def test_raw_transaction_ids_are_scoped_by_source(self):
        first = transaction_record(transaction_id="shared-id", source_id="sales")
        second = transaction_record(
            transaction_id="shared-id",
            source_id="assessor",
            economic_transfer_id="transfer-2",
            close_at=ORIGIN - timedelta(days=20),
            price=Decimal("350000"),
        )
        canonical = canonicalize_transactions((first, second))
        self.assertEqual(len(canonical), 2)
        self.assertEqual(
            {row.economic_transfer_id for row in canonical},
            {"transfer-1", "transfer-2"},
        )


class PointInTimeFeatureTests(unittest.TestCase):
    def snapshot(
        self,
        *,
        mode="OFF",
        attributes=(),
        listings=(),
        transactions=(),
        subject_transaction_id=None,
        subject_source_id=None,
        subject_economic_transfer_id=None,
    ):
        extra = {
            **(
                {"subject_source_id": subject_source_id}
                if subject_source_id is not None
                else {}
            ),
            **(
                {"subject_economic_transfer_id": subject_economic_transfer_id}
                if subject_economic_transfer_id is not None
                else {}
            ),
        }
        return assemble_snapshot(
            property_record(),
            ORIGIN,
            mode,
            source_snapshot(),
            attributes=attributes,
            listing_events=listings,
            transactions=transactions,
            subject_transaction_id=subject_transaction_id,
            **extra,
        )

    def test_exact_availability_boundary_is_inclusive(self):
        at_origin = attribute_record(available_at=ORIGIN)
        after_origin = attribute_record(
            name="bedrooms", value=3, available_at=ORIGIN + timedelta(microseconds=1)
        )
        snapshot = self.snapshot(attributes=(at_origin, after_origin))
        self.assertEqual(snapshot.values["condition"], "good")
        self.assertNotIn("bedrooms", snapshot.values)

    def test_off_mode_excludes_listings_even_if_available(self):
        empty = self.snapshot()
        with_listing = self.snapshot(listings=(listing_record(),))
        self.assertEqual(empty.values, with_listing.values)
        self.assertEqual(empty.lineage, with_listing.lineage)

    def test_on_mode_is_explicitly_unavailable_without_historical_feed(self):
        with self.assertRaises(NotImplementedError):
            self.snapshot(mode="ON", listings=(listing_record(),))

    def test_late_published_sale_is_unavailable_despite_earlier_close(self):
        late = transaction_record(available_at=ORIGIN + timedelta(days=1))
        empty = self.snapshot()
        with_late_sale = self.snapshot(transactions=(late,))
        self.assertEqual(empty.values, with_late_sale.values)
        self.assertEqual(empty.lineage, with_late_sale.lineage)

    def test_sale_after_origin_is_not_prior_history_even_if_published(self):
        future = transaction_record(
            close_at=ORIGIN + timedelta(days=1), available_at=ORIGIN
        )
        empty = self.snapshot()
        with_future = self.snapshot(transactions=(future,))
        self.assertEqual(empty.values, with_future.values)
        self.assertEqual(empty.lineage, with_future.lineage)

    def test_known_prior_sale_is_available_except_subject_transaction(self):
        prior = transaction_record()
        with_prior = self.snapshot(transactions=(prior,))
        without_prior = self.snapshot()
        excluded = self.snapshot(
            transactions=(prior,),
            subject_transaction_id=prior.transaction_id,
            subject_source_id=prior.source_id,
        )
        self.assertNotEqual(with_prior.values, without_prior.values)
        self.assertEqual(excluded.values, without_prior.values)
        self.assertEqual(excluded.lineage, without_prior.lineage)

    def test_subject_sale_duplicate_from_another_feed_is_also_excluded(self):
        subject = transaction_record()
        duplicate = transaction_record(
            transaction_id="sale-1-copy", source_id="assessor"
        )
        excluded = self.snapshot(
            transactions=(subject, duplicate),
            subject_transaction_id=subject.transaction_id,
            subject_source_id=subject.source_id,
        )
        self.assertNotIn("prior_sale_price", excluded.values)

    def test_subject_economic_transfer_id_excludes_sale_when_subject_row_absent(self):
        duplicate = transaction_record(
            transaction_id="sale-1-copy", source_id="assessor"
        )
        excluded = self.snapshot(
            transactions=(duplicate,),
            subject_economic_transfer_id=duplicate.economic_transfer_id,
        )
        self.assertNotIn("prior_sale_price", excluded.values)

    def test_unknown_subject_transaction_id_fails_closed(self):
        with self.assertRaises(ValueError):
            self.snapshot(
                transactions=(transaction_record(),),
                subject_transaction_id="sale-not-found",
                subject_source_id="sales",
            )

    def test_subject_transaction_id_requires_source_namespace(self):
        with self.assertRaises(ValueError):
            self.snapshot(
                transactions=(transaction_record(),),
                subject_transaction_id="sale-1",
            )

    def test_both_subject_ids_fail_closed_when_transaction_id_is_absent(self):
        duplicate = transaction_record(transaction_id="sale-1-copy")
        with self.assertRaises(ValueError):
            self.snapshot(
                transactions=(duplicate,),
                subject_transaction_id="sale-not-found",
                subject_source_id="sales",
                subject_economic_transfer_id=duplicate.economic_transfer_id,
            )

    def test_ineligible_prior_sales_do_not_become_features(self):
        variants = (
            {"scope": "partial_interest"},
            {"scope": "multi_property"},
            {"consideration_type": "nominal"},
            {"arm_length_status": "unknown"},
            {"adjustment_flags": ("foreclosure",)},
        )
        for change in variants:
            with self.subTest(change=change):
                sale = transaction_record(**change)
                snapshot = self.snapshot(transactions=(sale,))
                self.assertNotIn("prior_sale_price", snapshot.values)

    def test_conflicting_duplicate_eligibility_is_quarantined_before_filtering(self):
        unflagged = transaction_record(source_id="sales")
        flagged_duplicate = transaction_record(
            transaction_id="sale-1-copy",
            source_id="assessor",
            adjustment_flags=("foreclosure",),
        )
        with self.assertRaises(ValueError):
            self.snapshot(transactions=(unflagged, flagged_duplicate))

    def test_subject_id_match_on_another_property_fails_closed(self):
        target_duplicate = transaction_record(transaction_id="sale-1-copy")
        unrelated_same_id = transaction_record(
            economic_transfer_id="transfer-2", property_id="home-2"
        )
        with self.assertRaises(ValueError):
            self.snapshot(
                transactions=(target_duplicate, unrelated_same_id),
                subject_transaction_id="sale-1",
                subject_source_id="sales",
            )

    def test_same_property_cross_feed_raw_id_collision_fails_closed(self):
        older_assessor = transaction_record(
            transaction_id="sale-1",
            economic_transfer_id="older-transfer",
            source_id="assessor",
            close_at=ORIGIN - timedelta(days=365),
            price=Decimal("300000"),
        )
        target_duplicate = transaction_record(
            transaction_id="sale-1-copy",
            economic_transfer_id="target-transfer",
            source_id="sales",
        )
        with self.assertRaises(ValueError):
            self.snapshot(
                transactions=(older_assessor, target_duplicate),
                subject_transaction_id="sale-1",
                subject_source_id="sales",
            )

    def test_future_observation_disappears_when_origin_moves_earlier(self):
        recent = attribute_record(available_at=ORIGIN)
        current = self.snapshot(attributes=(recent,))
        earlier = assemble_snapshot(
            property_record(),
            ORIGIN - timedelta(days=1),
            "OFF",
            source_snapshot(),
            attributes=(recent,),
        )
        self.assertIn("condition", current.values)
        self.assertNotIn("condition", earlier.values)

    def test_target_and_forbidden_features_cannot_enter_snapshot(self):
        for name in ("SalePrice", "F172", "F349", "F350"):
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    self.snapshot(attributes=(attribute_record(name=name),))

    def test_unregistered_attribute_fails_closed(self):
        with self.assertRaises(ValueError):
            self.snapshot(
                attributes=(attribute_record(name="speculative_investment_score"),)
            )

    def test_lineage_retains_source_observation_and_availability(self):
        source = attribute_record()
        snapshot = self.snapshot(attributes=(source,))
        lineage = snapshot.lineage["condition"]
        self.assertEqual(lineage.source_id, "assessor")
        self.assertEqual(lineage.observed_at, source.observed_at)
        self.assertEqual(lineage.available_at, source.available_at)

    def test_unregistered_source_cannot_enter_snapshot(self):
        with self.assertRaises(ValueError):
            self.snapshot(attributes=(attribute_record(source_id="unknown-feed"),))

    def test_source_snapshot_cannot_authorize_later_availability(self):
        too_new = attribute_record(
            name="bedrooms", value=3, available_at=ORIGIN - timedelta(hours=1)
        )
        stale_snapshot = SourceSnapshot(
            snapshot_id="old-snapshot",
            source_ids=("assessor",),
            as_of=ORIGIN - timedelta(days=1),
        )
        result = assemble_snapshot(
            property_record(), ORIGIN, "OFF", stale_snapshot, attributes=(too_new,)
        )
        self.assertNotIn("bedrooms", result.values)

    def test_source_snapshot_cannot_authorize_later_observation(self):
        cutoff = ORIGIN - timedelta(days=1)
        too_new_attribute = attribute_record(
            name="bedrooms",
            value=3,
            observed_at=cutoff + timedelta(hours=1),
            available_at=cutoff - timedelta(hours=1),
        )
        too_new_sale = transaction_record(
            close_at=cutoff + timedelta(hours=1),
            available_at=cutoff - timedelta(hours=1),
        )
        stale_snapshot = source_snapshot(as_of=cutoff)
        result = assemble_snapshot(
            property_record(),
            ORIGIN,
            "OFF",
            stale_snapshot,
            attributes=(too_new_attribute,),
            transactions=(too_new_sale,),
        )
        self.assertNotIn("bedrooms", result.values)
        self.assertNotIn("prior_sale_price", result.values)

    def test_source_manifest_content_changes_snapshot_hash(self):
        base = self.snapshot()
        with_extra_source = assemble_snapshot(
            property_record(),
            ORIGIN,
            "OFF",
            source_snapshot(source_ids=("assessor", "sales", "listings", "other")),
        )
        with_earlier_cutoff = assemble_snapshot(
            property_record(),
            ORIGIN,
            "OFF",
            source_snapshot(as_of=ORIGIN - timedelta(hours=1)),
        )
        self.assertNotEqual(base.snapshot_hash, with_extra_source.snapshot_hash)
        self.assertNotEqual(base.snapshot_hash, with_earlier_cutoff.snapshot_hash)

    def test_snapshot_retains_missing_states_without_converting_to_zero(self):
        missing_property = property_record(
            living_area=None, living_area_unit=None, living_area_state="unknown"
        )
        missing_bedrooms = attribute_record(
            name="bedrooms", value=None, missing_state="structurally_absent"
        )
        missing = assemble_snapshot(
            missing_property,
            ORIGIN,
            "OFF",
            source_snapshot(),
            attributes=(missing_bedrooms,),
        )
        zero = self.snapshot(attributes=(attribute_record(name="bedrooms", value=0),))
        self.assertNotIn("living_area", missing.values)
        self.assertEqual(missing.values["living_area_state"], "unknown")
        self.assertNotIn("bedrooms", missing.values)
        self.assertEqual(missing.values["bedrooms_state"], "structurally_absent")
        self.assertEqual(zero.values["bedrooms"], 0)

    def test_property_source_must_be_available_by_origin(self):
        future_property = property_record(available_at=ORIGIN + timedelta(seconds=1))
        with self.assertRaises(ValueError):
            assemble_snapshot(future_property, ORIGIN, "OFF", source_snapshot())


if __name__ == "__main__":
    unittest.main()
