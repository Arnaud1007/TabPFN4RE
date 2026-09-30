"""Synthetic run and replay tests for NYC v3 worksheet qualification."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from hashlib import sha256
from io import StringIO
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import capture_nyc_dof_borough_exports as capture  # noqa: E402
import inspect_nyc_dof_borough_exports as earlier  # noqa: E402
import inspect_nyc_dof_borough_exports_v3 as runner  # noqa: E402
import nyc_workbook_xml_v3 as parser  # noqa: E402

from tests.test_nyc_workbook_xml import TEST_PIN  # noqa: E402
from tests.test_nyc_workbook_xml_v3 import workbook  # noqa: E402


class V3RunnerTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "data" / "raw" / "nyc_dof"
        self.root.mkdir(parents=True)
        self.source = self.root / "official-exports-20260929T123000Z-000000000001"
        self.source.mkdir()
        self.output = (
            self.root / "worksheet-inspection-v3-20260929T123100Z-000000000002"
        )
        self.body = workbook()
        self.files = []
        for borough, url in capture.BOROUGHS:
            name = capture._filename(borough)
            (self.source / name).write_bytes(self.body)
            self.files.append(
                {
                    "borough": borough,
                    "url": url,
                    "filename": name,
                    "bytes": len(self.body),
                    "sha256": sha256(self.body).hexdigest(),
                }
            )
        manifest = {
            "protocol": capture.PROTOCOL,
            "run_id": self.source.name,
            "files": self.files,
        }
        body = capture._json_bytes(manifest)
        (self.source / "manifest.json").write_bytes(body)
        patchers = [
            patch.object(runner, "PRIVATE_ROOT", self.root),
            patch.object(earlier, "PRIVATE_ROOT", self.root),
            patch.object(capture, "PRIVATE_ROOT", self.root),
            patch.object(earlier, "CAPTURE_MANIFEST_SHA256", sha256(body).hexdigest()),
            patch.object(
                capture,
                "replay",
                return_value={"manifest_sha256": sha256(body).hexdigest()},
            ),
            patch.object(runner, "verify_acl"),
            patch.object(earlier, "verify_acl"),
            patch.object(runner, "secure_directory"),
            patch.object(
                runner,
                "inspect_workbook",
                side_effect=lambda handle, **kw: parser._inspect_with_pin(
                    handle, TEST_PIN, **kw
                ),
            ),
        ]
        for item in patchers:
            item.start()
            self.addCleanup(item.stop)

    def test_private_public_replay_and_no_label_admission(self):
        public = runner.inspect_capture(self.source, self.output)
        self.assertEqual(public["worksheet_qualified_count"], 5)
        self.assertEqual(public["label_status"], "unqualified")
        self.assertEqual(public["sale_labels_certified"], 0)
        self.assertEqual(len(public["files"]), 5)
        private = json.loads((self.output / "result.json").read_bytes())
        self.assertEqual(
            private["files"][0]["header_lineage"]["source_name"], "EASEMENT"
        )
        self.assertNotIn("header_lineage", (self.output / "public.json").read_text())
        self.assertEqual(runner.replay(self.source, self.output), public)
        self.assertNotIn(
            "PRIVATE_SALE_ADDRESS", (self.output / "public.json").read_text()
        )
        self.assertNotIn("987654321", (self.output / "public.json").read_text())
        with self.assertRaises(FileExistsError):
            runner.inspect_capture(self.source, self.output)

    def test_wrong_header_is_unqualified_without_private_row_leak(self):
        from tests.test_nyc_workbook_xml_v3 import RAW_HEADER  # noqa: PLC0415

        wrong = (*RAW_HEADER[:6], "WRONG", *RAW_HEADER[7:])
        changed = workbook(header=wrong)
        for entry in self.files:
            (self.source / entry["filename"]).write_bytes(changed)
            entry["bytes"] = len(changed)
            entry["sha256"] = sha256(changed).hexdigest()
        self._refresh_manifest()
        public = runner.inspect_capture(self.source, self.output)
        self.assertEqual(public["worksheet_qualified_count"], 0)
        self.assertEqual(public["sale_labels_certified"], 0)
        self.assertNotIn("WRONG", (self.output / "public.json").read_text())

    def _refresh_manifest(self):
        manifest = {
            "protocol": capture.PROTOCOL,
            "run_id": self.source.name,
            "files": self.files,
        }
        body = capture._json_bytes(manifest)
        (self.source / "manifest.json").write_bytes(body)
        for item in (
            patch.object(earlier, "CAPTURE_MANIFEST_SHA256", sha256(body).hexdigest()),
            patch.object(
                capture,
                "replay",
                return_value={"manifest_sha256": sha256(body).hexdigest()},
            ),
        ):
            item.start()
            self.addCleanup(item.stop)

    def test_input_hash_change_creates_no_valid_aggregate(self):
        path = self.source / self.files[0]["filename"]
        path.write_bytes(self.body + b"tampered")
        with self.assertRaises(ValueError):
            runner.inspect_capture(self.source, self.output)
        self.assertFalse((self.output / "public.json").exists())

    def test_intent_lock_hash_and_missing_lock_before_run_reservation(self):
        runner.inspect_capture(self.source, self.output)
        intent = json.loads((self.output / "intent.json").read_bytes())
        expected = sha256(runner.ENVIRONMENT_LOCK.read_bytes()).hexdigest()
        self.assertEqual(intent["environment_lock_sha256"], expected)
        missing = self.root / "worksheet-inspection-v3-20260929T123200Z-000000000003"
        with patch.object(runner, "ENVIRONMENT_LOCK", self.root / "absent.json"):
            with self.assertRaises(FileNotFoundError):
                runner.inspect_capture(self.source, missing)
        self.assertFalse(missing.exists())

    def test_replay_detects_tampered_public_projection(self):
        runner.inspect_capture(self.source, self.output)
        path = self.output / "public.json"
        public = json.loads(path.read_bytes())
        public["sale_labels_certified"] = 1
        path.write_bytes(earlier._json_bytes(public))
        with self.assertRaises(ValueError):
            runner.replay(self.source, self.output)

    def test_replay_rejects_environment_lock_drift(self):
        runner.inspect_capture(self.source, self.output)
        changed_lock = self.root / "changed-lock.json"
        changed_lock.write_text("{}")
        with patch.object(runner, "ENVIRONMENT_LOCK", changed_lock):
            with self.assertRaises(ValueError):
                runner.replay(self.source, self.output)

    def test_intent_write_failure_records_incomplete_run(self):
        original = runner.new_file

        def fail_intent(path, body):
            if path.name == "intent.json":
                raise OSError("private failure")
            return original(path, body)

        with patch.object(runner, "new_file", side_effect=fail_intent):
            with self.assertRaises(OSError):
                runner.inspect_capture(self.source, self.output)
        failure = json.loads((self.output / "failure.json").read_bytes())
        self.assertEqual(failure["status"], "incomplete")

    def test_rejected_package_is_counted_without_raw_content(self):
        changed = b"PRIVATE_ADDRESS_BAD_ZIP"
        for entry in self.files:
            (self.source / entry["filename"]).write_bytes(changed)
            entry["bytes"] = len(changed)
            entry["sha256"] = sha256(changed).hexdigest()
        self._refresh_manifest()
        public = runner.inspect_capture(self.source, self.output)
        self.assertEqual(public["worksheet_qualified_count"], 0)
        self.assertTrue(
            all(file["status"] == "rejected_structure" for file in public["files"])
        )
        self.assertNotIn("PRIVATE_ADDRESS", (self.output / "public.json").read_text())
        self.assertEqual(runner.replay(self.source, self.output), public)

    def test_timeout_leaves_incomplete_run_and_replay_rejects(self):
        with patch.object(
            runner, "inspect_workbook", side_effect=TimeoutError("PRIVATE_DETAILS")
        ):
            with self.assertRaises(TimeoutError):
                runner.inspect_capture(self.source, self.output)
        failure = json.loads((self.output / "failure.json").read_bytes())
        self.assertEqual(failure["status"], "incomplete")
        self.assertEqual(failure["category"], "timeout")
        self.assertNotIn("PRIVATE_DETAILS", str(failure))
        self.assertFalse((self.output / "public.json").exists())
        with self.assertRaises(ValueError):
            runner.replay(self.source, self.output)

    def test_postparse_mutation_rejects_complete_aggregate(self):
        original = parser._inspect_with_pin
        path = self.source / self.files[0]["filename"]

        def mutate(handle, **kw):
            result = original(handle, TEST_PIN, **kw)
            if handle.name == str(path):
                with path.open("ab") as writer:
                    writer.write(b"changed")
            return result

        with patch.object(runner, "inspect_workbook", side_effect=mutate):
            with self.assertRaises(ValueError):
                runner.inspect_capture(self.source, self.output)
        self.assertFalse((self.output / "public.json").exists())
        self.assertEqual(
            json.loads((self.output / "failure.json").read_bytes())["status"],
            "incomplete",
        )

    def test_plan_cli_and_path_guards(self):
        self.assertEqual(runner.plan()["status"], "plan_only_no_workbook_open")
        command = [sys.executable, str(Path(runner.__file__)), "plan"]
        completed = subprocess.run(command, capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(completed.stdout)["label_status"], "unqualified")
        with self.assertRaises(ValueError):
            runner._run_dir(self.root / "wrong-name", new=True)
        with self.assertRaises(ValueError):
            runner._run_dir(self.output, new=False)

    def test_hash_manifest_tamper_rejected_on_replay(self):
        runner.inspect_capture(self.source, self.output)
        path = self.output / "hash_manifest.json"
        hashes = json.loads(path.read_bytes())
        hashes["public_sha256"] = "0" * 64
        path.write_bytes(earlier._json_bytes(hashes))
        with self.assertRaises(ValueError):
            runner.replay(self.source, self.output)

    def test_cli_dispatch_and_safe_failure_message(self):
        commands = (
            (["plan"], "plan"),
            (["inspect", str(self.source), str(self.output)], "inspect_capture"),
            (["replay", str(self.source), str(self.output)], "replay"),
        )
        for args, function in commands:
            with (
                self.subTest(function=function),
                patch.object(sys, "argv", ["inspector", *args]),
                patch.object(runner, function, return_value={"status": "safe"}),
                redirect_stdout(StringIO()) as output,
            ):
                runner.main()
                self.assertEqual(json.loads(output.getvalue())["status"], "safe")
        with (
            patch.object(
                sys,
                "argv",
                ["inspector", "inspect", str(self.source), str(self.output)],
            ),
            patch.object(
                runner, "inspect_capture", side_effect=ValueError("PRIVATE_SALE_DATA")
            ),
            redirect_stderr(StringIO()) as errors,
            self.assertRaises(SystemExit) as caught,
        ):
            runner.main()
        self.assertEqual(caught.exception.code, 2)
        self.assertNotIn("PRIVATE_SALE_DATA", errors.getvalue())


if __name__ == "__main__":
    unittest.main()
