"""Native form and CLI parity on a private, freshly trained Ames bundle."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import tkinter as tk
import unittest
from unittest import mock

from scripts.ames_dev_prototype import predict, run_experiment
from scripts.ames_manual12_form import AmesManual12Form, format_result


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data/raw/openml/house_prices-42165.arff"
HOLDOUT = ROOT / "data/legacy/holdout_ids.csv"
EXAMPLE = json.loads(
    (ROOT / "examples/ames-manual12-request.json").read_text(encoding="utf-8")
)


class ManualFormFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        private_root = ROOT / "data/raw/ames-prototype"
        private_root.mkdir(parents=True, exist_ok=True)
        cls.temporary = tempfile.TemporaryDirectory(dir=private_root)
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.bundle = Path(cls.temporary.name) / "manual12"
        run_experiment(SOURCE, HOLDOUT, cls.bundle, profile="manual12")
        cls.digest = hashlib.sha256(
            (cls.bundle / "bundle.json").read_bytes()
        ).hexdigest()

    def test_form_matches_cli_and_clears_failed_prediction(self) -> None:
        root = tk.Tk()
        root.withdraw()
        try:
            app = AmesManual12Form(root, self.bundle, self.digest)
            app.load_demo()
            app.predict_button.invoke()
            root.update_idletasks()
            direct = predict(self.bundle, EXAMPLE, self.digest)
            self.assertEqual(app.result_var.get(), format_result(direct))
            command = [
                sys.executable,
                "-m",
                "scripts.ames_dev_prototype",
                "predict",
                "--bundle",
                str(self.bundle),
                "--request",
                str(ROOT / "examples/ames-manual12-request.json"),
                "--bundle-sha256",
                self.digest,
            ]
            process = subprocess.run(
                command,
                cwd=ROOT,
                env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
                capture_output=True,
                text=True,
                check=True,
            )
            self.assertEqual(
                app.result_var.get(), format_result(json.loads(process.stdout))
            )
            app.entries["LotArea"].delete(0, "end")
            app.entries["LotArea"].insert(0, "-1")
            with mock.patch.object(app.entries["LotArea"], "focus_set") as focus:
                app.predict_button.invoke()
                focus.assert_called_once_with()
            self.assertEqual(app.result_var.get(), "")
            self.assertIn("LotArea", app.status_var.get())
            missing_demo = ROOT / "examples/ames-manual12-request.json"
            with mock.patch(
                "scripts.ames_manual12_form.demo_path",
                return_value=missing_demo.with_name("missing-demo.json"),
            ):
                app.load_demo()
            self.assertIn("unavailable", app.status_var.get().lower())
            self.assertEqual(app.result_var.get(), "")
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()
