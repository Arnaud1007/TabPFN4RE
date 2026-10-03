"""Synthetic checks for binding calendar windows to label maturity."""

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import sys
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


from tabpfn4realestate.evaluation.calendar_schedule import (  # noqa: E402
    CalendarOriginRef,
    build_calendar_schedule,
)
from tabpfn4realestate.evaluation.chronological_plan import (  # noqa: E402
    ChronologicalMaturityRef,
    build_chronological_plan,
    origin_policy_hash,
)
from tabpfn4realestate.evaluation.local_dates import DateOnlyAvailability  # noqa: E402


UTC = timezone.utc
ORIGINS = (
    CalendarOriginRef("history", "p-history", date(2021, 1, 1)),
    CalendarOriginRef("q1", "p-q1", date(2023, 1, 1)),
    CalendarOriginRef("q2", "p-q2", date(2023, 4, 1)),
    CalendarOriginRef("q3", "p-q3", date(2023, 7, 1)),
    CalendarOriginRef("q4", "p-q4", date(2023, 10, 1)),
    CalendarOriginRef("calibration", "p-cal", date(2024, 1, 1)),
    CalendarOriginRef("test", "p-test", date(2024, 4, 1)),
)
ZONES = {row.row_id: "America/New_York" for row in ORIGINS}
CUTOFFS = tuple(
    datetime(year, month, 1, tzinfo=UTC)
    for year, month in ((2023, 1), (2023, 4), (2023, 7), (2023, 10), (2024, 1))
)


def fixture_maturity():
    result = []
    for row in ORIGINS[:5]:
        close_date = row.origin_date + timedelta(days=90)
        available = DateOnlyAvailability(close_date, "America/New_York")
        if row.row_id == "q1":
            available = DateOnlyAvailability(date(2023, 4, 5), "America/New_York")
        result.append(ChronologicalMaturityRef(row.row_id, close_date, available))
    return tuple(result)


def fixture_schedule(origins=ORIGINS, zones=ZONES):
    return build_calendar_schedule(
        origins,
        history_start=date(2021, 1, 1),
        calibration_start=date(2024, 1, 1),
        test_start=date(2024, 4, 1),
        source_snapshot_sha256="a" * 64,
        origin_policy_sha256=origin_policy_hash(origins, zones),
    )


def plan(*, schedule=None, origins=ORIGINS, zones=ZONES, maturity=None, cutoffs=CUTOFFS):
    return build_chronological_plan(
        fixture_schedule(origins, zones) if schedule is None else schedule,
        origins,
        zones,
        fixture_maturity() if maturity is None else maturity,
        fit_cutoffs_utc=cutoffs,
    )


