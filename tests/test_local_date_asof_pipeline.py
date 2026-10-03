"""Calendar-origin OFF feature snapshots use an exclusive source-local day end."""

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


from tabpfn4realestate.data.schema import (
    Attribute,
    Property,
    SourceSnapshot,
    Transaction,
)  # noqa: E402
from tabpfn4realestate.evaluation.local_dates import derive_local_date_origin  # noqa: E402
from tabpfn4realestate.features import asof  # noqa: E402
from tabpfn4realestate.features.asof import (  # noqa: E402
    assemble_local_date_snapshot,
    assemble_local_date_snapshot_from_versions,
)


UTC = timezone.utc
SOURCE = "synthetic-county"
SPRING = derive_local_date_origin(date(2024, 6, 8), "America/New_York")
FALL = derive_local_date_origin(date(2025, 2, 1), "America/New_York")


def property_row(**changes):
    return replace(
        Property(
            property_id="home-1",
            country="US",
            property_type="single_family",
            source_id=SOURCE,
            observed_at=datetime(2023, 1, 1, tzinfo=UTC),
            available_at=datetime(2023, 1, 2, tzinfo=UTC),
            living_area=Decimal("1500"),
            living_area_unit="sqft",
        ),
        **changes,
    )


def source_snapshot(as_of):
    return SourceSnapshot("synthetic-source-snapshot", (SOURCE,), as_of)


def condition(value, available_at):
    return Attribute(
        property_id="home-1",
        name="condition",
        value=value,
        observed_at=available_at,
        available_at=available_at,
        source_id=SOURCE,
    )


def prior_sale(available_at):
    return Transaction(
        transaction_id="earlier-deed",
        economic_transfer_id="earlier-sale",
        property_id="home-1",
        close_at=datetime(2024, 2, 1, tzinfo=UTC),
        available_at=available_at,
        price=Decimal("120000"),
        currency="USD",
        source_id=SOURCE,
        scope="single_property",
        consideration_type="gross_recorded_sale",
        arm_length_status="confirmed",
        adjustment_flags=(),
    )


