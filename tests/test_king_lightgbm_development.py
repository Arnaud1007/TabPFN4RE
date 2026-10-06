from __future__ import annotations

import math
import hashlib
import json
import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np

from scripts import run_king_lightgbm_development as lightgbm_run
from scripts.king_historical_benchmark import NUMERIC_FEATURES, Sale


def sale(row_id: str, when: date, price: str = "100000") -> Sale:
    attributes = {name: 1.0 for name in NUMERIC_FEATURES}
    attributes["zipcode"] = "98001"
    return Sale(row_id, row_id, when, Decimal(price), attributes)


class KingLightGBMDevelopmentTests(unittest.TestCase):
    def test_frozen_manifest_design_membership_and_predictions_are_bound(self) -> None:
        manifest_payload = b'{"status":"complete"}'
        with (
            patch.object(
                lightgbm_run,
                "read_regular_snapshot",
                return_value=manifest_payload,
            ),
            patch.object(
                lightgbm_run,
                "FROZEN_MANIFEST_SHA256",
                hashlib.sha256(manifest_payload).hexdigest(),
            ),
        ):
            self.assertEqual(
                lightgbm_run.load_frozen_manifest(), {"status": "complete"}
            )

        validation = sale("valid", date(2014, 11, 1), "125000")
        windows = (("2014-11", (), (validation,)),)
        membership = lightgbm_run.membership_for(windows)
        split = lightgbm_run.membership_sha256(membership)
        feature_hash = hashlib.sha256(
            json.dumps(lightgbm_run.FEATURES, separators=(",", ":")).encode()
        ).hexdigest()
        payload = (
            "row_id,sale_date,window,actual_usd,xgboost_usd,"
            "xgboost_log_absolute_error_usd\n"
            "valid,2014-11-01,2014-11,125000,124000,123000\n"
        ).encode()
        prediction_hash = hashlib.sha256(payload).hexdigest()
        frozen = {
            "protocol": "king_log_absolute_error_development_screen_v1",
            "status": "complete",
            "source_sha256": lightgbm_run.SOURCE_SHA256,
            "frozen_rolling_split_sha256": split,
            "feature_policy_sha256": feature_hash,
            "prediction_artifact_sha256": prediction_hash,
            "outputs": {"predictions.csv": prediction_hash},
            "window_membership": membership,
        }
        with (
            patch.object(lightgbm_run, "FROZEN_SPLIT_SHA256", split),
            patch.object(lightgbm_run, "FROZEN_PREDICTION_SHA256", prediction_hash),
            patch.object(lightgbm_run, "read_regular_snapshot", return_value=payload),
        ):
            lightgbm_run.verify_frozen_design(frozen)
            lightgbm_run.verify_frozen_membership(membership, frozen)
            self.assertEqual(
                lightgbm_run.read_frozen_incumbent(Path("frozen.csv"), frozen, windows),
                {"2014-11": (123000.0,)},
            )

            changed = {**frozen, "window_membership": {}}
            with self.assertRaisesRegex(ValueError, "membership"):
                lightgbm_run.verify_frozen_membership(membership, changed)
            with (
                patch.object(
                    lightgbm_run, "read_regular_snapshot", return_value=b"tampered"
                ),
                self.assertRaisesRegex(ValueError, "hash"),
            ):
                lightgbm_run.read_frozen_incumbent(Path("frozen.csv"), frozen, windows)

    def test_manifest_and_lock_reject_invalid_snapshots(self) -> None:
        with (
            patch.object(lightgbm_run, "read_regular_snapshot", return_value=b"{}"),
            self.assertRaisesRegex(ValueError, "manifest hash"),
        ):
            lightgbm_run.load_frozen_manifest()
        with (
            patch.object(lightgbm_run, "read_regular_snapshot", return_value=b"[]"),
            patch.object(
                lightgbm_run,
                "FROZEN_MANIFEST_SHA256",
                hashlib.sha256(b"[]").hexdigest(),
            ),
            self.assertRaisesRegex(TypeError, "must be an object"),
        ):
            lightgbm_run.load_frozen_manifest()
        with (
            patch.object(lightgbm_run, "read_regular_snapshot", return_value=b"{}"),
            self.assertRaisesRegex(ValueError, "lock hash"),
        ):
            lightgbm_run.verify_runtime_versions({})

    def test_configuration_is_one_exact_candidate(self) -> None:
        self.assertEqual(
            lightgbm_run.MODEL_PARAMETERS,
            {
                "objective": "regression_l1",
                "n_estimators": 250,
                "learning_rate": 0.05,
                "num_leaves": 31,
                "max_depth": 6,
                "min_child_samples": 20,
                "subsample": 0.8,
                "subsample_freq": 1,
                "colsample_bytree": 0.8,
                "reg_alpha": 0.0,
                "reg_lambda": 0.0,
                "random_state": 42,
                "n_jobs": 4,
                "deterministic": True,
                "force_col_wise": True,
                "verbosity": -1,
            },
        )
        configured = lightgbm_run.configuration()
        self.assertEqual(configured["fit_count"], 4)
        self.assertEqual(len(configured["windows"]), 4)
        self.assertNotIn("search", configured)

    def test_runtime_drift_blocks_before_labels_or_fit(self) -> None:
        frozen = {"dependency_lock_sha256": lightgbm_run.DECLARED_LOCK_SHA256}
        with (
            patch.object(
                lightgbm_run,
                "runtime_versions",
                return_value={
                    "python": "3.11.6",
                    "numpy": "2.4.6",
                    "scipy": "1.17.0",
                    "lightgbm": "4.6.0",
                    "narwhals": "2.26.0",
                },
            ),
            self.assertRaisesRegex(ValueError, "frozen lock"),
        ):
            lightgbm_run.verify_runtime_versions(frozen)

        source_reader, incumbent_reader, fitter = Mock(), Mock(), Mock()
        with tempfile.TemporaryDirectory() as temporary:
            private = Path(temporary) / "private"
            private.mkdir()
            with (
                patch.object(lightgbm_run, "PRIVATE_ROOT", private),
                patch.object(lightgbm_run, "_committed_code", return_value="a" * 40),
                patch.object(lightgbm_run, "real_directory"),
                patch.object(lightgbm_run, "verify_acl"),
                patch.object(lightgbm_run, "load_frozen_manifest", return_value=frozen),
                patch.object(lightgbm_run, "verify_frozen_design"),
                patch.object(
                    lightgbm_run,
                    "verify_runtime_versions",
                    side_effect=ValueError("runtime drift"),
                ),
                patch.object(lightgbm_run, "read_development_source", source_reader),
                patch.object(lightgbm_run, "read_frozen_incumbent", incumbent_reader),
                patch.object(lightgbm_run, "fit_lightgbm", fitter),
                self.assertRaisesRegex(ValueError, "runtime drift"),
            ):
                lightgbm_run.run(Path("source"), Path("incumbent"), private / "out")
        source_reader.assert_not_called()
        incumbent_reader.assert_not_called()
        fitter.assert_not_called()

    def test_corrupt_incumbent_is_rejected_before_source_labels(self) -> None:
        source_reader = Mock()
        with tempfile.TemporaryDirectory() as temporary:
            private = Path(temporary) / "private"
            private.mkdir()
            with (
                patch.object(lightgbm_run, "PRIVATE_ROOT", private),
                patch.object(lightgbm_run, "_committed_code", return_value="a" * 40),
                patch.object(lightgbm_run, "real_directory"),
                patch.object(lightgbm_run, "verify_acl"),
                patch.object(lightgbm_run, "load_frozen_manifest", return_value={}),
                patch.object(lightgbm_run, "verify_frozen_design"),
                patch.object(lightgbm_run, "verify_runtime_versions", return_value={}),
                patch.object(
                    lightgbm_run,
                    "read_frozen_prediction_snapshot",
                    side_effect=ValueError("corrupt incumbent"),
                ),
                patch.object(lightgbm_run, "read_development_source", source_reader),
                self.assertRaisesRegex(ValueError, "corrupt incumbent"),
            ):
                lightgbm_run.run(Path("source"), Path("incumbent"), private / "out")
        source_reader.assert_not_called()

    def test_adoption_rule_boundaries(self) -> None:
        common = dict(
            incumbent_mdape=Decimal("0.10"),
            challenger_mdape=Decimal("0.098"),
            incumbent_within_10=Decimal("0.50"),
            challenger_within_10=Decimal("0.495"),
            incumbent_p90=Decimal("0.30"),
            challenger_p90=Decimal("0.305"),
            challenger_bias=Decimal("0.01"),
        )
        self.assertEqual(
            lightgbm_run.screening_candidate(**common, improved_windows=3), "lightgbm"
        )
        self.assertEqual(
            lightgbm_run.screening_candidate(**common, improved_windows=2),
            "xgboost_log_absolute_error",
        )
        with self.assertRaisesRegex(ValueError, "between zero and four"):
            lightgbm_run.screening_candidate(**common, improved_windows=5)
        self.assertEqual(
            lightgbm_run.screening_candidate(
                **{**common, "challenger_bias": Decimal("0.010001")},
                improved_windows=3,
            ),
            "xgboost_log_absolute_error",
        )

    def test_fit_uses_log_target_and_positive_exponentiated_output(self) -> None:
        observed: dict[str, object] = {}

        class FakeModel:
            def __init__(self, **parameters: object) -> None:
                observed["parameters"] = parameters

            def fit(self, features: object, labels: object) -> None:
                observed["features"] = features
                observed["labels"] = labels

            def predict(self, features: object) -> np.ndarray:
                return np.full(len(features), math.log(125000.0))  # type: ignore[arg-type]

        with patch.object(lightgbm_run, "_lgbm_regressor", return_value=FakeModel):
            fitted = lightgbm_run.fit_lightgbm(
                (sale("train", date(2014, 1, 1), "100000"),),
                (sale("valid", date(2014, 11, 1), "120000"),),
            )
        self.assertEqual(observed["parameters"], lightgbm_run.MODEL_PARAMETERS)
        self.assertAlmostEqual(float(observed["labels"][0]), math.log(100000.0))  # type: ignore[index]
        self.assertAlmostEqual(fitted.predictions[0], 125000.0)
        self.assertEqual(
            fitted.feature_names[: len(NUMERIC_FEATURES)], NUMERIC_FEATURES
        )

    def test_native_text_booster_and_encoder_are_persisted_and_replayed(self) -> None:
        from lightgbm import LGBMRegressor

        training = tuple(
            sale(f"train-{i}", date(2014, 1, 1), str(100000 + i * 1000))
            for i in range(40)
        )
        validation = (sale("valid", date(2014, 11, 1), "125000"),)
        names, features, validation_features = lightgbm_run.encode_features(
            training, validation
        )
        labels = np.log(np.asarray([float(row.price) for row in training]))
        parameters = {**lightgbm_run.MODEL_PARAMETERS, "n_estimators": 8}
        model = LGBMRegressor(**parameters).fit(features, labels)
        predictions = tuple(
            float(value)
            for value in np.exp(model.predict(np.asarray(validation_features)))
        )
        fitted = lightgbm_run.FittedWindow(model, names, validation, predictions)
        with tempfile.TemporaryDirectory() as temporary:
            artifacts = lightgbm_run.save_and_verify_window(
                Path(temporary), "2014-11", fitted
            )
            self.assertEqual(
                set(artifacts),
                {"2014-11-lightgbm.txt", "2014-11-feature-order.json"},
            )
            persisted = json.loads(
                (Path(temporary) / "2014-11-feature-order.json").read_text()
            )
            self.assertEqual(tuple(persisted["feature_names"]), names)

    def test_missing_or_mismatched_feature_order_is_rejected(self) -> None:
        validation = (sale("valid", date(2014, 11, 1)),)
        with self.assertRaisesRegex(ValueError, "feature order"):
            lightgbm_run.encode_with_feature_names(validation, NUMERIC_FEATURES[1:])
        with self.assertRaisesRegex(ValueError, "ZIP encoder"):
            lightgbm_run.encode_with_feature_names(validation, NUMERIC_FEATURES)
        with self.assertRaisesRegex(ValueError, "feature order"):
            lightgbm_run.encode_with_feature_names(
                validation, (*reversed(NUMERIC_FEATURES), "zipcode=98001")
            )

    def test_native_replay_mismatch_fails_before_artifact_completion(self) -> None:
        fitted = Mock()
        fitted.model.booster_.save_model.side_effect = lambda path: Path(
            path
        ).write_text("model", encoding="utf-8")
        fitted.feature_names = (*NUMERIC_FEATURES, "zipcode=98001")
        fitted.validation = (sale("valid", date(2014, 11, 1)),)
        fitted.predictions = (100000.0,)
        reloaded = Mock()
        reloaded.predict.return_value = np.asarray([math.log(200000.0)])
        with (
            tempfile.TemporaryDirectory() as temporary,
            patch("lightgbm.Booster", return_value=reloaded),
            self.assertRaisesRegex(ValueError, "replay prediction mismatch"),
        ):
            lightgbm_run.save_and_verify_window(Path(temporary), "2014-11", fitted)

    def test_four_fits_are_timed_and_result_is_never_promotion_eligible(self) -> None:
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
        windows = lightgbm_run.monthly_windows(rows)
        membership = lightgbm_run.membership_for(windows)
        fits: list[str] = []

        class Booster:
            def save_model(self, path: Path) -> None:
                path.write_text("booster", encoding="utf-8")

        class Model:
            booster_ = Booster()

        def fit(training: object, validation: object):
            del training
            fits.append(lightgbm_run.WINDOWS[len(fits)][0])
            predictions = tuple(float(row.price) for row in validation)
            return lightgbm_run.FittedWindow(
                Model(),
                (*NUMERIC_FEATURES, "zipcode=98001"),
                tuple(validation),
                predictions,
            )

        def persist(staging: Path, name: str, fitted: object) -> dict[str, str]:
            del fitted
            paths = (
                staging / f"{name}-lightgbm.txt",
                staging / f"{name}-feature-order.json",
            )
            for path in paths:
                path.write_text("artifact", encoding="utf-8")
            return {path.name: lightgbm_run._digest(path) for path in paths}

        frozen = {
            "dependency_lock_sha256": lightgbm_run.DECLARED_LOCK_SHA256,
            "prediction_artifact_sha256": "f" * 64,
            "split_sha256": lightgbm_run.membership_sha256(membership),
            "window_membership": membership,
        }
        clock_values = iter(float(value) for value in range(20))
        with tempfile.TemporaryDirectory() as temporary:
            private = Path(temporary) / "private"
            private.mkdir()
            output = private / "lightgbm"
            with (
                patch.object(lightgbm_run, "PRIVATE_ROOT", private),
                patch.object(lightgbm_run, "_committed_code", return_value="a" * 40),
                patch.object(lightgbm_run, "real_directory"),
                patch.object(lightgbm_run, "secure_directory"),
                patch.object(lightgbm_run, "verify_acl"),
                patch.object(lightgbm_run, "load_frozen_manifest", return_value=frozen),
                patch.object(lightgbm_run, "verify_frozen_design"),
                patch.object(
                    lightgbm_run,
                    "FROZEN_SPLIT_SHA256",
                    lightgbm_run.membership_sha256(membership),
                ),
                patch.object(
                    lightgbm_run,
                    "verify_runtime_versions",
                    return_value={"python": "3.11.6", "lightgbm": "4.7.0"},
                ),
                patch.object(
                    lightgbm_run, "read_development_source", return_value=rows
                ),
                patch.object(
                    lightgbm_run, "select_eligible_sales", return_value=(rows, {})
                ),
                patch.object(
                    lightgbm_run,
                    "read_frozen_prediction_snapshot",
                    return_value=b"frozen",
                ),
                patch.object(
                    lightgbm_run,
                    "parse_frozen_incumbent",
                    return_value={
                        name: tuple(float(row.price) * 1.03 for row in validation)
                        for name, _, validation in windows
                    },
                ),
                patch.object(lightgbm_run, "fit_lightgbm", side_effect=fit),
                patch.object(
                    lightgbm_run,
                    "save_and_verify_window",
                    side_effect=persist,
                ),
                patch.object(lightgbm_run.time, "monotonic", side_effect=clock_values),
            ):
                result = lightgbm_run.run(Path("source"), Path("incumbent"), output)
                manifest = json.loads(
                    (output / "manifest.json").read_text(encoding="utf-8")
                )
                feature_order_digests = {
                    window: lightgbm_run._digest(
                        output / f"{window}-feature-order.json"
                    )
                    for window in manifest["feature_order_identities"]
                }
        self.assertEqual(fits, [item[0] for item in lightgbm_run.WINDOWS])
        self.assertFalse(result["promotion_eligible"])
        self.assertEqual(result["g_us_gate"], "PENDING")
        self.assertEqual(result["fit_count"], 4)
        self.assertTrue(manifest["native_replay"]["verified"])
        self.assertEqual(
            set(manifest["feature_order_identities"]),
            {item[0] for item in lightgbm_run.WINDOWS},
        )
        for window, digest in manifest["feature_order_identities"].items():
            self.assertEqual(digest, feature_order_digests[window])

    def test_fit_or_overall_cap_fails_without_final_output(self) -> None:
        with self.assertRaisesRegex(TimeoutError, "fit time cap"):
            lightgbm_run.enforce_time_caps(121.0, 121.0)
        with self.assertRaisesRegex(TimeoutError, "overall time cap"):
            lightgbm_run.enforce_time_caps(1.0, 301.0)

    def test_post_publication_timeout_removes_atomic_output(self) -> None:
        class Booster:
            def save_model(self, path: Path) -> None:
                path.write_text("booster", encoding="utf-8")

        class Model:
            booster_ = Booster()

        def persist(staging: Path, name: str, fitted: object) -> dict[str, str]:
            del fitted
            paths = (
                staging / f"{name}-lightgbm.txt",
                staging / f"{name}-feature-order.json",
            )
            for path in paths:
                path.write_text("artifact", encoding="utf-8")
            return {path.name: lightgbm_run._digest(path) for path in paths}

        with tempfile.TemporaryDirectory() as temporary:
            private = Path(temporary)
            output = private / "final"
            summary: dict[str, object] = {}
            # artifact-ready, pre-rename, post-rename: only the last exceeds cap.
            clock = iter((100.0, 200.0, 301.0))
            with (
                patch.object(lightgbm_run, "PRIVATE_ROOT", private),
                patch.object(lightgbm_run, "secure_directory"),
                patch.object(lightgbm_run, "real_directory"),
                patch.object(lightgbm_run, "verify_acl"),
                patch.object(
                    lightgbm_run,
                    "save_and_verify_window",
                    side_effect=persist,
                ),
                patch.object(lightgbm_run.time, "monotonic", side_effect=clock),
                self.assertRaisesRegex(TimeoutError, "overall time cap"),
            ):
                lightgbm_run._write_outputs(
                    output,
                    summary,
                    (),
                    {
                        "2014-11": lightgbm_run.FittedWindow(
                            Model(),
                            (*NUMERIC_FEATURES, "zipcode=98001"),
                            (),
                            (),
                        )
                    },
                    {},
                    {},
                    "a" * 40,
                    0.0,
                )
            self.assertFalse(output.exists())
            self.assertEqual(summary, {})


if __name__ == "__main__":
    unittest.main()
