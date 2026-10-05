from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import run_king_historical_intervals as intervals


class KingHistoricalIntervalsTests(unittest.TestCase):
    def _write_run(self, root: Path, rows: list[tuple[str, str, int, int]]) -> Path:
        directory = root / "later"
        directory.mkdir()
        path = directory / "later_predictions.csv"
        with path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream)
            writer.writerow(intervals.EXPECTED_COLUMNS)
            for row_id, when, actual, predicted in rows:
                writer.writerow((row_id, when, actual, predicted, predicted))
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        manifest = {
            "source_sha256": "a" * 64,
            "split_sha256": "b" * 64,
            "model_sha256": "c" * 64,
            "outputs": {"later_predictions.csv": digest},
        }
        (directory / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        return directory

    @staticmethod
    def _rows() -> list[tuple[str, str, int, int]]:
        months = (("2015-03-15", 20), ("2015-04-15", 12), ("2015-05-15", 8))
        rows = []
        for when, count in months:
            rows.extend(
                (f"row-{len(rows)}", when, 100, 100 if index % 5 else 80)
                for index in range(count)
            )
        return rows

    def _frozen(self, run: Path):
        return patch.multiple(
            intervals,
            EXPECTED_MANIFEST_SHA256=hashlib.sha256(
                (run / "manifest.json").read_bytes()
            ).hexdigest(),
            EXPECTED_PREDICTIONS_SHA256=hashlib.sha256(
                (run / "later_predictions.csv").read_bytes()
            ).hexdigest(),
            EXPECTED_TOTAL_ROWS=40,
            EXPECTED_CALIBRATION_ROWS=20,
            EXPECTED_EVALUATION_ROWS=20,
        )

    @patch.object(intervals, "_committed_code", return_value="d" * 40)
    def test_builds_nested_intervals_from_frozen_disjoint_periods(
        self, _commit
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run = self._write_run(root, self._rows())
            output = root / "output"
            with self._frozen(run):
                aggregate = intervals.build_intervals(run, output)

            self.assertEqual(aggregate["calibration_rows"], 20)
            self.assertEqual(aggregate["evaluation_rows"], 20)
            self.assertEqual(aggregate["interval_failures"], 0)
            self.assertEqual(aggregate["nested_intervals"], 20)
            self.assertFalse(aggregate["certified_90_day_origin"])
            manifest = json.loads(
                (output / "manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(manifest["code_commit"], "d" * 40)
            for filename, digest in manifest["outputs"].items():
                actual = hashlib.sha256((output / filename).read_bytes()).hexdigest()
                self.assertEqual(actual, digest)

    @patch.object(intervals, "_committed_code", return_value="d" * 40)
    def test_rejects_coordinated_tampering_and_out_of_period_rows(
        self, _commit
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run = self._write_run(root, self._rows())
            expected_manifest = hashlib.sha256(
                (run / "manifest.json").read_bytes()
            ).hexdigest()
            prediction = run / "later_predictions.csv"
            prediction.write_bytes(prediction.read_bytes() + b"tamper")
            manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
            manifest["outputs"]["later_predictions.csv"] = hashlib.sha256(
                prediction.read_bytes()
            ).hexdigest()
            (run / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            with patch.object(intervals, "EXPECTED_MANIFEST_SHA256", expected_manifest):
                with self.assertRaisesRegex(ValueError, "manifest"):
                    intervals.build_intervals(run, root / "tampered")

            other = root / "other"
            other.mkdir()
            rows = self._rows()
            rows[-1] = (rows[-1][0], "2015-06-01", 100, 100)
            run = self._write_run(other, rows)
            with self._frozen(run):
                with self.assertRaisesRegex(ValueError, "evaluation cohort"):
                    intervals.build_intervals(run, other / "output")


if __name__ == "__main__":
    unittest.main()
