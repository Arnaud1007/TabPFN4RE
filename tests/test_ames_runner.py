"""Behavioral contract for the non-certifying Ames engineering smoke run."""

import csv
import hashlib
import json
from pathlib import Path
import subprocess
import statistics
import sys
import tempfile
import unittest
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from tabpfn4realestate.ames_smoke import run_smoke  # noqa: E402
from tabpfn4realestate import ames_smoke  # noqa: E402
from tabpfn4realestate import ames as ames_module  # noqa: E402
from tabpfn4realestate.ames import Split  # noqa: E402


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class AmesRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.work_dir = Path(temporary.name)
        self.source = self.write_source(240)
        self.output_dir = self.work_dir / "runs"

    def write_source(
        self, count: int, *, schema: str | None = None, padded_ids: bool = False
    ) -> Path:
        path = self.work_dir / f"ames_{count}.arff"
        header = schema or (
            "@RELATION house_prices\n"
            "@ATTRIBUTE Id NUMERIC\n"
            "@ATTRIBUTE GrLivArea NUMERIC\n"
            "@ATTRIBUTE SalePrice NUMERIC\n"
            "@DATA\n"
        )
        records = "".join(
            f"{' ' + str(identifier) + ' ' if padded_ids else identifier},"
            f"{1000 + identifier},{100000 + identifier * 1000}\n"
            for identifier in range(1, count + 1)
        )
        path.write_bytes((header + records).encode("utf-8"))
        return path

    def run_fixture(self, *, seed: int = 42) -> Path:
        return run_smoke(
            self.source,
            self.output_dir,
            expected_sha256=sha256(self.source),
            sample_size=200,
            seed=seed,
        )

    def completed_manifests(self) -> list[Path]:
        manifests = self.output_dir.rglob("manifest.json") if self.output_dir.exists() else ()
        return [
            path
            for path in manifests
            if json.loads(path.read_text(encoding="utf-8")).get("status") == "complete"
        ]

    def test_run_persists_auditable_non_certifying_split_and_predictions(self) -> None:
        run_dir = self.run_fixture()

        self.assertIsInstance(run_dir, Path)
        self.assertEqual(run_dir.parent, self.output_dir)
        split_path = run_dir / "split.json"
        predictions_path = run_dir / "predictions.csv"
        metrics_path = run_dir / "metrics.json"
        manifest_path = run_dir / "manifest.json"
        self.assertTrue(all(path.is_file() for path in (
            split_path, predictions_path, metrics_path, manifest_path
        )))

        split = json.loads(split_path.read_text(encoding="utf-8"))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
        with predictions_path.open(encoding="utf-8", newline="") as stream:
            predictions = list(csv.DictReader(stream))

        development = set(split["development_ids"])
        reserved = set(split["reserved_ids"])
        self.assertEqual(split["protocol_id"], "ames_engineering_v1")
        self.assertEqual((len(development), len(reserved)), (160, 40))
        self.assertFalse(development & reserved)
        self.assertEqual(len(development | reserved), 200)
        self.assertEqual(len(predictions), 40)
        self.assertEqual({row["Id"] for row in predictions}, reserved)
        self.assertTrue({"Id", "actual", "predicted"}.issubset(predictions[0]))

        # The baseline must never include reserved labels in its fitted median.
        expected_median = statistics.median(100000 + int(identifier) * 1000
                                            for identifier in development)
        self.assertTrue(all(float(row["predicted"]) == expected_median
                            for row in predictions))
        for row in predictions:
            self.assertEqual(float(row["actual"]), 100000 + int(row["Id"]) * 1000)
        expected_mdape = statistics.median(
            abs((float(row["predicted"]) - float(row["actual"])) / float(row["actual"]))
            for row in predictions
        )
        self.assertEqual(metrics["count"], 40)
        self.assertAlmostEqual(metrics["mdape"], expected_mdape)

        self.assertEqual(manifest["status"], "complete")
        self.assertEqual(manifest["protocol_id"], "ames_engineering_v1")
        self.assertIs(manifest["certification_eligible"], False)
        self.assertEqual(manifest["source_identity"], "unverified_fixture")
        self.assertEqual(manifest["run_id"], run_dir.name)
        self.assertEqual(manifest["source_sha256"], sha256(self.source))
        self.assertEqual(manifest["split_sha256"], sha256(split_path))
        self.assertRegex(manifest["config_sha256"], r"^[0-9a-f]{64}$")
        self.assertRegex(manifest["feature_policy_sha256"], r"^[0-9a-f]{64}$")
        self.assertEqual(manifest["checkpoint_identity"], "median_baseline_v1")
        self.assertIn("code_commit", manifest)
        self.assertIsInstance(manifest["dirty_tree"], bool)

        policy = PROJECT_ROOT / "policies" / "ames-smoke.json"
        if policy.is_file():
            self.assertEqual(manifest["feature_policy_sha256"], sha256(policy))
        lock = PROJECT_ROOT / "locks" / "ames-smoke-environment.json"
        self.assertIn("environment_lock_sha256", manifest)
        if lock.is_file():
            self.assertEqual(manifest["environment_lock_sha256"], sha256(lock))
        else:
            self.assertIsNone(manifest["environment_lock_sha256"])

    def test_identical_runs_are_reproducible_but_never_overwrite_each_other(self) -> None:
        first = self.run_fixture()
        second = self.run_fixture()

        self.assertNotEqual(first, second)
        self.assertEqual((first / "split.json").read_bytes(),
                         (second / "split.json").read_bytes())
        self.assertEqual((first / "predictions.csv").read_bytes(),
                         (second / "predictions.csv").read_bytes())
        first_manifest = json.loads((first / "manifest.json").read_text(encoding="utf-8"))
        second_manifest = json.loads((second / "manifest.json").read_text(encoding="utf-8"))
        self.assertNotEqual(first_manifest["run_id"], second_manifest["run_id"])
        self.assertEqual(first_manifest["config_sha256"], second_manifest["config_sha256"])
        self.assertEqual(first_manifest["split_sha256"], second_manifest["split_sha256"])

    def test_hash_mismatch_fails_without_completed_run(self) -> None:
        with self.assertRaisesRegex(ValueError, "hash|SHA|checksum"):
            run_smoke(self.source, self.output_dir, expected_sha256="0" * 64)

        self.assertEqual(self.completed_manifests(), [])

    def test_invalid_source_schema_fails_without_completed_run(self) -> None:
        invalid = self.write_source(
            240,
            schema=(
                "@RELATION house_prices\n"
                "@ATTRIBUTE Id NUMERIC\n"
                "@ATTRIBUTE GrLivArea NUMERIC\n"
                "@ATTRIBUTE OtherPrice NUMERIC\n"
                "@DATA\n"
            ),
        )
        with self.assertRaisesRegex(ValueError, "SalePrice"):
            run_smoke(invalid, self.output_dir, expected_sha256=sha256(invalid))

        self.assertEqual(self.completed_manifests(), [])

    def test_too_small_source_fails_without_completed_run(self) -> None:
        small_source = self.write_source(199)

        with self.assertRaisesRegex(ValueError, "sample|row|200"):
            run_smoke(small_source, self.output_dir, expected_sha256=sha256(small_source))

        self.assertEqual(self.completed_manifests(), [])

    def test_padded_ids_produce_one_prediction_per_reserved_id(self) -> None:
        self.source = self.write_source(240, padded_ids=True)

        run_dir = self.run_fixture()

        split = json.loads((run_dir / "split.json").read_text(encoding="utf-8"))
        with (run_dir / "predictions.csv").open(encoding="utf-8", newline="") as stream:
            predictions = list(csv.DictReader(stream))
        reserved_ids = set(split["reserved_ids"])
        self.assertEqual(len(predictions), 40)
        self.assertEqual({row["Id"] for row in predictions}, reserved_ids)
        self.assertEqual(len(reserved_ids), len(predictions))

    def test_split_partition_mismatch_fails_without_completed_run(self) -> None:
        original_split = ames_smoke.engineering_split

        def mismatched_split(rows: object, *, seed: int) -> Split:
            actual = original_split(rows, seed=seed)
            return Split(
                actual.development_ids,
                (*actual.reserved_ids[:-1], "999999"),
                actual.protocol_id,
            )

        with patch.object(ames_smoke, "engineering_split", side_effect=mismatched_split):
            with self.assertRaisesRegex(ValueError, "partition|split|Id|membership"):
                self.run_fixture()

        self.assertEqual(self.completed_manifests(), [])

    def test_explicit_project_root_supplies_lock_and_policy(self) -> None:
        project_root = self.work_dir / "installed_project"
        lock = project_root / "locks" / "ames-smoke-environment.json"
        policy = project_root / "policies" / "ames-smoke.json"
        lock.parent.mkdir(parents=True)
        policy.parent.mkdir(parents=True)
        for source, destination in (
            (PROJECT_ROOT / "locks" / lock.name, lock),
            (PROJECT_ROOT / "policies" / policy.name, policy),
        ):
            content = json.loads(source.read_text(encoding="utf-8"))
            content["test_instance"] = "isolated_project_root"
            destination.write_text(json.dumps(content), encoding="utf-8")

        run_dir = run_smoke(
            self.source,
            self.output_dir,
            expected_sha256=sha256(self.source),
            project_root=project_root,
        )

        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["environment_lock_sha256"], sha256(lock))
        self.assertEqual(manifest["feature_policy_sha256"], sha256(policy))
        self.assertEqual((run_dir / "environment.lock.json").read_bytes(), lock.read_bytes())
        self.assertEqual((run_dir / "feature_policy.json").read_bytes(), policy.read_bytes())

    def test_dirty_tree_is_explicitly_not_replayable(self) -> None:
        with patch.object(ames_smoke, "_git_state", return_value=("a" * 40, True)):
            run_dir = self.run_fixture()

        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        self.assertIs(manifest["dirty_tree"], True)
        self.assertIs(manifest["replayable"], False)

    def test_git_state_ignores_untracked_runs_but_detects_tracked_code_change(self) -> None:
        repository = self.work_dir / "fixture_repo"
        repository.mkdir()

        def git(*args: str) -> None:
            subprocess.run(
                ["git", "-C", str(repository), *args],
                check=True, capture_output=True, text=True,
            )

        git("init", "-q")
        code = repository / "src" / "ames_smoke.py"
        code.parent.mkdir()
        code.write_text("BASELINE = 1\n", encoding="utf-8")
        git("add", "src/ames_smoke.py")
        git(
            "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
            "commit", "-q", "-m", "base",
        )

        run_artifact = repository / "runs" / "u0-fixture" / "manifest.json"
        run_artifact.parent.mkdir(parents=True)
        run_artifact.write_text('{"status":"complete"}', encoding="utf-8")
        commit, dirty = ames_smoke._git_state(repository)
        self.assertRegex(commit or "", r"^[0-9a-f]{40}$")
        self.assertIs(dirty, False)

        code.write_text("BASELINE = 2\n", encoding="utf-8")
        changed_commit, changed_dirty = ames_smoke._git_state(repository)
        self.assertEqual(changed_commit, commit)
        self.assertIs(changed_dirty, True)

    def test_unrelated_clean_project_cannot_attest_executed_module_commit(self) -> None:
        project_root = self.work_dir / "unrelated_project"
        lock = project_root / "locks" / "ames-smoke-environment.json"
        policy = project_root / "policies" / "ames-smoke.json"
        lock.parent.mkdir(parents=True)
        policy.parent.mkdir(parents=True)
        lock.write_bytes((PROJECT_ROOT / "locks" / lock.name).read_bytes())
        policy.write_bytes((PROJECT_ROOT / "policies" / policy.name).read_bytes())
        expected_modules = {
            "tabpfn4realestate.ames": sha256(Path(ames_module.__file__)),
            "tabpfn4realestate.ames_smoke": sha256(Path(ames_smoke.__file__)),
        }

        with patch.object(ames_smoke, "_git_state", return_value=("a" * 40, False)):
            run_dir = run_smoke(
                self.source,
                self.output_dir,
                expected_sha256=sha256(self.source),
                project_root=project_root,
            )

        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["executed_module_sha256"], expected_modules)
        self.assertIsNone(manifest["code_commit"])
        self.assertIs(manifest["replayable"], False)

    def test_source_change_after_load_cannot_complete_run(self) -> None:
        original_load = ames_smoke.load_ames_arff

        def change_source_after_load(path: Path, **kwargs: object) -> list[dict[str, str]]:
            rows = original_load(path, **kwargs)
            path.write_bytes(path.read_bytes() + b"\n% changed after verified load\n")
            return rows

        with patch.object(ames_smoke, "load_ames_arff", side_effect=change_source_after_load):
            with self.assertRaises((ValueError, RuntimeError)):
                self.run_fixture()

        self.assertEqual(self.completed_manifests(), [])

    def test_rename_error_cannot_leave_a_complete_manifest_anywhere(self) -> None:
        original_rename = Path.rename

        def move_then_report_failure(staging: Path, final: Path) -> None:
            # A failed finalisation can be ambiguous: the move may already have
            # happened when the caller observes an error.
            original_rename(staging, final)
            raise OSError("injected final rename failure")

        with patch.object(Path, "rename", autospec=True, side_effect=move_then_report_failure):
            with self.assertRaises(OSError):
                self.run_fixture()

        self.assertEqual(self.completed_manifests(), [])


if __name__ == "__main__":
    unittest.main()
