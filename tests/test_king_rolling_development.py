from __future__ import annotations

import csv
import hashlib
import json
import math
import sys
import tempfile
import types
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from scripts import run_king_rolling_development as rolling
from scripts.king_historical_benchmark import NUMERIC_FEATURES, Sale
from scripts.run_king_rolling_development import (
    choose_recency_challenger,
    monthly_windows,
    recency_weights,
)


def sale(row: str, when: date) -> Sale:
    return Sale(row, row, when, Decimal(100000), {"zipcode": "98001"})


def full_sale(row: str, when: date) -> Sale:
    attributes = {name: 1.0 for name in NUMERIC_FEATURES}
    attributes["zipcode"] = "98001"
    return Sale(row, row, when, Decimal(100000), attributes)


class KingRollingDevelopmentTests(unittest.TestCase):
    def test_monthly_windows_are_strictly_chronological_and_disjoint(self) -> None:
        sales = tuple(
            sale(str(index), when)
            for index, when in enumerate(
                (
                    date(2014, 10, 31),
                    date(2014, 11, 1),
                    date(2014, 11, 30),
                    date(2014, 12, 1),
                    date(2015, 1, 1),
                    date(2015, 2, 1),
                    date(2015, 2, 28),
                    date(2015, 3, 1),
                )
            )
        )

        windows = monthly_windows(sales)

        self.assertEqual(
            [name for name, _, _ in windows],
            ["2014-11", "2014-12", "2015-01", "2015-02"],
        )
        validation_ids: set[str] = set()
        for _, training, validation in windows:
            self.assertTrue(training)
            self.assertTrue(validation)
            self.assertLess(
                max(row.sale_date for row in training),
                min(row.sale_date for row in validation),
            )
            self.assertFalse(validation_ids & {row.row_id for row in validation})
            validation_ids.update(row.row_id for row in validation)
        self.assertNotIn("7", validation_ids)

    def test_recency_weights_use_only_training_dates_and_expected_half_life(
        self,
    ) -> None:
        training = (
            sale("old", date(2014, 5, 5)),
            sale("half", date(2014, 11, 2)),
            sale("recent", date(2015, 4, 30)),
        )
        weights = recency_weights(training, cutoff=date(2015, 5, 1), half_life_days=180)
        self.assertAlmostEqual(weights[1], 0.5, places=12)
        self.assertAlmostEqual(weights[0], 0.25, delta=0.002)
        self.assertGreater(weights[2], weights[1])
        with self.assertRaisesRegex(ValueError, "before cutoff"):
            recency_weights(
                (sale("future", date(2015, 5, 1)),),
                cutoff=date(2015, 5, 1),
                half_life_days=180,
            )

    def test_challenger_requires_three_windows_and_two_percent_pooled_gain(
        self,
    ) -> None:
        self.assertEqual(
            choose_recency_challenger(
                incumbent_mdape=Decimal("0.100"),
                challenger_mdape=Decimal("0.097"),
                incumbent_within_10=Decimal("0.50"),
                challenger_within_10=Decimal("0.50"),
                incumbent_p90=Decimal("0.30"),
                challenger_p90=Decimal("0.30"),
                improved_windows=3,
            ),
            "xgboost_recency_180d",
        )
        self.assertEqual(
            choose_recency_challenger(
                incumbent_mdape=Decimal("0.100"),
                challenger_mdape=Decimal("0.097"),
                incumbent_within_10=Decimal("0.50"),
                challenger_within_10=Decimal("0.50"),
                incumbent_p90=Decimal("0.30"),
                challenger_p90=Decimal("0.30"),
                improved_windows=2,
            ),
            "xgboost",
        )

    def test_runner_writes_common_row_predictions_and_research_only_summary(
        self,
    ) -> None:
        rows = tuple(
            sale(str(index), when)
            for index, when in enumerate(
                (
                    date(2014, 10, 1),
                    date(2014, 11, 15),
                    date(2014, 12, 15),
                    date(2015, 1, 15),
                    date(2015, 2, 15),
                    date(2015, 3, 15),
                )
            )
        )
        with tempfile.TemporaryDirectory() as temporary:
            private = Path(temporary) / "king-benchmark"
            private.mkdir()
            output = private / "rolling-v1"

            def model(training, validation, weights):
                del training
                adjustment = 1000 if weights is not None else 0
                saved = types.SimpleNamespace(
                    save_model=lambda path: Path(path).write_text(
                        f"model-{adjustment}", encoding="utf-8"
                    )
                )
                return tuple(100000 + adjustment for _ in validation), saved

            cutoffs = []
            real_recency = rolling.recency_weights

            def weights(training, *, cutoff, half_life_days=180):
                cutoffs.append(cutoff)
                return real_recency(
                    training, cutoff=cutoff, half_life_days=half_life_days
                )

            with (
                patch.object(rolling, "PRIVATE_ROOT", private),
                patch.object(rolling, "_committed_code", return_value="a" * 40),
                patch.object(rolling, "secure_directory"),
                patch.object(rolling, "real_directory"),
                patch.object(rolling, "verify_acl"),
                patch.object(rolling, "read_pinned_source", return_value=rows),
                patch.object(rolling, "select_eligible_sales", return_value=(rows, {})),
                patch.object(rolling, "_fit_predict", side_effect=model),
                patch.object(rolling, "recency_weights", side_effect=weights),
                patch.object(
                    rolling,
                    "baseline_predictions",
                    side_effect=lambda training, validation: tuple(
                        90000 for _ in validation
                    ),
                ),
            ):
                result = rolling.run(Path("ignored.arff"), output)

            self.assertEqual(result["march_may_rows_scored"], 0)
            self.assertFalse(result["certified_90_day_origin"])
            self.assertEqual(result["g_us_gate"], "PENDING")
            self.assertEqual(
                set(result["windows"]), {item[0] for item in rolling.WINDOWS}
            )
            with (output / "predictions.csv").open(
                newline="", encoding="utf-8"
            ) as stream:
                predictions = list(csv.DictReader(stream))
            self.assertEqual(
                [(row["row_id"], row["window"]) for row in predictions],
                [
                    ("1", "2014-11"),
                    ("2", "2014-12"),
                    ("3", "2015-01"),
                    ("4", "2015-02"),
                ],
            )
            self.assertNotIn("5", {row["row_id"] for row in predictions})
            saved = json.loads((output / "scorecards.json").read_text())
            self.assertEqual(saved, result)
            manifest = json.loads((output / "manifest.json").read_text())
            self.assertEqual(manifest["status"], "complete")
            self.assertEqual(manifest["code_commit"], "a" * 40)
            self.assertEqual(cutoffs, [item[1] for item in rolling.WINDOWS])
            self.assertEqual(manifest["source_sha256"], rolling.SOURCE_SHA256)
            self.assertEqual(set(manifest["window_membership"]), set(result["windows"]))
            for name, digest in manifest["outputs"].items():
                self.assertEqual(
                    digest, hashlib.sha256((output / name).read_bytes()).hexdigest()
                )
            self.assertEqual(
                manifest["prediction_artifact_sha256"],
                manifest["outputs"]["predictions.csv"],
            )
            self.assertEqual(len(manifest["checkpoint_identities"]), 8)
            for checkpoint, digest in manifest["checkpoint_identities"].items():
                self.assertEqual(digest, manifest["outputs"][f"{checkpoint}.json"])
            membership = manifest["window_membership"]
            for name, training, validation in rolling.monthly_windows(rows):
                self.assertEqual(membership[name]["training_count"], len(training))
                self.assertEqual(membership[name]["validation_count"], len(validation))
                self.assertEqual(
                    membership[name]["training_sha256"],
                    hashlib.sha256(
                        ("\n".join(item.row_id for item in training) + "\n").encode()
                    ).hexdigest(),
                )
                self.assertEqual(
                    membership[name]["validation_sha256"],
                    hashlib.sha256(
                        ("\n".join(item.row_id for item in validation) + "\n").encode()
                    ).hexdigest(),
                )
            expected_split = hashlib.sha256(
                json.dumps(membership, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            self.assertEqual(manifest["split_sha256"], expected_split)

            failed_output = private / "failed-v1"
            with (
                patch.object(rolling, "PRIVATE_ROOT", private),
                patch.object(rolling, "_committed_code", return_value="a" * 40),
                patch.object(rolling, "secure_directory"),
                patch.object(rolling, "real_directory"),
                patch.object(rolling, "verify_acl"),
                patch.object(rolling, "read_pinned_source", return_value=rows),
                patch.object(rolling, "select_eligible_sales", return_value=(rows, {})),
                patch.object(
                    rolling, "_fit_predict", side_effect=RuntimeError("fit failed")
                ),
                self.assertRaisesRegex(RuntimeError, "fit failed"),
            ):
                rolling.run(Path("ignored.arff"), failed_output)
            self.assertFalse(failed_output.exists())

    def test_fit_predict_passes_only_registered_sample_weights(self) -> None:
        calls = []

        class FakeModel:
            def __init__(self, **parameters):
                self.parameters = parameters

            def fit(self, features, labels, **kwargs):
                calls.append((features.copy(), labels.copy(), kwargs.copy()))

            def predict(self, features):
                return [math.log(100000.0) for _ in features]

        fake_module = types.SimpleNamespace(XGBRegressor=FakeModel)
        fake_numpy = types.SimpleNamespace(
            asarray=lambda values, dtype=None: list(values),
            log=lambda values: [math.log(value) for value in values],
            exp=lambda values: [math.exp(value) for value in values],
        )
        training = (
            full_sale("a", date(2014, 1, 1)),
            full_sale("b", date(2014, 2, 1)),
        )
        validation = (full_sale("c", date(2014, 3, 1)),)
        with patch.dict(sys.modules, {"xgboost": fake_module, "numpy": fake_numpy}):
            plain, _ = rolling._fit_predict(training, validation, None)
            weighted, _ = rolling._fit_predict(training, validation, (0.5, 1.0))

        self.assertAlmostEqual(plain[0], 100000.0)
        self.assertAlmostEqual(weighted[0], 100000.0)
        self.assertEqual(calls[0][2], {})
        self.assertEqual(calls[1][2]["sample_weight"], [0.5, 1.0])


if __name__ == "__main__":
    unittest.main()
