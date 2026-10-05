from __future__ import annotations

from datetime import date
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

from scripts import build_king_absolute_error_bundle as bundle
from scripts.king_historical_benchmark import NUMERIC_FEATURES, Sale


def sale(row_id: str) -> Sale:
    attributes = {name: 1.0 for name in NUMERIC_FEATURES}
    attributes["yr_built"] = 1900.0
    attributes["zipcode"] = "98001"
    return Sale(row_id, row_id, date(2015, 2, 1), Decimal("100000"), attributes)


class FakeModel:
    def save_model(self, path: Path) -> None:
        path.write_bytes(b"absolute-error-model")


class KingAbsoluteErrorBundleTests(unittest.TestCase):
    def test_runtime_verification_binds_lock_and_rejects_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            lock = Path(temporary) / "requirements.txt"
            lock.write_text("numpy==2.4.6\nxgboost==3.2.0\n", encoding="utf-8")
            numpy = types.ModuleType("numpy")
            numpy.__version__ = "2.4.6"
            xgboost = types.ModuleType("xgboost")
            xgboost.__version__ = "3.2.0"
            with (
                patch.dict("sys.modules", {"numpy": numpy, "xgboost": xgboost}),
                patch.object(bundle, "DECLARED_LOCK", lock),
                patch.object(
                    bundle,
                    "DECLARED_LOCK_SHA256",
                    hashlib.sha256(lock.read_bytes()).hexdigest(),
                ),
                patch.object(bundle.platform, "python_version", return_value="3.11.6"),
            ):
                observed = bundle.verify_runtime_versions()
                self.assertEqual(observed["xgboost"], "3.2.0")
                xgboost.__version__ = "9.9.9"
                with self.assertRaisesRegex(ValueError, "frozen lock"):
                    bundle.verify_runtime_versions()
                xgboost.__version__ = "3.2.0"
                with (
                    patch.object(
                        bundle.platform, "python_version", return_value="3.11.9"
                    ),
                    self.assertRaisesRegex(ValueError, "frozen lock"),
                ):
                    bundle.verify_runtime_versions()
                with (
                    patch.object(bundle.platform, "platform", return_value="other-os"),
                    self.assertRaisesRegex(ValueError, "frozen lock"),
                ):
                    bundle.verify_runtime_versions()
            with (
                patch.dict("sys.modules", {"numpy": numpy, "xgboost": xgboost}),
                patch.object(bundle, "DECLARED_LOCK", lock),
                self.assertRaisesRegex(ValueError, "lock hash"),
            ):
                bundle.verify_runtime_versions()

    def test_configuration_and_membership_are_deterministic(self) -> None:
        configured = bundle.configuration()
        self.assertEqual(configured["objective"], "reg:absoluteerror")
        first = bundle.membership_sha256((sale("one"), sale("two")))
        second = bundle.membership_sha256((sale("one"), sale("two")))
        self.assertEqual(first, second)
        self.assertNotEqual(first, bundle.membership_sha256((sale("two"), sale("one"))))

    def test_selection_evidence_is_digest_pinned_and_requires_selected_candidate(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = root / "manifest.json"
            aggregate = root / "aggregate.json"
            aggregate.write_text(
                json.dumps(
                    {
                        "development_screening_candidate": "xgboost_log_absolute_error",
                        "eligible_rows": 16849,
                        "improved_windows": 4,
                        "march_may_labels_parsed": 0,
                        "march_may_rows_scored": 0,
                    }
                ),
                encoding="utf-8",
            )
            manifest.write_text(
                json.dumps(
                    {
                        "protocol": "king_log_absolute_error_development_screen_v1",
                        "status": "complete",
                        "source_sha256": bundle.SOURCE_SHA256,
                        "declared_lock_sha256": bundle.DECLARED_LOCK_SHA256,
                        "runtime_versions": dict(bundle.EXPECTED_RUNTIME),
                        "outputs": {"scorecards.json": bundle.digest(aggregate)},
                        "configuration": {
                            "model": dict(bundle.ABSOLUTE_MODEL_CONFIGURATION),
                            "challenger_objective": "reg:absoluteerror",
                        },
                    }
                ),
                encoding="utf-8",
            )
            with (
                patch.object(bundle, "SELECTION_MANIFEST", manifest),
                patch.object(bundle, "SELECTION_AGGREGATE", aggregate),
                patch.object(
                    bundle, "SELECTION_MANIFEST_SHA256", bundle.digest(manifest)
                ),
                patch.object(
                    bundle, "SELECTION_AGGREGATE_SHA256", bundle.digest(aggregate)
                ),
            ):
                evidence = bundle.load_selection_evidence()
                self.assertEqual(evidence["improved_windows"], 4)
                saved = json.loads(manifest.read_text(encoding="utf-8"))
                for name, value in (("max_depth", 99), ("random_state", 7)):
                    changed = json.loads(json.dumps(saved))
                    changed["configuration"]["model"][name] = value
                    manifest.write_text(json.dumps(changed), encoding="utf-8")
                    with (
                        patch.object(
                            bundle,
                            "SELECTION_MANIFEST_SHA256",
                            bundle.digest(manifest),
                        ),
                        self.assertRaisesRegex(ValueError, "selection evidence"),
                    ):
                        bundle.load_selection_evidence()
                manifest.write_text(json.dumps(saved), encoding="utf-8")
                aggregate.write_text("{}", encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "selection evidence"):
                    bundle.load_selection_evidence()

    def test_build_checks_clean_code_before_evidence_or_stage(self) -> None:
        clean = Mock(side_effect=ValueError("dirty tree"))
        evidence = Mock()
        staged = Mock()
        with (
            patch.object(bundle, "_committed_code", clean),
            patch.object(bundle, "load_selection_evidence", evidence),
            patch.object(bundle, "load_staged_training", staged),
            self.assertRaisesRegex(ValueError, "dirty tree"),
        ):
            bundle.build(Path("stage"), "a" * 64, Path("output"))
        evidence.assert_not_called()
        staged.assert_not_called()

    def test_build_refits_once_on_exact_pre_march_cohort_and_writes_bound_manifest(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            private = root / "private"
            private.mkdir()
            output = private / bundle.EXPECTED_RUN_ID
            rows = tuple(sale(str(index)) for index in range(16849))
            fit = Mock(return_value=(FakeModel(), ("bedrooms", "zipcode=98001")))
            evidence = {
                "development_screening_candidate": "xgboost_log_absolute_error",
                "eligible_rows": 16849,
                "improved_windows": 4,
                "march_may_labels_parsed": 0,
                "march_may_rows_scored": 0,
            }
            stage_manifest = {"training_membership_sha256": "b" * 64}
            verification = {
                "status": "passed",
                "probe_count": 8,
                "probe_sha256": "1" * 64,
                "prediction_sha256": "2" * 64,
                "absolute_tolerance": 1e-12,
                "relative_tolerance": 1e-12,
                "maximum_absolute_difference": 0.0,
                "maximum_relative_difference": 0.0,
            }
            with (
                patch.object(bundle, "PRIVATE_ROOT", private),
                patch.object(bundle, "_committed_code", return_value="a" * 40),
                patch.object(bundle, "load_selection_evidence", return_value=evidence),
                patch.object(
                    bundle,
                    "verify_runtime_versions",
                    return_value={
                        "machine": "AMD64",
                        "python": "3.11.6",
                        "numpy": "2.4.6",
                        "platform": "Windows-10-10.0.26200-SP0",
                        "xgboost": "3.2.0",
                    },
                ),
                patch.object(
                    bundle,
                    "load_staged_training",
                    return_value=(rows, stage_manifest),
                ),
                patch.object(bundle, "fit_bundle", fit),
                patch.object(bundle, "_verify_saved_model", return_value=verification),
                patch.object(bundle, "real_directory"),
                patch.object(bundle, "verify_acl"),
            ):
                summary = bundle.build(Path("stage"), "c" * 64, output)
            fit.assert_called_once_with(rows)
            self.assertEqual(summary["training_rows"], 16849)
            self.assertEqual(summary["fit_count"], 1)
            self.assertEqual(summary["march_may_labels_parsed"], 0)
            self.assertEqual(summary["save_load_verification"], verification)
            manifest = json.loads(
                (output / "manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["protocol"], bundle.PROTOCOL)
            self.assertEqual(manifest["objective"], "reg:absoluteerror")
            self.assertEqual(manifest["training_cutoff_exclusive"], "2015-03-01")
            self.assertEqual(manifest["training_rows"], 16849)
            self.assertEqual(manifest["fit_count"], 1)
            self.assertEqual(manifest["code_commit"], "a" * 40)
            self.assertEqual(manifest["stage_manifest_sha256"], "c" * 64)
            self.assertEqual(manifest["training_membership_sha256"], "b" * 64)
            self.assertEqual(
                manifest["checkpoint_identity"],
                hashlib.sha256(b"absolute-error-model").hexdigest(),
            )
            self.assertEqual(manifest["save_load_verification"], verification)

    def test_save_load_verification_failure_prevents_publication(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            private = Path(temporary)
            output = private / bundle.EXPECTED_RUN_ID
            training = tuple(sale(str(index)) for index in range(8))
            with (
                patch.object(bundle, "PRIVATE_ROOT", private),
                patch.object(bundle, "secure_directory"),
                patch.object(
                    bundle,
                    "_verify_saved_model",
                    side_effect=ValueError("reload mismatch"),
                ),
                self.assertRaisesRegex(ValueError, "reload mismatch"),
            ):
                bundle._write_bundle(
                    output,
                    FakeModel(),
                    ("bedrooms", "zipcode=98001"),
                    training,
                    dict(bundle.EXPECTED_RUNTIME),
                    "a" * 40,
                    {},
                    "b" * 64,
                    {"training_membership_sha256": "c" * 64},
                )
            self.assertFalse(output.exists())

    def test_real_xgboost_save_load_predictions_are_equivalent(self) -> None:
        try:
            import numpy as np
            from xgboost import XGBRegressor
        except ImportError as error:
            self.skipTest(f"Scientific runtime unavailable: {error}")
        training = tuple(sale(f"{index:064x}") for index in range(8))
        names, rows, _ = bundle.encode_features(training, ())
        model = XGBRegressor(
            **{
                **dict(bundle.ABSOLUTE_MODEL_CONFIGURATION),
                "n_estimators": 2,
                "max_depth": 1,
            }
        )
        model.fit(
            np.asarray(rows, dtype=float),
            np.log(np.asarray([float(item.price) for item in training])),
        )
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "model.json"
            model.save_model(path)
            result = bundle._verify_saved_model(model, path, training)
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["probe_count"], 8)
        self.assertEqual(result["maximum_absolute_difference"], 0.0)

    def test_builder_has_no_full_source_reader_and_opens_only_staged_artifacts(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            private = Path(temporary)
            stage = private / "stage-v1"
            stage.mkdir()
            row = sale("a" * 64)
            record = {
                "row_id": row.row_id,
                "property_id": row.property_id,
                "sale_date": row.sale_date.isoformat(),
                "price_usd": str(row.price),
                "features": dict(row.attributes),
            }
            artifact = stage / bundle.ARTIFACT_NAME
            artifact.write_text(
                json.dumps(record, separators=(",", ":")) + "\n", encoding="utf-8"
            )
            manifest = {
                "run_id": stage.name,
                "protocol": bundle.STAGE_PROTOCOL,
                "scope": "private_historical_research_training_only",
                "status": "complete",
                "code_commit": "a" * 40,
                "source_sha256": bundle.SOURCE_SHA256,
                "source_rows_parsed": 1,
                "training_rows": 1,
                "training_cutoff_exclusive": "2015-03-01",
                "training_membership_sha256": bundle.membership_sha256((row,)),
                "quarantine_counts": {"future_year_built": 12},
                "schema": [
                    "row_id",
                    "property_id",
                    "sale_date",
                    "price_usd",
                    "features",
                ],
                "feature_names": list(bundle.FEATURES),
                "march_may_labels_parsed": 0,
                "outputs": {bundle.ARTIFACT_NAME: bundle.digest(artifact)},
            }
            manifest_path = stage / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            opened: list[Path] = []
            original = bundle.read_regular_snapshot

            def observed(path: Path, limit: int, label: str) -> bytes:
                opened.append(path)
                return original(path, limit, label)

            with (
                patch.object(bundle, "PRIVATE_ROOT", private),
                patch.object(bundle, "EXPECTED_SOURCE_ROWS", 1),
                patch.object(bundle, "EXPECTED_TRAINING_ROWS", 1),
                patch.object(bundle, "read_regular_snapshot", side_effect=observed),
                patch.object(bundle, "real_directory"),
                patch.object(bundle, "verify_acl"),
            ):
                rows, _ = bundle.load_staged_training(
                    stage, bundle.digest(manifest_path)
                )
            self.assertEqual(rows, (row,))
            self.assertEqual(opened, [manifest_path, artifact])
            self.assertFalse(hasattr(bundle, "read_development_source"))

    def test_build_rejects_output_outside_private_root_before_source_read(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            private = root / "private"
            private.mkdir()
            staged = Mock(
                return_value=(
                    (sale("a" * 64),),
                    {"training_membership_sha256": "b" * 64},
                )
            )
            with (
                patch.object(bundle, "PRIVATE_ROOT", private),
                patch.object(bundle, "_committed_code", return_value="a" * 40),
                patch.object(bundle, "load_selection_evidence", return_value={}),
                patch.object(bundle, "verify_runtime_versions", return_value={}),
                patch.object(bundle, "real_directory"),
                patch.object(bundle, "verify_acl"),
                patch.object(bundle, "load_staged_training", staged),
                self.assertRaisesRegex(ValueError, "private King"),
            ):
                bundle.build(Path("stage"), "a" * 64, root / "outside" / "bundle")
            staged.assert_called_once()


if __name__ == "__main__":
    unittest.main()
