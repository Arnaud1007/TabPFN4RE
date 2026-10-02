"""Label-free calendar schedule for synthetic US11 engineering checks."""

from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
import sys
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tabpfn4realestate.evaluation.calendar_schedule import (  # noqa: E402
    CalendarOriginRef,
    build_calendar_schedule,
)
from tabpfn4realestate.evaluation.splits import (  # noqa: E402
    LabelMaturity,
    OriginRef,
    build_temporal_fold,
)


SOURCE_HASH = "a" * 64
POLICY_HASH = "b" * 64
HISTORY_START = date(2021, 1, 1)
CALIBRATION_START = date(2024, 1, 1)
TEST_START = date(2024, 4, 1)


def row(name: str, day: date, *, property_id: str | None = None) -> CalendarOriginRef:
    return CalendarOriginRef(name, property_id or f"property-{name}", day)


def example_rows() -> tuple[CalendarOriginRef, ...]:
    return (
        row("history", HISTORY_START),
        row("q1", date(2023, 1, 1)),
        row("q2", date(2023, 4, 1)),
        row("q3", date(2023, 7, 1)),
        row("q4", date(2023, 10, 1)),
        row("calibration", CALIBRATION_START),
        row("test-start", TEST_START),
        row("test-last", date(2025, 3, 31)),
    )


def schedule(rows=None, **changes):
    fields = {
        "history_start": HISTORY_START,
        "calibration_start": CALIBRATION_START,
        "test_start": TEST_START,
        "source_snapshot_sha256": SOURCE_HASH,
        "origin_policy_sha256": POLICY_HASH,
    }
    return build_calendar_schedule(
        example_rows() if rows is None else rows,
        **(fields | changes),
    )


