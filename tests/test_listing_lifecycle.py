"""Synthetic adversarial fixtures for the US04 listing lifecycle contract."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
import sys
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tabpfn4realestate.data.lifecycle import (  # noqa: E402
    ListingObservation,
    PropertyIdentity,
    VerifiedListingAlias,
    resolve_lifecycle,
)


BASE = datetime(2025, 1, 1, 9, tzinfo=timezone.utc)


def home(**changes: object) -> PropertyIdentity:
    return PropertyIdentity(
        property_id=changes.get("property_id", "home-1"),
        address_key=changes.get("address_key", "10 MAIN ST"),
        parcel_key=changes.get("parcel_key", "parcel-1"),
        unit_key=changes.get("unit_key"),
        valid_from=changes.get("valid_from", BASE - timedelta(days=365)),
        valid_to=changes.get("valid_to"),
        available_at=changes.get("available_at", BASE - timedelta(days=365)),
    )


def event(
    event_id: str,
    event_type: str,
    event_at: datetime,
    **changes: object,
) -> ListingObservation:
    return ListingObservation(
        source_id=changes.get("source_id", "feed-a"),
        event_id=event_id,
        source_listing_id=changes.get("source_listing_id", "listing-1"),
        address_key=changes.get("address_key", "10 MAIN ST"),
        parcel_key=changes.get("parcel_key", "parcel-1"),
        unit_key=changes.get("unit_key"),
        event_type=event_type,
        event_at=event_at,
        available_at=changes.get("available_at", event_at),
        ingested_at=changes.get("ingested_at", event_at + timedelta(days=100)),
        amount=changes.get("amount"),
    )


def alias(source_id: str, source_listing_id: str = "listing-1") -> VerifiedListingAlias:
    return VerifiedListingAlias(
        source_id=source_id,
        source_listing_id=source_listing_id,
        canonical_listing_id="reviewed-listing-1",
        evidence_id="synthetic-review-1",
        available_at=BASE - timedelta(days=1),
    )


class ListingLifecycleTests(unittest.TestCase):
    def test_duplicate_feeds_need_verified_episode_alias_and_keep_raw_events(self):
        first = event("a-publication", "published", BASE, amount=Decimal("500000"))
        second = event(
            "b-publication",
            "published",
            BASE,
            source_id="feed-b",
            amount=Decimal("500000"),
        )
        separate = resolve_lifecycle((home(),), (first, second), origin=BASE)
        self.assertEqual(len(separate.episodes), 2)
        self.assertTrue(
            all("overlapping_listings" in e.flags for e in separate.episodes)
        )

        linked = resolve_lifecycle(
            (home(),),
            (first, second),
            aliases=(alias("feed-a"), alias("feed-b")),
            origin=BASE,
        )
        self.assertEqual(len(linked.episodes), 1)
        self.assertEqual(len(linked.episodes[0].events), 1)
        self.assertEqual(len(linked.episodes[0].events[0].source_events), 2)
        self.assertEqual(len(linked.source_events), 2)
        self.assertEqual(linked.quarantined, ())

    def test_future_alias_evidence_cannot_merge_historical_episodes(self):
        first = event("a-publication", "published", BASE, amount=Decimal("500000"))
        second = event(
            "b-publication",
            "published",
            BASE,
            source_id="feed-b",
            amount=Decimal("500000"),
        )
        future_aliases = (
            replace(alias("feed-a"), available_at=BASE + timedelta(days=2)),
            replace(alias("feed-b"), available_at=BASE + timedelta(days=2)),
        )
        before = resolve_lifecycle(
            (home(),), (first, second), aliases=future_aliases, origin=BASE
        )
        after = resolve_lifecycle(
            (home(),),
            (first, second),
            aliases=future_aliases,
            origin=BASE + timedelta(days=2),
        )
        self.assertEqual(len(before.episodes), 2)
        self.assertEqual(len(after.episodes), 1)

    def test_same_day_ordered_price_changes_are_retained(self):
        observations = (
            event("publish", "published", BASE, amount=Decimal("500000")),
            event(
                "change-1",
                "price_change",
                BASE + timedelta(hours=2),
                amount=Decimal("525000"),
            ),
            event(
                "change-2",
                "price_change",
                BASE + timedelta(hours=7),
                amount=Decimal("510000"),
            ),
        )
        result = resolve_lifecycle(
            (home(),), observations, origin=BASE + timedelta(hours=8)
        )
        self.assertEqual(len(result.episodes), 1)
        self.assertEqual(
            [e.event_type for e in result.episodes[0].events],
            ["published", "price_change", "price_change"],
        )
        self.assertEqual(result.episodes[0].asking_price, Decimal("510000"))

    def test_conflicting_same_instant_changes_quarantine_the_episode(self):
        observations = (
            event("publish", "published", BASE, amount=Decimal("500000")),
            event(
                "change-1",
                "price_change",
                BASE + timedelta(hours=2),
                amount=Decimal("510000"),
            ),
            event(
                "change-2",
                "price_change",
                BASE + timedelta(hours=2),
                amount=Decimal("520000"),
            ),
        )
        result = resolve_lifecycle(
            (home(),), observations, origin=BASE + timedelta(hours=3)
        )
        self.assertEqual(result.episodes, ())
        self.assertEqual(
            {q.reason for q in result.quarantined}, {"conflicting_simultaneous_events"}
        )

    def test_late_publication_is_hidden_until_available(self):
        delayed = event(
            "publish",
            "published",
            BASE,
            available_at=BASE + timedelta(days=2),
            amount=Decimal("500000"),
        )
        before = resolve_lifecycle(
            (home(),), (delayed,), origin=BASE + timedelta(days=1)
        )
        after = resolve_lifecycle(
            (home(),), (delayed,), origin=BASE + timedelta(days=2)
        )
        self.assertEqual(before.episodes, ())
        self.assertEqual(before.source_events, ())
        self.assertEqual(len(after.episodes), 1)
        self.assertEqual(after.episodes[0].status, "active")

    def test_late_status_event_does_not_end_episode_before_publication(self):
        publication = event("publish", "published", BASE, amount=Decimal("500000"))
        delayed_sale_status = event(
            "sale-status",
            "sold",
            BASE + timedelta(days=2),
            available_at=BASE + timedelta(days=4),
        )
        before = resolve_lifecycle(
            (home(),),
            (publication, delayed_sale_status),
            origin=BASE + timedelta(days=3),
        )
        at_availability = resolve_lifecycle(
            (home(),),
            (publication, delayed_sale_status),
            origin=BASE + timedelta(days=4),
        )
        self.assertEqual(before.episodes[0].status, "active")
        self.assertEqual(at_availability.episodes[0].status, "sold")

    def test_withdrawal_does_not_turn_into_a_sale_from_another_channel(self):
        observations = (
            event("publish", "published", BASE, amount=Decimal("500000")),
            event("withdraw", "withdrawn", BASE + timedelta(days=7)),
            event(
                "other-publish",
                "published",
                BASE + timedelta(days=10),
                source_id="other-agent",
                source_listing_id="other-listing",
                amount=Decimal("490000"),
            ),
            event(
                "other-sale",
                "sold",
                BASE + timedelta(days=20),
                source_id="other-agent",
                source_listing_id="other-listing",
            ),
        )
        result = resolve_lifecycle(
            (home(),), observations, origin=BASE + timedelta(days=21)
        )
        self.assertEqual(len(result.episodes), 2)
        self.assertEqual(
            {e.canonical_listing_id: e.status for e in result.episodes},
            {
                "source:feed-a:listing-1": "withdrawn",
                "source:other-agent:other-listing": "sold",
            },
        )
        self.assertEqual(result.quarantined, ())

    def test_subdivision_versions_and_units_resolve_to_distinct_properties(self):
        split = BASE + timedelta(days=1)
        properties = (
            home(property_id="old-house", valid_to=split),
            home(property_id="unit-a", unit_key="A", valid_from=split),
            home(property_id="unit-b", unit_key="B", valid_from=split),
        )
        observations = (
            event("old", "published", BASE, amount=Decimal("700000")),
            event(
                "a",
                "published",
                split,
                source_listing_id="a",
                unit_key="A",
                amount=Decimal("350000"),
            ),
            event(
                "b",
                "published",
                split,
                source_listing_id="b",
                unit_key="B",
                amount=Decimal("360000"),
            ),
        )
        result = resolve_lifecycle(properties, observations, origin=split)
        self.assertEqual(
            {e.property_id for e in result.episodes}, {"old-house", "unit-a", "unit-b"}
        )
        self.assertEqual(result.quarantined, ())

    def test_missing_apartment_in_multiunit_building_is_quarantined(self):
        properties = (
            home(property_id="unit-a", unit_key="A"),
            home(property_id="unit-b", unit_key="B"),
        )
        result = resolve_lifecycle(
            properties,
            (event("unknown-unit", "published", BASE, amount=Decimal("350000")),),
            origin=BASE,
        )
        self.assertEqual(result.episodes, ())
        self.assertEqual(result.quarantined[0].reason, "unit_missing_ambiguous")

    def test_relisting_starts_a_new_episode_on_the_same_property(self):
        observations = (
            event("publish-1", "published", BASE, amount=Decimal("500000")),
            event("withdraw", "withdrawn", BASE + timedelta(days=7)),
            event(
                "publish-2",
                "published",
                BASE + timedelta(days=14),
                amount=Decimal("490000"),
            ),
        )
        result = resolve_lifecycle(
            (home(),), observations, origin=BASE + timedelta(days=15)
        )
        self.assertEqual(
            [(e.property_id, e.generation, e.status) for e in result.episodes],
            [("home-1", 1, "withdrawn"), ("home-1", 2, "active")],
        )

    def test_source_event_ids_are_scoped_and_conflicts_quarantined(self):
        first = event("shared", "published", BASE, amount=Decimal("500000"))
        other_source = replace(first, source_id="feed-b")
        valid = resolve_lifecycle((home(),), (first, other_source), origin=BASE)
        self.assertEqual(len(valid.source_events), 2)
        conflicting = replace(first, amount=Decimal("450000"))
        invalid = resolve_lifecycle((home(),), (first, conflicting), origin=BASE)
        self.assertEqual(invalid.episodes, ())
        self.assertEqual(invalid.quarantined[0].reason, "source_event_id_conflict")

    def test_exact_reingestion_and_reversed_input_are_deterministic(self):
        publication = event("publish", "published", BASE, amount=Decimal("500000"))
        change = event(
            "change",
            "price_change",
            BASE + timedelta(hours=1),
            amount=Decimal("490000"),
        )
        forward = resolve_lifecycle(
            (home(),),
            (publication, publication, change),
            origin=BASE + timedelta(hours=2),
        )
        reversed_rows = resolve_lifecycle(
            (home(),),
            (change, publication, publication),
            origin=BASE + timedelta(hours=2),
        )
        self.assertEqual(forward, reversed_rows)
        self.assertEqual(len(forward.episodes[0].events), 2)
        self.assertEqual(len(forward.source_events), 3)

    def test_reingestion_with_later_local_timestamp_preserves_source_event(self):
        first = event("publish", "published", BASE, amount=Decimal("500000"))
        later_ingestion = replace(
            first, ingested_at=first.ingested_at + timedelta(days=1)
        )
        result = resolve_lifecycle((home(),), (first, later_ingestion), origin=BASE)
        self.assertEqual(len(result.episodes), 1)
        self.assertEqual(len(result.episodes[0].events), 1)
        self.assertEqual(len(result.episodes[0].events[0].source_events), 2)
        self.assertEqual(result.quarantined, ())

    def test_conflicting_source_event_quarantine_is_input_order_independent(self):
        first = event("publish", "published", BASE, amount=Decimal("500000"))
        conflicting = replace(first, amount=Decimal("450000"))
        forward = resolve_lifecycle((home(),), (first, conflicting), origin=BASE)
        backward = resolve_lifecycle((home(),), (conflicting, first), origin=BASE)
        self.assertEqual(forward, backward)

    def test_reviewed_alias_id_cannot_collide_with_unaliased_listing_id(self):
        first = event(
            "a", "published", BASE, source_id="feed-a", amount=Decimal("500000")
        )
        second = event(
            "b", "published", BASE, source_id="feed-b", amount=Decimal("500000")
        )
        colliding_alias = replace(
            alias("feed-a"), canonical_listing_id="feed-b:listing-1"
        )
        result = resolve_lifecycle(
            (home(),), (first, second), aliases=(colliding_alias,), origin=BASE
        )
        self.assertEqual(len(result.episodes), 2)
        self.assertEqual(
            {e.canonical_listing_id for e in result.episodes},
            {"reviewed:feed-b:listing-1", "source:feed-b:listing-1"},
        )

    def test_reviewed_alias_cannot_merge_distinct_units(self):
        properties = (
            home(property_id="unit-a", unit_key="A"),
            home(property_id="unit-b", unit_key="B"),
        )
        a = event(
            "a",
            "published",
            BASE,
            source_id="feed-a",
            unit_key="A",
            amount=Decimal("350000"),
        )
        b = event(
            "b",
            "published",
            BASE,
            source_id="feed-b",
            unit_key="B",
            amount=Decimal("350000"),
        )
        result = resolve_lifecycle(
            properties, (a, b), aliases=(alias("feed-a"), alias("feed-b")), origin=BASE
        )
        self.assertEqual(result.episodes, ())
        self.assertEqual(
            result.quarantined[0].reason, "listing_alias_property_conflict"
        )

    def test_unknown_first_availability_is_quarantined(self):
        unknown = event(
            "publish", "published", BASE, available_at=None, amount=Decimal("500000")
        )
        result = resolve_lifecycle(
            (home(),), (unknown,), origin=BASE + timedelta(days=1)
        )
        self.assertEqual(result.episodes, ())
        self.assertEqual(result.quarantined[0].reason, "availability_unknown")


if __name__ == "__main__":
    unittest.main()
