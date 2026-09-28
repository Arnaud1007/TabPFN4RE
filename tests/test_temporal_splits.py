"""Synthetic US11 rolling-origin split and label-maturity contract."""

from datetime import datetime, timedelta, timezone, tzinfo
from pathlib import Path
import sys
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tabpfn4realestate.evaluation.splits import (  # noqa: E402
    LabelMaturity,
    OriginRef,
    build_temporal_fold,
)
from tabpfn4realestate.models.guards import TrainingPartition  # noqa: E402
from tabpfn4realestate.models.off_baseline import GuardedOffMedian  # noqa: E402
from tests.test_u1_pipeline import synthetic_row  # noqa: E402


BASE = datetime(2024, 1, 1, 12, tzinfo=timezone.utc)


class FallBackTimezone(tzinfo):
    """Synthetic DST fallback without a system timezone database dependency."""

    def utcoffset(self, value):
        return timedelta(hours=-5 if value is not None and value.fold else -4)

    def dst(self, value):
        return timedelta(0)

    def tzname(self, value):
        return "synthetic-fallback"


def origin_ref(row_id: str, day: int) -> OriginRef:
    return OriginRef(
        row_id=row_id,
        property_id=f"home-{row_id}",
        origin=BASE + timedelta(days=day),
    )


def maturity(row: OriginRef, *, available_at=None, close_at=None) -> LabelMaturity:
    close = row.origin + timedelta(days=90) if close_at is None else close_at
    return LabelMaturity(
        row_id=row.row_id,
        close_at=close,
        available_at=close + timedelta(days=7)
        if available_at is None
        else available_at,
    )


def fold(origins, maturities, *, cutoff_day=120, start_day=130, end_day=160, **changes):
    fields = {
        "training_cutoff": BASE + timedelta(days=cutoff_day),
        "validation_start": BASE + timedelta(days=start_day),
        "validation_end": BASE + timedelta(days=end_day),
        "horizon_days": 90,
        "protocol_id": "us_synthetic_rolling_v2",
    }
    return build_temporal_fold(origins, maturities, **(fields | changes))


