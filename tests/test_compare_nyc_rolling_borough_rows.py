"""Synthetic run and recovery tests for the frozen NYC source comparison."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import BytesIO, StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import compare_nyc_rolling_borough_rows as runner  # noqa: E402


class RowConcordanceRunnerTest(unittest.TestCase):
    def setUp(self):
        self.original_preflight = runner._preflight
        self.original_aggregate = runner._aggregate
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "data" / "raw" / "nyc_dof"
        self.root.mkdir(parents=True)
        self.output = self.root / "row-concordance-v1-20260930T123100Z-000000000002"
        self.lock = self.root / "lock.json"
        self.lock.write_text("{}", encoding="utf-8")
        self.inputs = {
            "capture_manifest_sha256": "a" * 64,
            "csv_snapshot_sha256": "b" * 64,
            "v3_result_sha256": "c" * 64,
        }
        self.private = {
            "protocol": "nyc-dof-same-publisher-row-concordance-v1",
            "capture_manifest_sha256": "a" * 64,
            "csv_snapshot_sha256": "b" * 64,
            "v3_result_sha256": "c" * 64,
            "csv_source_rows": 82345,
            "excluded_manhattan_csv_rows": 19553,
            "csv_frame_rows": 62792,
            "xlsx_frame_rows": 62792,
            "boroughs": [],
            "label_status": "unqualified",
            "sale_labels_certified": 0,
        }
        patchers = [
            patch.object(runner, "PRIVATE_ROOT", self.root),
            patch.object(runner, "ENVIRONMENT_LOCK", self.lock),
            patch.object(runner, "verify_acl"),
            patch.object(runner, "secure_directory"),
            patch.object(runner, "_preflight", return_value=self.inputs),
            patch.object(runner, "_aggregate", return_value=self.private),
            patch.object(
                runner,
                "_provenance",
                return_value={"code_commit": "d" * 40, "dirty_tree": False},
            ),
        ]
        for item in patchers:
            item.start()
            self.addCleanup(item.stop)

    def test_private_public_replay_and_no_overwrite(self):
        public = runner.compare_sources(self.output)
        self.assertEqual(public["sale_labels_certified"], 0)
        self.assertEqual(public["label_status"], "unqualified")
        self.assertNotIn("ledger", (self.output / "public.json").read_text())
        self.assertEqual(runner.replay(self.output), public)
        with self.assertRaises(FileExistsError):
            runner.compare_sources(self.output)

    def test_missing_lock_does_not_reserve_run(self):
        self.lock.unlink()
        with self.assertRaisesRegex(ValueError, "environment lock"):
            runner.compare_sources(self.output)
        self.assertFalse(self.output.exists())

    def test_dirty_code_does_not_reserve_run(self):
        with patch.object(
            runner,
            "_provenance",
            return_value={"code_commit": "d" * 40, "dirty_tree": True},
        ):
            with self.assertRaises(ValueError):
                runner.compare_sources(self.output)
        self.assertFalse(self.output.exists())

    def test_failure_after_reservation_is_incomplete(self):
        with patch.object(runner, "_aggregate", side_effect=TimeoutError("PRIVATE")):
            with self.assertRaises(TimeoutError):
                runner.compare_sources(self.output)
        failure = json.loads((self.output / "failure.json").read_bytes())
        self.assertEqual(failure["status"], "incomplete")
        self.assertNotIn("PRIVATE", str(failure))
        self.assertFalse((self.output / "public.json").exists())
        with self.assertRaises(ValueError):
            runner.replay(self.output)

    def test_replay_detects_lock_and_public_drift(self):
        runner.compare_sources(self.output)
        self.lock.write_text('{"changed":true}', encoding="utf-8")
        with self.assertRaises(ValueError):
            runner.replay(self.output)
        self.lock.write_text("{}", encoding="utf-8")
        path = self.output / "public.json"
        public = json.loads(path.read_bytes())
        public["sale_labels_certified"] = 1
        path.write_bytes(runner._json_bytes(public))
        with self.assertRaises(ValueError):
            runner.replay(self.output)

    def test_replay_detects_implementation_drift(self):
        runner.compare_sources(self.output)
        with patch.object(runner, "_code_hashes", return_value={"changed": "0" * 64}):
            with self.assertRaises(ValueError):
                runner.replay(self.output)

    def test_plan_and_run_path_guards(self):
        with patch.object(runner, "_preflight", side_effect=AssertionError):
            self.assertEqual(runner.plan()["status"], "plan_only_no_row_read")
        with self.assertRaises(ValueError):
            runner._run_dir(self.root / "wrong-name", new=True)
        with self.assertRaises(ValueError):
            runner._run_dir(self.output, new=False)
        with (
            patch.object(sys, "argv", ["runner", "plan"]),
            redirect_stdout(StringIO()) as output,
        ):
            runner.main()
        self.assertEqual(json.loads(output.getvalue())["label_status"], "unqualified")

    def test_checked_scan_rejects_same_handle_content_change(self):
        source = self.root / "synthetic.csv"
        source.write_bytes(b"ORIGINAL")
        digest = runner._sha(b"ORIGINAL")

        with patch.object(
            runner.earlier,
            "_hash_handle",
            side_effect=[
                None,
                ValueError("Inspection input differs from captured bytes"),
            ],
        ) as check:
            with self.assertRaisesRegex(ValueError, "captured bytes"):
                runner._checked_scan(
                    source, 8, digest, lambda handle: "discarded", lambda: 0.0, 0.0
                )
        self.assertEqual(check.call_count, 2)

    def test_checked_scan_rejects_handle_metadata_change_during_scan(self):
        source = self.root / "synthetic.csv"
        source.write_bytes(b"ORIGINAL")
        digest = runner._sha(b"ORIGINAL")
        original_fstat = runner.os.fstat
        calls = 0

        def changed_after(fd):
            nonlocal calls
            calls += 1
            status = original_fstat(fd)
            if calls == 1:
                return status
            return SimpleNamespace(
                st_dev=status.st_dev,
                st_ino=status.st_ino,
                st_nlink=status.st_nlink + 1,
                st_size=status.st_size,
            )

        with patch.object(runner.os, "fstat", side_effect=changed_after):
            with self.assertRaisesRegex(ValueError, "changed during parsing"):
                runner._checked_scan(
                    source, 8, digest, lambda handle: "discarded", lambda: 0.0, 0.0
                )

    def test_csv_rows_keeps_only_requested_borough_and_checks_full_counts(self):
        expected = {"1": 1, "2": 2, "3": 1, "4": 1, "5": 1, "unknown": 1}
        rows = [("1",), ("2",), ("2",), ("3",), ("4",), ("5",), ("?",)]

        def scan(handle, count, receive, **kwargs):
            self.assertEqual(count, 7)
            for ordinal, values in enumerate(rows, 1):
                receive(ordinal, values)

        def checked(path, size, digest, operation, timer, start):
            self.assertEqual(path, self.root / "tiny.csv")
            self.assertEqual((size, digest), (7, "d" * 64))
            return operation(BytesIO())

        inputs = {
            "csv_manifest": {
                "raw_filename": "tiny.csv",
                "rows": 7,
                "bytes": 7,
                "sha256": "d" * 64,
            }
        }
        with (
            patch.object(runner, "CSV_COUNTS", expected),
            patch.object(runner.scanner, "scan_pinned_csv", side_effect=scan),
            patch.object(runner, "_checked_scan", side_effect=checked),
        ):
            self.assertEqual(
                runner._csv_rows(inputs, "2", lambda: 0.0, 0.0),
                [(2, ("2",)), (3, ("2",))],
            )
            rows.pop()
            with self.assertRaisesRegex(ValueError, "borough counts"):
                runner._csv_rows(inputs, "2", lambda: 0.0, 0.0)

    def test_xlsx_rows_uses_pinned_entry_and_preserves_source_ordinals(self):
        inputs = {
            "borough_entries": {
                "Bronx": {"filename": "tiny.xlsx", "bytes": 9, "sha256": "e" * 64}
            }
        }

        def scan(handle, code, receive, **kwargs):
            self.assertEqual(code, "2")
            receive(6, ("2", "unit"))
            receive(9, ("2", "another"))
            return {"rows": 2, "physical_rows": 9}

        def checked(path, size, digest, operation, timer, start):
            self.assertEqual(path, runner.CAPTURE_DIR / "tiny.xlsx")
            self.assertEqual((size, digest), (9, "e" * 64))
            return operation(BytesIO())

        with (
            patch.object(runner, "_checked_scan", side_effect=checked),
            patch.object(runner.scanner, "scan_qualified_workbook", side_effect=scan),
        ):
            self.assertEqual(
                runner._xlsx_rows(inputs, "Bronx", "2", lambda: 0.0, 0.0),
                [(6, ("2", "unit")), (9, ("2", "another"))],
            )

    def test_aggregate_rejects_any_frame_size_mismatch_before_comparison(self):
        with (
            patch.object(runner, "SELECTED", (("Bronx", "2", 2),)),
            patch.object(runner, "_csv_rows", return_value=[(1, ("2",))]),
            patch.object(runner, "_xlsx_rows", return_value=[(6, ("2",))] * 2),
            patch.object(runner.core, "compare_borough") as compare,
        ):
            with self.assertRaisesRegex(ValueError, "row count"):
                self.original_aggregate(self.inputs, lambda: 0.0, 0.0)
            compare.assert_not_called()

    def test_aggregate_accounts_for_selected_frames_and_keeps_labels_unqualified(self):
        selected = (("Bronx", "2", 2), ("Queens", "4", 3))

        def xlsx_rows(inputs, borough, code, timer, start):
            count = dict((name, rows) for name, _, rows in selected)[borough]
            return [(ordinal, (code,)) for ordinal in range(1, count + 1)]

        def csv_rows(inputs, code, timer, start):
            count = dict((code, rows) for _, code, rows in selected)[code]
            return [(ordinal, (code,)) for ordinal in range(1, count + 1)]

        def compare(csv, xlsx, **kwargs):
            return {"csv_rows": len(csv), "xlsx_rows": len(xlsx), **kwargs}

        with (
            patch.object(runner, "SELECTED", selected),
            patch.object(runner, "_csv_rows", side_effect=csv_rows),
            patch.object(runner, "_xlsx_rows", side_effect=xlsx_rows),
            patch.object(runner.core, "compare_borough", side_effect=compare),
        ):
            result = self.original_aggregate(self.inputs, lambda: 0.0, 0.0)
        self.assertEqual((result["csv_frame_rows"], result["xlsx_frame_rows"]), (5, 5))
        self.assertEqual(
            [item["borough"] for item in result["boroughs"]], ["Bronx", "Queens"]
        )
        self.assertEqual(result["sale_labels_certified"], 0)
        self.assertEqual(result["label_status"], "unqualified")

    def test_aggregate_core_integration_suppresses_small_public_cell(self):
        values = [""] * 21
        values[0], values[4], values[5] = "2", "0012", "003"
        values[8], values[18] = "PRIVATE ADDRESS", "A1"
        values[19], values[20] = "750000", "09/15/2025"
        row = tuple(values)
        with (
            patch.object(runner, "SELECTED", (("Bronx", "2", 1),)),
            patch.object(runner, "_csv_rows", return_value=[(1, row)]),
            patch.object(runner, "_xlsx_rows", return_value=[(6, row)]),
        ):
            private = self.original_aggregate(self.inputs, lambda: 0.0, 0.0)
        self.assertEqual(private["boroughs"][0]["counts"]["unique_key_pairs"], 1)
        self.assertEqual(
            private["boroughs"][0]["counts"]["exact_full_row_multiset_matches"], 1
        )
        public = runner._public_projection(private)
        self.assertIsNone(public["boroughs"][0]["counts"])
        self.assertEqual(
            public["boroughs"][0]["suppression_reason"], "small_positive_cell_1_to_4"
        )
        self.assertNotIn("PRIVATE ADDRESS", json.dumps(public))
        self.assertEqual(public["sale_labels_certified"], 0)

    def test_preflight_checks_pinned_manifest_counts_and_cross_source_hashes(self):
        snapshot = self.root / "snapshot.json"
        snapshot.write_bytes(b"synthetic snapshot")
        source = self.root / "capture"
        source.mkdir()
        capture_body = b"synthetic capture"
        entries = [
            {"borough": name, "sha256": code * 64} for name, code, _ in runner.SELECTED
        ]
        entries.append({"borough": "Manhattan", "sha256": "1" * 64})
        status = {item["borough"]: {"sha256": item["sha256"]} for item in entries}
        csv_manifest = {"rows": 82345, "sha256": "f" * 64}
        with (
            patch.object(runner, "SNAPSHOT_MANIFEST", snapshot),
            patch.object(
                runner, "SNAPSHOT_MANIFEST_SHA", runner._sha(snapshot.read_bytes())
            ),
            patch.object(runner, "CAPTURE_MANIFEST_SHA", runner._sha(capture_body)),
            patch.object(runner.profile, "_manifest_bytes", return_value=csv_manifest),
            patch.object(runner.capture, "_run_directory", return_value=source),
            patch.object(runner.capture, "_load_json", return_value=({}, capture_body)),
            patch.object(runner.earlier, "_expected_files", return_value=entries),
            patch.object(runner, "_verify_v3", return_value=status),
        ):
            self.assertEqual(
                self.original_preflight()["borough_entries"]["Bronx"], entries[0]
            )
            csv_manifest["rows"] = 82344
            with self.assertRaisesRegex(ValueError, "CSV row count"):
                self.original_preflight()
            csv_manifest["rows"] = 82345
            status["Bronx"]["sha256"] = "0" * 64
            with self.assertRaisesRegex(ValueError, "workbook hashes"):
                self.original_preflight()

    def test_replay_rejects_dirty_intent_even_if_hash_manifest_is_recomputed(self):
        runner.compare_sources(self.output)
        intent_path = self.output / "intent.json"
        intent = json.loads(intent_path.read_bytes())
        intent["dirty_tree"] = True
        intent_bytes = runner._json_bytes(intent)
        intent_path.write_bytes(intent_bytes)
        private_bytes = (self.output / "result.json").read_bytes()
        public_bytes = (self.output / "public.json").read_bytes()
        hashes = runner._hash_manifest(
            self.output, intent_bytes, private_bytes, public_bytes
        )
        (self.output / "hash_manifest.json").write_bytes(runner._json_bytes(hashes))
        with self.assertRaisesRegex(ValueError, "intent"):
            runner.replay(self.output)

    def test_keyboard_interrupt_after_intent_leaves_incomplete_artifact(self):
        with patch.object(runner, "_aggregate", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                runner.compare_sources(self.output)
        failure = json.loads((self.output / "failure.json").read_bytes())
        self.assertEqual(failure["status"], "incomplete")
        self.assertEqual(failure["category"], "interrupted")
        self.assertFalse((self.output / "public.json").exists())

    def test_partial_private_write_cannot_publish_result(self):
        original_new_file = runner.new_file
        private_bytes = runner._json_bytes(self.private)

        def interrupted_write(path, content):
            if content == private_bytes:
                path.write_bytes(content[:5])
                raise OSError("synthetic private write interruption")
            return original_new_file(path, content)

        with (
            patch.object(runner, "new_file", side_effect=interrupted_write),
            self.assertRaises(OSError),
        ):
            runner.compare_sources(self.output)
        self.assertFalse((self.output / "result.json").exists())
        self.assertFalse((self.output / "public.json").exists())
        failure = json.loads((self.output / "failure.json").read_bytes())
        self.assertEqual(failure["status"], "incomplete")

    def test_preflight_rejects_oversized_snapshot_without_unbounded_read(self):
        snapshot = self.root / "snapshot-oversized.json"
        with snapshot.open("wb") as handle:
            handle.truncate(runner.profile.MAX_MANIFEST_BYTES + 1)
        with (
            patch.object(runner, "SNAPSHOT_MANIFEST", snapshot),
            patch.object(
                Path,
                "read_bytes",
                side_effect=AssertionError("unbounded read was attempted"),
            ),
            self.assertRaisesRegex(ValueError, "manifest exceeds"),
        ):
            self.original_preflight()

    def test_v3_rejects_oversized_artifact_without_unbounded_read(self):
        v3 = self.root / "synthetic-v3"
        v3.mkdir()
        artifact_hashes = {name: "a" * 64 for name in runner.V3_ARTIFACT_SHA}
        for name in artifact_hashes:
            path = v3 / name
            with path.open("wb") as handle:
                handle.truncate(runner.earlier.MAX_JSON_BYTES + 1)
        with (
            patch.object(runner, "V3_DIR", v3),
            patch.object(runner, "V3_ARTIFACT_SHA", artifact_hashes),
            patch.object(
                Path,
                "read_bytes",
                side_effect=AssertionError("unbounded read was attempted"),
            ),
            self.assertRaisesRegex(ValueError, "artifact exceeds"),
        ):
            runner._verify_v3()

    def test_public_projection_excludes_private_ledger_and_source_values(self):
        private = {
            **self.private,
            "boroughs": [{"ledger": [{"address": "PRIVATE HOME"}]}],
            "untrusted_extra": "PRIVATE HOME",
        }
        with patch.object(
            runner.core,
            "public_projection",
            return_value={"borough": "Bronx", "counts": None},
        ):
            public = runner._public_projection(private)
        self.assertEqual(public["boroughs"], [{"borough": "Bronx", "counts": None}])
        self.assertNotIn("PRIVATE HOME", json.dumps(public))
        self.assertNotIn("ledger", json.dumps(public))
        self.assertEqual(public["sale_labels_certified"], 0)

    def test_replay_rejects_missing_and_noncanonical_artifacts(self):
        runner.compare_sources(self.output)
        result_path = self.output / "result.json"
        original = result_path.read_bytes()
        result_path.unlink()
        with self.assertRaises(ValueError):
            runner.replay(self.output)
        result_path.write_bytes(original + b" ")
        with self.assertRaisesRegex(ValueError, "not canonical"):
            runner.replay(self.output)
        result_path.write_bytes(b"{")
        with self.assertRaisesRegex(ValueError, "invalid JSON"):
            runner.replay(self.output)

    def test_cli_compare_and_replay_failures_do_not_print_private_error(self):
        for command in ("compare", "replay"):
            with (
                self.subTest(command=command),
                patch.object(sys, "argv", ["runner", command, str(self.output)]),
                patch.object(
                    runner,
                    "compare_sources" if command == "compare" else "replay",
                    side_effect=ValueError("PRIVATE HOME"),
                ),
                redirect_stdout(StringIO()) as output,
                patch("sys.stderr", new_callable=StringIO) as errors,
                self.assertRaises(SystemExit) as exited,
            ):
                runner.main()
            self.assertEqual(exited.exception.code, 2)
            self.assertNotIn("PRIVATE HOME", output.getvalue() + errors.getvalue())


if __name__ == "__main__":
    unittest.main()
