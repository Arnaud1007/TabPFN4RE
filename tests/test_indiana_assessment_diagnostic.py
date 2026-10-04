"""Paired saved-prediction checks for the assessment snapshot diagnostic."""

from __future__ import annotations

import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

from scripts.indiana_assessment_diagnostic import (
    PRIVATE_ROOT,
    PROTOCOL,
    _validated_output_path,
    replay_prediction_table,
    write_prediction_table,
)
from scripts.indiana_historical_benchmark import Sale


class IndianaAssessmentDiagnosticTests(unittest.TestCase):
    def test_private_output_rejects_parent_traversal(self) -> None:
        with self.assertRaisesRegex(ValueError, "private"):
            _validated_output_path(PRIVATE_ROOT / "junction" / ".." / "escape")
        self.assertEqual(
            _validated_output_path(PRIVATE_ROOT / "new-run"),
            PRIVATE_ROOT / "new-run",
        )

    def test_paired_scores_replay_from_one_saved_cohort(self) -> None:
        sales = (
            Sale("sale-a", date(2025, 1, 1), Decimal("100"), "49", "46204", 0.2),
            Sale("sale-b", date(2025, 1, 2), Decimal("200"), "49", "46204", 0.3),
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "predictions.csv"
            write_prediction_table(
                path,
                sales,
                base=(110.0, 180.0),
                assessment=(100.0, 200.0),
                median=(90.0, 220.0),
            )
            scores = replay_prediction_table(path)
            self.assertEqual(
                PROTOCOL, "indiana_sdf_snapshot_assessment_retrospective_diagnostic_v1"
            )
            self.assertEqual(
                {score["eligible_count"] for score in scores.values()}, {2}
            )
            self.assertEqual(scores["assessment_xgboost"]["mdape"], 0.0)
            self.assertAlmostEqual(scores["base_xgboost"]["mdape"], 0.1)
            self.assertAlmostEqual(scores["zip_county_median"]["mdape"], 0.1)

    def test_bad_predictions_and_duplicate_economic_ids_fail_closed(self) -> None:
        sale = Sale("sale-a", date(2025, 1, 1), Decimal("100"), "49", "46204", 0.2)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "predictions.csv"
            with self.assertRaisesRegex(ValueError, "count"):
                write_prediction_table(
                    path, (sale,), base=(), assessment=(100.0,), median=(100.0,)
                )
            with self.assertRaisesRegex(ValueError, "duplicate"):
                write_prediction_table(
                    path,
                    (sale, sale),
                    base=(100.0, 100.0),
                    assessment=(100.0, 100.0),
                    median=(100.0, 100.0),
                )
            with self.assertRaisesRegex(ValueError, "positive"):
                write_prediction_table(
                    path,
                    (sale,),
                    base=(100.0,),
                    assessment=(0.0,),
                    median=(100.0,),
                )
            self.assertFalse(path.exists())

    def test_replay_rejects_extra_fields_and_invalid_dates(self) -> None:
        sale = Sale("sale-a", date(2025, 1, 1), Decimal("100"), "49", "46204", 0.2)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "predictions.csv"
            write_prediction_table(
                path,
                (sale,),
                base=(100.0,),
                assessment=(100.0,),
                median=(100.0,),
            )
            valid = path.read_text(encoding="utf-8")
            path.write_text(valid.replace("2025-01-01", "not-a-date"), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "date"):
                replay_prediction_table(path)
            path.write_text(valid.rstrip() + ",extra\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "row"):
                replay_prediction_table(path)


if __name__ == "__main__":
    unittest.main()
