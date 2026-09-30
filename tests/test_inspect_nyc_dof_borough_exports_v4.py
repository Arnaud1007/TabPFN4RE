"""RED tests for the private five-borough v4 inspection and replay."""

from __future__ import annotations

from contextlib import redirect_stdout
from hashlib import sha256
from io import BytesIO, StringIO
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import capture_nyc_dof_borough_exports as capture  # noqa: E402
import diagnose_nyc_manhattan_formula_v1 as diagnostic_runner  # noqa: E402
import inspect_nyc_dof_borough_exports as earlier  # noqa: E402
import inspect_nyc_dof_borough_exports_v4 as runner  # noqa: E402
import nyc_manhattan_formula_xml_v1 as diagnostic_core  # noqa: E402
import nyc_workbook_xml_v4 as core  # noqa: E402
from tests.test_nyc_manhattan_formula_xml_v1 import _before  # noqa: E402
from tests.test_nyc_workbook_xml import TEST_PIN  # noqa: E402
from tests.test_nyc_workbook_xml_v3 import workbook  # noqa: E402


class BoroughV4RunnerTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "data" / "raw" / "nyc_dof"
        self.root.mkdir(parents=True)
        self.source = self.root / "official-exports-20260930T210000Z-000000000001"
        self.source.mkdir()
        self.output = (
            self.root / "worksheet-inspection-v4-20260930T210100Z-000000000002"
        )
        self.diag_dir = self.root / "manhattan-formula-v1-20260930T201602Z-6d714e014144"
        self.diag_dir.mkdir()
        self.manhattan = workbook(before=_before("<f>1+1</f><v>PRIVATE_PRICE</v>"))
        diagnostic = diagnostic_core._diagnose_with_pin(
            BytesIO(self.manhattan), TEST_PIN, timer=lambda: 0.0
        )
        (self.diag_dir / "result.json").write_bytes(earlier._json_bytes(diagnostic))
        entries = []
        for borough, url in capture.BOROUGHS:
            name = capture._filename(borough)
            body = self.manhattan if borough == "Manhattan" else workbook()
            (self.source / name).write_bytes(body)
            entries.append(
                {
                    "borough": borough,
                    "url": url,
                    "filename": name,
                    "bytes": len(body),
                    "sha256": sha256(body).hexdigest(),
                }
            )
        manifest = {
            "protocol": capture.PROTOCOL,
            "run_id": self.source.name,
            "files": entries,
        }
        manifest_bytes = capture._json_bytes(manifest)
        (self.source / "manifest.json").write_bytes(manifest_bytes)
        self._patchers = [
            patch.object(runner, "PRIVATE_ROOT", self.root),
            patch.object(earlier, "PRIVATE_ROOT", self.root),
            patch.object(capture, "PRIVATE_ROOT", self.root),
            patch.object(diagnostic_runner, "PRIVATE_ROOT", self.root),
            patch.object(runner, "CAPTURE_RUN_ID", self.source.name),
            patch.object(
                runner, "MANHATTAN_SHA256", sha256(self.manhattan).hexdigest()
            ),
            patch.object(
                earlier, "CAPTURE_MANIFEST_SHA256", sha256(manifest_bytes).hexdigest()
            ),
            patch.object(
                capture,
                "replay",
                return_value={"manifest_sha256": sha256(manifest_bytes).hexdigest()},
            ),
            patch.object(
                diagnostic_runner, "replay", return_value={"diagnostic_completed": True}
            ),
            patch.object(runner, "verify_acl"),
            patch.object(earlier, "verify_acl"),
            patch.object(runner, "secure_directory"),
            patch.object(
                runner,
                "inspect_workbook",
                side_effect=lambda handle, **kw: core._inspect_with_pin(
                    handle, TEST_PIN, **kw
                ),
            ),
        ]
        for item in self._patchers:
            item.start()
            self.addCleanup(item.stop)

    def test_five_structural_passes_private_run_replay_and_no_overwrite(self):
        public = runner.inspect_capture(self.source, self.output)
        self.assertEqual(public["worksheet_qualified_count"], 5)
        self.assertEqual(public["sale_labels_certified"], 0)
        self.assertEqual(public["label_status"], "unqualified")
        self.assertNotIn("PRIVATE_PRICE", json.dumps(public))
        self.assertNotIn("1+1", json.dumps(public))
        private = json.loads((self.output / "result.json").read_bytes())
        self.assertEqual(private["worksheet_qualified_count"], 5)
        self.assertEqual(runner.replay(self.source, self.output), public)
        self.assertNotIn('"formula":', json.dumps(private))
        self.assertNotIn("PRIVATE_PRICE", json.dumps(private))
        with self.assertRaises(FileExistsError):
            runner.inspect_capture(self.source, self.output)

    def test_changed_workbook_fails_before_published_result(self):
        (self.source / "manhattan.xlsx").write_bytes(self.manhattan + b"tamper")
        with self.assertRaises(ValueError):
            runner.inspect_capture(self.source, self.output)
        self.assertFalse((self.output / "result.json").exists())

    def test_missing_or_tampered_private_diagnostic_blocks_v4(self):
        with patch.object(
            diagnostic_runner, "replay", side_effect=ValueError("tampered")
        ):
            with self.assertRaisesRegex(ValueError, "tampered"):
                runner.inspect_capture(self.source, self.output)
        self.assertFalse(self.output.exists())
        (self.diag_dir / "result.json").write_bytes(b'{"tampered":true}\n')
        with self.assertRaises(ValueError):
            runner.inspect_capture(self.source, self.output)
        self.assertFalse(self.output.exists())

    def test_parser_failure_keeps_incomplete_intent(self):
        with patch.object(runner, "_aggregate", side_effect=TimeoutError("late")):
            with self.assertRaises(TimeoutError):
                runner.inspect_capture(self.source, self.output)
        self.assertTrue((self.output / "intent.json").is_file())
        self.assertTrue((self.output / "failure.json").is_file())
        self.assertFalse((self.output / "result.json").exists())
        with self.assertRaises(ValueError):
            runner.replay(self.source, self.output)

    def test_replay_rejects_tampered_result(self):
        runner.inspect_capture(self.source, self.output)
        (self.output / "result.json").write_bytes(b'{"tampered":true}\n')
        with self.assertRaises(ValueError):
            runner.replay(self.source, self.output)

    def test_output_path_is_confined_and_nonredirecting(self):
        for target in (
            self.root.parent / self.output.name,
            self.root / "worksheet-inspection-v4-invalid",
        ):
            with self.subTest(target=target), self.assertRaises(ValueError):
                runner._run_dir(target, new=True)
        with patch.object(earlier, "_reparse", return_value=True):
            with self.assertRaisesRegex(ValueError, "redirects"):
                runner._run_dir(self.output, new=True)

    def test_cli_stdout_contains_only_public_projection(self):
        args = ["v4", "inspect", str(self.source), str(self.output)]
        output = StringIO()
        with patch.object(sys, "argv", args), redirect_stdout(output):
            runner.main()
        self.assertEqual(json.loads(output.getvalue())["worksheet_qualified_count"], 5)
        self.assertNotIn("PRIVATE_PRICE", output.getvalue())
        self.assertNotIn("1+1", output.getvalue())


if __name__ == "__main__":
    unittest.main()
