"""Input, service, and display contract for the local King research form."""

from __future__ import annotations

import json
from pathlib import Path
import unittest
from unittest.mock import patch

from scripts.king_historical_benchmark import NUMERIC_FEATURES
from scripts import king_research_predict as serving
from scripts import king_research_form as form


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = json.loads(
    (ROOT / "examples/king-research-request.json").read_text(encoding="utf-8")
)
FEATURE_NAMES = (*NUMERIC_FEATURES, f"zipcode={EXAMPLE['zipcode']}")
RESPONSE = {
    "amount": 200_000.25,
    "currency": "USD",
    "model": "xgboost",
    "status": "historical_research_only",
    "reference_period": "King County sales, January-February 2015",
    "certified_90_day_origin": False,
    "g_us_gate": "PENDING",
    "manifest_sha256": "a" * 64,
    "model_sha256": "b" * 64,
}


class KingResearchFormTests(unittest.TestCase):
    def setUp(self) -> None:
        self.raw = {name: str(value) for name, value in EXAMPLE.items()}

    def test_form_exposes_exactly_the_trained_fifteen_property_fields(self) -> None:
        self.assertEqual(len(form.FORM_FIELDS), 15)
        self.assertEqual(tuple(form.FORM_FIELDS), tuple(EXAMPLE))
        self.assertEqual(set(form.FORM_FIELDS), {*NUMERIC_FEATURES, "zipcode"})
        self.assertFalse({"price", "asking_price", "target_price"} & set(form.FORM_FIELDS))

    def test_parses_text_then_uses_the_existing_request_validator(self) -> None:
        with patch.object(serving, "validate_request", wraps=serving.validate_request) as validate:
            parsed = form.parse_form_values(self.raw, FEATURE_NAMES)

        validate.assert_called_once()
        request, feature_names = validate.call_args.args
        self.assertEqual(feature_names, FEATURE_NAMES)
        self.assertEqual(tuple(request), tuple(EXAMPLE))
        self.assertEqual(request["zipcode"], EXAMPLE["zipcode"])
        self.assertTrue(all(type(request[name]) in (int, float) for name in NUMERIC_FEATURES))
        self.assertEqual(parsed, serving.validate_request(EXAMPLE, FEATURE_NAMES))

    def test_rejects_missing_extra_invalid_and_unsupported_fields(self) -> None:
        invalid = (
            {**self.raw, "asking_price": "350000"},
            {**self.raw, "target_price": "350000"},
            {name: value for name, value in self.raw.items() if name != "bedrooms"},
            {**self.raw, "sqft_living": ""},
            {**self.raw, "sqft_living": "NaN"},
            {**self.raw, "bedrooms": "three"},
            {**self.raw, "waterfront": "2"},
            {**self.raw, "lat": "0"},
            {**self.raw, "zipcode": "99999"},
            {**self.raw, "zipcode": "9810"},
        )
        for raw in invalid:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                form.parse_form_values(raw, FEATURE_NAMES)

    def test_rejects_non_text_form_values(self) -> None:
        with self.assertRaises(ValueError):
            form.parse_form_values({**self.raw, "bedrooms": 3}, FEATURE_NAMES)

    def test_formats_estimate_with_full_historical_scope_warning(self) -> None:
        display = form.format_prediction(RESPONSE)

        self.assertIn("$200,000", display)
        self.assertIn("2015", display)
        self.assertRegex(display.lower(), r"historical research only")
        self.assertRegex(display.lower(), r"no calibrated interval")
        self.assertRegex(display.lower(), r"not (?:a )?current")
        self.assertRegex(display.lower(), r"not (?:a )?90.day")

    def test_rejects_incompatible_service_responses(self) -> None:
        incompatible = (
            {**RESPONSE, "status": "commercial"},
            {**RESPONSE, "certified_90_day_origin": True},
            {**RESPONSE, "currency": "EUR"},
            {**RESPONSE, "reference_period": "King County sales, 2026"},
            {**RESPONSE, "amount": -1},
            {**RESPONSE, "amount": float("nan")},
            {**RESPONSE, "amount": True},
            {name: value for name, value in RESPONSE.items() if name != "status"},
        )
        for response in incompatible:
            with self.subTest(response=response), self.assertRaises(ValueError):
                form.format_prediction(response)

    def test_headless_submit_flow_calls_the_cli_prediction_service(self) -> None:
        bundle_dir = Path("private-king-bundle")
        manifest_sha256 = "a" * 64
        with patch.object(serving, "predict", return_value=RESPONSE) as predict:
            response = form.predict_from_form(
                self.raw, bundle_dir, manifest_sha256, FEATURE_NAMES
            )

        predict.assert_called_once_with(
            bundle_dir,
            serving.validate_request(EXAMPLE, FEATURE_NAMES),
            manifest_sha256,
        )
        self.assertIn("$200,000", form.format_prediction(response))


if __name__ == "__main__":
    unittest.main()
