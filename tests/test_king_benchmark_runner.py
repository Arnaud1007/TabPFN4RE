"""Synthetic tests for the frozen, research-only King benchmark runner."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
import hashlib
import unittest

from scripts.king_historical_benchmark import Sale, split_sales
from scripts.run_king_historical_benchmark import (
    baseline_predictions,
    choose_champion,
    verify_split_manifest,
)


def sale(row_id: str, when: date, price: int, zipcode: str) -> Sale:
    return Sale(row_id, row_id, when, Decimal(price), {"zipcode": zipcode})


class KingBenchmarkRunnerTests(unittest.TestCase):
    def test_zipcode_baseline_uses_only_past_training_prices(self) -> None:
        training = (
            sale("a", date(2014, 5, 1), 100, "98001"),
            sale("b", date(2014, 6, 1), 300, "98001"),
            sale("c", date(2014, 7, 1), 900, "98002"),
        )
        queries = (
            sale("d", date(2015, 3, 1), 1, "98001"),
            sale("e", date(2015, 3, 1), 1, "99999"),
        )
        self.assertEqual(baseline_predictions(training, queries), (200.0, 300.0))

    def test_champion_decision_is_validation_only_with_tail_guard(self) -> None:
        self.assertEqual(
            choose_champion(
                baseline_mdape=Decimal("0.10"),
                model_mdape=Decimal("0.09"),
                baseline_p90=Decimal("0.25"),
                model_p90=Decimal("0.24"),
                baseline_within_10=Decimal("0.60"),
                model_within_10=Decimal("0.65"),
            ),
            "xgboost",
        )
        self.assertEqual(
            choose_champion(
                baseline_mdape=Decimal("0.10"),
                model_mdape=Decimal("0.09"),
                baseline_p90=Decimal("0.25"),
                model_p90=Decimal("0.27"),
                baseline_within_10=Decimal("0.60"),
                model_within_10=Decimal("0.65"),
            ),
            "zipcode_median",
        )

    def test_split_manifest_rejects_changed_membership(self) -> None:
        sales = (
            sale("a", date(2014, 12, 31), 100, "98001"),
            sale("b", date(2015, 1, 1), 200, "98001"),
            sale("c", date(2015, 3, 1), 300, "98001"),
        )
        splits = split_sales(sales)
        manifest = {
            "protocol": "king_historical_sale_date_v1",
            "source_sha256": "pinned",
            "cohort_notes": {"eligible_rows": 3, "quarantine_counts": {}},
            "splits": {
                name: {
                    "count": len(rows),
                    "membership_sha256": hashlib.sha256(
                        ("\n".join(row.row_id for row in rows) + "\n").encode()
                    ).hexdigest(),
                }
                for name, rows in splits.items()
            },
        }
        verify_split_manifest(splits, manifest, expected_source_sha256="pinned", quarantine_counts={})
        altered = {**manifest, "splits": {**manifest["splits"], "test": {**manifest["splits"]["test"], "count": 2}}}
        with self.assertRaisesRegex(ValueError, "split manifest"):
            verify_split_manifest(splits, altered, expected_source_sha256="pinned", quarantine_counts={})


if __name__ == "__main__":
    unittest.main()