class LocalDateAsOfTests(unittest.TestCase):
    def test_spring_day_excludes_attribute_and_prior_sale_at_exact_cutoff(self):
        cutoff = SPRING.cutoff_exclusive_utc
        snapshot = assemble_local_date_snapshot(
            property_row(),
            SPRING,
            "OFF",
            source_snapshot(cutoff + timedelta(days=1)),
            attributes=(
                condition("known", cutoff - timedelta(microseconds=1)),
                condition("future", cutoff),
            ),
            transactions=(prior_sale(cutoff),),
        )
        self.assertEqual(snapshot.values["condition"], "known")
        self.assertNotIn("prior_sale_price", snapshot.values)
        self.assertEqual(snapshot.origin, SPRING)
        self.assertEqual(snapshot.origin.policy_hash, SPRING.policy_hash)

    def test_fall_fold_remains_visible_until_next_local_midnight(self):
        first_fold = datetime(2024, 11, 3, 5, 30, tzinfo=UTC)
        second_fold = datetime(2024, 11, 3, 6, 30, tzinfo=UTC)
        snapshot = assemble_local_date_snapshot(
            property_row(),
            FALL,
            "OFF",
            source_snapshot(FALL.cutoff_exclusive_utc),
            attributes=(
                condition("first", first_fold),
                condition("second", second_fold),
            ),
        )
        self.assertEqual(snapshot.values["condition"], "second")
        self.assertEqual(
            FALL.cutoff_exclusive_utc, datetime(2024, 11, 4, 5, tzinfo=UTC)
        )

    def test_source_snapshot_cap_excludes_later_publication(self):
        published = SPRING.cutoff_exclusive_utc - timedelta(hours=1)
        snapshot = assemble_local_date_snapshot(
            property_row(),
            SPRING,
            "OFF",
            source_snapshot(published - timedelta(seconds=1)),
            attributes=(condition("not-yet-in-source", published),),
        )
        self.assertNotIn("condition", snapshot.values)

    def test_source_snapshot_cap_is_inclusive_when_earlier_but_origin_end_is_exclusive(
        self,
    ):
        earlier_cap = SPRING.cutoff_exclusive_utc - timedelta(hours=1)
        at_cap = assemble_local_date_snapshot(
            property_row(),
            SPRING,
            "OFF",
            source_snapshot(earlier_cap),
            attributes=(condition("known-at-cap", earlier_cap),),
        )
        self.assertEqual(at_cap.values["condition"], "known-at-cap")
        at_origin_end = assemble_local_date_snapshot(
            property_row(),
            SPRING,
            "OFF",
            source_snapshot(SPRING.cutoff_exclusive_utc),
            attributes=(
                condition("future-at-origin-end", SPRING.cutoff_exclusive_utc),
            ),
        )
        self.assertNotIn("condition", at_origin_end.values)

    def test_version_start_at_cutoff_is_future_and_end_at_cutoff_is_still_current(self):
        cutoff = SPRING.cutoff_exclusive_utc
        old = property_row(
            valid_to=cutoff,
            valid_to_available_at=cutoff - timedelta(hours=1),
        )
        future = property_row(
            observed_at=cutoff,
            available_at=cutoff,
            valid_from=cutoff,
            living_area=Decimal("1800"),
        )
        snapshot = assemble_local_date_snapshot_from_versions(
            "home-1",
            (old, future),
            SPRING,
            "OFF",
            source_snapshot(cutoff + timedelta(days=1)),
        )
        self.assertEqual(snapshot.values["living_area"], Decimal("1500"))
        self.assertEqual(snapshot.lineage["living_area"].valid_to, cutoff)

    def test_version_end_published_at_cutoff_is_not_known_yet(self):
        cutoff = SPRING.cutoff_exclusive_utc
        future_disclosure = property_row(valid_to=cutoff, valid_to_available_at=cutoff)
        snapshot = assemble_local_date_snapshot_from_versions(
            "home-1",
            (future_disclosure,),
            SPRING,
            "OFF",
            source_snapshot(cutoff + timedelta(days=1)),
        )
        self.assertIsNone(snapshot.lineage["living_area"].valid_to)

    def test_calendar_snapshot_identity_is_deterministic_and_protocol_distinct(self):
        first = assemble_local_date_snapshot(
            property_row(), SPRING, "OFF", source_snapshot(SPRING.cutoff_exclusive_utc)
        )
        second = assemble_local_date_snapshot(
            property_row(), SPRING, "OFF", source_snapshot(SPRING.cutoff_exclusive_utc)
        )
        other_zone = derive_local_date_origin(date(2024, 6, 8), "America/Chicago")
        third = assemble_local_date_snapshot(
            property_row(),
            other_zone,
            "OFF",
            source_snapshot(SPRING.cutoff_exclusive_utc),
        )
        self.assertEqual(first.snapshot_hash, second.snapshot_hash)
        self.assertNotEqual(first.snapshot_hash, third.snapshot_hash)
        self.assertEqual(len(first.snapshot_hash), 64)

    def test_calendar_snapshot_identity_includes_assembler_policy(self):
        original = assemble_local_date_snapshot(
            property_row(), SPRING, "OFF", source_snapshot(SPRING.cutoff_exclusive_utc)
        )
        with patch.object(
            asof, "LOCAL_DATE_ASSEMBLER_POLICY_VERSION", "test-revision", create=True
        ):
            revised = assemble_local_date_snapshot(
                property_row(),
                SPRING,
                "OFF",
                source_snapshot(SPRING.cutoff_exclusive_utc),
            )
        self.assertNotEqual(original.snapshot_hash, revised.snapshot_hash)


if __name__ == "__main__":
    unittest.main()
