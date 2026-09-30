"""Synthetic RED tests for the private Manhattan formula run and replay."""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from defusedxml.common import DefusedXmlException
from hashlib import sha256
from io import StringIO
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import capture_nyc_dof_borough_exports as capture  # noqa: E402
import diagnose_nyc_manhattan_formula_v1 as runner  # noqa: E402
import inspect_nyc_dof_borough_exports as earlier  # noqa: E402
import nyc_manhattan_formula_xml_v1 as core  # noqa: E402
from tests.test_nyc_manhattan_formula_xml_v1 import _before  # noqa: E402
from tests.test_nyc_workbook_xml import TEST_PIN  # noqa: E402
from tests.test_nyc_workbook_xml_v3 import workbook  # noqa: E402


class ManhattanFormulaRunnerTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "data" / "raw" / "nyc_dof"
        self.root.mkdir(parents=True)
        self.source = self.root / "official-exports-20260930T200000Z-000000000001"
        self.source.mkdir()
        self.output = self.root / "manhattan-formula-v1-20260930T200100Z-000000000002"
        self.body = workbook(before=_before("<f>1+1</f><v>PRIVATE_CACHED_PRICE</v>"))
        entries = []
        for borough, url in capture.BOROUGHS:
            name = capture._filename(borough)
            body = self.body if borough == "Manhattan" else workbook()
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
        body = capture._json_bytes(manifest)
        (self.source / "manifest.json").write_bytes(body)
        self._patchers = [
            patch.object(runner, "PRIVATE_ROOT", self.root),
            patch.object(earlier, "PRIVATE_ROOT", self.root),
            patch.object(capture, "PRIVATE_ROOT", self.root),
            patch.object(runner, "CAPTURE_RUN_ID", self.source.name),
            patch.object(runner, "MANHATTAN_SHA256", sha256(self.body).hexdigest()),
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
                "diagnose_workbook",
                side_effect=lambda handle, **kw: core._diagnose_with_pin(
                    handle, TEST_PIN, **kw
                ),
            ),
        ]
        for item in self._patchers:
            item.start()
            self.addCleanup(item.stop)

    def test_private_formula_public_redaction_replay_and_no_overwrite(self):
        public = runner.inspect_capture(self.source, self.output)
        self.assertEqual(public["protocol"], "nyc-manhattan-formula-diagnostic-v1")
        self.assertEqual(public["projection"], "private_only_v1")
        self.assertFalse(public["v3_worksheet_qualified"])
        self.assertEqual(public["sale_labels_certified"], 0)
        self.assertNotIn("formula", public)
        private = json.loads((self.output / "result.json").read_bytes())
        self.assertEqual(private["formula"]["coordinate"], "A1")
        self.assertEqual(private["formula"]["expression"], "1+1")
        self.assertNotIn("PRIVATE_CACHED_PRICE", json.dumps(private))
        self.assertEqual(runner.replay(self.source, self.output), public)
        self.assertNotIn("1+1", (self.output / "public.json").read_text())
        with self.assertRaises(FileExistsError):
            runner.inspect_capture(self.source, self.output)

    def test_public_projection_is_fixed_across_private_formula_values(self):
        first = {"formula": {"expression": "PRIVATE_A", "coordinate": "A1"}}
        second = {"formula": {"expression": "PRIVATE_B", "coordinate": "U4"}}
        self.assertEqual(
            runner._public_projection(first), runner._public_projection(second)
        )

    def test_changed_workbook_fails_before_result(self):
        (self.source / "manhattan.xlsx").write_bytes(self.body + b"tamper")
        with self.assertRaises(ValueError):
            runner.inspect_capture(self.source, self.output)
        self.assertFalse((self.output / "result.json").exists())

    def test_output_must_be_direct_private_child_with_valid_run_id(self):
        outside = self.root.parent / self.output.name
        malformed = self.root / "manhattan-formula-v1-invalid"
        for target in (outside, malformed):
            with self.subTest(target=target), self.assertRaises(ValueError):
                runner._run_dir(target, new=True)
        with patch.object(earlier, "_reparse", return_value=True):
            with self.assertRaisesRegex(ValueError, "redirects"):
                runner._run_dir(self.output, new=True)

    def test_parser_failure_keeps_incomplete_private_intent(self):
        with patch.object(runner, "diagnose_workbook", side_effect=ValueError("bad")):
            with self.assertRaisesRegex(ValueError, "bad"):
                runner.inspect_capture(self.source, self.output)
        self.assertTrue((self.output / "intent.json").is_file())
        self.assertFalse((self.output / "result.json").exists())
        with self.assertRaises(ValueError):
            runner.replay(self.source, self.output)

    def test_tampered_private_result_replay_fails(self):
        runner.inspect_capture(self.source, self.output)
        result = self.output / "result.json"
        result.write_text('{"tampered":true}', encoding="utf-8")
        with self.assertRaises(ValueError):
            runner.replay(self.source, self.output)

    def test_cli_stdout_is_fixed_projection(self):
        arguments = ["diagnostic", "diagnose", str(self.source), str(self.output)]
        stream = StringIO()
        with patch.object(sys, "argv", arguments), redirect_stdout(stream):
            runner.main()
        output = stream.getvalue()
        self.assertEqual(json.loads(output), runner._public_projection({}))
        self.assertNotIn("PRIVATE_CACHED_PRICE", output)
        self.assertNotIn("1+1", output)

    def test_cli_xml_rejection_has_fixed_error_without_traceback(self):
        arguments = ["diagnostic", "diagnose", str(self.source), str(self.output)]
        errors = StringIO()
        with (
            patch.object(sys, "argv", arguments),
            patch.object(
                runner,
                "inspect_capture",
                side_effect=DefusedXmlException("PRIVATE_XML_CONTENT"),
            ),
            redirect_stderr(errors),
            self.assertRaises(SystemExit) as raised,
        ):
            runner.main()
        self.assertEqual(raised.exception.code, 2)
        self.assertNotIn("PRIVATE_XML_CONTENT", errors.getvalue())
        self.assertNotIn("Traceback", errors.getvalue())


if __name__ == "__main__":
    unittest.main()
