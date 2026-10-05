"""Contract tests for privacy-safe public King receipt commitments."""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from contextlib import redirect_stderr, redirect_stdout

from scripts import capture_king_prediction as capture
from scripts import prepare_king_receipt_commitment as commitment
from tests.test_capture_king_prediction import NOW, REQUEST, RESPONSE


class KingReceiptCommitmentTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.private_root = self.root / "private"
        self.output_dir = self.root / "public"
        self.private_root.mkdir()
        self.output_dir.mkdir()
        request_path = self.root / "request.json"
        request_path.write_text(json.dumps(REQUEST), encoding="utf-8")
        with patch.object(capture, "PRIVATE_ROOT", self.private_root):
            receipt = capture.capture_prediction(
                bundle=Path("bundle"),
                manifest_sha256="a" * 64,
                request_path=request_path,
                enrollment_reference="private-enrollment-0001",
                fhfa_source=None,
                clock=lambda: NOW,
                predictor=lambda *_args: RESPONSE,
                code_state=lambda: ("c" * 40, False),
                privacy_nonce_factory=lambda: "1" * 64,
            )
        self.receipt = self.private_root / f"{receipt['receipt_id']}.json"

    def prepare(self) -> dict[str, object]:
        return commitment.prepare_public_commitment(
            self.receipt,
            self.output_dir,
            clock=lambda: datetime(2026, 10, 5, 19, 30, tzinfo=UTC),
        )

    def test_prepares_one_canonical_private_free_commitment(self) -> None:
        result = self.prepare()
        expected_path = self.output_dir / (
            f"king-research-commitment-{result['receipt_sha256']}.json"
        )
        self.assertEqual(expected_path.read_bytes(), commitment.canonical_bytes(result))
        self.assertEqual(
            result["receipt_sha256"], sha256(self.receipt.read_bytes()).hexdigest()
        )
        self.assertEqual(result["receipt_bytes"], self.receipt.stat().st_size)
        self.assertEqual(result["protocol"], "king-research-public-commitment-v1")
        self.assertEqual(result["scope"], "public_integrity_commitment_only")
        self.assertFalse(result["certification_eligible"])
        self.assertFalse(result["external_timestamped"])
        self.assertEqual(result["g_us_gate"], "PENDING")
        serialized = expected_path.read_text(encoding="utf-8")
        private_receipt = json.loads(self.receipt.read_text(encoding="utf-8"))
        forbidden = (
            "request",
            "request_sha256",
            "request_raw_sha256",
            "enrollment_reference_sha256",
            "response_sha256",
            "prediction_captured_at_utc",
            "receipt_id",
            private_receipt["request_sha256"],
            private_receipt["enrollment_reference_sha256"],
            private_receipt["receipt_id"],
            private_receipt["response_sha256"],
            str(RESPONSE["amount"]),
            "bedrooms",
            "zipcode",
            "98103",
        )
        for value in forbidden:
            self.assertNotIn(str(value), serialized)
        with self.assertRaises(FileExistsError):
            self.prepare()

    def test_rejects_tampered_or_noncanonical_receipt_without_output(self) -> None:
        original = json.loads(self.receipt.read_text(encoding="utf-8"))
        cases = (
            {**original, "request": {**original["request"], "bedrooms": 9}},
            {**original, "response_sha256": "d" * 64},
            {**original, "receipt_id": "wrong"},
            {**original, "certification_eligible": True},
            {**original, "extra": "field"},
        )
        for index, value in enumerate(cases):
            with self.subTest(index=index):
                self.receipt.write_bytes(capture.canonical_bytes(value))
                with self.assertRaises(ValueError):
                    self.prepare()
                self.assertEqual(list(self.output_dir.iterdir()), [])
                self.receipt.write_bytes(capture.canonical_bytes(original))

        confused = {**original}
        confused_raw = original["request_raw_utf8"].replace(
            '"waterfront": 0', '"waterfront": false'
        )
        self.assertNotEqual(confused_raw, original["request_raw_utf8"])
        confused["request_raw_utf8"] = confused_raw
        confused["request_raw_sha256"] = sha256(confused_raw.encode()).hexdigest()
        confused["request_bytes"] = len(confused_raw.encode())
        self.receipt.write_bytes(capture.canonical_bytes(confused))
        with self.assertRaises(ValueError):
            self.prepare()
        self.assertEqual(list(self.output_dir.iterdir()), [])
        self.receipt.write_bytes(capture.canonical_bytes(original))

        self.receipt.write_text(json.dumps(original, indent=2), encoding="utf-8")
        with self.assertRaises(ValueError):
            self.prepare()
        self.assertEqual(list(self.output_dir.iterdir()), [])

    def test_publish_failure_cleans_incomplete_output(self) -> None:
        with patch.object(commitment.os, "link", side_effect=OSError("injected")):
            with self.assertRaisesRegex(OSError, "injected"):
                self.prepare()
        self.assertEqual(list(self.output_dir.iterdir()), [])

    def test_concurrent_publishers_create_one_complete_commitment(self) -> None:
        barrier = threading.Barrier(2)
        results: list[dict[str, object]] = []
        errors: list[BaseException] = []

        def worker() -> None:
            try:
                barrier.wait(timeout=2)
                results.append(self.prepare())
            except BaseException as error:
                errors.append(error)

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=3)
        self.assertTrue(all(not thread.is_alive() for thread in threads))
        self.assertEqual(len(results), 1)
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], FileExistsError)
        files = list(self.output_dir.iterdir())
        self.assertEqual(len(files), 1)
        self.assertEqual(json.loads(files[0].read_text()), results[0])

    def test_cli_output_is_public_and_failure_is_controlled(self) -> None:
        argv = [
            "prepare_king_receipt_commitment",
            "--receipt",
            str(self.receipt),
            "--output-dir",
            str(self.output_dir),
        ]
        output = io.StringIO()
        with patch("sys.argv", argv), redirect_stdout(output):
            self.assertEqual(commitment.main(), 0)
        public = json.loads(output.getvalue())
        self.assertEqual(public["protocol"], "king-research-public-commitment-v1")
        for forbidden in ("request", "bedrooms", "zipcode", "receipt_id"):
            self.assertNotIn(forbidden, output.getvalue())

        output = io.StringIO()
        error = io.StringIO()
        with (
            patch("sys.argv", argv),
            redirect_stdout(output),
            redirect_stderr(error),
        ):
            self.assertEqual(commitment.main(), 2)
        self.assertEqual(output.getvalue(), "")
        self.assertIn("unavailable", error.getvalue().lower())
        self.assertNotIn(str(self.receipt), error.getvalue())


if __name__ == "__main__":
    unittest.main()
