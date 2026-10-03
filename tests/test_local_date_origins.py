"""US source-local calendar-date origins and availability boundary tests."""

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tabpfn4realestate.evaluation.local_dates import (  # noqa: E402
    DateOnlyAvailability,
    derive_local_date_origin,
    is_visible_at_date_origin,
)
from tabpfn4realestate.evaluation import local_dates  # noqa: E402


class LocalDateOriginTests(unittest.TestCase):
    def test_pinned_zone_load_is_cached_after_each_call_validates_inputs(self):
        local_dates._load_pinned_zone.cache_clear()
        self.addCleanup(local_dates._load_pinned_zone.cache_clear)
        with patch.object(local_dates, "files", wraps=local_dates.files) as resources:
            first = derive_local_date_origin(date(2024, 6, 8), "America/New_York")
            second = derive_local_date_origin(date(2024, 6, 8), "America/New_York")
            self.assertEqual(first, second)
            self.assertEqual(resources.call_count, 1)
            with patch.object(local_dates.tzdata, "__version__", "unapproved"):
                with self.assertRaisesRegex(RuntimeError, "frozen date policy"):
                    derive_local_date_origin(date(2024, 6, 8), "America/New_York")
            self.assertEqual(resources.call_count, 1)
            with self.assertRaisesRegex(ValueError, "normalized IANA"):
                derive_local_date_origin(date(2024, 6, 8), "America/../New_York")

    def test_unknown_zone_failure_is_not_cached(self):
        local_dates._load_pinned_zone.cache_clear()
        self.addCleanup(local_dates._load_pinned_zone.cache_clear)
        with patch.object(local_dates, "files", wraps=local_dates.files) as resources:
            for _ in range(2):
                with self.assertRaisesRegex(ValueError, "Unknown IANA"):
                    derive_local_date_origin(date(2024, 6, 8), "Unknown/Nowhere")
            self.assertEqual(resources.call_count, 2)

    def test_origin_is_ninety_local_calendar_days_before_close(self):
        previous = derive_local_date_origin(date(2024, 6, 7), "America/New_York")
        origin = derive_local_date_origin(date(2024, 6, 8), "America/New_York")
        self.assertEqual(origin.origin_date, date(2024, 3, 10))
        self.assertEqual(
            origin.cutoff_exclusive_utc, datetime(2024, 3, 11, 4, tzinfo=timezone.utc)
        )
        self.assertEqual(
            origin.cutoff_exclusive_utc - previous.cutoff_exclusive_utc,
            timedelta(hours=23),
        )
        self.assertEqual(origin.protocol_id, "us_local_date_90d_v1")

    def test_fall_day_has_a_twenty_five_hour_window(self):
        previous = derive_local_date_origin(date(2025, 1, 31), "America/New_York")
        origin = derive_local_date_origin(date(2025, 2, 1), "America/New_York")
        self.assertEqual(origin.origin_date, date(2024, 11, 3))
        self.assertEqual(
            origin.cutoff_exclusive_utc, datetime(2024, 11, 4, 5, tzinfo=timezone.utc)
        )
        self.assertEqual(
            origin.cutoff_exclusive_utc - previous.cutoff_exclusive_utc,
            timedelta(hours=25),
        )
        self.assertTrue(
            is_visible_at_date_origin(
                datetime(2024, 11, 4, 4, 59, tzinfo=timezone.utc), origin
            )
        )

    def test_leap_day_and_year_boundary_use_calendar_days(self):
        leap = derive_local_date_origin(date(2024, 5, 29), "America/New_York")
        self.assertEqual(leap.origin_date, date(2024, 2, 29))
        year = derive_local_date_origin(date(2024, 2, 1), "America/New_York")
        self.assertEqual(year.origin_date, date(2023, 11, 3))
        self.assertEqual(year.origin_date + timedelta(days=90), date(2024, 2, 1))

    def test_exact_cutoff_is_exclusive_for_timestamped_availability(self):
        origin = derive_local_date_origin(date(2024, 6, 8), "America/New_York")
        self.assertTrue(
            is_visible_at_date_origin(
                datetime(2024, 3, 11, 3, 59, 59, tzinfo=timezone.utc), origin
            )
        )
        self.assertFalse(is_visible_at_date_origin(origin.cutoff_exclusive_utc, origin))
        self.assertFalse(
            is_visible_at_date_origin(
                datetime(2024, 3, 11, 4, 0, 1, tzinfo=timezone.utc), origin
            )
        )

    def test_date_only_availability_keeps_its_original_precision(self):
        origin = derive_local_date_origin(date(2024, 6, 8), "America/New_York")
        source = "America/New_York"
        self.assertTrue(
            is_visible_at_date_origin(
                DateOnlyAvailability(date(2024, 3, 9), source), origin
            )
        )
        self.assertTrue(
            is_visible_at_date_origin(
                DateOnlyAvailability(date(2024, 3, 10), source), origin
            )
        )
        self.assertFalse(
            is_visible_at_date_origin(
                DateOnlyAvailability(date(2024, 3, 11), source), origin
            )
        )

    def test_cross_zone_date_only_availability_uses_source_local_day_end(self):
        origin = derive_local_date_origin(date(2024, 6, 8), "America/New_York")
        same_date = date(2024, 3, 10)
        self.assertTrue(
            is_visible_at_date_origin(
                DateOnlyAvailability(same_date, "America/New_York"), origin
            )
        )
        # The Los Angeles day ends at 07:00 UTC, after New York's 04:00 UTC cutoff.
        self.assertFalse(
            is_visible_at_date_origin(
                DateOnlyAvailability(same_date, "America/Los_Angeles"), origin
            )
        )

    def test_timestamp_comparison_uses_utc_instants_across_fall_fold(self):
        origin = derive_local_date_origin(date(2025, 2, 1), "America/New_York")
        # The two 01:30 local observations are distinct UTC instants.
        first = datetime(2024, 11, 3, 5, 30, tzinfo=timezone.utc)
        second = datetime(2024, 11, 3, 6, 30, tzinfo=timezone.utc)
        self.assertTrue(is_visible_at_date_origin(first, origin))
        self.assertTrue(is_visible_at_date_origin(second, origin))

    def test_unknown_zone_and_invalid_inputs_are_rejected(self):
        for close_date, zone_key in (
            (None, "America/New_York"),
            ("2024-06-08", "America/New_York"),
            (datetime(2024, 6, 8, tzinfo=timezone.utc), "America/New_York"),
            (date(2024, 6, 8), ""),
            (date(2024, 6, 8), "Unknown/Nowhere"),
            (date(2024, 6, 8), "../America/New_York"),
            (date(2024, 6, 8), "America\\New_York"),
            (date(2024, 6, 8), "America/\x00New_York"),
        ):
            with self.subTest(close_date=close_date, zone_key=zone_key):
                with self.assertRaises(ValueError):
                    derive_local_date_origin(close_date, zone_key)

    def test_naive_and_invalid_availability_are_rejected(self):
        origin = derive_local_date_origin(date(2024, 6, 8), "America/New_York")
        for available_at in (
            None,
            "2024-03-10",
            date(2024, 3, 10),
            datetime(2024, 3, 10, 12),
        ):
            with self.subTest(available_at=available_at):
                with self.assertRaises(ValueError):
                    is_visible_at_date_origin(available_at, origin)

    def test_ambiguous_cutoff_midnight_selects_earliest_valid_instant(self):
        # Cuba repeated local midnight when daylight saving ended on 1 Nov 2020.
        origin = derive_local_date_origin(date(2021, 1, 29), "America/Havana")
        self.assertEqual(origin.origin_date, date(2020, 10, 31))
        self.assertEqual(
            origin.cutoff_exclusive_utc, datetime(2020, 11, 1, 4, tzinfo=timezone.utc)
        )

    def test_nonexistent_origin_midnight_fails_closed(self):
        # Cuba skipped local midnight when daylight saving began on 8 Mar 2020.
        with self.assertRaises(ValueError):
            derive_local_date_origin(date(2020, 6, 6), "America/Havana")

    def test_nonexistent_cutoff_midnight_fails_closed(self):
        with self.assertRaises(ValueError):
            derive_local_date_origin(date(2020, 6, 5), "America/Havana")

    def test_skipped_civil_origin_date_fails_closed(self):
        # Samoa skipped 30 Dec 2011 when it changed sides of the date line.
        with self.assertRaises(ValueError):
            derive_local_date_origin(date(2012, 3, 29), "Pacific/Apia")

    def test_policy_hash_is_stable_and_identifies_zone_and_origin(self):
        a = derive_local_date_origin(date(2024, 6, 8), "America/New_York")
        self.assertEqual(
            a.policy_hash,
            derive_local_date_origin(date(2024, 6, 8), "America/New_York").policy_hash,
        )
        self.assertNotEqual(
            a.policy_hash,
            derive_local_date_origin(date(2024, 6, 9), "America/New_York").policy_hash,
        )
        self.assertNotEqual(
            a.policy_hash,
            derive_local_date_origin(date(2024, 6, 8), "America/Chicago").policy_hash,
        )

    def test_forged_later_cutoff_cannot_admit_a_future_timestamp(self):
        origin = derive_local_date_origin(date(2024, 6, 8), "America/New_York")
        future = origin.cutoff_exclusive_utc
        self.assertFalse(is_visible_at_date_origin(future, origin))
        with self.assertRaises(ValueError):
            replace(origin, cutoff_exclusive_utc=future + timedelta(hours=1))

    def test_forged_later_origin_date_cannot_admit_a_future_date(self):
        origin = derive_local_date_origin(date(2024, 6, 8), "America/New_York")
        future = origin.origin_date + timedelta(days=1)
        self.assertFalse(
            is_visible_at_date_origin(
                DateOnlyAvailability(future, "America/New_York"), origin
            )
        )
        with self.assertRaises(ValueError):
            replace(origin, origin_date=future)

    def test_corrupted_protocol_and_hash_are_rejected_before_visibility(self):
        origin = derive_local_date_origin(date(2024, 6, 8), "America/New_York")
        for changes in (
            {"protocol_id": "us_synthetic_rolling_v2"},
            {"policy_hash": "0" * len(origin.policy_hash)},
        ):
            with self.subTest(changes=changes):
                with self.assertRaises(ValueError):
                    replace(origin, **changes)


if __name__ == "__main__":
    unittest.main()