class ChronologicalPlanTests(unittest.TestCase):
    def test_four_folds_and_final_fit_exclude_reserved_rows(self):
        result = plan()
        self.assertEqual(len(result.development), 4)
        self.assertEqual(result.development[0].train_row_ids, ("history",))
        self.assertEqual(result.development[1].train_row_ids, ("history",))
        self.assertEqual(result.development[1].immature_row_ids, ("q1",))
        self.assertEqual(result.development[2].train_row_ids, ("history", "q1"))
        self.assertEqual(result.development[2].immature_row_ids, ("q2",))
        self.assertEqual(result.development[3].validation_row_ids, ("q4",))
        self.assertNotIn("q4", result.development[3].train_row_ids)
        self.assertEqual(result.final_fit.train_row_ids, ("history", "q1", "q2", "q3", "q4"))
        self.assertFalse({"calibration", "test"} & set(result.final_fit.train_row_ids))
        self.assertEqual(len(result.plan_hash), 64)

    def test_exact_utc_cutoff_is_mature_but_new_york_prior_date_is_not(self):
        refs = list(fixture_maturity())
        refs[4] = ChronologicalMaturityRef("q4", date(2023, 12, 30), CUTOFFS[4])
        self.assertIn("q4", plan(maturity=tuple(refs)).final_fit.train_row_ids)
        refs[4] = ChronologicalMaturityRef(
            "q4", date(2023, 12, 30), DateOnlyAvailability(date(2023, 12, 31), "America/New_York")
        )
        self.assertIn("q4", plan(maturity=tuple(refs)).final_fit.immature_row_ids)

    def test_cross_zone_date_only_publication_uses_instant(self):
        refs = list(fixture_maturity())
        refs[4] = ChronologicalMaturityRef(
            "q4", date(2023, 12, 30), DateOnlyAvailability(date(2023, 12, 31), "UTC")
        )
        self.assertIn("q4", plan(maturity=tuple(refs)).final_fit.train_row_ids)

    def test_dst_and_leap_origin_are_calendar_dates(self):
        origins = (*ORIGINS, CalendarOriginRef("dst", "p-dst", date(2024, 3, 10)))
        zones = ZONES | {"dst": "America/New_York"}
        close = date(2024, 6, 8)
        self.assertEqual((close - date(2024, 3, 10)).days, 90)
        schedule = fixture_schedule(origins, zones)
        self.assertIn("dst", schedule.calibration.row_ids)
        self.assertEqual(plan(schedule=schedule, origins=origins, zones=zones).schedule.schedule_hash, schedule.schedule_hash)

    def test_reserved_unknown_duplicate_and_missing_maturity_fail(self):
        refs = fixture_maturity()
        for bad in (
            (*refs, ChronologicalMaturityRef("calibration", date(2024, 3, 31), CUTOFFS[4])),
            (*refs, ChronologicalMaturityRef("unknown", date(2024, 3, 31), CUTOFFS[4])),
            (*refs, refs[0]),
            refs[:-1],
        ):
            with self.subTest(bad=bad[-1].row_id), self.assertRaises(ValueError):
                plan(maturity=bad)

    def test_wrong_close_origin_and_early_publication_fail(self):
        refs = list(fixture_maturity())
        refs[0] = replace(refs[0], close_date=date(2021, 4, 2))
        with self.assertRaises(ValueError):
            plan(maturity=tuple(refs))
        refs[0] = replace(fixture_maturity()[0], available_at=datetime(2020, 12, 31, tzinfo=UTC))
        with self.assertRaises(ValueError):
            plan(maturity=tuple(refs))

    def test_schedule_policy_and_membership_tamper_fail(self):
        valid = fixture_schedule()
        for bad in (
            replace(valid, schedule_hash="0" * 64),
            replace(valid, origin_policy_sha256="b" * 64),
            replace(valid, pre_development_row_ids=("q1",)),
        ):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                plan(schedule=bad)

    def test_cutoffs_are_single_utc_freezes_before_validation(self):
        with self.assertRaises(ValueError):
            plan(cutoffs=CUTOFFS[:4])
        late = (*CUTOFFS[:1], datetime(2023, 4, 1, 5, 0, tzinfo=UTC), *CUTOFFS[2:])
        with self.assertRaises(ValueError):
            plan(cutoffs=late)
        naive = (datetime(2023, 1, 1), *CUTOFFS[1:])
        with self.assertRaises(ValueError):
            plan(cutoffs=naive)

    def test_hash_is_order_independent_and_changes_with_evidence(self):
        original = plan()
        self.assertEqual(
            original.plan_hash,
            plan(origins=tuple(reversed(ORIGINS)), maturity=tuple(reversed(fixture_maturity()))).plan_hash,
        )
        refs = list(fixture_maturity())
        refs[1] = replace(refs[1], available_at=DateOnlyAvailability(date(2023, 4, 6), "America/New_York"))
        self.assertNotEqual(original.plan_hash, plan(maturity=tuple(refs)).plan_hash)
        shifted = (CUTOFFS[0] - timedelta(hours=1), *CUTOFFS[1:])
        self.assertNotEqual(original.plan_hash, plan(cutoffs=shifted).plan_hash)


if __name__ == "__main__":
    unittest.main()
