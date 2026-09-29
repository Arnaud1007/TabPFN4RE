"""Synthetic capture and private-output tests for borough inspection."""

from __future__ import annotations

from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import capture_nyc_dof_borough_exports as capture  # noqa: E402
import inspect_nyc_dof_borough_exports as inspection  # noqa: E402
import nyc_workbook_xml as xml  # noqa: E402
from tests.test_nyc_workbook_xml import TEST_PIN, synthetic_xlsx  # noqa: E402


class InspectorTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / "data" / "raw" / "nyc_dof"
        self.root.mkdir(parents=True)
        self.capture_dir = self.root / "official-exports-20260929T123000Z-000000000001"
        self.capture_dir.mkdir()
        self.output_dir = (
            self.root / "worksheet-inspection-20260929T123100Z-000000000002"
        )
        self.body = synthetic_xlsx()
        self.files = []
        for borough, url in capture.BOROUGHS:
            name = capture._filename(borough)
            (self.capture_dir / name).write_bytes(self.body)
            self.files.append(
                {
                    "borough": borough,
                    "url": url,
                    "filename": name,
                    "bytes": len(self.body),
                    "sha256": sha256(self.body).hexdigest(),
                }
            )
        self.manifest = {
            "protocol": capture.PROTOCOL,
            "run_id": self.capture_dir.name,
            "files": self.files,
        }
        self.manifest_bytes = capture._json_bytes(self.manifest)
        (self.capture_dir / "manifest.json").write_bytes(self.manifest_bytes)
        patchers = [
            patch.object(inspection, "PRIVATE_ROOT", self.root),
            patch.object(capture, "PRIVATE_ROOT", self.root),
            patch.object(
                inspection,
                "CAPTURE_MANIFEST_SHA256",
                sha256(self.manifest_bytes).hexdigest(),
            ),
            patch.object(
                capture,
                "replay",
                return_value={
                    "manifest_sha256": sha256(self.manifest_bytes).hexdigest()
                },
            ),
            patch.object(inspection, "verify_acl"),
            patch.object(inspection, "secure_directory"),
            patch.object(
                inspection,
                "inspect_workbook",
                side_effect=lambda handle, **kwargs: xml._inspect_workbook_with_pin(
                    handle, TEST_PIN, **kwargs
                ),
            ),
        ]
        for item in patchers:
            item.start()
            self.addCleanup(item.stop)

    def test_inspect_and_offline_replay(self):
        result = inspection.inspect_capture(self.capture_dir, self.output_dir)
        self.assertEqual(result["qualified_borough_count"], 5)
        self.assertEqual(result["files"][0]["status"], "qualified")
        with (
            patch.object(
                socket, "create_connection", side_effect=AssertionError("offline only")
            ),
            patch.object(
                inspection, "inspect_workbook", wraps=inspection.inspect_workbook
            ) as parser,
        ):
            self.assertEqual(
                inspection.replay(self.capture_dir, self.output_dir), result
            )
            self.assertEqual(parser.call_count, 5)
        self.assertTrue((self.output_dir / "intent.json").is_file())
        self.assertTrue((self.output_dir / "result.json").is_file())
        hashes = json.loads((self.output_dir / "hash_manifest.json").read_text())
        self.assertEqual(
            hashes["result_sha256"],
            sha256((self.output_dir / "result.json").read_bytes()).hexdigest(),
        )
        with self.assertRaises(FileExistsError):
            inspection.inspect_capture(self.capture_dir, self.output_dir)

    def test_public_result_redacts_cell_values(self):
        result = inspection.inspect_capture(self.capture_dir, self.output_dir)
        text = json.dumps(result)
        for value in ("SALE PRICE", "SALE DATE", "09/15/2025", "ADDRESS"):
            self.assertNotIn(value, text)
        self.assertIn("sha256", text)

    def test_wrong_hash_fails_without_result(self):
        self.files[0]["sha256"] = "0" * 64
        self.manifest["files"] = self.files
        body = capture._json_bytes(self.manifest)
        (self.capture_dir / "manifest.json").write_bytes(body)
        with (
            patch.object(
                inspection, "CAPTURE_MANIFEST_SHA256", sha256(body).hexdigest()
            ),
            patch.object(
                capture,
                "replay",
                return_value={"manifest_sha256": sha256(body).hexdigest()},
            ),
        ):
            with self.assertRaises(ValueError):
                inspection.inspect_capture(self.capture_dir, self.output_dir)
        self.assertFalse((self.output_dir / "result.json").exists())

    def test_acl_failure_prevents_open(self):
        with patch.object(inspection, "verify_acl", side_effect=ValueError("ACL")):
            with self.assertRaises(ValueError):
                inspection.inspect_capture(self.capture_dir, self.output_dir)
        self.assertFalse(self.output_dir.exists())

    def test_reparse_path_and_hardlink_rejected(self):
        path = self.capture_dir / self.files[0]["filename"]
        other = self.root / "other.xlsx"
        other.write_bytes(self.body)
        original = inspection._reparse
        with patch.object(
            inspection,
            "_reparse",
            side_effect=lambda candidate: candidate == path or original(candidate),
        ):
            with self.assertRaises(ValueError):
                inspection.inspect_capture(self.capture_dir, self.output_dir)
        path.unlink()
        os.link(other, path)
        with self.assertRaises(ValueError):
            inspection.inspect_capture(
                self.capture_dir,
                self.root / "worksheet-inspection-20260929T123200Z-000000000003",
            )

    def test_plan_is_offline_and_names_no_rows(self):
        result = inspection.plan()
        self.assertEqual(result["protocol"], inspection.PROTOCOL)
        self.assertEqual(result["status"], "plan_only_no_workbook_open")
        self.assertNotIn("SALE PRICE", str(result))

    def test_post_read_mutation_fails_and_replay_detects_change(self):
        original = inspection.inspect_workbook

        def change(handle, **kwargs):
            outcome = original(handle, **kwargs)
            with open(handle.name, "ab") as writer:
                writer.write(b"mutated")
            return outcome

        with patch.object(inspection, "inspect_workbook", side_effect=change):
            with self.assertRaises(ValueError):
                inspection.inspect_capture(self.capture_dir, self.output_dir)
        self.assertFalse((self.output_dir / "result.json").exists())

    def test_rejected_package_is_safe_and_not_qualified(self):
        path = self.capture_dir / self.files[0]["filename"]
        path.write_bytes(b"PRIVATE_ADDRESS_NOT_A_ZIP")
        self.files[0]["bytes"] = path.stat().st_size
        self.files[0]["sha256"] = sha256(path.read_bytes()).hexdigest()
        body = capture._json_bytes(self.manifest)
        (self.capture_dir / "manifest.json").write_bytes(body)
        with (
            patch.object(
                inspection, "CAPTURE_MANIFEST_SHA256", sha256(body).hexdigest()
            ),
            patch.object(
                capture,
                "replay",
                return_value={"manifest_sha256": sha256(body).hexdigest()},
            ),
        ):
            outcome = inspection.inspect_capture(self.capture_dir, self.output_dir)
        self.assertEqual(outcome["qualified_borough_count"], 4)
        self.assertEqual(outcome["files"][0]["status"], "rejected_package")
        self.assertNotIn("PRIVATE_ADDRESS", str(outcome))

    def test_parser_mapping_is_not_mutated(self):
        parser_result = {"qualified": False, "status": "rejected_package"}
        with patch.object(inspection, "inspect_workbook", return_value=parser_result):
            outcome = inspection.inspect_capture(self.capture_dir, self.output_dir)
        self.assertEqual(
            parser_result, {"qualified": False, "status": "rejected_package"}
        )
        self.assertTrue(
            all(item["status"] == "rejected_package" for item in outcome["files"])
        )

    def test_replay_recomputes_and_rejects_tampered_result(self):
        inspection.inspect_capture(self.capture_dir, self.output_dir)
        result_path = self.output_dir / "result.json"
        content = json.loads(result_path.read_text())
        content["qualified_borough_count"] = 0
        result_path.write_bytes(inspection._json_bytes(content))
        with self.assertRaises(ValueError):
            inspection.replay(self.capture_dir, self.output_dir)

    def test_replay_rejects_tampered_hash_manifest(self):
        inspection.inspect_capture(self.capture_dir, self.output_dir)
        path = self.output_dir / "hash_manifest.json"
        hashes = json.loads(path.read_text())
        hashes["result_sha256"] = "0" * 64
        path.write_bytes(inspection._json_bytes(hashes))
        with self.assertRaises(ValueError):
            inspection.replay(self.capture_dir, self.output_dir)

    def test_timeout_leaves_incomplete_artifact_and_replay_rejects(self):
        with patch.object(
            inspection, "inspect_workbook", side_effect=TimeoutError("synthetic")
        ):
            with self.assertRaises(TimeoutError):
                inspection.inspect_capture(self.capture_dir, self.output_dir)
        self.assertFalse((self.output_dir / "result.json").exists())
        self.assertEqual(
            json.loads((self.output_dir / "failure.json").read_text())["category"],
            "timeout",
        )
        with self.assertRaises(ValueError):
            inspection.replay(self.capture_dir, self.output_dir)

    def test_failure_artifact_write_error_is_attached_safely(self):
        original_write = inspection.new_file

        def fail_failure_write(path, content):
            if path.name == "failure.json":
                raise OSError("PRIVATE_PATH_DO_NOT_LEAK")
            return original_write(path, content)

        with (
            patch.object(
                inspection, "inspect_workbook", side_effect=TimeoutError("synthetic")
            ),
            patch.object(inspection, "new_file", side_effect=fail_failure_write),
        ):
            with self.assertRaises(TimeoutError) as caught:
                inspection.inspect_capture(self.capture_dir, self.output_dir)
        notes = getattr(caught.exception, "__notes__", [])
        self.assertTrue(any("OSError" in note for note in notes))
        self.assertNotIn("PRIVATE_PATH_DO_NOT_LEAK", str(notes))

    def test_private_intent_tamper_and_invalid_json_rejected(self):
        inspection.inspect_capture(self.capture_dir, self.output_dir)
        path = self.output_dir / "intent.json"
        intent = json.loads(path.read_text())
        intent["capture_run_id"] = "wrong"
        path.write_bytes(inspection._json_bytes(intent))
        with self.assertRaises(ValueError):
            inspection.replay(self.capture_dir, self.output_dir)
        path.write_text("not-json", encoding="utf-8")
        with self.assertRaises(ValueError):
            inspection.replay(self.capture_dir, self.output_dir)
        path.write_text('{"valid": true}', encoding="utf-8")
        with self.assertRaises(ValueError):
            inspection.replay(self.capture_dir, self.output_dir)

    def test_bad_inspection_paths_and_file_metadata(self):
        with self.assertRaises(ValueError):
            inspection._inspection_dir(self.root / "wrong-name", new=True)
        with self.assertRaises(ValueError):
            inspection._inspection_dir(
                self.root / "worksheet-inspection-20261329T123100Z-000000000002",
                new=True,
            )
        with self.assertRaises(ValueError):
            inspection._inspection_dir(self.output_dir, new=False)
        with self.assertRaises(ValueError):
            inspection._expected_files({"files": []})
        bad = [dict(item) for item in self.files]
        bad[0]["borough"] = "wrong"
        with self.assertRaises(ValueError):
            inspection._expected_files({"files": bad})
        bad[0] = dict(self.files[0], bytes="wrong")
        with self.assertRaises(ValueError):
            inspection._expected_files({"files": bad})

    def test_capture_manifest_hash_or_identity_mismatch_fails(self):
        with patch.object(inspection, "CAPTURE_MANIFEST_SHA256", "0" * 64):
            with self.assertRaises(ValueError):
                inspection.inspect_capture(self.capture_dir, self.output_dir)
        self.assertFalse(self.output_dir.exists())
        manifest = dict(self.manifest, protocol="wrong")
        body = capture._json_bytes(manifest)
        (self.capture_dir / "manifest.json").write_bytes(body)
        with (
            patch.object(
                inspection, "CAPTURE_MANIFEST_SHA256", sha256(body).hexdigest()
            ),
            patch.object(
                capture,
                "replay",
                return_value={"manifest_sha256": sha256(body).hexdigest()},
            ),
        ):
            with self.assertRaises(ValueError):
                inspection.inspect_capture(self.capture_dir, self.output_dir)

    def test_cli_plan_without_opening_workbook(self):
        command = [sys.executable, str(Path(inspection.__file__)), "plan"]
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        self.assertEqual(
            json.loads(result.stdout)["status"], "plan_only_no_workbook_open"
        )

    def test_production_parser_and_cli_offer_no_pin_override(self):
        with patch.dict(os.environ, {"TABPFN_PRINTER_SHA256": TEST_PIN[1]}):
            with self.assertRaises(ValueError):
                xml.inspect_workbook(BytesIO(self.body), timer=lambda: 0.0, start=0.0)
        with self.assertRaises(TypeError):
            inspection.inspect_capture(
                self.capture_dir, self.output_dir, printer_pin=TEST_PIN
            )
        command = [
            sys.executable,
            str(Path(inspection.__file__)),
            "plan",
            "--printer-pin",
            TEST_PIN[1],
        ]
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)


if __name__ == "__main__":
    unittest.main()
