from __future__ import annotations

import hashlib
import json
import math
import tempfile
import unittest
from types import SimpleNamespace
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock, patch

from scripts import run_king_tabpfn_development as tabpfn_run
from scripts.king_historical_benchmark import NUMERIC_FEATURES, Sale


def sale(row_id: str, when: date, price: str = "100000") -> Sale:
    attributes = {name: 1.0 for name in NUMERIC_FEATURES}
    attributes["zipcode"] = "98001"
    return Sale(row_id, row_id, when, Decimal(price), attributes)


class KingTabPFNDevelopmentTests(unittest.TestCase):
    def test_committed_lock_matches_the_runner_hash(self) -> None:
        self.assertEqual(tabpfn_run._load_lock(), tabpfn_run.EXPECTED_LOCK)

    def test_runtime_identity_and_exact_lock_validation(self) -> None:
        fake_torch = SimpleNamespace(
            __version__="2.10.0+cpu", version=SimpleNamespace(cuda=None)
        )
        completed = SimpleNamespace(stdout="610.60\n")
        with (
            patch.dict("sys.modules", {"torch": fake_torch}),
            patch.object(
                tabpfn_run.importlib.metadata,
                "version",
                side_effect=lambda name: {
                    "numpy": "2.4.6",
                    "tabpfn": "9.1.0",
                    "torch": "2.10.0",
                }[name],
            ),
            patch.object(tabpfn_run, "python_version", return_value="3.11.6"),
            patch.object(tabpfn_run.subprocess, "run", return_value=completed),
        ):
            identity = tabpfn_run.verify_runtime(tabpfn_run.EXPECTED_LOCK)
        self.assertEqual(identity["nvidia_driver"], "610.60")
        self.assertEqual(identity["torch_build"], "2.10.0+cpu")
        with (
            patch.object(
                tabpfn_run,
                "runtime_identity",
                return_value={"python": "3.12.0", "packages": {}},
            ),
            self.assertRaisesRegex(ValueError, "frozen lock"),
        ):
            tabpfn_run.verify_runtime(tabpfn_run.EXPECTED_LOCK)

    def test_frozen_beat_rule_boundaries(self) -> None:
        values = {
            "incumbent_mdape": Decimal("0.10"),
            "challenger_mdape": Decimal("0.098"),
            "incumbent_within_10": Decimal("0.50"),
            "challenger_within_10": Decimal("0.495"),
            "incumbent_p90": Decimal("0.30"),
            "challenger_p90": Decimal("0.305"),
            "improved_windows": 3,
        }
        self.assertEqual(
            tabpfn_run.frozen_beat_rule(**values), "tabpfn_3_5_reduced_context"
        )
        self.assertEqual(
            tabpfn_run.frozen_beat_rule(**{**values, "improved_windows": 2}),
            "xgboost_log_absolute_error",
        )
        with self.assertRaisesRegex(ValueError, "between zero and four"):
            tabpfn_run.frozen_beat_rule(**{**values, "improved_windows": 5})
        self.assertEqual(
            tabpfn_run.frozen_beat_rule(
                **{**values, "challenger_mdape": Decimal("0.098001")}
            ),
            "xgboost_log_absolute_error",
        )

    def test_lock_pins_official_code_and_filename_but_not_unverified_weights(
        self,
    ) -> None:
        lock = tabpfn_run._load_lock()
        self.assertEqual(lock, tabpfn_run.EXPECTED_LOCK)
        self.assertEqual(lock["source"], {"commit": "0b1a081", "release_tag": "v9.1.0"})
        self.assertEqual(
            lock["checkpoint"]["hugging_face_repository"], "Prior-Labs/tabpfn_3_5"
        )
        self.assertEqual(
            lock["checkpoint"]["filename"], "tabpfn-v3.5-20260909.safetensors"
        )
        self.assertIsNone(lock["checkpoint"]["revision"])
        self.assertIsNone(lock["checkpoint"]["sha256"])

    def test_configuration_is_one_bounded_research_candidate(self) -> None:
        configured = tabpfn_run.configuration()
        self.assertEqual(configured["package"], "tabpfn==9.1.0")
        self.assertEqual(configured["model_family"], "tabpfn_3_5")
        self.assertEqual(configured["fit_count"], 4)
        self.assertEqual(configured["max_context_rows"], 10000)
        self.assertEqual(configured["device"], "cuda")
        self.assertFalse(configured["remote_inference"])
        self.assertFalse(configured["automatic_downloads"])

    def test_preflight_reports_every_blocker_without_opening_labels(self) -> None:
        source_reader = Mock()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            lock = root / "lock.json"
            lock.write_text(json.dumps(tabpfn_run.EXPECTED_LOCK), encoding="utf-8")
            with (
                patch.object(tabpfn_run, "DECLARED_LOCK", lock),
                patch.object(
                    tabpfn_run,
                    "DECLARED_LOCK_SHA256",
                    hashlib.sha256(lock.read_bytes()).hexdigest(),
                ),
                patch.object(tabpfn_run, "package_version", return_value=None),
                patch.object(
                    tabpfn_run,
                    "dependency_version",
                    side_effect=lambda name: tabpfn_run.EXPECTED_LOCK["dependencies"][
                        name
                    ],
                ),
                patch.object(tabpfn_run, "python_version", return_value="3.11.6"),
                patch.object(
                    tabpfn_run,
                    "cuda_capability",
                    return_value=(False, 0, "torch unavailable"),
                ),
                patch.object(tabpfn_run, "free_disk_bytes", return_value=100),
                patch.object(tabpfn_run, "read_development_source", source_reader),
            ):
                result = tabpfn_run.preflight(
                    root / "missing.ckpt", root / "missing-license.json"
                )
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(
            {item["code"] for item in result["blockers"]},
            {
                "package_unavailable",
                "cuda_unavailable",
                "destination_disk_insufficient",
                "checkpoint_identity_unresolved",
                "checkpoint_unavailable",
                "license_decision_unavailable",
            },
        )
        self.assertNotIn(str(root), json.dumps(result))
        source_reader.assert_not_called()

    def test_preflight_rejects_wrong_package_checkpoint_and_license(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            checkpoint = root / "model.ckpt"
            checkpoint.write_bytes(b"wrong")
            decision = root / "license.json"
            decision.write_text(
                json.dumps({"checkpoint_id": "wrong", "commercially_eligible": True}),
                encoding="utf-8",
            )
            pinned = {
                **tabpfn_run.EXPECTED_LOCK,
                "checkpoint": {
                    **tabpfn_run.EXPECTED_LOCK["checkpoint"],
                    "revision": "verified-revision",
                    "sha256": "a" * 64,
                },
            }
            lock = root / "lock.json"
            lock.write_text(json.dumps(pinned), encoding="utf-8")
            with (
                patch.object(tabpfn_run, "DECLARED_LOCK", lock),
                patch.object(
                    tabpfn_run,
                    "DECLARED_LOCK_SHA256",
                    hashlib.sha256(lock.read_bytes()).hexdigest(),
                ),
                patch.object(tabpfn_run, "package_version", return_value="9.0.0"),
                patch.object(
                    tabpfn_run,
                    "dependency_version",
                    side_effect=lambda name: pinned["dependencies"][name],
                ),
                patch.object(tabpfn_run, "python_version", return_value="3.11.6"),
                patch.object(
                    tabpfn_run,
                    "cuda_capability",
                    return_value=(True, 16 * 1024**3, "ok"),
                ),
                patch.object(tabpfn_run, "free_disk_bytes", return_value=20 * 1024**3),
            ):
                result = tabpfn_run.preflight(checkpoint, decision)
        codes = {item["code"] for item in result["blockers"]}
        self.assertIn("package_version_mismatch", codes)
        self.assertIn("checkpoint_hash_mismatch", codes)
        self.assertIn("license_decision_incompatible", codes)

    def test_ready_preflight_requires_exact_local_artifacts(self) -> None:
        checkpoint = b"official weights"
        expected = {
            **tabpfn_run.EXPECTED_LOCK,
            "checkpoint": {
                **tabpfn_run.EXPECTED_LOCK["checkpoint"],
                "revision": "verified-test-revision",
                "sha256": hashlib.sha256(checkpoint).hexdigest(),
            },
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            model = root / "model.ckpt"
            model.write_bytes(checkpoint)
            decision = root / "license.json"
            decision.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "checkpoint_id": expected["checkpoint"]["id"],
                        "checkpoint_revision": expected["checkpoint"]["revision"],
                        "checkpoint_sha256": expected["checkpoint"]["sha256"],
                        "research_use_permitted": True,
                        "commercially_eligible": False,
                        "decision": "approved_for_local_research",
                    }
                ),
                encoding="utf-8",
            )
            lock = root / "lock.json"
            lock.write_text(json.dumps(expected), encoding="utf-8")
            with (
                patch.object(tabpfn_run, "DECLARED_LOCK", lock),
                patch.object(
                    tabpfn_run,
                    "DECLARED_LOCK_SHA256",
                    hashlib.sha256(lock.read_bytes()).hexdigest(),
                ),
                patch.object(tabpfn_run, "package_version", return_value="9.1.0"),
                patch.object(
                    tabpfn_run,
                    "dependency_version",
                    side_effect=lambda name: expected["dependencies"][name],
                ),
                patch.object(tabpfn_run, "python_version", return_value="3.11.6"),
                patch.object(
                    tabpfn_run,
                    "cuda_capability",
                    return_value=(True, 16 * 1024**3, "ok"),
                ),
                patch.object(tabpfn_run, "free_disk_bytes", return_value=20 * 1024**3),
            ):
                result = tabpfn_run.preflight(model, decision)
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["blockers"], [])
        self.assertFalse(result["commercially_eligible"])

    def test_run_stops_before_source_when_preflight_is_blocked(self) -> None:
        source_reader, fitter = Mock(), Mock()
        with (
            patch.object(
                tabpfn_run,
                "preflight",
                return_value={
                    "status": "blocked",
                    "blockers": [
                        {"code": "cuda_unavailable", "message": "CUDA is unavailable"}
                    ],
                },
            ),
            patch.object(tabpfn_run, "read_development_source", source_reader),
            patch.object(tabpfn_run, "fit_tabpfn", fitter),
            self.assertRaisesRegex(RuntimeError, "preflight blocked"),
        ):
            tabpfn_run.run(
                Path("source"),
                Path("incumbent"),
                Path("checkpoint"),
                Path("license"),
                Path("output"),
            )
        source_reader.assert_not_called()
        fitter.assert_not_called()

    def test_fit_uses_recent_bounded_context_and_log_target(self) -> None:
        observed: dict[str, object] = {}

        class FakeRegressor:
            def fit(self, features: object, labels: object) -> None:
                observed["features"] = features
                observed["labels"] = labels

            def predict(self, features: object) -> list[float]:
                return [math.log(125000.0)] * len(features)  # type: ignore[arg-type]

        rows = tuple(
            sale(
                str(index),
                date(2010, 1, 1) + timedelta(days=index),
                str(100000 + index),
            )
            for index in range(5)
        )
        with (
            patch.object(tabpfn_run, "MAX_CONTEXT_ROWS", 3),
            patch.object(tabpfn_run, "_regressor", return_value=FakeRegressor()),
            patch.object(tabpfn_run, "checkpoint_sha256", return_value="hash"),
        ):
            predictions, evidence = tabpfn_run.fit_tabpfn(
                rows, (sale("v", date(2014, 11, 1)),), Path("model"), "hash"
            )
        self.assertEqual(len(observed["features"]), 3)  # type: ignore[arg-type]
        labels = observed["labels"]
        self.assertAlmostEqual(float(labels[0]), math.log(100002.0))  # type: ignore[index]
        self.assertAlmostEqual(predictions[0], 125000.0)
        self.assertEqual(evidence["context_row_count"], 3)
        self.assertEqual(evidence["prediction_repeat_count"], 3)

    def test_ready_run_writes_private_atomic_artifacts(self) -> None:
        training = (sale("t", date(2014, 1, 1)),)
        validation = (sale("v", date(2014, 11, 1), "120000"),)
        windows = (("2014-11", training, validation),)
        with tempfile.TemporaryDirectory() as temporary:
            private = Path(temporary) / "private"
            private.mkdir()
            checkpoint = Path(temporary) / "model.ckpt"
            checkpoint.write_bytes(b"checkpoint")
            license_decision = Path(temporary) / "license.json"
            license_decision.write_text("{}", encoding="utf-8")
            checkpoint_hash = hashlib.sha256(b"checkpoint").hexdigest()
            locked = {
                **tabpfn_run.EXPECTED_LOCK,
                "checkpoint": {
                    **tabpfn_run.EXPECTED_LOCK["checkpoint"],
                    "revision": "revision",
                    "sha256": checkpoint_hash,
                },
            }
            output = private / "result"
            with (
                patch.object(tabpfn_run, "PRIVATE_ROOT", private),
                patch.object(tabpfn_run, "preflight", return_value={"status": "ready"}),
                patch.object(tabpfn_run, "real_directory"),
                patch.object(tabpfn_run, "verify_acl"),
                patch.object(tabpfn_run, "secure_directory"),
                patch.object(tabpfn_run, "_load_lock", return_value=locked),
                patch.object(
                    tabpfn_run, "verify_runtime", return_value={"python": "3.11.6"}
                ),
                patch.object(tabpfn_run, "_committed_code", return_value="a" * 40),
                patch.object(tabpfn_run, "load_frozen_manifest", return_value={}),
                patch.object(tabpfn_run, "verify_frozen_design"),
                patch.object(
                    tabpfn_run,
                    "read_development_source",
                    return_value=((training + validation), "source-hash"),
                ),
                patch.object(tabpfn_run, "monthly_windows", return_value=windows),
                patch.object(tabpfn_run, "verify_frozen_membership"),
                patch.object(
                    tabpfn_run,
                    "read_frozen_prediction_snapshot",
                    return_value=b"frozen",
                ),
                patch.object(
                    tabpfn_run,
                    "parse_frozen_incumbent",
                    return_value={"2014-11": (119000.0,)},
                ),
                patch.object(
                    tabpfn_run,
                    "fit_tabpfn",
                    return_value=(
                        (121000.0,),
                        {
                            "context_row_count": 1,
                            "context_row_ids_sha256": "b" * 64,
                            "prediction_repeat_count": 3,
                            "max_absolute_variation_usd": 0.0,
                            "max_relative_variation": 0.0,
                        },
                    ),
                ),
            ):
                manifest = tabpfn_run.run(
                    Path("source"),
                    Path("incumbent"),
                    checkpoint,
                    license_decision,
                    output,
                )
            self.assertEqual(manifest["status"], "complete")
            self.assertFalse(manifest["promotion_eligible"])
            self.assertEqual(manifest["g_us"], "PENDING")
            self.assertTrue((output / "predictions.csv").is_file())
            self.assertTrue((output / "manifest.json").is_file())

    def test_run_rejects_non_private_or_existing_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            private = Path(temporary) / "private"
            private.mkdir()
            existing = private / "existing"
            existing.mkdir()
            with (
                patch.object(tabpfn_run, "PRIVATE_ROOT", private),
                patch.object(tabpfn_run, "preflight", return_value={"status": "ready"}),
                patch.object(tabpfn_run, "real_directory"),
                patch.object(tabpfn_run, "verify_acl"),
                self.assertRaisesRegex(ValueError, "new private"),
            ):
                tabpfn_run.run(
                    Path("source"),
                    Path("incumbent"),
                    Path("checkpoint"),
                    Path("license"),
                    existing,
                )

    def test_checkpoint_reader_rejects_symlink_and_oversized_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "target"
            target.write_bytes(b"x")
            link = root / "link"
            try:
                link.symlink_to(target)
            except OSError:
                self.skipTest("symlink creation unavailable")
            with self.assertRaisesRegex(ValueError, "regular local file"):
                tabpfn_run.checkpoint_sha256(link)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "large"
            path.write_bytes(b"xx")
            with (
                patch.object(tabpfn_run, "MAX_CHECKPOINT_BYTES", 1),
                self.assertRaisesRegex(ValueError, "size"),
            ):
                tabpfn_run.checkpoint_sha256(path)

    def test_cli_preflight_writes_privacy_safe_json_and_never_downloads(self) -> None:
        result = {
            "status": "blocked",
            "blockers": [
                {"code": "package_unavailable", "message": "TabPFN is not installed"}
            ],
        }
        with (
            patch.object(tabpfn_run, "preflight", return_value=result),
            patch("builtins.print") as printer,
        ):
            code = tabpfn_run.main(
                [
                    "preflight",
                    "--checkpoint",
                    "secret/model.ckpt",
                    "--license-decision",
                    "secret/license.json",
                ]
            )
        self.assertEqual(code, 3)
        emitted = json.loads(printer.call_args.args[0])
        self.assertEqual(emitted, result)
        self.assertNotIn("secret", printer.call_args.args[0])

    def test_cli_run_dispatches_only_explicit_local_paths(self) -> None:
        with patch.object(tabpfn_run, "run", return_value={}) as runner:
            code = tabpfn_run.main(
                [
                    "run",
                    "--source",
                    "source",
                    "--incumbent-predictions",
                    "incumbent",
                    "--checkpoint",
                    "checkpoint",
                    "--license-decision",
                    "license",
                    "--output",
                    "output",
                ]
            )
        self.assertEqual(code, 0)
        runner.assert_called_once_with(
            Path("source"),
            Path("incumbent"),
            Path("checkpoint"),
            Path("license"),
            Path("output"),
        )

    def test_invalid_prediction_is_rejected(self) -> None:
        class InvalidRegressor:
            def fit(self, features: object, labels: object) -> None:
                pass

            def predict(self, features: object) -> list[float]:
                return [float("nan")] * len(features)  # type: ignore[arg-type]

        with (
            patch.object(tabpfn_run, "_regressor", return_value=InvalidRegressor()),
            patch.object(tabpfn_run, "checkpoint_sha256", return_value="hash"),
            self.assertRaisesRegex(ValueError, "invalid predictions"),
        ):
            tabpfn_run.fit_tabpfn(
                (sale("t", date(2014, 1, 1)),),
                (sale("v", date(2014, 11, 1)),),
                Path("model"),
                "hash",
            )

    def test_invalid_or_short_later_prediction_repeat_is_rejected(self) -> None:
        class LaterInvalidRegressor:
            calls = 0

            def fit(self, features: object, labels: object) -> None:
                pass

            def predict(self, features: object) -> list[float]:
                self.calls += 1
                if self.calls == 1:
                    return [math.log(125000.0)] * len(features)  # type: ignore[arg-type]
                if self.calls == 2:
                    return []
                return [float("nan")] * len(features)  # type: ignore[arg-type]

        with (
            patch.object(
                tabpfn_run, "_regressor", return_value=LaterInvalidRegressor()
            ),
            patch.object(tabpfn_run, "checkpoint_sha256", return_value="hash"),
            self.assertRaisesRegex(ValueError, "invalid predictions"),
        ):
            tabpfn_run.fit_tabpfn(
                (sale("t", date(2014, 1, 1)),),
                (sale("v", date(2014, 11, 1)),),
                Path("model"),
                "hash",
            )


if __name__ == "__main__":
    unittest.main()
