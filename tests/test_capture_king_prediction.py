"""Contract tests for exclusive local King research receipts."""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from contextlib import redirect_stderr, redirect_stdout

from scripts import capture_king_prediction as capture


REQUEST = {
    "bedrooms": 3,
    "bathrooms": 2,
    "sqft_living": 1800,
    "sqft_lot": 6000,
    "floors": 2,
    "waterfront": 0,
    "view": 0,
    "condition": 3,
    "grade": 7,
    "sqft_above": 1800,
    "sqft_basement": 0,
    "yr_built": 1985,
    "lat": 47.55,
    "long": -122.25,
    "zipcode": "98103",
}
RESPONSE = {
    "amount": 542149.79,
    "currency": "USD",
    "model": "xgboost",
    "status": "historical_research_only",
    "reference_period": "King County sales, January-February 2015",
    "certified_90_day_origin": False,
    "g_us_gate": "PENDING",
    "manifest_sha256": "a" * 64,
    "model_sha256": "b" * 64,
}
HPI_FACTOR = 638.47 / 293.68
HPI = {
    "amount": RESPONSE["amount"] * HPI_FACTOR,
    "currency": "USD",
    "status": "research_only",
    "series_id": "FHFA_PO_NSA_SEATTLE_BELLEVUE_KENT",
    "cbsa_code": capture.serving.FHFA_CBSA,
    "geography": capture.serving.FHFA_GEOGRAPHY,
    "index_type": "purchase-only",
    "seasonality": "not-seasonally-adjusted",
    "base_quarter": capture.serving.FHFA_BASE_QUARTER,
    "target_quarter": capture.serving.FHFA_TARGET_QUARTER,
    "factor": HPI_FACTOR,
    "as_of": capture.serving.FHFA_SNAPSHOT_DATE.isoformat(),
    "source_release_date": capture.serving.FHFA_RELEASE_DATE.isoformat(),
    "retrieved_at": capture.serving.FHFA_SNAPSHOT_DATE.isoformat(),
    "snapshot_available_at": capture.serving.FHFA_SNAPSHOT_DATE.isoformat(),
    "base_index": 293.68,
    "target_index": 638.47,
    "base_available_at": "2026-10-05",
    "target_available_at": "2026-10-05",
    "source_sha256": capture.serving.FHFA_SOURCE_SHA256,
    "warning": (
        "Research only: this applies average market appreciation and is not "
        "a current valuation, not a 90-day estimate, and not property-specific."
    ),
}
NOW = datetime(2026, 10, 5, 12, 34, 56, tzinfo=UTC)


class KingPredictionCaptureTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.private_root = Path(temporary.name) / "receipts"
        self.private_root.mkdir()
        self.request_path = Path(temporary.name) / "request.json"
        self.request_path.write_text(json.dumps(REQUEST), encoding="utf-8")

    def test_capture_creates_one_exclusive_canonical_receipt(self) -> None:
        with patch.object(capture, "PRIVATE_ROOT", self.private_root):
            result = capture.capture_prediction(
                bundle=Path("private-bundle"),
                manifest_sha256="a" * 64,
                request_path=self.request_path,
                enrollment_reference="prospect-0001",
                fhfa_source=None,
                clock=lambda: NOW,
                predictor=lambda *_args: RESPONSE,
                code_state=lambda: ("c" * 40, False),
                privacy_nonce_factory=lambda: "1" * 64,
            )

        receipt_path = self.private_root / f"{result['receipt_id']}.json"
        self.assertEqual(json.loads(receipt_path.read_text()), result)
        self.assertEqual(result["captured_at_utc"], "2026-10-05T12:34:56Z")
        self.assertEqual(result["protocol"], "king-research-prospective-receipt-v2")
        self.assertEqual(result["privacy_nonce"], "1" * 64)
        self.assertEqual(
            result["request_raw_utf8"], self.request_path.read_text(encoding="utf-8")
        )
        self.assertEqual(result["scope"], "prospective_research_observation")
        self.assertEqual(result["prediction"], RESPONSE)
        self.assertEqual(
            result["request_sha256"],
            sha256(capture.canonical_bytes(REQUEST)).hexdigest(),
        )
        self.assertEqual(
            result["enrollment_reference_sha256"],
            sha256(b"prospect-0001").hexdigest(),
        )
        self.assertNotIn("prospect-0001", receipt_path.read_text())
        self.assertEqual(result["request"], REQUEST)
        self.assertIn("external timestamp", result["integrity_limit"].lower())
        self.assertFalse(result["certification_eligible"])
        self.assertEqual(result["g_us_gate"], "PENDING")
        self.assertEqual(result["code_commit"], "c" * 40)
        self.assertFalse(result["dirty_tree_at_capture"])

        with patch.object(capture, "PRIVATE_ROOT", self.private_root):
            with self.assertRaises(FileExistsError):
                capture.capture_prediction(
                    bundle=Path("private-bundle"),
                    manifest_sha256="a" * 64,
                    request_path=self.request_path,
                    enrollment_reference="prospect-0001",
                    fhfa_source=None,
                    clock=lambda: NOW,
                    predictor=lambda *_args: RESPONSE,
                    code_state=lambda: ("c" * 40, False),
                    privacy_nonce_factory=lambda: "1" * 64,
                )

    def test_rejects_bad_reference_time_request_and_prediction_scope(self) -> None:
        cases = (
            ("bad reference!", NOW, REQUEST, RESPONSE),
            ("valid-ref", NOW.replace(tzinfo=None), REQUEST, RESPONSE),
            ("valid-ref", NOW, [1, 2], RESPONSE),
            ("valid-ref", NOW, REQUEST, {**RESPONSE, "status": "certified"}),
            ("valid-ref", NOW, REQUEST, {**RESPONSE, "amount": float("nan")}),
            ("valid-ref", NOW, REQUEST, {**RESPONSE, "manifest_sha256": "d" * 64}),
            ("valid-ref", NOW, REQUEST, {**RESPONSE, "address": "private"}),
            (
                "valid-ref",
                NOW,
                REQUEST,
                {
                    **RESPONSE,
                    "experimental_hpi_adjustment": {**HPI, "factor": -1},
                },
            ),
        )
        for index, (reference, moment, request, response) in enumerate(cases):
            with self.subTest(index=index):
                self.request_path.write_text(json.dumps(request), encoding="utf-8")
                with patch.object(capture, "PRIVATE_ROOT", self.private_root):
                    with self.assertRaises(ValueError):
                        capture.capture_prediction(
                            bundle=Path("private-bundle"),
                            manifest_sha256="a" * 64,
                            request_path=self.request_path,
                            enrollment_reference=reference,
                            fhfa_source=None,
                            clock=lambda moment=moment: moment,
                            predictor=lambda *_args, response=response: response,
                            code_state=lambda: ("c" * 40, False),
                            privacy_nonce_factory=lambda: "1" * 64,
                        )
                self.assertEqual(list(self.private_root.iterdir()), [])

    def test_accepts_only_consistent_real_hpi_metadata(self) -> None:
        response = {**RESPONSE, "experimental_hpi_adjustment": HPI}
        self.assertEqual(capture._validate_response(response, "a" * 64), response)
        tampered = (
            {**HPI, "index_type": "purchase_only"},
            {**HPI, "base_available_at": "2015-01-01"},
            {**HPI, "factor": HPI_FACTOR + 0.01},
            {**HPI, "amount": HPI["amount"] + 100},
        )
        for hpi in tampered:
            with self.subTest(hpi=hpi), self.assertRaises(ValueError):
                capture._validate_response(
                    {**RESPONSE, "experimental_hpi_adjustment": hpi}, "a" * 64
                )

    def test_actual_absolute_response_is_accepted_by_capture_contract(self) -> None:
        bundle = capture.serving.VerifiedBundle(
            ("bedrooms", "zipcode=98103"),
            b"model",
            "a" * 64,
            "b" * 64,
            capture.serving.ABSOLUTE_PROTOCOL,
            "reg:absoluteerror",
            "2015-03-01",
            "King County sales before March 2015",
            "King County sales, November 2014-February 2015",
        )
        response = capture.serving._prediction_response(542149.79, bundle)
        self.assertEqual(capture._validate_response(response, "a" * 64), response)
        invalid = (
            {key: value for key, value in response.items() if key != "support"},
            {**response, "extra_disclosure": True},
            {**response, "response_schema_version": "v3"},
            {**response, "support": {**response["support"], "status": "supported"}},
            {
                **response,
                "valuation_reference": {
                    **response["valuation_reference"],
                    "current_market_valuation": True,
                },
            },
            {
                **response,
                "data_freshness": {
                    **response["data_freshness"],
                    "current_market_inputs_included": True,
                },
            },
            {
                **response,
                "uncertainty": {
                    **response["uncertainty"],
                    "interval_90": [100_000, 300_000],
                },
            },
            {**response, "limitations": []},
        )
        for candidate in invalid:
            with self.subTest(candidate=candidate), self.assertRaises(ValueError):
                capture._validate_response(candidate, "a" * 64)
        self.assertEqual(
            set(response),
            capture.BASE_RESPONSE_KEYS | capture.ABSOLUTE_EXTENSION_KEYS,
        )

    def test_predictor_failure_leaves_no_receipt(self) -> None:
        def fail(*_args):
            raise ValueError("bad bundle")

        with patch.object(capture, "PRIVATE_ROOT", self.private_root):
            with self.assertRaisesRegex(ValueError, "bad bundle"):
                capture.capture_prediction(
                    bundle=Path("private-bundle"),
                    manifest_sha256="a" * 64,
                    request_path=self.request_path,
                    enrollment_reference="prospect-0001",
                    fhfa_source=None,
                    clock=lambda: NOW,
                    predictor=fail,
                    code_state=lambda: ("c" * 40, False),
                    privacy_nonce_factory=lambda: "1" * 64,
                )
        self.assertEqual(list(self.private_root.iterdir()), [])

    def test_invalid_privacy_nonce_never_publishes_a_receipt(self) -> None:
        invalid = ("1" * 63, "A" * 64, "g" * 64, 1, None)
        for index, nonce in enumerate(invalid):
            with self.subTest(index=index):
                with patch.object(capture, "PRIVATE_ROOT", self.private_root):
                    with self.assertRaises(ValueError):
                        capture.capture_prediction(
                            bundle=Path("private-bundle"),
                            manifest_sha256="a" * 64,
                            request_path=self.request_path,
                            enrollment_reference="prospect-0001",
                            fhfa_source=None,
                            clock=lambda: NOW,
                            predictor=lambda *_args: RESPONSE,
                            code_state=lambda: ("c" * 40, False),
                            privacy_nonce_factory=lambda nonce=nonce: nonce,
                        )
                self.assertEqual(list(self.private_root.iterdir()), [])

        with patch.object(capture, "PRIVATE_ROOT", self.private_root):
            with self.assertRaisesRegex(RuntimeError, "nonce failure"):
                capture.capture_prediction(
                    bundle=Path("private-bundle"),
                    manifest_sha256="a" * 64,
                    request_path=self.request_path,
                    enrollment_reference="prospect-0001",
                    fhfa_source=None,
                    clock=lambda: NOW,
                    predictor=lambda *_args: RESPONSE,
                    code_state=lambda: ("c" * 40, False),
                    privacy_nonce_factory=lambda: (_ for _ in ()).throw(
                        RuntimeError("nonce failure")
                    ),
                )
        self.assertEqual(list(self.private_root.iterdir()), [])

    def test_code_change_or_publication_failure_leaves_no_final_receipt(self) -> None:
        states = iter((("c" * 40, False), ("d" * 40, False)))
        with patch.object(capture, "PRIVATE_ROOT", self.private_root):
            with self.assertRaisesRegex(ValueError, "Code state changed"):
                capture.capture_prediction(
                    bundle=Path("private-bundle"),
                    manifest_sha256="a" * 64,
                    request_path=self.request_path,
                    enrollment_reference="prospect-0001",
                    fhfa_source=None,
                    clock=lambda: NOW,
                    predictor=lambda *_args: RESPONSE,
                    code_state=lambda: next(states),
                    privacy_nonce_factory=lambda: "1" * 64,
                )
        self.assertEqual(list(self.private_root.iterdir()), [])

    def test_cli_prints_only_a_non_sensitive_acknowledgement(self) -> None:
        private_receipt = {
            "receipt_id": "receipt-1",
            "captured_at_utc": "2026-10-05T12:34:56Z",
            "scope": "prospective_research_observation",
            "prediction": RESPONSE,
            "manifest_sha256": "a" * 64,
            "model_sha256": "b" * 64,
            "request_sha256": "e" * 64,
            "response_sha256": "f" * 64,
            "dirty_tree_at_capture": False,
            "integrity_limit": "External anchor required.",
            "request": REQUEST,
        }
        argv = [
            "capture_king_prediction",
            "--bundle",
            "private-bundle",
            "--manifest-sha256",
            "a" * 64,
            "--request",
            str(self.request_path),
            "--enrollment-reference",
            "prospect-0001",
        ]
        output = io.StringIO()
        with (
            patch("sys.argv", argv),
            patch.object(capture, "prepare_private_root"),
            patch.object(capture, "capture_prediction", return_value=private_receipt),
            redirect_stdout(output),
        ):
            self.assertEqual(capture.main(), 0)
        public = json.loads(output.getvalue())
        self.assertEqual(public["receipt_id"], "receipt-1")
        self.assertNotIn("request", public)
        self.assertNotIn("request_sha256", public)
        self.assertNotIn("response_sha256", public)
        serialized = output.getvalue()
        for secret in ("bedrooms", "zipcode", "98103", "prospect-0001"):
            self.assertNotIn(secret, serialized)

        error_output = io.StringIO()
        output = io.StringIO()
        with (
            patch("sys.argv", argv),
            patch.object(capture, "prepare_private_root"),
            patch.object(
                capture, "capture_prediction", side_effect=ValueError("bad request")
            ),
            redirect_stdout(output),
            redirect_stderr(error_output),
        ):
            self.assertEqual(capture.main(), 2)
        self.assertEqual(output.getvalue(), "")
        self.assertIn("bad request", error_output.getvalue())

        with (
            patch.object(capture, "PRIVATE_ROOT", self.private_root),
            patch.object(capture.os, "link", side_effect=OSError("injected")),
        ):
            with self.assertRaisesRegex(OSError, "injected"):
                capture.capture_prediction(
                    bundle=Path("private-bundle"),
                    manifest_sha256="a" * 64,
                    request_path=self.request_path,
                    enrollment_reference="prospect-0001",
                    fhfa_source=None,
                    clock=lambda: NOW,
                    predictor=lambda *_args: RESPONSE,
                    code_state=lambda: ("c" * 40, False),
                    privacy_nonce_factory=lambda: "1" * 64,
                )
        self.assertEqual(list(self.private_root.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
