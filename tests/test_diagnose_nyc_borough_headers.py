"""Synthetic capture tests for candidate-only borough header diagnosis."""

from __future__ import annotations

from hashlib import sha256
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
import diagnose_nyc_borough_headers as diagnosis  # noqa: E402
import inspect_nyc_dof_borough_exports as inspection  # noqa: E402
import nyc_header_diagnostic_xml as scanner  # noqa: E402
from tests.test_nyc_workbook_xml import TEST_PIN, cell, synthetic_xlsx  # noqa: E402


class DiagnosisTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "data" / "raw" / "nyc_dof"
        self.root.mkdir(parents=True)
        self.capture_dir = self.root / "official-exports-20260929T123000Z-000000000001"
        self.capture_dir.mkdir()
        self.output = self.root / "header-diagnostic-20260929T123100Z-000000000002"
        self.body = synthetic_xlsx()
        self.files = []
        for borough, url in capture.BOROUGHS:
            filename = capture._filename(borough)
            (self.capture_dir / filename).write_bytes(self.body)
            self.files.append(
                {
                    "borough": borough,
                    "url": url,
                    "filename": filename,
                    "bytes": len(self.body),
                    "sha256": sha256(self.body).hexdigest(),
                }
            )
        manifest = {
            "protocol": capture.PROTOCOL,
            "run_id": self.capture_dir.name,
            "files": self.files,
        }
        body = capture._json_bytes(manifest)
        (self.capture_dir / "manifest.json").write_bytes(body)
        patchers = [
            patch.object(diagnosis, "PRIVATE_ROOT", self.root),
            patch.object(inspection, "PRIVATE_ROOT", self.root),
            patch.object(capture, "PRIVATE_ROOT", self.root),
            patch.object(
                inspection, "CAPTURE_MANIFEST_SHA256", sha256(body).hexdigest()
            ),
            patch.object(
                capture,
                "replay",
                return_value={"manifest_sha256": sha256(body).hexdigest()},
            ),
            patch.object(diagnosis, "verify_acl"),
            patch.object(inspection, "verify_acl"),
            patch.object(diagnosis, "secure_directory"),
            patch.object(
                diagnosis,
                "scan_workbook",
                side_effect=lambda handle, **kw: scanner._scan_with_pin(
                    handle, TEST_PIN, **kw
                ),
            ),
        ]
        for item in patchers:
            item.start()
            self.addCleanup(item.stop)

    def test_private_and_public_canonical_offline_replay(self):
        public = diagnosis.diagnose_capture(self.capture_dir, self.output)
        private = json.loads((self.output / "result.json").read_text())
        self.assertEqual(public["scope"], "candidate_only")
        self.assertEqual(public["qualified_borough_count"], 0)
        self.assertEqual(public["label_status"], "unqualified")
        self.assertEqual(public["files"][0]["status"], "candidate_found")
        self.assertEqual(private["files"][0]["candidate"]["score"], 21)
        self.assertEqual(len(private["files"][0]["candidate"]["cells"]), 21)
        self.assertNotIn("cells", public["files"][0]["candidate"])
        self.assertEqual(
            (self.output / "public.json").read_bytes(), inspection._json_bytes(public)
        )
        with patch.object(
            socket, "create_connection", side_effect=AssertionError("network")
        ):
            self.assertEqual(diagnosis.replay(self.capture_dir, self.output), public)
        with self.assertRaises(FileExistsError):
            diagnosis.diagnose_capture(self.capture_dir, self.output)

    def test_intent_hashes_the_diagnostic_environment_lock(self):
        diagnosis.diagnose_capture(self.capture_dir, self.output)
        intent = json.loads((self.output / "intent.json").read_bytes())
        lock = (
            inspection.PROJECT_ROOT / "locks" / "nyc-header-diagnostic-environment.json"
        )
        self.assertEqual(
            intent["environment_lock_sha256"], sha256(lock.read_bytes()).hexdigest()
        )
        self.assertEqual(
            intent["worksheet_inspection_environment_lock_sha256"],
            sha256(inspection.ENVIRONMENT_LOCK.read_bytes()).hexdigest(),
        )

    def test_missing_diagnostic_lock_does_not_reserve_run_id(self):
        with patch.object(
            diagnosis, "ENVIRONMENT_LOCK", self.root / "missing-lock.json"
        ):
            with self.assertRaises(FileNotFoundError):
                diagnosis.diagnose_capture(self.capture_dir, self.output)
        self.assertFalse(self.output.exists())

    def test_bad_structure_is_file_rejection_without_raw_content(self):
        path = self.capture_dir / self.files[0]["filename"]
        path.write_bytes(b"PRIVATE_ADDRESS_BAD_ZIP")
        self.files[0]["bytes"] = path.stat().st_size
        self.files[0]["sha256"] = sha256(path.read_bytes()).hexdigest()
        self._refresh_manifest()
        public = diagnosis.diagnose_capture(self.capture_dir, self.output)
        self.assertEqual(public["files"][0]["status"], "rejected_structure")
        self.assertNotIn("PRIVATE_ADDRESS", str(public))
        self.assertEqual(public["qualified_borough_count"], 0)

    def _refresh_manifest(self):
        manifest = {
            "protocol": capture.PROTOCOL,
            "run_id": self.capture_dir.name,
            "files": self.files,
        }
        body = capture._json_bytes(manifest)
        (self.capture_dir / "manifest.json").write_bytes(body)
        for item in (
            patch.object(
                inspection, "CAPTURE_MANIFEST_SHA256", sha256(body).hexdigest()
            ),
            patch.object(
                capture,
                "replay",
                return_value={"manifest_sha256": sha256(body).hexdigest()},
            ),
        ):
            item.start()
            self.addCleanup(item.stop)

    def test_hash_acl_links_and_postread_mutation_leave_incomplete(self):
        with patch.object(diagnosis, "verify_acl", side_effect=ValueError("ACL")):
            with self.assertRaises(ValueError):
                diagnosis.diagnose_capture(self.capture_dir, self.output)
        self.assertFalse(self.output.exists())
        path = self.capture_dir / self.files[0]["filename"]
        original = inspection._reparse
        with patch.object(
            inspection,
            "_reparse",
            side_effect=lambda item: item == path or original(item),
        ):
            with self.assertRaises(ValueError):
                diagnosis.diagnose_capture(self.capture_dir, self.output)
        self.assertFalse((self.output / "result.json").exists())
        with self.assertRaises(ValueError):
            diagnosis.replay(self.capture_dir, self.output)

    def test_hash_change_and_mutation_after_parser_reject(self):
        path = self.capture_dir / self.files[0]["filename"]
        path.write_bytes(self.body + b"tampered")
        with self.assertRaises(ValueError):
            diagnosis.diagnose_capture(self.capture_dir, self.output)
        self.assertFalse((self.output / "result.json").exists())
        path.write_bytes(self.body)
        other = self.root / "linked.xlsx"
        other.write_bytes(self.body)
        path.unlink()
        os.link(other, path)
        second = self.root / "header-diagnostic-20260929T123200Z-000000000003"
        with self.assertRaises(ValueError):
            diagnosis.diagnose_capture(self.capture_dir, second)
        path.unlink()
        path.write_bytes(self.body)
        original = diagnosis.scan_workbook

        def mutate(handle, **kwargs):
            result = original(handle, **kwargs)
            with open(handle.name, "ab") as writer:
                writer.write(b"changed")
            return result

        third = self.root / "header-diagnostic-20260929T123300Z-000000000004"
        with patch.object(diagnosis, "scan_workbook", side_effect=mutate):
            with self.assertRaises(ValueError):
                diagnosis.diagnose_capture(self.capture_dir, third)
        self.assertFalse((third / "result.json").exists())

    def test_replay_detects_both_private_and_public_tampering(self):
        diagnosis.diagnose_capture(self.capture_dir, self.output)
        for filename in ("result.json", "public.json"):
            path = self.output / filename
            before = path.read_bytes()
            value = json.loads(before)
            value["label_status"] = "qualified"
            path.write_bytes(inspection._json_bytes(value))
            with self.assertRaises(ValueError):
                diagnosis.replay(self.capture_dir, self.output)
            path.write_bytes(before)

    def test_timeout_and_safe_failure_artifact(self):
        with patch.object(
            diagnosis, "scan_workbook", side_effect=TimeoutError("secret")
        ):
            with self.assertRaises(TimeoutError):
                diagnosis.diagnose_capture(self.capture_dir, self.output)
        self.assertEqual(
            json.loads((self.output / "failure.json").read_text())["status"],
            "incomplete",
        )
        self.assertFalse((self.output / "public.json").exists())
        with self.assertRaises(ValueError):
            diagnosis.replay(self.capture_dir, self.output)

    def test_plan_and_no_policy_override(self):
        self.assertEqual(diagnosis.plan()["status"], "plan_only_no_workbook_open")
        with self.assertRaises(TypeError):
            diagnosis.diagnose_capture(
                self.capture_dir, self.output, printer_pin=TEST_PIN
            )
        with patch.dict(os.environ, {"TABPFN_PRINTER_SHA256": TEST_PIN[1]}):
            with self.assertRaises(ValueError):
                scanner.scan_workbook(
                    __import__("io").BytesIO(self.body), timer=lambda: 0.0, start=0.0
                )
        command = [sys.executable, str(Path(diagnosis.__file__)), "plan"]
        planned = subprocess.run(command, capture_output=True, text=True, check=True)
        self.assertEqual(
            json.loads(planned.stdout)["status"], "plan_only_no_workbook_open"
        )
        bad = subprocess.run(
            command + ["--printer-pin", TEST_PIN[1]], capture_output=True
        )
        self.assertEqual(bad.returncode, 2)

    def test_public_redaction_for_non_candidate_and_private_candidate(self):
        from profile_nyc_rolling_snapshot import HEADER  # noqa: PLC0415

        header = (
            '<row r="1">'
            + "".join(cell(i, 1, name) for i, name in enumerate(HEADER, 1))
            + "</row>"
        )
        sale = f'<row r="2">{cell(9, 2, "PRIVATE_SALE_ADDRESS")}{cell(20, 2, "987654321")}</row>'
        body = synthetic_xlsx(rows=header + sale)
        for entry in self.files:
            (self.capture_dir / entry["filename"]).write_bytes(body)
            entry["bytes"] = len(body)
            entry["sha256"] = sha256(body).hexdigest()
        self._refresh_manifest()
        public = diagnosis.diagnose_capture(self.capture_dir, self.output)
        public_bytes = (self.output / "public.json").read_bytes()
        self.assertNotIn(b"PRIVATE_SALE_ADDRESS", public_bytes)
        self.assertNotIn(b"987654321", public_bytes)
        self.assertNotIn(b"SALE PRICE", public_bytes)
        self.assertEqual(public["files"][0]["candidate"]["score"], 21)

    def test_private_candidate_value_is_never_public_and_replay_recomputes(self):
        from profile_nyc_rolling_snapshot import HEADER  # noqa: PLC0415

        changed = ("PRIVATE_CANDIDATE_ADDRESS", *HEADER[1:])
        row = (
            '<row r="1">'
            + "".join(cell(i, 1, name) for i, name in enumerate(changed, 1))
            + "</row>"
        )
        body = synthetic_xlsx(rows=row)
        for entry in self.files:
            (self.capture_dir / entry["filename"]).write_bytes(body)
            entry["bytes"] = len(body)
            entry["sha256"] = sha256(body).hexdigest()
        self._refresh_manifest()
        diagnosis.diagnose_capture(self.capture_dir, self.output)
        private_path = self.output / "result.json"
        public_path = self.output / "public.json"
        self.assertIn(b"PRIVATE_CANDIDATE_ADDRESS", private_path.read_bytes())
        self.assertNotIn(b"PRIVATE_CANDIDATE_ADDRESS", public_path.read_bytes())

        private = json.loads(private_path.read_bytes())
        private["files"][0]["candidate"]["cells"][0] = "TAMPERED_PRIVATE"
        private_bytes = inspection._json_bytes(private)
        private_path.write_bytes(private_bytes)
        hashes_path = self.output / "hash_manifest.json"
        hashes = json.loads(hashes_path.read_bytes())
        hashes["result_sha256"] = sha256(private_bytes).hexdigest()
        hashes_path.write_bytes(inspection._json_bytes(hashes))
        with self.assertRaises(ValueError):
            diagnosis.replay(self.capture_dir, self.output)

    def test_bad_path_intent_hash_and_public_replay_fails(self):
        with self.assertRaises(ValueError):
            diagnosis._diagnostic_dir(self.root / "wrong-name", new=True)
        with self.assertRaises(ValueError):
            diagnosis._diagnostic_dir(
                self.root / "header-diagnostic-20261329T123100Z-000000000002", new=True
            )
        with self.assertRaises(ValueError):
            diagnosis._diagnostic_dir(self.output, new=False)
        diagnosis.diagnose_capture(self.capture_dir, self.output)
        intent_path = self.output / "intent.json"
        original = intent_path.read_bytes()
        intent = json.loads(original)
        intent["capture_run_id"] = "wrong"
        intent_path.write_bytes(inspection._json_bytes(intent))
        with self.assertRaises(ValueError):
            diagnosis.replay(self.capture_dir, self.output)
        intent_path.write_bytes(original)
        hashes_path = self.output / "hash_manifest.json"
        hashes = json.loads(hashes_path.read_bytes())
        hashes["public_sha256"] = "0" * 64
        hashes_path.write_bytes(inspection._json_bytes(hashes))
        with self.assertRaises(ValueError):
            diagnosis.replay(self.capture_dir, self.output)

    def test_parser_result_is_not_mutated_and_failure_write_is_not_silent(self):
        fixture = {
            "protocol": scanner.PROTOCOL,
            "status": "no_unique_candidate",
            "physical_rows": 0,
        }
        with patch.object(diagnosis, "scan_workbook", return_value=fixture):
            public = diagnosis.diagnose_capture(self.capture_dir, self.output)
        self.assertEqual(
            fixture,
            {
                "protocol": scanner.PROTOCOL,
                "status": "no_unique_candidate",
                "physical_rows": 0,
            },
        )
        self.assertEqual(public["files"][0]["status"], "no_unique_candidate")
        other = self.root / "header-diagnostic-20260929T123200Z-000000000003"
        original = diagnosis.new_file

        def failed_artifact(path, content):
            if path.name == "failure.json":
                raise OSError("PRIVATE_DO_NOT_LEAK")
            return original(path, content)

        with (
            patch.object(
                diagnosis, "scan_workbook", side_effect=TimeoutError("secret")
            ),
            patch.object(diagnosis, "new_file", side_effect=failed_artifact),
        ):
            with self.assertRaises(TimeoutError) as caught:
                diagnosis.diagnose_capture(self.capture_dir, other)
        notes = getattr(caught.exception, "__notes__", [])
        self.assertTrue(any("OSError" in item for item in notes))
        self.assertNotIn("PRIVATE_DO_NOT_LEAK", str(notes))

    def test_formula_rejection_public_keeps_only_safe_counts(self):
        fixture = {
            "protocol": scanner.PROTOCOL,
            "status": "rejected_formula_candidate",
            "physical_rows": 26,
            "candidate_score": 20,
            "formula_cells": 1,
            "nonempty_count": 20,
            "beyond_21_count": 0,
            "source_row_number": 1,
            "physical_ordinal": 1,
        }
        with patch.object(diagnosis, "scan_workbook", return_value=fixture):
            public = diagnosis.diagnose_capture(self.capture_dir, self.output)
        file = public["files"][0]
        self.assertEqual(file["candidate_score"], 20)
        self.assertEqual(file["formula_cells"], 1)
        self.assertNotIn("candidate", file)
        self.assertNotIn("fingerprint_sha256", str(file))


if __name__ == "__main__":
    unittest.main()
