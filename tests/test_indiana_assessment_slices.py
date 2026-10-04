"""Development-only diagnostics from fixed Indiana prediction rows."""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

from scripts.indiana_assessment_diagnostic import write_prediction_table
from scripts.indiana_assessment_slices import analyze_slices, training_quintile_cuts
from scripts.indiana_historical_benchmark import Sale


def _sale(
    row_id: str,
    year: int,
    price: int,
    *,
    county: str = "49",
    land: int | None = 100,
    improvement: int | None = 200,
) -> Sale:
    return Sale(
        row_id=row_id,
        sale_date=date(year, 1, 1),
        price=Decimal(price),
        county_id=county,
        zipcode="46204",
        acreage=0.2,
        assessed_land=land,
        assessed_improvement=improvement,
    )


class IndianaAssessmentSliceTests(unittest.TestCase):
    def test_train_only_quintiles_and_exhaustive_slice_counts(self) -> None:
        training = tuple(_sale(f"t-{i}", 2024, i * 100) for i in range(1, 6))
        validation = (
            _sale("v-1", 2025, 50, land=0, improvement=0),
            _sale("v-2", 2025, 100),
            _sale("v-3", 2025, 250),
            _sale("v-4", 2025, 400),
            _sale("v-5", 2025, 1000, land=None),
        )
        self.assertEqual(training_quintile_cuts(training), (100, 200, 300, 400))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "predictions.csv"
            write_prediction_table(
                path,
                validation,
                base=(100, 110, 300, 500, 1100),
                assessment=(50, 100, 250, 400, 1000),
                median=(100, 100, 100, 100, 100),
            )
            result = analyze_slices(training, validation, path)
        self.assertEqual(
            result["training_price_quintile_cuts_usd"], [100, 200, 300, 400]
        )
        self.assertEqual(
            [band["count"] for band in result["price_quintiles"]], [2, 0, 1, 1, 1]
        )
        self.assertEqual(
            {
                name: group["count"]
                for name, group in result["assessment_states"].items()
            },
            {"both_positive": 3, "any_zero": 1, "missing": 1},
        )
        self.assertEqual(result["overall"]["count"], 5)
        self.assertEqual(
            result["overall"]["scorecards"]["assessment_xgboost"]["mdape"], 0
        )
        self.assertEqual(result["overall"]["paired_assessment_better_count"], 5)
        self.assertTrue(
            all(band["scorecards"] is None for band in result["price_quintiles"])
        )
        self.assertTrue(
            all(
                group["paired_assessment_better_count"] is None
                for group in result["assessment_states"].values()
            )
        )
        self.assertNotIn("v-1", json.dumps(result))
        self.assertNotIn("row_id", json.dumps(result))

    def test_county_floor_uses_full_eligible_rows(self) -> None:
        training = tuple(_sale(f"t-{i}", 2024, 100 + i) for i in range(10))
        validation = tuple(
            _sale(f"a-{i}", 2025, 100 + i, county="49") for i in range(199)
        ) + tuple(_sale(f"b-{i}", 2025, 100 + i, county="50") for i in range(200))
        prices = tuple(float(sale.price) for sale in validation)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "predictions.csv"
            write_prediction_table(
                path, validation, base=prices, assessment=prices, median=prices
            )
            result = analyze_slices(training, validation, path)
        self.assertEqual(set(result["counties"]), {"50"})
        self.assertEqual(result["counties_below_floor"], {"count": 1, "sales": 199})
        self.assertEqual(result["overall"]["count"], 399)

    def test_mismatched_saved_rows_and_wrong_year_fail(self) -> None:
        training = (_sale("t-1", 2024, 100),)
        validation = (_sale("v-1", 2025, 100),)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "predictions.csv"
            write_prediction_table(
                path,
                validation,
                base=(100,),
                assessment=(100,),
                median=(100,),
            )
            with self.assertRaisesRegex(ValueError, "membership"):
                analyze_slices(training, (_sale("other", 2025, 100),), path)
            with self.assertRaisesRegex(ValueError, "actual"):
                analyze_slices(training, (_sale("v-1", 2025, 101),), path)
            with self.assertRaisesRegex(ValueError, "2024"):
                training_quintile_cuts((_sale("bad", 2025, 100),))
            with self.assertRaisesRegex(ValueError, "at least 200"):
                analyze_slices(training, validation, path, min_county=1)


if __name__ == "__main__":
    unittest.main()
