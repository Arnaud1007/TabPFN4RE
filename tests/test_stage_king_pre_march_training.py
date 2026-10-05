from __future__ import annotations

from datetime import date
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from scripts.king_historical_benchmark import NUMERIC_FEATURES, Sale
from scripts import stage_king_pre_march_training as staging


def sale(row_id: str, when: date = date(2015, 2, 1)) -> Sale:
    attributes = {name: 1.0 for name in NUMERIC_FEATURES}
    attributes["zipcode"] = "98001"
    return Sale(row_id, row_id, when, Decimal("100000"), attributes)


class KingPreMarchStageTests(unittest.TestCase):
    def test_stage_writes_only_canonical_pre_march_rows_and_bound_manifest(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            private = Path(temporary)
            output = private / "stage-v1"
            training = tuple(sale(str(index)) for index in range(16849))
            source_rows = (*training, *(sale(f"q-{index}") for index in range(12)))
            with (
                patch.object(staging, "PRIVATE_ROOT", private),
                patch.object(staging, "_committed_code", return_value="a" * 40),
                patch.object(
                    staging, "read_development_source", return_value=source_rows
                ),
                patch.object(
                    staging,
                    "select_eligible_sales",
                    return_value=(training, {"future_year_built": 12}),
                ),
                patch.object(staging, "real_directory"),
                patch.object(staging, "secure_directory"),
                patch.object(staging, "verify_acl"),
            ):
                summary = staging.stage(Path("full.arff"), output)
            self.assertEqual(summary["training_rows"], 16849)
            content = (output / "training.jsonl").read_text(encoding="utf-8")
            self.assertEqual(content.count("\n"), 16849)
            self.assertNotIn("2015-03-", content)
            manifest = json.loads(
                (output / "manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                manifest["training_membership_sha256"],
                staging.membership_sha256(training),
            )
            self.assertEqual(
                manifest["outputs"]["training.jsonl"],
                hashlib.sha256(content.encode()).hexdigest(),
            )
            self.assertEqual(manifest["march_may_labels_parsed"], 0)

    def test_stage_rejects_a_later_row_before_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            private = Path(temporary)
            output = private / "stage-v1"
            later = tuple(sale(str(index)) for index in range(16848)) + (
                sale("later", date(2015, 3, 1)),
            )
            source_rows = (*later, *(sale(f"q-{index}") for index in range(12)))
            with (
                patch.object(staging, "PRIVATE_ROOT", private),
                patch.object(staging, "_committed_code", return_value="a" * 40),
                patch.object(
                    staging, "read_development_source", return_value=source_rows
                ),
                patch.object(
                    staging,
                    "select_eligible_sales",
                    return_value=(later, {"future_year_built": 12}),
                ),
                patch.object(staging, "real_directory"),
                patch.object(staging, "verify_acl"),
                self.assertRaisesRegex(ValueError, "cutoff"),
            ):
                staging.stage(Path("full.arff"), output)
            self.assertFalse(output.exists())

    def test_stage_requires_clean_code_before_opening_source(self) -> None:
        source = Mock()
        with (
            patch.object(staging, "_committed_code", side_effect=ValueError("dirty")),
            patch.object(staging, "read_development_source", source),
            self.assertRaisesRegex(ValueError, "dirty"),
        ):
            staging.stage(Path("full.arff"), Path("output"))
        source.assert_not_called()


if __name__ == "__main__":
    unittest.main()
