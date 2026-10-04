"""Local replay of the saved historical King validation checkpoint."""

from __future__ import annotations

import csv
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts.king_historical_benchmark import (
    read_pinned_source,
    select_eligible_sales,
    split_sales,
)
from scripts.king_research_predict import predict


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = Path(
    os.environ.get(
        "KING_RESEARCH_BUNDLE_DIR",
        str(ROOT / "data/raw/king-benchmark/king-validation-20261004-v1"),
    )
)
SOURCE = ROOT / "data/raw/openml-king-42092/house_sales.arff"
MANIFEST_SHA256 = os.environ.get(
    "KING_RESEARCH_MANIFEST_SHA256",
    "32c11c3ac12e69126d2e1b2b58ab9eb5403a001836cfeb102442b234fef7cbe9",
)


class KingResearchPredictionFlowTests(unittest.TestCase):
    def test_saved_validation_prediction_matches_library_and_cli(self) -> None:
        eligible, _ = select_eligible_sales(read_pinned_source(SOURCE))
        sale = split_sales(eligible)["validation"][0]
        with (BUNDLE / "validation_predictions.csv").open(
            newline="", encoding="utf-8"
        ) as stream:
            archived = next(
                row for row in csv.DictReader(stream) if row["row_id"] == sale.row_id
            )
        request = dict(sale.attributes)
        expected = float(archived["xgboost_usd"])
        direct = predict(BUNDLE, request, MANIFEST_SHA256)
        self.assertLessEqual(abs(direct["amount"] - expected), 0.10)
        self.assertTrue(math.isfinite(direct["amount"]))
        self.assertEqual(direct["status"], "historical_research_only")
        self.assertFalse(direct["certified_90_day_origin"])

        with tempfile.TemporaryDirectory(dir=BUNDLE.parent) as directory:
            request_path = Path(directory) / "request.json"
            request_path.write_text(json.dumps(request), encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "scripts.king_research_predict",
                    "--bundle",
                    str(BUNDLE),
                    "--manifest-sha256",
                    MANIFEST_SHA256,
                    "--request",
                    str(request_path),
                ],
                cwd=ROOT,
                env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
                capture_output=True,
                text=True,
                check=True,
            )
            bad = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "scripts.king_research_predict",
                    "--bundle",
                    str(BUNDLE),
                    "--manifest-sha256",
                    "0" * 64,
                    "--request",
                    str(request_path),
                ],
                cwd=ROOT,
                env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
                capture_output=True,
                text=True,
            )
        cli = json.loads(result.stdout)
        self.assertEqual(cli["amount"], direct["amount"])
        self.assertEqual(cli["model_sha256"], direct["model_sha256"])
        self.assertEqual(bad.returncode, 2)
        self.assertIn("checksum", bad.stderr)
        self.assertEqual(bad.stdout, "")


if __name__ == "__main__":
    unittest.main()
