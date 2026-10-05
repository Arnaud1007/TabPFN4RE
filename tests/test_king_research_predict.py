"""Contract tests for the historical King County prediction command."""

from __future__ import annotations

import hashlib
import io
import json
import math
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
from contextlib import redirect_stderr, redirect_stdout

from scripts.king_historical_benchmark import NUMERIC_FEATURES, SOURCE_SHA256
from scripts import king_research_predict as serving


REQUEST = {
    "bedrooms": 3,
    "bathrooms": 2,
    "sqft_living": 1800,
    "sqft_lot": 6000,
    "floors": 2,
    "waterfront": 0,
    "view": 0,
    "condition": 3,
    "grade": 7,
    "sqft_above": 1800,
    "sqft_basement": 0,
    "yr_built": 1985,
    "lat": 47.55,
    "long": -122.25,
    "zipcode": "98103",
}
FEATURE_NAMES = (*NUMERIC_FEATURES, "zipcode=98001", "zipcode=98103")


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


class LogModel:
    def predict(self, matrix):
        self.matrix = matrix
        return [math.log(200_000)]


class OverflowModel:
    def predict(self, matrix):
        return [1000.0]


class KingResearchPredictTests(unittest.TestCase):
    def test_predict_uses_verified_bundle_and_emits_historical_scope(self) -> None:
        fake_xgboost = types.ModuleType("xgboost")

        class FakeRegressor:
            def load_model(self, model_bytes):
                self.model_bytes = model_bytes

            def predict(self, matrix):
                self.matrix = matrix
                return [math.log(200_000)]

        fake_xgboost.XGBRegressor = FakeRegressor
        verified = serving.VerifiedBundle(FEATURE_NAMES, b"model", "a" * 64, "b" * 64)
        with (
            patch.dict(sys.modules, {"xgboost": fake_xgboost}),
            patch.object(serving, "load_bundle", return_value=verified) as load,
        ):
            result = serving.predict(Path("private-bundle"), REQUEST, "a" * 64)
        load.assert_called_once_with(Path("private-bundle"), "a" * 64)
        self.assertAlmostEqual(result["amount"], 200_000, places=6)
        self.assertEqual(result["status"], "historical_research_only")
        self.assertFalse(result["certified_90_day_origin"])
        self.assertEqual(result["g_us_gate"], "PENDING")

    def test_cli_reads_request_and_reports_prediction_or_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            request_file = Path(directory) / "request.json"
            request_file.write_text(json.dumps(REQUEST), encoding="utf-8")
            argv = [
                "king_research_predict",
                "--bundle",
                "private-bundle",
                "--manifest-sha256",
                "a" * 64,
                "--request",
                str(request_file),
            ]
            response = {"amount": 200_000.0, "status": "historical_research_only"}
            output = io.StringIO()
            with (
                patch.object(sys, "argv", argv),
                patch.object(serving, "predict", return_value=response) as predict,
                redirect_stdout(output),
            ):
                self.assertEqual(serving.main(), 0)
            self.assertEqual(json.loads(output.getvalue()), response)
            predict.assert_called_once_with(
                Path("private-bundle"), REQUEST, "a" * 64, None
            )

            error_output = io.StringIO()
            with (
                patch.object(sys, "argv", argv),
                patch.object(serving, "predict", side_effect=ValueError("bad bundle")),
                redirect_stderr(error_output),
            ):
                self.assertEqual(serving.main(), 2)
            self.assertIn("bad bundle", error_output.getvalue())

    def test_valid_request_uses_frozen_feature_order_and_log_price(self) -> None:
        values = serving.validate_request(REQUEST, FEATURE_NAMES)
        vector = serving.encode_request(values, FEATURE_NAMES)
        self.assertEqual(
            vector[: len(NUMERIC_FEATURES)],
            tuple(float(REQUEST[name]) for name in NUMERIC_FEATURES),
        )
        self.assertEqual(vector[-2:], (0.0, 1.0))
        model = LogModel()
        self.assertAlmostEqual(serving.predict_price(model, vector), 200_000, places=6)
        self.assertEqual(len(model.matrix), 1)
        self.assertEqual(len(model.matrix[0]), len(FEATURE_NAMES))

    def test_request_rejects_unsupported_or_invalid_inputs(self) -> None:
        invalid = (
            {**REQUEST, "price": 200_000},
            {key: value for key, value in REQUEST.items() if key != "sqft_living"},
            {**REQUEST, "sqft_living": 0},
            {**REQUEST, "sqft_living": float("nan")},
            {**REQUEST, "sqft_living": 10**400},
            {**REQUEST, "bedrooms": True},
            {**REQUEST, "bedrooms": 2.5},
            {**REQUEST, "view": 1.5},
            {**REQUEST, "condition": 3.5},
            {**REQUEST, "grade": 7.5},
            {**REQUEST, "yr_built": 1985.5},
            {**REQUEST, "zipcode": "99999"},
            {**REQUEST, "zipcode": "9810"},
            {**REQUEST, "lat": 0},
            {**REQUEST, "long": 0},
            {**REQUEST, "yr_built": 2026},
        )
        for request in invalid:
            with self.subTest(request=request), self.assertRaises(ValueError):
                serving.validate_request(request, FEATURE_NAMES)

    def test_overflowing_model_output_is_an_explicit_failure(self) -> None:
        with self.assertRaisesRegex(ValueError, "invalid sale-price"):
            serving.predict_price(OverflowModel(), (1.0,))

    def test_verified_bundle_rejects_tampering_and_wrong_scope(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            private_root = Path(directory)
            bundle = private_root / "run"
            bundle.mkdir()
            names = json.dumps(FEATURE_NAMES).encode()
            model = b"model bytes"
            candidate = json.dumps(
                {"selected_on_validation": "xgboost", "artifact": "xgboost_model.json"}
            ).encode()
            files = {
                "feature_names.json": names,
                "xgboost_model.json": model,
                "candidate.json": candidate,
            }
            for name, content in files.items():
                (bundle / name).write_bytes(content)
            manifest = {
                "run_id": "run",
                "scope": "historical_research_only",
                "status": "validation_complete_test_unscored",
                "selected_candidate": "xgboost",
                "source_sha256": SOURCE_SHA256,
                "split_manifest_sha256": digest(serving._SPLIT_PATH.read_bytes()),
                "dependency_lock_sha256": digest(serving._LOCK_PATH.read_bytes()),
                "configuration_sha256": digest(
                    json.dumps(serving.MODEL_PARAMETERS, sort_keys=True).encode()
                ),
                "checkpoint_identity": digest(model),
                "feature_policy_sha256": digest(names),
                "outputs": {name: digest(content) for name, content in files.items()},
            }
            manifest_path = bundle / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            expected = digest(manifest_path.read_bytes())
            with (
                patch.object(serving, "PRIVATE_ROOT", private_root),
                patch.object(serving, "verify_acl"),
            ):
                with self.assertRaisesRegex(ValueError, "checksum"):
                    serving.load_bundle(bundle, "0" * 64)
                loaded = serving.load_bundle(bundle, expected)
                self.assertEqual(loaded.feature_names, FEATURE_NAMES)
                self.assertEqual(loaded.model_bytes, model)
                (bundle / "xgboost_model.json").write_bytes(b"changed")
                with self.assertRaises(ValueError):
                    serving.load_bundle(bundle, expected)
                (bundle / "xgboost_model.json").write_bytes(model)
                manifest["scope"] = "commercial"
                manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
                with self.assertRaises(ValueError):
                    serving.load_bundle(bundle, digest(manifest_path.read_bytes()))


if __name__ == "__main__":
    unittest.main()
