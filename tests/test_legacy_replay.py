"""The retrospective legacy replay must never parse or score reserved labels."""

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.replay_legacy_ames_dev import (
    ReplayRun,
    assert_development_only,
    build_replay_manifest,
    canonical_sha256,
    collect_git_identity,
    day8_mae_pivot_rows,
    filter_development_arff,
    installed_packages,
    load_frozen_holdout,
    prepare_staging,
    promote_staging,
    require_legacy_lock,
    validate_finite_replay_values,
    verify_replay_identity,
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class LegacyReplayTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.source = self.root / "ames.arff"
        self.source.write_text(
            "@RELATION house_prices\n"
            "@ATTRIBUTE Id INTEGER\n"
            "@ATTRIBUTE SalePrice INTEGER\n"
            "@DATA\n"
            "1,100\n"
            "2,not_a_price\n"
            "3,300\n"
            "4,also_not_a_price\n",
            encoding="utf-8",
        )
        self.holdout = self.root / "holdout_ids.csv"
        self.holdout.write_text("row_id\n1\n3\n", encoding="utf-8")

    def test_reserved_labels_are_never_parsed(self) -> None:
        reserved = load_frozen_holdout(
            self.holdout,
            expected_sha256=digest(self.holdout),
            expected_count=2,
            source_count=4,
        )
        filtered = filter_development_arff(
            self.source,
            reserved,
            expected_sha256=digest(self.source),
            expected_rows=4,
        )
        self.assertEqual(filtered.row_indices, (0, 2))
        self.assertEqual(filtered.field_names, ("Id", "SalePrice"))
        self.assertEqual(filtered.csv_text, "Id,SalePrice\n1,100\n3,300\n")
        self.assertNotIn("not_a_price", filtered.csv_text)

    def test_development_category_preserves_literal_apostrophes(self) -> None:
        self.source.write_text(
            "@RELATION house_prices\n"
            "@ATTRIBUTE Id INTEGER\n"
            "@ATTRIBUTE Exterior1st STRING\n"
            "@ATTRIBUTE SalePrice INTEGER\n"
            "@DATA\n"
            "1,'Wd Sdng',100\n"
            "2,'reserved',not_a_price\n",
            encoding="utf-8",
        )
        filtered = filter_development_arff(
            self.source,
            (1,),
            expected_sha256=digest(self.source),
            expected_rows=2,
        )
        self.assertEqual(
            filtered.csv_text, "Id,Exterior1st,SalePrice\n1,'Wd Sdng',100\n"
        )

    def test_rejects_bad_source_or_holdout_checksum(self) -> None:
        with self.assertRaisesRegex(ValueError, "holdout.*SHA-256"):
            load_frozen_holdout(
                self.holdout,
                expected_sha256="0" * 64,
                expected_count=2,
                source_count=4,
            )
        with self.assertRaisesRegex(ValueError, "ARFF.*SHA-256"):
            filter_development_arff(
                self.source,
                (1, 3),
                expected_sha256="0" * 64,
                expected_rows=4,
            )

    def test_rejects_duplicate_and_out_of_range_holdout_indices(self) -> None:
        self.holdout.write_text("row_id\n1\n1\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "duplicate"):
            load_frozen_holdout(
                self.holdout,
                expected_sha256=digest(self.holdout),
                expected_count=2,
                source_count=4,
            )
        self.holdout.write_text("row_id\n1\n4\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "range"):
            load_frozen_holdout(
                self.holdout,
                expected_sha256=digest(self.holdout),
                expected_count=2,
                source_count=4,
            )

    def test_rejects_reserved_id_in_fit_or_score(self) -> None:
        assert_development_only((0, 2), (1, 3), source_count=4)
        with self.assertRaisesRegex(ValueError, "reserved"):
            assert_development_only((0, 1), (1, 3), source_count=4)
        with self.assertRaisesRegex(ValueError, "duplicate"):
            assert_development_only((0, 0), (1, 3), source_count=4)

    def test_rejects_source_count_or_incomplete_reservation(self) -> None:
        with self.assertRaisesRegex(ValueError, "rows"):
            filter_development_arff(
                self.source,
                (1, 3),
                expected_sha256=digest(self.source),
                expected_rows=5,
            )
        with self.assertRaisesRegex(ValueError, "reserved"):
            filter_development_arff(
                self.source,
                (1, 9),
                expected_sha256=digest(self.source),
                expected_rows=4,
            )

    def test_day8_mae_pivot_is_not_labelled_baseline_reproduction(self) -> None:
        scores = [
            {"modele": "Dummy", "pli": 1, "mae": 100.0},
            {"modele": "XGBoost", "pli": 1, "mae": 20.0},
            {"modele": "Dummy", "pli": 2, "mae": 80.0},
            {"modele": "XGBoost", "pli": 2, "mae": 15.0},
        ]
        self.assertEqual(
            day8_mae_pivot_rows(scores),
            [
                {"pli": 1, "MAE_dummy": 100.0, "MAE_xgboost": 20.0},
                {"pli": 2, "MAE_dummy": 80.0, "MAE_xgboost": 15.0},
            ],
        )
        with self.assertRaisesRegex(ValueError, "pair"):
            day8_mae_pivot_rows(scores[:-1])

    def test_manifest_hashes_cover_ordered_split_and_configuration(self) -> None:
        split = {
            "development_order": [0, 2],
            "folds": [{"train": [0], "validation": [2]}],
        }
        self.assertEqual(canonical_sha256(split), canonical_sha256(split))
        self.assertNotEqual(
            canonical_sha256(split), canonical_sha256({**split, "folds": []})
        )
        self.assertNotEqual(
            canonical_sha256({"features": ["Id", "Area"]}),
            canonical_sha256({"features": ["Area"]}),
        )

    def test_missing_or_wrong_legacy_lock_is_rejected(self) -> None:
        with self.assertRaises(FileNotFoundError):
            require_legacy_lock(self.root / "missing.lock")
        lock = self.root / "uv.lock"
        lock.write_text("wrong lock", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "lock.*SHA-256"):
            require_legacy_lock(lock)

    def test_git_identity_contains_commit_and_dirty_flag(self) -> None:
        identity = collect_git_identity(Path(__file__).resolve().parents[1])
        self.assertRegex(identity["code_commit"], r"^[0-9a-f]{40}$")
        self.assertIsInstance(identity["dirty_tree"], bool)

    def test_installed_version_snapshot_excludes_direct_urls(self) -> None:
        packages = installed_packages()
        self.assertTrue(packages)
        self.assertTrue(
            all(
                isinstance(name, str) and isinstance(version, str)
                for name, version in packages.items()
            )
        )
        self.assertTrue(
            all("@" not in value and "://" not in value for value in packages.values())
        )

    @staticmethod
    def populate_staged_run(staging: Path) -> None:
        files = {
            "cv_scores.csv": "model,mae\nDummy,1\n",
            "metrics.csv": "model,mae\nDummy,1\n",
            "day8_mae_pivot.csv": "pli,MAE_dummy,MAE_xgboost\n1,1,1\n",
            "dev_fold_predictions.csv": "row,actual,predicted\n0,1,1\n",
            "split_membership.json": "{}\n",
            "replay_config.json": "{}\n",
            "feature_policy.json": "{}\n",
            "environment_packages.json": "{}\n",
        }
        for name, content in files.items():
            (staging / name).write_text(content, encoding="utf-8")
        run = ReplayRun(
            data=None,
            scores=(),
            predictions=(),
            split={},
            policy={},
            config={},
            packages={},
            context={
                "code_commit": "a" * 40,
                "dirty_tree": True,
                "script_sha256": "b" * 64,
                "legacy_uv_lock_sha256": "c" * 64,
                "checkpoint_identity": None,
                "checkpoint_persisted": False,
                "command": ["python", "replay.py"],
                "duration_seconds": 1.0,
            },
            started_clock=0.0,
        )
        manifest = build_replay_manifest(staging, "fixture", run)
        (staging / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    def test_staged_artifacts_are_not_published_until_complete(self) -> None:
        target = self.root / "replay"
        staging = prepare_staging(target)
        self.assertFalse(target.exists())
        self.assertEqual(
            (staging / "status.json").read_text(encoding="utf-8"),
            '{"status":"incomplete"}\n',
        )
        self.populate_staged_run(staging)
        manifest = json.loads((staging / "manifest.json").read_text(encoding="utf-8"))
        self.assertIn("environment_packages_sha256", manifest)
        self.assertIn("configuration_sha256", manifest)
        self.assertEqual(manifest["checkpoint_identity"], None)
        promote_staging(staging, target)
        self.assertTrue((target / "manifest.json").exists())
        self.assertFalse(staging.exists())
        with self.assertRaisesRegex(ValueError, "exists"):
            prepare_staging(target)

    def test_promotion_rejects_missing_and_modified_artifacts(self) -> None:
        for mutation in ("missing", "modified"):
            with self.subTest(mutation=mutation):
                target = self.root / mutation
                staging = prepare_staging(target)
                self.populate_staged_run(staging)
                if mutation == "missing":
                    (staging / "dev_fold_predictions.csv").unlink()
                else:
                    (staging / "cv_scores.csv").write_text("modified", encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "missing|checksum"):
                    promote_staging(staging, target)
                self.assertFalse(target.exists())
                self.assertIn(
                    "incomplete", (staging / "status.json").read_text(encoding="utf-8")
                )

    def test_promotion_rejects_incomplete_manifest(self) -> None:
        target = self.root / "bad-manifest"
        staging = prepare_staging(target)
        self.populate_staged_run(staging)
        manifest = json.loads((staging / "manifest.json").read_text(encoding="utf-8"))
        manifest["status"] = "incomplete"
        (staging / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "complete"):
            promote_staging(staging, target)
        self.assertFalse(target.exists())

    def test_unfinished_staging_has_no_valid_final_output(self) -> None:
        target = self.root / "failed-replay"
        staging = prepare_staging(target)
        (staging / "cv_scores.csv").write_text("partial", encoding="utf-8")
        self.assertFalse(target.exists())
        self.assertEqual(
            (staging / "status.json").read_text(encoding="utf-8"),
            '{"status":"incomplete"}\n',
        )

    def test_rejects_nonfinite_predictions_and_metrics(self) -> None:
        validate_finite_replay_values([100.0, -1.0], field="prediction")
        validate_finite_replay_values([0.2, 1.5], field="metric")
        for invalid in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(value=str(invalid)):
                with self.assertRaisesRegex(ValueError, "prediction.*finite"):
                    validate_finite_replay_values([100.0, invalid], field="prediction")
                with self.assertRaisesRegex(ValueError, "metric.*finite"):
                    validate_finite_replay_values([invalid], field="metric")

    def test_rejects_empty_or_non_numeric_model_output(self) -> None:
        with self.assertRaisesRegex(ValueError, "prediction.*empty"):
            validate_finite_replay_values([], field="prediction")
        with self.assertRaisesRegex(ValueError, "prediction.*finite"):
            validate_finite_replay_values(["bad"], field="prediction")

    def test_runtime_identity_recheck_rejects_script_or_package_change(self) -> None:
        script = self.root / "replay.py"
        script.write_text("original", encoding="utf-8")
        expected_hash = digest(script)
        project_root = Path(__file__).resolve().parents[1]
        identity = collect_git_identity(project_root)
        packages = installed_packages()
        target = self.root / "identity-run"
        staging = prepare_staging(target)
        verify_replay_identity(script, project_root, identity, expected_hash, packages)
        script.write_text("changed", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "script.*changed"):
            verify_replay_identity(
                script, project_root, identity, expected_hash, packages
            )
        script.write_text("original", encoding="utf-8")
        with (
            patch(
                "scripts.replay_legacy_ames_dev.installed_packages",
                return_value={"changed": "9"},
            ),
            self.assertRaisesRegex(ValueError, "packages.*changed"),
        ):
            verify_replay_identity(
                script, project_root, identity, expected_hash, packages
            )
        self.assertFalse(target.exists())
        self.assertIn(
            "incomplete", (staging / "status.json").read_text(encoding="utf-8")
        )


if __name__ == "__main__":
    unittest.main()
