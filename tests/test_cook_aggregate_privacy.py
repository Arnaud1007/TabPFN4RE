"""Synthetic privacy checks for the Cook public audit projection."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import unittest


RUNNER = (
    Path(__file__).resolve().parents[1]
    / "runs"
    / "u0-cook-sales-sample-20261003T004123Z"
    / "rebuild_aggregate.py"
)
SPEC = importlib.util.spec_from_file_location("cook_aggregate", RUNNER)
assert SPEC is not None and SPEC.loader is not None
aggregate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(aggregate)


class CookAggregatePrivacyTest(unittest.TestCase):
    def test_public_capture_timestamp_requires_valid_utc_value(self):
        with self.assertRaisesRegex(ValueError, "capture timestamp"):
            aggregate.validate_capture_timestamp("Private Person at 123 Main St")
        self.assertEqual(
            aggregate.validate_capture_timestamp("2026-10-03T00:41:23.032937Z"),
            "2026-10-03T00:41:23.032937Z",
        )

    def test_capture_order_handles_mixed_fractional_precision(self):
        self.assertEqual(
            aggregate.validated_capture_times(
                "2026-10-03T00:00:00Z", "2026-10-03T00:00:00.000001Z"
            ),
            ("2026-10-03T00:00:00Z", "2026-10-03T00:00:00.000001Z"),
        )
        with self.assertRaisesRegex(ValueError, "out of order"):
            aggregate.validated_capture_times(
                "2026-10-03T00:00:00.000001Z", "2026-10-03T00:00:00Z"
            )

    def test_unexpected_category_values_do_not_enter_public_projection(self):
        rows = [
            {
                "class": "Person Name at 123 Main St",
                "sale_type": "Phone 555-1234",
                "is_multisale": "Secret customer name",
                "doc_no": "PRIVATE-DOCUMENT",
                "pin": "00000000000001",
            },
            {
                "class": "299",
                "sale_type": "LAND AND BUILDING",
                "is_multisale": True,
                "doc_no": "PRIVATE-DOCUMENT",
                "pin": "00000000000002",
            },
        ]
        result = aggregate.summarize_sample_rows(rows)
        rendered = json.dumps(result)
        for secret in (
            "Person Name",
            "123 Main",
            "Phone",
            "Secret",
            "PRIVATE-DOCUMENT",
        ):
            self.assertNotIn(secret, rendered)
        self.assertEqual(
            result["sample_multisale"], {"false": 0, "true": 1, "other": 1}
        )
        self.assertEqual(
            result["sample_sale_type"],
            {
                "missing": 0,
                "land": 0,
                "land_and_building": 1,
                "other": 1,
            },
        )
        self.assertEqual(result["sample_duplicate_document_groups"], 1)
        self.assertEqual(result["sample_duplicate_document_rows"], 2)
        self.assertNotIn("sample_min_price_usd", result)
        self.assertNotIn("sample_max_price_usd", result)


if __name__ == "__main__":
    unittest.main()