class CalendarScheduleTests(unittest.TestCase):
    def test_four_calendar_quarters_and_disjoint_reserved_windows(self):
        result = schedule()
        self.assertEqual(result.protocol_id, "us_synthetic_calendar_schedule_v1")
        self.assertEqual(
            [(part.start, part.end) for part in result.development],
            [
                (date(2023, 1, 1), date(2023, 4, 1)),
                (date(2023, 4, 1), date(2023, 7, 1)),
                (date(2023, 7, 1), date(2023, 10, 1)),
                (date(2023, 10, 1), date(2024, 1, 1)),
            ],
        )
        self.assertEqual(result.calibration.start, CALIBRATION_START)
        self.assertEqual(result.calibration.end, TEST_START)
        self.assertEqual(result.final_test.start, TEST_START)
        self.assertEqual(result.final_test.end, date(2025, 4, 1))
        self.assertEqual(result.pre_development_row_ids, ("history",))
        self.assertEqual(result.calibration.row_ids, ("calibration",))
        self.assertEqual(result.final_test.row_ids, ("test-start", "test-last"))
        self.assertEqual(len(result.schedule_hash), 64)

    def test_training_candidates_are_not_claimed_as_matured_labels(self):
        result = schedule()
        self.assertEqual(result.development[0].training_candidate_ids, ("history",))
        self.assertEqual(
            result.development[1].training_candidate_ids,
            ("history", "q1"),
        )
        self.assertEqual(
            result.development[3].training_candidate_ids,
            ("history", "q1", "q2", "q3"),
        )
        self.assertEqual(result.development[3].row_ids, ("q4",))
        self.assertFalse(hasattr(result.development[3], "train_row_ids"))

    def test_quarters_and_test_use_calendar_months_not_ninety_days(self):
        rows = (
            row("history", date(2021, 4, 1)),
            row("q1", date(2023, 4, 1)),
            row("q2", date(2023, 7, 1)),
            row("q3", date(2023, 10, 1)),
            row("q4", date(2024, 1, 1)),
            row("calibration", date(2024, 4, 1)),
            row("test", date(2024, 7, 1)),
        )
        result = schedule(
            rows,
            history_start=date(2021, 4, 1),
            calibration_start=date(2024, 4, 1),
            test_start=date(2024, 7, 1),
        )
        self.assertEqual(result.development[3].start, date(2024, 1, 1))
        self.assertEqual(result.development[3].end, date(2024, 4, 1))
        self.assertEqual(
            (result.development[3].end - result.development[3].start).days,
            91,
        )
        self.assertEqual(result.final_test.end, date(2025, 7, 1))

    def test_boundary_membership_and_input_order_do_not_change_hash(self):
        rows = example_rows()
        first = schedule(rows)
        reversed_rows = schedule(tuple(reversed(rows)))
        self.assertEqual(first.schedule_hash, reversed_rows.schedule_hash)
        self.assertEqual(first.development[0].row_ids, ("q1",))
        self.assertEqual(first.development[1].row_ids, ("q2",))
        self.assertEqual(first.final_test.row_ids, ("test-start", "test-last"))
        self.assertNotEqual(
            first.schedule_hash,
            schedule(
                tuple(
                    row(r.row_id, r.origin_date, property_id="changed")
                    if r.row_id == "q1"
                    else r
                    for r in rows
                )
            ).schedule_hash,
        )

    def test_source_and_policy_fingerprints_change_hash(self):
        baseline = schedule()
        self.assertNotEqual(
            baseline.schedule_hash,
            schedule(source_snapshot_sha256="c" * 64).schedule_hash,
        )
        self.assertNotEqual(
            baseline.schedule_hash,
            schedule(origin_policy_sha256="d" * 64).schedule_hash,
        )

    def test_short_declared_history_and_missing_window_fail(self):
        with self.assertRaisesRegex(ValueError, "24 calendar months"):
            schedule(history_start=date(2021, 2, 1))
        rows = tuple(item for item in example_rows() if item.row_id != "q3")
        with self.assertRaisesRegex(ValueError, "empty"):
            schedule(rows)

    def test_invalid_dates_boundaries_and_protocol_fail(self):
        with self.assertRaises(ValueError):
            row("bad", datetime(2023, 1, 1, tzinfo=timezone.utc))
        with self.assertRaisesRegex(ValueError, "quarter"):
            schedule(calibration_start=date(2024, 2, 1))
        with self.assertRaises(ValueError):
            schedule(test_start=date(2024, 1, 15))
        with self.assertRaises(ValueError):
            schedule(test_start=CALIBRATION_START)
        with self.assertRaises(ValueError):
            schedule(protocol_id="us_real_v1")

    def test_duplicate_ids_out_of_range_and_bad_hash_fail(self):
        with self.assertRaisesRegex(ValueError, "duplicate"):
            schedule((*example_rows(), example_rows()[1]))
        with self.assertRaisesRegex(ValueError, "outside"):
            schedule((*example_rows(), row("too-late", date(2025, 4, 1))))
        with self.assertRaises(ValueError):
            schedule(source_snapshot_sha256="not-a-hash")

    def test_earlier_validation_label_needs_actual_maturity_in_later_fold(self):
        planned = schedule()
        refs = {
            item.row_id: OriginRef(
                item.row_id,
                item.property_id,
                datetime.combine(item.origin_date, time(12), timezone.utc),
            )
            for item in example_rows()
        }
        labels = {
            name: LabelMaturity(
                name,
                refs[name].origin + timedelta(days=90),
                refs[name].origin + timedelta(days=97),
            )
            for name in ("history", "q1", "q2")
        }
        second = planned.development[1]
        second_cutoff = datetime.combine(second.start, time(), timezone.utc)
        second_fold = build_temporal_fold(
            tuple(
                refs[name] for name in (*second.training_candidate_ids, *second.row_ids)
            ),
            tuple(labels[name] for name in second.training_candidate_ids),
            training_cutoff=second_cutoff,
            validation_start=second_cutoff,
            validation_end=datetime.combine(second.end, time(), timezone.utc),
        )
        self.assertEqual(second_fold.train_row_ids, ("history",))
        self.assertEqual(second_fold.immature_row_ids, ("q1",))

        third = planned.development[2]
        third_cutoff = datetime.combine(third.start, time(), timezone.utc)
        third_fold = build_temporal_fold(
            tuple(
                refs[name] for name in (*third.training_candidate_ids, *third.row_ids)
            ),
            tuple(labels[name] for name in third.training_candidate_ids),
            training_cutoff=third_cutoff,
            validation_start=third_cutoff,
            validation_end=datetime.combine(third.end, time(), timezone.utc),
        )
        self.assertEqual(third_fold.train_row_ids, ("history", "q1"))
        self.assertEqual(third_fold.immature_row_ids, ("q2",))


if __name__ == "__main__":
    unittest.main()
