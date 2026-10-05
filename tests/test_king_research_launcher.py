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
            r"data\raw\king-benchmark\king-absolute-error-serving-20261006-v1",
        ):
            with self.subTest(required=required):
                self.assertIn(required, text)
                self.assertRegex(
                    text, rf"if\s+not\s+exist[^\r\n]*{re.escape(required)}"
                )

        self.assertIn("-m scripts.king_research_form", text)
        self.assertIn("--manifest-sha256", text)
        self.assertIn(
            "50ca467e61a52752e5ff9082297eeff1b294ef761aec383c8c7d2537c027941d",
            text,
        )
        self.assertNotIn("--fhfa-source", text)
        self.assertNotIn("hpi_po_metro", text)
        self.assertRegex(text, r"exit\s+/b\s+%errorlevel%")
        self.assertNotRegex(text, r"\b(?:curl|wget|invoke-webrequest|bitsadmin)\b")


if __name__ == "__main__":
    unittest.main()
