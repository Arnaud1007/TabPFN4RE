"""Synthetic guards for the one-use King later-period research check."""

from __future__ import annotations

import sys
import unittest
from contextlib import nullcontext
from datetime import date
from decimal import Decimal
from math import exp
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from scripts import run_king_historical_later as later_runner
from scripts.king_historical_benchmark import NUMERIC_FEATURES, SOURCE_SHA256, Sale
from scripts.king_research_predict import VerifiedBundle
from scripts.run_king_historical_later import (
    BUNDLE_MANIFEST_SHA256,
    MODEL_SHA256,
    SPLIT_SHA256,
    consume_once,
    summarize_later,
    verify_frozen_inputs,
    verify_runtime_packages,
)


def sale(row_id: str, amount: int) -> Sale:
    return Sale(row_id, row_id, date(2015, 3, 1), Decimal(amount), {})


class KingLaterResearchTests(unittest.TestCase):
    def test_frozen_inputs_reject_any_changed_evaluation_identity(self) -> None:
        identity = {
            "source_sha256": SOURCE_SHA256,
            "split_sha256": SPLIT_SHA256,
            "bundle_manifest_sha256": BUNDLE_MANIFEST_SHA256,
            "model_sha256": MODEL_SHA256,
            "selected_candidate": "xgboost",
        }
        verify_frozen_inputs(**identity)
        for key in identity:
            changed = {
                **identity,
                key: "zipcode_median" if key == "selected_candidate" else "0" * 64,
            }
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "frozen"):
                verify_frozen_inputs(**changed)

    def test_runtime_must_match_the_pinned_model_environment(self) -> None:
        verify_runtime_packages({"numpy": "2.4.6", "xgboost": "3.2.0"})
        with self.assertRaisesRegex(ValueError, "runtime"):
            verify_runtime_packages({"numpy": "2.4.6", "xgboost": "3.1.0"})

    def test_opening_intent_is_durable_before_action_and_never_reopens(self) -> None:
        with TemporaryDirectory() as directory:
            ledger = Path(directory) / "opened.json"
            intent = {"protocol": "king_later_2015_research_v1", "run_id": "fixture"}

            def work() -> str:
                self.assertEqual(
                    ledger.read_text(encoding="utf-8").strip(),
                    '{"protocol":"king_later_2015_research_v1","run_id":"fixture"}',
                )
                return "done"

            self.assertEqual(consume_once(ledger, intent, work), "done")
            with self.assertRaises(FileExistsError):
                consume_once(ledger, intent, lambda: "reopened")

    def test_crash_after_intent_consumes_research_cohort(self) -> None:
        with TemporaryDirectory() as directory:
            ledger = Path(directory) / "opened.json"

            def crash() -> None:
                raise RuntimeError("injected crash")

            with self.assertRaisesRegex(RuntimeError, "injected crash"):
                consume_once(ledger, {"run_id": "fixture"}, crash)
            self.assertTrue(ledger.is_file())
            with self.assertRaises(FileExistsError):
                consume_once(ledger, {"run_id": "new"}, lambda: None)

    def test_summary_scores_same_rows_and_never_claims_certification(self) -> None:
        later = (sale("a", 100), sale("b", 200))
        result = summarize_later(later, (110.0, 180.0), (150.0, 150.0))
        self.assertEqual(result["test_rows"], 2)
        self.assertEqual(result["later_period"]["xgboost"]["eligible_count"], 2)
        self.assertEqual(result["later_period"]["zipcode_median"]["eligible_count"], 2)
        self.assertEqual(result["later_period"]["xgboost"]["mdape"], 0.1)
        self.assertEqual(result["selected_on_prior_validation"], "xgboost")
        self.assertFalse(result["certified_90_day_origin"])
        self.assertEqual(result["g_us_gate"], "PENDING")
        with self.assertRaisesRegex(ValueError, "Prediction count"):
            summarize_later(later, (110.0,), (150.0, 150.0))

    def test_prediction_file_precedes_scoring_and_output_is_private(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            split = root / "split.json"
            split.write_text("{}", encoding="utf-8")
            training = (sale("train", 100),)
            later = (sale("a", 100), sale("b", 200))
            original_summary = later_runner.summarize_later

            def score_after_file(*args):
                files = list(root.glob("king-later-staging-*/later_predictions.csv"))
                self.assertEqual(len(files), 1)
                self.assertEqual(
                    len(files[0].read_text(encoding="utf-8").splitlines()), 3
                )
                return original_summary(*args)

            with (
                patch.object(later_runner, "PRIVATE_ROOT", root),
                patch.object(later_runner, "OUTPUT_PATH", root / "output"),
                patch.object(later_runner, "SPLIT_PATH", split),
                patch.object(later_runner, "EXPECTED_LATER_ROWS", 2),
                patch.object(
                    later_runner, "read_pinned_source", return_value=training + later
                ),
                patch.object(
                    later_runner,
                    "select_eligible_sales",
                    return_value=(training + later, {}),
                ),
                patch.object(
                    later_runner,
                    "split_sales",
                    return_value={"train": training, "validation": (), "test": later},
                ),
                patch.object(later_runner, "verify_split_manifest"),
                patch.object(later_runner, "_predict", return_value=(110.0, 180.0)),
                patch.object(
                    later_runner, "baseline_predictions", return_value=(150.0, 150.0)
                ),
                patch.object(later_runner, "secure_directory"),
                patch.object(later_runner, "real_directory"),
                patch.object(
                    later_runner, "summarize_later", side_effect=score_after_file
                ),
            ):
                result = later_runner._evaluate(None, {"run_id": "fixture"})
            self.assertEqual(result["test_rows"], 2)
            self.assertTrue((root / "output/later_predictions.csv").is_file())
            self.assertTrue((root / "output/scorecards.json").is_file())
            self.assertTrue((root / "output/manifest.json").is_file())

    def test_later_price_cannot_change_frozen_model_input(self) -> None:
        attributes = {name: 1.0 for name in NUMERIC_FEATURES}
        attributes["zipcode"] = "98001"
        training = (
            Sale("train", "train", date(2014, 12, 1), Decimal(100), attributes),
        )
        low = (Sale("later", "later", date(2015, 3, 1), Decimal(100), attributes),)
        high = (Sale("later", "later", date(2015, 3, 1), Decimal(900), attributes),)
        names = (*NUMERIC_FEATURES, "zipcode=98001")
        bundle = VerifiedBundle(names, b"model", "a" * 64, "b" * 64)

        class Model:
            def load_model(self, _: bytearray) -> None:
                pass

            def predict(self, rows):
                return [float(sum(row) / 1_000) for row in rows]

        dependencies = {
            "numpy": SimpleNamespace(
                asarray=lambda rows, dtype: rows,
                exp=lambda values: [exp(value) for value in values],
                errstate=lambda **_: nullcontext(),
            ),
            "xgboost": SimpleNamespace(XGBRegressor=Model),
        }
        with patch.dict(sys.modules, dependencies):
            self.assertEqual(
                later_runner._predict(bundle, training, low),
                later_runner._predict(bundle, training, high),
            )


if __name__ == "__main__":
    unittest.main()
