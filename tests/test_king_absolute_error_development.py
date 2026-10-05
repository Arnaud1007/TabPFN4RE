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
from unittest.mock import Mock, patch

from scripts import run_king_absolute_error_development as absolute
from scripts.king_historical_benchmark import COLUMNS, NUMERIC_FEATURES, Sale


def sale(row_id: str, when: date, price: str = "100000") -> Sale:
    attributes = {name: 1.0 for name in NUMERIC_FEATURES}
    attributes["zipcode"] = "98001"
    return Sale(row_id, row_id, when, Decimal(price), attributes)


class KingAbsoluteErrorDevelopmentTests(unittest.TestCase):
    def test_bounded_snapshot_rejects_oversized_and_non_regular_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            oversized = root / "oversized.json"
            oversized.write_bytes(b"12345")
            with self.assertRaisesRegex(ValueError, "size limit"):
                absolute.read_regular_snapshot(oversized, 4, "Test")
            with self.assertRaisesRegex(ValueError, "regular file"):
                absolute.read_regular_snapshot(root, 100, "Test")

    def test_manifest_is_hashed_and_parsed_from_one_snapshot(self) -> None:
        payload = b'{"status":"complete"}'
        snapshot = Mock(return_value=payload)
        with (
            patch.object(absolute, "read_regular_snapshot", snapshot),
            patch.object(
                absolute,
                "FROZEN_MANIFEST_SHA256",
                hashlib.sha256(payload).hexdigest(),
            ),
        ):
            self.assertEqual(absolute.load_frozen_manifest(), {"status": "complete"})
        snapshot.assert_called_once_with(
            absolute.FROZEN_MANIFEST,
            absolute.MAX_MANIFEST_BYTES,
            "Frozen rolling manifest",
        )

    def test_manifest_loader_rejects_changed_bytes_and_non_object(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            manifest = Path(temporary) / "manifest.json"
            manifest.write_text("{}", encoding="utf-8")
            digest = hashlib.sha256(manifest.read_bytes()).hexdigest()
            with (
                patch.object(absolute, "FROZEN_MANIFEST", manifest),
                patch.object(absolute, "FROZEN_MANIFEST_SHA256", digest),
            ):
                self.assertEqual(absolute.load_frozen_manifest(), {})
            with (
                patch.object(absolute, "FROZEN_MANIFEST", manifest),
                patch.object(absolute, "FROZEN_MANIFEST_SHA256", "0" * 64),
                self.assertRaisesRegex(ValueError, "manifest hash"),
            ):
                absolute.load_frozen_manifest()
            manifest.write_text("[]", encoding="utf-8")
            digest = hashlib.sha256(manifest.read_bytes()).hexdigest()
            with (
                patch.object(absolute, "FROZEN_MANIFEST", manifest),
                patch.object(absolute, "FROZEN_MANIFEST_SHA256", digest),
                self.assertRaisesRegex(TypeError, "must be an object"),
            ):
                absolute.load_frozen_manifest()

    def test_selective_reader_never_csv_parses_future_rows(self) -> None:
        header = ["@ATTRIBUTE " + name + " NUMERIC" for name in COLUMNS] + ["@DATA"]
        pre_march = "1,20150228T000000,100000,remaining,fields"
        future = "2,20150301T000000,SECRET,FUTURE,ROW"
        lines = header + [pre_march] + [future] * 21_612
        parsed = sale("pre", date(2015, 2, 28))
        csv_reader = Mock(return_value=iter([["parsed"]]))
        parse_sale = Mock(return_value=parsed)
        with (
            patch.object(absolute, "_decode_source", return_value=lines),
            patch.object(absolute.csv, "reader", csv_reader),
            patch.object(absolute, "_parse_sale", parse_sale),
        ):
            result = absolute.read_development_source(Path("ignored.arff"))
        self.assertEqual(result, (parsed,))
        csv_reader.assert_called_once()
        parse_sale.assert_called_once_with(["parsed"], pre_march)
        self.assertNotIn("SECRET", repr(csv_reader.call_args_list))

    def test_screening_candidate_requires_gain_and_three_windows(self) -> None:
        common = {
            "incumbent_mdape": Decimal("0.10"),
            "challenger_mdape": Decimal("0.097"),
            "incumbent_within_10": Decimal("0.50"),
            "challenger_within_10": Decimal("0.50"),
            "incumbent_p90": Decimal("0.30"),
            "challenger_p90": Decimal("0.30"),
        }
        self.assertEqual(
            absolute.screening_candidate(**common, improved_windows=3),
            "xgboost_log_absolute_error",
        )
        self.assertEqual(
            absolute.screening_candidate(**common, improved_windows=2), "xgboost"
        )
        with self.assertRaisesRegex(ValueError, "between zero and four"):
            absolute.screening_candidate(**common, improved_windows=5)

    def test_runtime_drift_fails_before_source_read_fit_or_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            lock = root / "requirements.txt"
            lock.write_text("numpy==2.4.6\nxgboost==3.2.0\n", encoding="utf-8")
            frozen = {
                "dependency_lock_sha256": hashlib.sha256(lock.read_bytes()).hexdigest()
            }
            with (
                patch.object(absolute, "DECLARED_LOCK", lock),
                patch.object(
                    absolute,
                    "runtime_versions",
                    return_value={
                        "python": "3.11.14",
                        "numpy": "2.4.6",
                        "xgboost": "9.9.9",
                    },
                ),
                self.assertRaisesRegex(ValueError, "do not match"),
            ):
                absolute.verify_runtime_versions(frozen)

            private = root / "private"
            private.mkdir()
            output = private / "must-not-exist"
            source_reader = Mock()
            fitter = Mock()
            with (
                patch.object(absolute, "PRIVATE_ROOT", private),
                patch.object(absolute, "_committed_code", return_value="a" * 40),
                patch.object(absolute, "real_directory"),
                patch.object(absolute, "verify_acl"),
                patch.object(absolute, "load_frozen_manifest", return_value=frozen),
                patch.object(absolute, "verify_frozen_design"),
                patch.object(
                    absolute,
                    "verify_runtime_versions",
                    side_effect=ValueError("runtime drift"),
                ),
                patch.object(absolute, "read_development_source", source_reader),
                patch.object(absolute, "fit_absolute_error", fitter),
                self.assertRaisesRegex(ValueError, "runtime drift"),
            ):
                absolute.run(Path("source.arff"), Path("frozen.csv"), output)
            source_reader.assert_not_called()
            fitter.assert_not_called()
            self.assertFalse(output.exists())

    def test_frozen_design_rejects_model_and_feature_drift(self) -> None:
        rolling_configuration = {
            "model": absolute.MODEL_PARAMETERS,
            "half_life_days": 180,
            "windows": [
                (name, start.isoformat(), end.isoformat())
                for name, start, end in absolute.WINDOWS
            ],
        }
        frozen = {
            "configuration_sha256": hashlib.sha256(
                json.dumps(rolling_configuration, sort_keys=True).encode()
            ).hexdigest(),
            "feature_policy_sha256": hashlib.sha256(
                json.dumps(absolute.FEATURES, separators=(",", ":")).encode()
            ).hexdigest(),
        }
        absolute.verify_frozen_design(frozen)
        changed = {**absolute.MODEL_PARAMETERS, "max_depth": 999}
        with (
            patch.object(absolute, "MODEL_PARAMETERS", changed),
            self.assertRaisesRegex(ValueError, "configuration hash"),
        ):
            absolute.verify_frozen_design(frozen)
        with (
            patch.object(absolute, "FEATURES", (*absolute.FEATURES, "future")),
            self.assertRaisesRegex(ValueError, "feature policy"),
        ):
            absolute.verify_frozen_design(frozen)

        with tempfile.TemporaryDirectory() as temporary:
            private = Path(temporary) / "private"
            private.mkdir()
            output = private / "must-not-exist"
            source_reader = Mock()
            fitter = Mock()
            with (
                patch.object(absolute, "PRIVATE_ROOT", private),
                patch.object(absolute, "_committed_code", return_value="a" * 40),
                patch.object(absolute, "real_directory"),
                patch.object(absolute, "verify_acl"),
                patch.object(absolute, "load_frozen_manifest", return_value=frozen),
                patch.object(
                    absolute,
                    "verify_frozen_design",
                    side_effect=ValueError("configuration drift"),
                ),
                patch.object(absolute, "read_development_source", source_reader),
                patch.object(absolute, "fit_absolute_error", fitter),
                self.assertRaisesRegex(ValueError, "configuration drift"),
            ):
                absolute.run(Path("source.arff"), Path("frozen.csv"), output)
            source_reader.assert_not_called()
            fitter.assert_not_called()
            self.assertFalse(output.exists())

    def test_fit_changes_only_objective_and_returns_positive_predictions(self) -> None:
        calls: list[dict[str, object]] = []

        class FakeModel:
            def __init__(self, **parameters: object) -> None:
                calls.append(parameters)

            def fit(self, features: object, labels: object) -> None:
                self.features = features
                self.labels = labels

            def predict(self, features: object) -> list[float]:
                return [math.log(101000.0) for _ in features]  # type: ignore[arg-type]

        fake_numpy = types.SimpleNamespace(
            asarray=lambda values, dtype=None: list(values),
            log=lambda values: [math.log(value) for value in values],
            exp=lambda values: [math.exp(value) for value in values],
        )
        with patch.dict(
            sys.modules,
            {
                "numpy": fake_numpy,
                "xgboost": types.SimpleNamespace(XGBRegressor=FakeModel),
            },
        ):
            predicted, _ = absolute.fit_absolute_error(
                (sale("train", date(2014, 1, 1)),),
                (sale("valid", date(2014, 11, 1)),),
            )

        expected = dict(absolute.MODEL_PARAMETERS)
        expected["objective"] = "reg:absoluteerror"
        self.assertEqual(calls, [expected])
        self.assertAlmostEqual(predicted[0], 101000.0)

    def test_frozen_predictions_require_exact_hash_and_membership(self) -> None:
        windows = (
            (
                "2014-11",
                (sale("train", date(2014, 10, 1)),),
                (sale("valid", date(2014, 11, 1), "125000"),),
            ),
        )
        membership = absolute.membership_for(windows)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            predictions = root / "predictions.csv"
            predictions.write_text(
                "row_id,sale_date,window,actual_usd,zipcode_median_usd,"
                "xgboost_usd,xgboost_recency_180d_usd\n"
                "valid,2014-11-01,2014-11,125000,120000,123000,124000\n",
                encoding="utf-8",
            )
            digest = hashlib.sha256(predictions.read_bytes()).hexdigest()
            frozen = {
                "run_id": "king-rolling-development-20261005-v1",
                "protocol": "king_rolling_development_v1",
                "status": "complete",
                "source_sha256": absolute.SOURCE_SHA256,
                "window_membership": membership,
                "split_sha256": absolute.membership_sha256(membership),
                "prediction_artifact_sha256": digest,
                "outputs": {"predictions.csv": digest},
            }

            loaded = absolute.read_frozen_incumbent(predictions, frozen, windows)
            self.assertEqual(loaded, {"2014-11": (123000.0,)})

            predictions.write_text(
                predictions.read_text(encoding="utf-8") + "tamper", encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "hash"):
                absolute.read_frozen_incumbent(predictions, frozen, windows)

            predictions.write_text("wrong,columns\n", encoding="utf-8")
            changed_digest = hashlib.sha256(predictions.read_bytes()).hexdigest()
            frozen["prediction_artifact_sha256"] = changed_digest
            frozen["outputs"] = {"predictions.csv": changed_digest}
            with self.assertRaisesRegex(ValueError, "schema"):
                absolute.read_frozen_incumbent(predictions, frozen, windows)

            payload = (
                b"row_id,sale_date,window,actual_usd,zipcode_median_usd,"
                b"xgboost_usd,xgboost_recency_180d_usd\n"
                b"valid,2014-11-01,2014-11,125000,120000,123000,124000\n"
            )
            frozen["prediction_artifact_sha256"] = hashlib.sha256(payload).hexdigest()
            frozen["outputs"] = {
                "predictions.csv": frozen["prediction_artifact_sha256"]
            }
            snapshot = Mock(return_value=payload)
            with patch.object(absolute, "read_regular_snapshot", snapshot):
                self.assertEqual(
                    absolute.read_frozen_incumbent(
                        Path("does-not-exist.csv"), frozen, windows
                    ),
                    {"2014-11": (123000.0,)},
                )
            snapshot.assert_called_once_with(
                Path("does-not-exist.csv"),
                absolute.MAX_PREDICTION_BYTES,
                "Frozen rolling predictions",
            )

    def test_runner_performs_exactly_four_fits_and_never_scores_march(self) -> None:
        rows = tuple(
            sale(str(index), when, str(100000 + index * 1000))
            for index, when in enumerate(
                (
                    date(2014, 10, 1),
                    date(2014, 11, 15),
                    date(2014, 12, 15),
                    date(2015, 1, 15),
                    date(2015, 2, 15),
                )
            )
        )
        windows = absolute.monthly_windows(rows)
        membership = absolute.membership_for(windows)
        frozen_predictions = {
            name: tuple(float(item.price) * 1.02 for item in validation)
            for name, _, validation in windows
        }
        fit_calls: list[str] = []

        class Model:
            def __init__(self, name: str) -> None:
                self.name = name

            def save_model(self, path: Path) -> None:
                path.write_text(self.name, encoding="utf-8")

        def fit(training: object, validation: object):
            del training
            name = absolute.WINDOWS[len(fit_calls)][0]
            fit_calls.append(name)
            return tuple(float(item.price) for item in validation), Model(name)

        frozen = {
            "run_id": "king-rolling-development-20261005-v1",
            "protocol": "king_rolling_development_v1",
            "status": "complete",
            "source_sha256": absolute.SOURCE_SHA256,
            "window_membership": membership,
            "split_sha256": absolute.membership_sha256(membership),
            "prediction_artifact_sha256": "f" * 64,
            "outputs": {"predictions.csv": "f" * 64},
            "dependency_lock_sha256": "e" * 64,
        }

        with tempfile.TemporaryDirectory() as temporary:
            private = Path(temporary) / "private"
            private.mkdir()
            output = private / "absolute-v1"
            with (
                patch.object(absolute, "PRIVATE_ROOT", private),
                patch.object(absolute, "_committed_code", return_value="a" * 40),
                patch.object(absolute, "real_directory"),
                patch.object(absolute, "secure_directory"),
                patch.object(absolute, "verify_acl"),
                patch.object(absolute, "read_development_source", return_value=rows),
                patch.object(
                    absolute, "select_eligible_sales", return_value=(rows, {})
                ),
                patch.object(absolute, "load_frozen_manifest", return_value=frozen),
                patch.object(absolute, "verify_frozen_design"),
                patch.object(
                    absolute,
                    "verify_runtime_versions",
                    return_value={"python": "test", "xgboost": "test"},
                ),
                patch.object(
                    absolute,
                    "read_frozen_incumbent",
                    return_value=frozen_predictions,
                ),
                patch.object(absolute, "fit_absolute_error", side_effect=fit),
            ):
                result = absolute.run(Path("source.arff"), Path("frozen.csv"), output)

            self.assertEqual(fit_calls, [item[0] for item in absolute.WINDOWS])
            self.assertEqual(result["fit_count"], 4)
            self.assertEqual(result["march_may_labels_parsed"], 0)
            self.assertEqual(result["march_may_rows_scored"], 0)
            self.assertFalse(result["promotion_eligible"])
            self.assertEqual(result["evidence_class"], "development_screening_only")
            self.assertEqual(set(result["windows"]), set(fit_calls))
            manifest = json.loads((output / "manifest.json").read_text())
            self.assertEqual(manifest["fit_count"], 4)
            self.assertEqual(manifest["runtime_versions"]["python"], "test")
            self.assertEqual(manifest["frozen_rolling_prediction_sha256"], "f" * 64)
            self.assertEqual(
                manifest["configuration_sha256"],
                hashlib.sha256(
                    json.dumps(
                        manifest["configuration"],
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode()
                ).hexdigest(),
            )
            with (output / "predictions.csv").open(
                newline="", encoding="utf-8"
            ) as stream:
                saved = list(csv.DictReader(stream))
            self.assertEqual(len(saved), 4)
            self.assertNotIn("2015-03", {row["window"] for row in saved})
            self.assertEqual(len(manifest["challenger_checkpoint_identities"]), 4)
            for name, digest in manifest["outputs"].items():
                self.assertEqual(
                    digest, hashlib.sha256((output / name).read_bytes()).hexdigest()
                )

    def test_atomic_output_is_absent_after_fit_failure(self) -> None:
        rows = tuple(
            sale(str(index), when)
            for index, when in enumerate(
                (
                    date(2014, 10, 1),
                    date(2014, 11, 15),
                    date(2014, 12, 15),
                    date(2015, 1, 15),
                    date(2015, 2, 15),
                )
            )
        )
        windows = absolute.monthly_windows(rows)
        membership = absolute.membership_for(windows)
        frozen = {
            "run_id": "king-rolling-development-20261005-v1",
            "protocol": "king_rolling_development_v1",
            "status": "complete",
            "source_sha256": absolute.SOURCE_SHA256,
            "prediction_artifact_sha256": "f" * 64,
            "window_membership": membership,
            "split_sha256": absolute.membership_sha256(membership),
        }
        with tempfile.TemporaryDirectory() as temporary:
            private = Path(temporary) / "private"
            private.mkdir()
            output = private / "failed"
            with (
                patch.object(absolute, "PRIVATE_ROOT", private),
                patch.object(absolute, "_committed_code", return_value="a" * 40),
                patch.object(absolute, "real_directory"),
                patch.object(absolute, "secure_directory"),
                patch.object(absolute, "verify_acl"),
                patch.object(absolute, "read_development_source", return_value=rows),
                patch.object(
                    absolute, "select_eligible_sales", return_value=(rows, {})
                ),
                patch.object(absolute, "load_frozen_manifest", return_value=frozen),
                patch.object(absolute, "verify_frozen_design"),
                patch.object(
                    absolute,
                    "verify_runtime_versions",
                    return_value={"python": "test", "xgboost": "test"},
                ),
                patch.object(
                    absolute,
                    "read_frozen_incumbent",
                    return_value={
                        name: tuple(100000.0 for _ in validation)
                        for name, _, validation in windows
                    },
                ),
                patch.object(
                    absolute,
                    "fit_absolute_error",
                    side_effect=RuntimeError("fit failed"),
                ),
                self.assertRaisesRegex(RuntimeError, "fit failed"),
            ):
                absolute.run(Path("source.arff"), Path("frozen.csv"), output)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