class TemporalFoldTests(unittest.TestCase):
    def test_real_protocol_id_cannot_use_synthetic_builder(self):
        train = origin_ref("transfer-train", 0)
        validation = origin_ref("transfer-validation", 130)
        with self.assertRaisesRegex(ValueError, "synthetic protocol"):
            fold(
                (train, validation),
                (maturity(train),),
                protocol_id="us_real_v1",
            )

    def test_fallback_fold_does_not_mature_a_future_label(self):
        zone = FallBackTimezone()
        close = datetime(2024, 11, 3, 1, 15, tzinfo=zone, fold=0)
        availability = datetime(2024, 11, 3, 1, 30, tzinfo=zone, fold=1)
        cutoff = datetime(2024, 11, 3, 1, 45, tzinfo=zone, fold=0)
        ready = OriginRef(
            "transfer-ready", "home-ready", datetime(2024, 7, 1, tzinfo=zone)
        )
        train = OriginRef("transfer-train", "home-train", close - timedelta(days=90))
        validation = OriginRef(
            "transfer-validation", "home-validation", datetime(2024, 11, 4, tzinfo=zone)
        )
        result = build_temporal_fold(
            (ready, train, validation),
            (maturity(ready), LabelMaturity(train.row_id, close, availability)),
            training_cutoff=cutoff,
            validation_start=datetime(2024, 11, 4, tzinfo=zone),
            validation_end=datetime(2024, 11, 5, tzinfo=zone),
        )
        self.assertEqual(result.train_row_ids, (ready.row_id,))
        self.assertEqual(result.immature_row_ids, (train.row_id,))

    def test_fold_rejects_no_matured_training_labels(self):
        immature = origin_ref("transfer-immature", 50)
        validation = origin_ref("transfer-validation", 130)
        with self.assertRaisesRegex(ValueError, "matured training"):
            fold((immature, validation), (maturity(immature),))

    def test_membership_and_hash_ignore_input_order(self):
        train = origin_ref("transfer-a", 0)
        immature = origin_ref("transfer-b", 50)
        validation = origin_ref("transfer-c", 130)
        origins = (train, immature, validation)
        labels = (maturity(train), maturity(immature))
        first = fold(origins, labels)
        shuffled = fold(tuple(reversed(origins)), tuple(reversed(labels)))
        self.assertEqual(first.train_row_ids, ("transfer-a",))
        self.assertEqual(first.immature_row_ids, ("transfer-b",))
        self.assertEqual(first.validation_row_ids, ("transfer-c",))
        self.assertEqual(first.train_row_ids, shuffled.train_row_ids)
        self.assertEqual(first.validation_row_ids, shuffled.validation_row_ids)
        self.assertEqual(first.immature_row_ids, shuffled.immature_row_ids)
        self.assertEqual(first.split_hash, shuffled.split_hash)
        self.assertEqual(len(first.split_hash), 64)

    def test_equivalent_timezone_offsets_have_the_same_split_hash(self):
        train = origin_ref("transfer-train", 0)
        validation = origin_ref("transfer-validation", 130)
        baseline = fold((train, validation), (maturity(train),))
        offset = timezone(timedelta(hours=1))
        shifted_train = OriginRef(
            train.row_id, train.property_id, train.origin.astimezone(offset)
        )
        shifted_validation = OriginRef(
            validation.row_id,
            validation.property_id,
            validation.origin.astimezone(offset),
        )
        shifted_label = maturity(train)
        shifted = build_temporal_fold(
            (shifted_train, shifted_validation),
            (
                LabelMaturity(
                    shifted_label.row_id,
                    shifted_label.close_at.astimezone(offset),
                    shifted_label.available_at.astimezone(offset),
                ),
            ),
            training_cutoff=(BASE + timedelta(days=120)).astimezone(offset),
            validation_start=(BASE + timedelta(days=130)).astimezone(offset),
            validation_end=(BASE + timedelta(days=160)).astimezone(offset),
        )
        self.assertEqual(baseline.train_row_ids, shifted.train_row_ids)
        self.assertEqual(baseline.validation_row_ids, shifted.validation_row_ids)
        self.assertEqual(baseline.split_hash, shifted.split_hash)

    def test_validation_window_is_half_open(self):
        ready = origin_ref("transfer-ready", 0)
        at_start = origin_ref("transfer-start", 130)
        just_before_end = OriginRef(
            row_id="transfer-before-end",
            property_id="home-before-end",
            origin=BASE + timedelta(days=160) - timedelta(microseconds=1),
        )
        at_end = origin_ref("transfer-end", 160)
        result = fold((ready, at_start, just_before_end, at_end), (maturity(ready),))
        self.assertEqual(
            result.validation_row_ids,
            ("transfer-start", "transfer-before-end"),
        )
        self.assertNotIn("transfer-end", result.validation_row_ids)

    def test_label_at_cutoff_matures_but_microsecond_later_does_not(self):
        ready = origin_ref("transfer-ready", 0)
        later = origin_ref("transfer-later", 1)
        validation = origin_ref("transfer-validation", 130)
        cutoff = BASE + timedelta(days=120)
        result = fold(
            (ready, later, validation),
            (
                maturity(ready, available_at=cutoff),
                maturity(later, available_at=cutoff + timedelta(microseconds=1)),
            ),
        )
        self.assertEqual(result.train_row_ids, ("transfer-ready",))
        self.assertEqual(result.immature_row_ids, ("transfer-later",))

    def test_duplicate_economic_transfer_ids_are_rejected(self):
        first = origin_ref("same-transfer", 0)
        duplicate = origin_ref("same-transfer", 1)
        with self.assertRaises(ValueError):
            fold((first, duplicate), (maturity(first),))
        with self.assertRaises(ValueError):
            fold((first,), (maturity(first), maturity(first)))

    def test_invalid_datetime_and_fold_order_are_rejected(self):
        valid = origin_ref("transfer-a", 0)
        naive = BASE.replace(tzinfo=None)
        with self.assertRaises(ValueError):
            OriginRef(row_id="naive", property_id="home-naive", origin=naive)
        with self.assertRaises(ValueError):
            LabelMaturity(row_id=valid.row_id, close_at=naive, available_at=BASE)
        with self.assertRaises(ValueError):
            fold((valid,), (maturity(valid),), start_day=160, end_day=160)
        with self.assertRaises(ValueError):
            fold((valid,), (maturity(valid),), cutoff_day=140, start_day=130)

    def test_inconsistent_label_dates_and_horizon_are_rejected(self):
        row = origin_ref("transfer-a", 0)
        close = row.origin + timedelta(days=90)
        with self.assertRaises(ValueError):
            fold((row,), (maturity(row, available_at=close - timedelta(seconds=1)),))
        with self.assertRaises(ValueError):
            fold((row,), (maturity(row, close_at=close + timedelta(days=1)),))

    def test_validation_label_cannot_be_injected_into_training_maturity(self):
        train = origin_ref("transfer-train", 0)
        reserved = origin_ref("transfer-validation", 130)
        with self.assertRaises(ValueError):
            fold(
                (train, reserved),
                (maturity(train), maturity(reserved)),
            )

    def test_later_fold_uses_once_immature_label_only_after_availability(self):
        early = origin_ref("transfer-early", 0)
        delayed = origin_ref("transfer-delayed", 50)
        first_validation = origin_ref("transfer-first-validation", 130)
        first = fold(
            (early, delayed, first_validation),
            (maturity(early), maturity(delayed)),
        )
        self.assertIn(delayed.row_id, first.immature_row_ids)
        self.assertNotIn(delayed.row_id, first.train_row_ids)

        second_validation = origin_ref("transfer-second-validation", 300)
        second = fold(
            (early, delayed, second_validation),
            (maturity(early), maturity(delayed)),
            cutoff_day=250,
            start_day=300,
            end_day=330,
        )
        self.assertIn(delayed.row_id, second.train_row_ids)
        self.assertIn(second_validation.row_id, second.validation_row_ids)
        self.assertNotEqual(first.split_hash, second.split_hash)

    def test_fold_membership_drives_the_guarded_off_baseline(self):
        rows = tuple(synthetic_row(index) for index in range(200))
        cutoff = rows[159].label.available_at
        result = build_temporal_fold(
            tuple(
                OriginRef(row.row_id, row.property.property_id, row.origin)
                for row in rows
            ),
            tuple(
                LabelMaturity(row.row_id, row.label.close_at, row.label.available_at)
                for row in rows[:160]
            ),
            training_cutoff=cutoff,
            validation_start=rows[160].origin,
            validation_end=rows[-1].origin + timedelta(seconds=1),
        )
        self.assertEqual(len(result.train_row_ids), 160)
        self.assertEqual(len(result.validation_row_ids), 40)
        partition = TrainingPartition(
            frozenset(result.train_row_ids), frozenset(result.validation_row_ids)
        )
        fitted = GuardedOffMedian.fit(rows[:160], partition, training_cutoff=cutoff)
        self.assertEqual(len(fitted.train_row_ids), 160)


if __name__ == "__main__":
    unittest.main()
