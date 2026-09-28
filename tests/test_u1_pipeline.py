"""Small synthetic U1 integration path; no empirical accuracy claim."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
import sys
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tabpfn4realestate.data.schema import Property, SourceSnapshot, Transaction  # noqa: E402
from tabpfn4realestate.evaluation.metrics import PredictionRow, score_predictions  # noqa: E402
from tabpfn4realestate.models.guards import TrainingPartition  # noqa: E402
from tabpfn4realestate.models.off_baseline import (  # noqa: E402
    GuardedOffMedian,
    TrainingExample,
    label_row_id,
)


START = datetime(2024, 1, 1, 12, tzinfo=timezone.utc)
RESERVED_ORIGIN_SHIFT_DAYS = 120


def synthetic_row(index: int) -> TrainingExample:
    origin = START + timedelta(
        days=index + (RESERVED_ORIGIN_SHIFT_DAYS if index >= 160 else 0)
    )
    property_id = f"synthetic-home-{index:03d}"
    property = Property(
        property_id=property_id,
        country="US",
        property_type="single_family",
        source_id="assessor",
        observed_at=origin - timedelta(days=365),
        available_at=origin - timedelta(days=364),
        living_area=Decimal(1000 + index),
        living_area_unit="sqft",
    )
    label = Transaction(
        transaction_id=f"synthetic-sale-{index:03d}",
        economic_transfer_id=f"synthetic-transfer-{index:03d}",
        property_id=property_id,
        close_at=origin + timedelta(days=90),
        available_at=origin + timedelta(days=97),
        price=Decimal(100000 + 1000 * index),
        currency="USD",
        source_id="sales",
        scope="single_property",
        consideration_type="gross_recorded_sale",
        arm_length_status="confirmed",
        adjustment_flags=(),
    )
    return TrainingExample(
        row_id=label_row_id(label),
        property=property,
        origin=origin,
        source_snapshot=SourceSnapshot(
            snapshot_id=f"synthetic-asof-{index:03d}",
            source_ids=("assessor", "sales"),
            as_of=origin,
        ),
        label=label,
    )


def fixture():
    rows = tuple(synthetic_row(index) for index in range(200))
    train, reserved = rows[:160], rows[160:]
    partition = TrainingPartition(
        train_row_ids=frozenset(row.row_id for row in train),
        reserved_row_ids=frozenset(row.row_id for row in reserved),
    )
    training_cutoff = train[-1].label.available_at
    return rows, train, reserved, partition, training_cutoff


class SyntheticPipelineTests(unittest.TestCase):
    def test_200_row_off_pipeline_keeps_reserved_cohort_and_lineage(self):
        rows, train, reserved, partition, cutoff = fixture()
        self.assertEqual(len({row.label.economic_transfer_id for row in rows}), 200)
        self.assertEqual((len(train), len(reserved)), (160, 40))
        self.assertTrue(all(row.label.available_at <= cutoff for row in train))
        self.assertTrue(all(row.label.available_at > cutoff for row in reserved))
        self.assertLessEqual(cutoff, min(row.origin for row in reserved))
        self.assertLess(cutoff, reserved[0].label.available_at)

        model = GuardedOffMedian.fit(train, partition, training_cutoff=cutoff)
        predictions = tuple(
            model.predict(
                row.property,
                row.origin,
                row.source_snapshot,
            )
            for row in reserved
        )
        self.assertEqual(len(predictions), 40)
        self.assertEqual(
            {prediction.amount for prediction in predictions}, {Decimal("179500")}
        )
        for row, prediction in zip(reserved, predictions, strict=True):
            self.assertEqual(prediction.snapshot.property_id, row.property.property_id)
            self.assertNotIn("prior_sale_price", prediction.snapshot.values)
            self.assertTrue(
                all(
                    entry.observed_at <= row.origin and entry.available_at <= row.origin
                    for entry in prediction.snapshot.lineage.values()
                )
            )

        score = score_predictions(
            tuple(
                PredictionRow(
                    row_id=row.row_id,
                    actual=row.label.price,
                    predicted=prediction.amount,
                    actual_currency="USD",
                    predicted_currency="USD",
                    status="estimated",
                )
                for row, prediction in zip(reserved, predictions, strict=True)
            )
        )
        self.assertEqual(score.eligible_count, 40)
        self.assertEqual(score.success_count, 40)
        self.assertEqual(score.failed_count, 0)
        self.assertEqual(score.abstained_count, 0)
        self.assertEqual(score.success_coverage, Decimal("1"))

    def test_reserved_synthetic_row_cannot_enter_fit(self):
        _, train, reserved, partition, cutoff = fixture()
        matured_cutoff = reserved[0].label.available_at
        self.assertGreater(matured_cutoff, cutoff)
        with self.assertRaises(ValueError):
            GuardedOffMedian.fit(
                (*train, reserved[0]), partition, training_cutoff=matured_cutoff
            )


if __name__ == "__main__":
    unittest.main()
