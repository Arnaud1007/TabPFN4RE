"""User-input and display contract for the local Ames prediction form."""

from __future__ import annotations

import json
from pathlib import Path
import unittest

from scripts.ames_dev_prototype import MANUAL12_FEATURES, MANUAL12_PROTOCOL
from scripts.ames_manual12_form import (
    format_result,
    parse_form_values,
    validate_form_bundle,
)


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = json.loads(
    (ROOT / "examples/ames-manual12-request.json").read_text(encoding="utf-8")
)
SAVED_RESPONSE = json.loads(
    (ROOT / "runs/ames-manual12-20261004-v1/example_prediction.json").read_text(
        encoding="utf-8"
    )
)


class ManualFormContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.raw = {name: str(value) for name, value in EXAMPLE.items()}

    def test_parses_exact_twelve_fields_for_the_prediction_service(self) -> None:
        parsed = parse_form_values(self.raw)
        self.assertEqual(tuple(parsed), MANUAL12_FEATURES)
        self.assertEqual(parsed, EXAMPLE)

    def test_blank_optional_fields_are_explicitly_missing(self) -> None:
        parsed = parse_form_values({**self.raw, "GarageCars": "  "})
        self.assertIsNone(parsed["GarageCars"])
        self.assertEqual(parsed["Neighborhood"], "NAmes")

    def test_required_missing_extra_and_invalid_values_are_rejected(self) -> None:
        cases = (
            ({**self.raw, "GrLivArea": ""}, "GrLivArea"),
            ({**self.raw, "Neighborhood": " "}, "Neighborhood"),
            ({**self.raw, "LotArea": "-1"}, "LotArea"),
            ({**self.raw, "GarageCars": "1.5"}, "GarageCars"),
            ({**self.raw, "OverallCond": "99"}, "OverallCond"),
            ({**self.raw, "YearBuilt": "2500"}, "YearBuilt"),
            ({**self.raw, "GrLivArea": "NaN"}, "GrLivArea"),
            ({**self.raw, "FullBath": "unknown"}, "FullBath"),
            ({**self.raw, "Id": "1"}, "exactly"),
            (
                {key: value for key, value in self.raw.items() if key != "LotArea"},
                "exactly",
            ),
        )
        for raw, message in cases:
            with (
                self.subTest(message=message, raw=raw),
                self.assertRaisesRegex(ValueError, message),
            ):
                parse_form_values(raw)

    def test_formats_rounded_price_with_scope_and_input_warnings(self) -> None:
        display = format_result(SAVED_RESPONSE)
        self.assertIn("$147,844", display)
        self.assertIn("Historical Ames prototype", display)
        self.assertIn("no calibrated interval", display)
        warned = format_result(
            {
                **SAVED_RESPONSE,
                "missing_feature_count": 2,
                "support_status": "unseen_category",
                "unseen_category_features": ["Neighborhood"],
            }
        )
        self.assertIn("2 missing", warned)
        self.assertIn("Neighborhood", warned)

    def test_rejects_unsupported_prediction_status(self) -> None:
        with self.assertRaisesRegex(ValueError, "support status"):
            format_result({**SAVED_RESPONSE, "support_status": "unsupported"})

    def test_rejects_wrong_bundle_profile_before_opening_form(self) -> None:
        bundle = {
            "profile": "manual12",
            "protocol": MANUAL12_PROTOCOL,
            "features": list(MANUAL12_FEATURES),
        }
        validate_form_bundle(bundle)
        with self.assertRaisesRegex(ValueError, "12-field"):
            validate_form_bundle({**bundle, "profile": "full"})


if __name__ == "__main__":
    unittest.main()
