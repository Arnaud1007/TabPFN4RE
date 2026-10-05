"""Contract for the Windows one-click King research form launcher."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "Launch-KingResearchForm.cmd"


class KingResearchLauncherTests(unittest.TestCase):
    def test_launcher_is_local_pinned_validated_and_preserves_exit_code(self) -> None:
        self.assertTrue(LAUNCHER.is_file(), "Root one-click launcher is missing")
        text = LAUNCHER.read_text(encoding="utf-8").lower()

        self.assertIn("%~dp0", text)
        for required in (
            r"data\raw\legacy-replay\.venv\scripts\python.exe",
            r"data\raw\king-benchmark\king-validation-20261004-v1",
            r"data\raw\fhfa\hpi_po_metro_2026-10-05.txt",
        ):
            with self.subTest(required=required):
                self.assertIn(required, text)
                self.assertRegex(text, rf"if\s+not\s+exist[^\r\n]*{re.escape(required)}")

        self.assertIn("-m scripts.king_research_form", text)
        self.assertIn("--manifest-sha256", text)
        self.assertIn(
            "32c11c3ac12e69126d2e1b2b58ab9eb5403a001836cfeb102442b234fef7cbe9",
            text,
        )
        self.assertIn("--fhfa-source", text)
        self.assertRegex(text, r"exit\s+/b\s+%errorlevel%")
        self.assertNotRegex(text, r"\b(?:curl|wget|invoke-webrequest|bitsadmin)\b")


if __name__ == "__main__":
    unittest.main()
