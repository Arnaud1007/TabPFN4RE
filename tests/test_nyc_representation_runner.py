"""Synthetic run, provenance, privacy, and recovery checks for NYC v2."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import diagnose_nyc_representations_v2 as runner  # noqa: E402


class RepresentationRunnerTest(unittest.TestCase):
    def setUp(self):
        self.original_preflight = runner._preflight
        self.original_aggregate = runner._aggregate
        self.original_public_projection = runner._public_projection
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "data" / "raw" / "nyc_dof"
        self.root.mkdir(parents=True)
        self.output = (
            self.root / "representation-diagnostic-v2-20260930T140000Z-000000000001"
        )
        self.lock = self.root / "environment-lock.json"
        self.lock.write_text("{}", encoding="utf-8")
        self.inputs = {
            "capture_manifest_sha256": "a" * 64,
            "csv_snapshot_sha256": "b" * 64,
            "v3_result_sha256": "c" * 64,
            "v1_result_sha256": "d" * 64,
        }
        self.private = {
            "protocol": runner.PROTOCOL,
            **self.inputs,
            "csv_source_rows": 82345,
            "excluded_manhattan_csv_rows": 19553,
            "csv_frame_rows": 62792,
            "xlsx_frame_rows": 62792,
            "boroughs": [],
            "label_status": "unqualified",
            "sale_labels_certified": 0,
        }
        self.public = {
            "protocol": runner.PROTOCOL,
            **self.inputs,
            "csv_source_rows": 82345,
            "excluded_manhattan_csv_rows": 19553,
            "csv_frame_rows": 62792,
            "xlsx_frame_rows": 62792,
            "boroughs": [],
            "label_status": "unqualified",
            "sale_labels_certified": 0,
        }
        for patched in (
            patch.object(runner, "PRIVATE_ROOT", self.root),
            patch.object(runner, "ENVIRONMENT_LOCK", self.lock),
            patch.object(runner, "verify_acl"),
            patch.object(runner, "secure_directory"),
            patch.object(runner, "_preflight", return_value=self.inputs),
            patch.object(runner, "_aggregate", return_value=self.private),
            patch.object(runner, "_public_projection", return_value=self.public),
            patch.object(
                runner,
                "_provenance",
                return_value={"code_commit": "e" * 40, "dirty_tree": False},
            ),
        ):
            patched.start()
            self.addCleanup(patched.stop)

    def test_plan_is_safe_metadata_only(self):
        with patch.object(runner, "_preflight", side_effect=AssertionError("row read")):
            plan = runner.plan()
        self.assertEqual(plan["protocol"], runner.PROTOCOL)
        self.assertEqual(plan["expected_rows_per_source"], 62792)
        self.assertEqual(
            plan["expected_boroughs"],
            ["Bronx", "Brooklyn", "Queens", "Staten Island"],
        )
        self.assertEqual(plan["label_status"], "unqualified")
        self.assertEqual(plan["status"], "plan_only_no_row_read")

    def test_clean_tree_and_lock_are_required_before_reserving_run(self):
        self.lock.unlink()
        with self.assertRaises(ValueError):
            runner.compare_sources(self.output)
        self.assertFalse(self.output.exists())
        self.lock.write_text("{}", encoding="utf-8")
        with patch.object(
            runner,
            "_provenance",
            return_value={"code_commit": "e" * 40, "dirty_tree": True},
        ):
            with self.assertRaises(ValueError):
                runner.compare_sources(self.output)
        self.assertFalse(self.output.exists())

    def test_intent_is_persisted_before_first_row_scan(self):
        def scan_after_intent(*args, **kwargs):
            intent = json.loads((self.output / "intent.json").read_bytes())
            self.assertEqual(intent["protocol"], runner.PROTOCOL)
            self.assertFalse(intent["dirty_tree"])
            self.assertEqual(intent["code_commit"], "e" * 40)
            return self.private

        with patch.object(runner, "_aggregate", side_effect=scan_after_intent):
            runner.compare_sources(self.output)

    def test_compare_replay_and_create_only(self):
        self.assertEqual(runner.compare_sources(self.output), self.public)
        self.assertEqual(runner.replay(self.output), self.public)
        self.assertEqual(
            json.loads((self.output / "hash_manifest.json").read_bytes())["protocol"],
            runner.PROTOCOL,
        )
        with self.assertRaises(FileExistsError):
            runner.compare_sources(self.output)

    def test_failure_or_interruption_after_intent_stays_incomplete(self):
        for index, (error, category) in enumerate(
            (
                (TimeoutError("PRIVATE ADDRESS"), "timeout"),
                (KeyboardInterrupt(), "interrupted"),
            ),
            1,
        ):
            with self.subTest(category=category):
                output = self.output.with_name(
                    f"representation-diagnostic-v2-20260930T140000Z-{index:012x}"
                )
                with patch.object(runner, "_aggregate", side_effect=error):
                    with self.assertRaises(type(error)):
                        runner.compare_sources(output)
                failure = json.loads((output / "failure.json").read_bytes())
                self.assertEqual(failure["status"], "incomplete")
                self.assertEqual(failure["category"], category)
                self.assertNotIn("PRIVATE ADDRESS", str(failure))
                self.assertFalse((output / "public.json").exists())
                with self.assertRaises(ValueError):
                    runner.replay(output)

    def test_atomic_publication_leaves_no_partial_result(self):
        original_new_file = runner.v1.new_file
        private_bytes = runner._json_bytes(self.private)

        def interrupted_write(path: Path, content: bytes):
            if content == private_bytes:
                path.write_bytes(content[:7])
                raise OSError("synthetic private write interruption")
            return original_new_file(path, content)

        with patch.object(runner.v1, "new_file", side_effect=interrupted_write):
            with self.assertRaises(OSError):
                runner.compare_sources(self.output)
        self.assertFalse((self.output / "result.json").exists())
        self.assertFalse((self.output / "public.json").exists())
        self.assertFalse(
            any(path.name.startswith(".") for path in self.output.iterdir())
        )
        self.assertEqual(
            json.loads((self.output / "failure.json").read_bytes())["status"],
            "incomplete",
        )

    def test_replay_rejects_lock_code_and_saved_artifact_drift(self):
        runner.compare_sources(self.output)
        self.lock.write_text('{"changed":true}', encoding="utf-8")
        with self.assertRaises(ValueError):
            runner.replay(self.output)
        self.lock.write_text("{}", encoding="utf-8")
        with patch.object(runner, "_code_hashes", return_value={"changed": "0" * 64}):
            with self.assertRaises(ValueError):
                runner.replay(self.output)
        path = self.output / "public.json"
        path.write_bytes(path.read_bytes() + b" ")
        with self.assertRaises(ValueError):
            runner.replay(self.output)

    def test_replay_rejects_recomputed_manifest_for_dirty_intent(self):
        runner.compare_sources(self.output)
        intent_path = self.output / "intent.json"
        intent = json.loads(intent_path.read_bytes())
        intent["dirty_tree"] = True
        intent_bytes = runner._json_bytes(intent)
        intent_path.write_bytes(intent_bytes)
        private_bytes = (self.output / "result.json").read_bytes()
        public_bytes = (self.output / "public.json").read_bytes()
        manifest = runner._hash_manifest(
            self.output, intent_bytes, private_bytes, public_bytes
        )
        (self.output / "hash_manifest.json").write_bytes(runner._json_bytes(manifest))
        with self.assertRaises(ValueError):
            runner.replay(self.output)

    def test_public_projection_is_allowlisted_and_never_pools_borough_counts(self):
        private = {
            **self.private,
            "boroughs": [
                {"borough": "Bronx", "ledger": [{"address": "PRIVATE HOME"}]},
                {
                    "borough": "Staten Island",
                    "ledger": [{"price": "PRIVATE PRICE"}],
                },
            ],
            "secret": "PRIVATE HOME",
            "pooled_counts": {"private_small_cell": 1},
        }

        def redacted(borough):
            return {
                "borough": borough["borough"],
                "counts": None,
                "suppression_reason": "small_positive_cell_1_to_4"
                if borough["borough"] == "Bronx"
                else "cross_version_staten_island",
                "label_status": "unqualified",
                "sale_labels_certified": 0,
            }

        with patch.object(runner.core, "public_projection", side_effect=redacted):
            public = self.original_public_projection(private)
        serialized = json.dumps(public)
        self.assertEqual(len(public["boroughs"]), 2)
        self.assertIsNone(public["boroughs"][1]["counts"])
        self.assertNotIn("PRIVATE", serialized)
        self.assertNotIn("ledger", serialized)
        self.assertNotIn("pooled_counts", serialized)
        self.assertEqual(public["sale_labels_certified"], 0)

    def test_pinned_sources_and_four_borough_scope_are_fixed(self):
        self.assertEqual(runner.PROTOCOL, "nyc-dof-representation-diagnostic-v2")
        self.assertIn("scripts/nyc_representation_parsing.py", runner._code_hashes())
        self.assertEqual(
            tuple(item[0] for item in runner.SELECTED),
            ("Bronx", "Brooklyn", "Queens", "Staten Island"),
        )
        self.assertEqual(sum(item[2] for item in runner.SELECTED), 62792)
        self.assertEqual(
            runner.V1_ARTIFACT_SHA["result.json"],
            "5fd432e081911ff47df78bf183a40df99da00077d0e666175ca79840f18451ee",
        )

    @staticmethod
    def _one_row() -> tuple[int, tuple[str, ...]]:
        values = [""] * 21
        values[0] = "2"
        values[4] = "0012"
        values[5] = "003"
        values[8] = "SYNTHETIC STREET"
        values[18] = "A1"
        values[19] = "750000"
        values[20] = "09/15/2025"
        return 6, tuple(values)

    def test_aggregate_reconciles_k0_against_frozen_v1_counts(self):
        row = self._one_row()
        v1_counts = runner.v1.core.compare_borough(
            [row], [row], borough="Bronx", borough_code="2"
        )["counts"]
        inputs = {
            **self.inputs,
            "v1_counts": {"Bronx": v1_counts},
            "v3_status": {"Bronx": {"date_system": "1900_default"}},
        }
        with (
            patch.object(runner, "SELECTED", (("Bronx", "2", 1),)),
            patch.object(runner.v1, "_csv_rows", return_value=[row]),
            patch.object(runner.v1, "_xlsx_rows", return_value=[row]),
        ):
            result = self.original_aggregate(inputs, lambda: 0.0, 0.0)
        self.assertEqual(result["csv_frame_rows"], 1)
        self.assertEqual(result["xlsx_frame_rows"], 1)
        self.assertEqual(result["boroughs"][0]["borough"], "Bronx")
        self.assertEqual(result["sale_labels_certified"], 0)

    def test_aggregate_fails_closed_on_k0_drift(self):
        row = self._one_row()
        v1_counts = runner.v1.core.compare_borough(
            [row], [row], borough="Bronx", borough_code="2"
        )["counts"]
        incompatible = {**v1_counts, "unique_key_pairs": 0}
        inputs = {
            **self.inputs,
            "v1_counts": {"Bronx": incompatible},
            "v3_status": {"Bronx": {"date_system": "1900_default"}},
        }
        with (
            patch.object(runner, "SELECTED", (("Bronx", "2", 1),)),
            patch.object(runner.v1, "_csv_rows", return_value=[row]),
            patch.object(runner.v1, "_xlsx_rows", return_value=[row]),
            self.assertRaisesRegex(ValueError, "K0"),
        ):
            self.original_aggregate(inputs, lambda: 0.0, 0.0)

    def test_aggregate_rejects_non_key_frozen_v1_metric_drift(self):
        row = self._one_row()
        v1_counts = runner.v1.core.compare_borough(
            [row], [row], borough="Bronx", borough_code="2"
        )["counts"]
        incompatible = {
            **v1_counts,
            "exact_full_row_multiset_matches": 0,
            "csv_full_row_multiset_residual_rows": 1,
            "xlsx_full_row_multiset_residual_rows": 1,
        }
        self.assertEqual(
            incompatible["unique_key_pairs"], v1_counts["unique_key_pairs"]
        )
        inputs = {
            **self.inputs,
            "v1_counts": {"Bronx": incompatible},
            "v3_status": {"Bronx": {"date_system": "1900_default"}},
        }
        with (
            patch.object(runner, "SELECTED", (("Bronx", "2", 1),)),
            patch.object(runner.v1, "_csv_rows", return_value=[row]),
            patch.object(runner.v1, "_xlsx_rows", return_value=[row]),
            self.assertRaisesRegex(ValueError, "Full K0"),
        ):
            self.original_aggregate(inputs, lambda: 0.0, 0.0)

    def test_aggregate_rejects_frame_mismatch_before_core_analysis(self):
        row = self._one_row()
        inputs = {
            **self.inputs,
            "v1_counts": {"Bronx": {}},
            "v3_status": {"Bronx": {"date_system": "1900_default"}},
        }
        with (
            patch.object(runner, "SELECTED", (("Bronx", "2", 2),)),
            patch.object(runner.v1, "_csv_rows", return_value=[row]),
            patch.object(runner.v1, "_xlsx_rows", return_value=[row]),
            patch.object(runner.core, "analyze_borough") as analyze,
        ):
            with self.assertRaisesRegex(ValueError, "row count"):
                self.original_aggregate(inputs, lambda: 0.0, 0.0)
        analyze.assert_not_called()

    def test_preflight_rejects_non_1900_date_system_without_rows(self):
        v3_status = {
            borough: {"date_system": "1900_default"}
            for borough, _, _ in runner.SELECTED
        }
        v3_status["Bronx"]["date_system"] = "1904"
        with (
            patch.object(runner.v1, "_preflight", return_value=self.inputs),
            patch.object(runner, "_verify_v1", return_value={}),
            patch.object(runner, "_verify_v3", return_value=v3_status),
            self.assertRaisesRegex(ValueError, "date system"),
        ):
            self.original_preflight()

    def _synthetic_v1_artifacts(
        self,
        *,
        code_commit: str | None = None,
        boroughs: list[dict] | None = None,
        result_hash_override: str | None = None,
        directory_name: str = "synthetic-v1-evidence",
    ) -> tuple[Path, dict, dict]:
        directory = self.root / directory_name
        directory.mkdir()
        boroughs = (
            boroughs
            if boroughs is not None
            else [
                {"borough": name, "counts": {"synthetic": index}}
                for index, (name, _, _) in enumerate(runner.SELECTED)
            ]
        )
        documents = {
            "intent.json": {
                "protocol": runner.v1.PROTOCOL,
                "run_id": directory.name,
                "code_commit": code_commit or runner.V1_CODE_COMMIT,
                "dirty_tree": False,
            },
            "result.json": {
                "protocol": runner.v1.PROTOCOL,
                "sale_labels_certified": 0,
                "csv_frame_rows": 62792,
                "xlsx_frame_rows": 62792,
                "boroughs": boroughs,
            },
            "public.json": {"status": "synthetic_public_projection"},
        }
        bodies = {name: runner._json_bytes(value) for name, value in documents.items()}
        documents["hash_manifest.json"] = {
            "intent_sha256": runner._sha(bodies["intent.json"]),
            "result_sha256": result_hash_override or runner._sha(bodies["result.json"]),
            "public_sha256": runner._sha(bodies["public.json"]),
        }
        bodies["hash_manifest.json"] = runner._json_bytes(
            documents["hash_manifest.json"]
        )
        for name, body in bodies.items():
            (directory / name).write_bytes(body)
        hashes = {name: runner._sha(body) for name, body in bodies.items()}
        return directory, hashes, documents["public.json"]

    def test_verify_v1_accepts_pinned_synthetic_evidence(self):
        directory, hashes, public = self._synthetic_v1_artifacts()
        with (
            patch.object(runner, "V1_DIR", directory),
            patch.object(runner, "V1_ARTIFACT_SHA", hashes),
            patch.object(runner.v1, "_public_projection", return_value=public),
        ):
            counts = runner._verify_v1()
        self.assertEqual(set(counts), {name for name, _, _ in runner.SELECTED})
        self.assertEqual(counts["Bronx"], {"synthetic": 0})

    def test_verify_v1_rejects_inventory_and_hash_tamper(self):
        directory, hashes, public = self._synthetic_v1_artifacts()
        with (
            patch.object(runner, "V1_DIR", directory),
            patch.object(runner, "V1_ARTIFACT_SHA", hashes),
            patch.object(runner.v1, "_public_projection", return_value=public),
        ):
            extra = directory / "unregistered.json"
            extra.write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "inventory"):
                runner._verify_v1()
            extra.unlink()
            path = directory / "result.json"
            path.write_bytes(path.read_bytes() + b" ")
            with self.assertRaisesRegex(ValueError, "digest"):
                runner._verify_v1()

    def test_verify_v1_rejects_incompatible_commit_and_borough_scope(self):
        directory, hashes, public = self._synthetic_v1_artifacts(code_commit="0" * 40)
        with (
            patch.object(runner, "V1_DIR", directory),
            patch.object(runner, "V1_ARTIFACT_SHA", hashes),
            patch.object(runner.v1, "_public_projection", return_value=public),
            self.assertRaisesRegex(ValueError, "incompatible"),
        ):
            runner._verify_v1()

        second, second_hashes, second_public = self._synthetic_v1_artifacts(
            boroughs=[{"borough": "Bronx", "counts": {}}],
            directory_name="synthetic-v1-scope-evidence",
        )
        with (
            patch.object(runner, "V1_DIR", second),
            patch.object(runner, "V1_ARTIFACT_SHA", second_hashes),
            patch.object(runner.v1, "_public_projection", return_value=second_public),
            self.assertRaisesRegex(ValueError, "borough inventory"),
        ):
            runner._verify_v1()

    def test_verify_v1_rejects_internal_hash_manifest_tamper(self):
        directory, hashes, public = self._synthetic_v1_artifacts(
            result_hash_override="0" * 64
        )
        with (
            patch.object(runner, "V1_DIR", directory),
            patch.object(runner, "V1_ARTIFACT_SHA", hashes),
            patch.object(runner.v1, "_public_projection", return_value=public),
            self.assertRaisesRegex(ValueError, "incompatible"),
        ):
            runner._verify_v1()

    def test_parse_pinned_rejects_malformed_and_noncanonical_json(self):
        for body, message in ((b"{", "invalid JSON"), (b' {"a":1}', "canonical")):
            with self.subTest(body=body), self.assertRaisesRegex(ValueError, message):
                runner._parse_pinned(body, "synthetic v1")

    def test_cli_errors_do_not_print_private_messages(self):
        for command in ("compare", "replay"):
            with (
                self.subTest(command=command),
                patch.object(sys, "argv", ["runner", command, str(self.output)]),
                patch.object(
                    runner,
                    "compare_sources" if command == "compare" else "replay",
                    side_effect=ValueError("PRIVATE ADDRESS"),
                ),
                redirect_stdout(StringIO()) as output,
                patch("sys.stderr", new_callable=StringIO) as errors,
                self.assertRaises(SystemExit) as exited,
            ):
                runner.main()
            self.assertEqual(exited.exception.code, 2)
            self.assertNotIn("PRIVATE ADDRESS", output.getvalue() + errors.getvalue())


if __name__ == "__main__":
    unittest.main()
