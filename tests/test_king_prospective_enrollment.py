"""One-action contract for private King enrollment and public commitment."""

from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from scripts import capture_king_prediction as capture
from scripts import prepare_king_receipt_commitment as commitment
from tests.test_capture_king_prediction import NOW, REQUEST, RESPONSE

try:
    from scripts import king_prospective_enrollment as enrollment
except ImportError:
    enrollment = None


COMMITTED_AT = datetime(2026, 10, 5, 19, 30, tzinfo=UTC)


class KingProspectiveEnrollmentTests(unittest.TestCase):
    def setUp(self) -> None:
        if enrollment is None:
            self.fail(
                "scripts.king_prospective_enrollment must provide the one-action "
                "prospective enrollment coordinator"
            )
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.private_root = self.root / "private"
        self.public_root = self.root / "public"
        self.private_root.mkdir()
        self.public_root.mkdir()
        self.predictor = Mock(return_value=RESPONSE)

    def enroll(self, privacy_nonce: str = "1" * 64):
        return enrollment.enroll_prediction(
            bundle=Path("already-loaded-private-bundle"),
            manifest_sha256="a" * 64,
            request=REQUEST,
            enrollment_reference="prospect-0001",
            fhfa_source=None,
            private_root=self.private_root,
            public_output_dir=self.public_root,
            predictor=self.predictor,
            code_state=lambda: ("c" * 40, False),
            capture_clock=lambda: NOW,
            commitment_clock=lambda: COMMITTED_AT,
            privacy_nonce_factory=lambda: privacy_nonce,
        )

    def assert_no_staging_files(self) -> None:
        names = {path.name for path in self.root.rglob("*") if path.is_file()}
        self.assertTrue(all(not name.startswith(".") for name in names), names)
        self.assertTrue(
            all("request" not in name.lower() for name in names),
            names,
        )

    def test_one_prediction_creates_matching_private_receipt_and_public_commitment(
        self,
    ) -> None:
        with patch.object(
            capture, "prepare_private_root", wraps=capture.prepare_private_root
        ) as prepare:
            result = self.enroll()

        self.predictor.assert_called_once()
        prepare.assert_called_once_with(self.private_root)
        private_files = list(self.private_root.glob("*.json"))
        public_files = list(self.public_root.glob("*.json"))
        self.assertEqual(len(private_files), 1)
        self.assertEqual(len(public_files), 1)

        receipt_path = private_files[0]
        commitment_path = public_files[0]
        receipt_raw = receipt_path.read_bytes()
        receipt = json.loads(receipt_raw)
        published = json.loads(commitment_path.read_text(encoding="utf-8"))
        self.assertEqual(receipt_raw, capture.canonical_bytes(receipt))
        self.assertEqual(
            commitment_path.read_bytes(), commitment.canonical_bytes(published)
        )
        self.assertEqual(published["receipt_sha256"], sha256(receipt_raw).hexdigest())
        self.assertEqual(published["receipt_bytes"], len(receipt_raw))
        self.assertEqual(published["manifest_sha256"], receipt["manifest_sha256"])
        self.assertEqual(published["model_sha256"], receipt["model_sha256"])
        self.assertEqual(result.receipt_path, receipt_path)
        self.assertEqual(result.commitment_path, commitment_path)

        serialized = commitment_path.read_text(encoding="utf-8")
        forbidden = (
            "request",
            "request_sha256",
            "request_raw_sha256",
            "response_sha256",
            "enrollment_reference_sha256",
            "receipt_id",
            receipt["receipt_id"],
            receipt["request_sha256"],
            receipt["response_sha256"],
            str(RESPONSE["amount"]),
            "bedrooms",
            "zipcode",
            "98103",
            "prospect-0001",
        )
        for private_value in forbidden:
            self.assertNotIn(str(private_value), serialized)
        self.assert_no_staging_files()

    def test_existing_exact_commitment_is_an_idempotent_commit_only_retry(self) -> None:
        result = self.enroll()
        before = result.commitment_path.read_bytes()

        retried = enrollment.commit_saved_receipt(
            result.receipt_path,
            self.public_root,
            clock=lambda: datetime(2030, 1, 1, tzinfo=UTC),
        )

        self.predictor.assert_called_once()
        self.assertEqual(retried.commitment_path, result.commitment_path)
        self.assertEqual(retried.commitment_path.read_bytes(), before)
        self.assertEqual(len(list(self.public_root.glob("*.json"))), 1)

    def test_pending_discovery_ignores_legacy_and_returns_only_uncommitted_v2(
        self,
    ) -> None:
        committed = self.enroll()
        pending = self.enroll("2" * 64)
        pending.commitment_path.unlink()
        legacy_path = self.private_root / "retained-legacy-v1.json"
        legacy_path.write_bytes(
            commitment.canonical_bytes(
                {"protocol": "king-research-prospective-receipt-v1"}
            )
        )

        discovered = enrollment.find_pending_receipts(
            self.private_root, self.public_root
        )

        self.assertEqual(discovered, (pending.receipt_path,))
        self.assertNotIn(committed.receipt_path, discovered)
        self.assertNotIn(legacy_path, discovered)

    def test_result_verifier_rejects_malformed_public_artifact(self) -> None:
        result = self.enroll()
        self.assertTrue(
            enrollment.verify_commitment_result(result, result.receipt_path)
        )

        result.commitment_path.write_text("{}", encoding="utf-8")

        self.assertFalse(
            enrollment.verify_commitment_result(result, result.receipt_path)
        )

    def test_pending_discovery_rejects_unknown_receipt_protocol(self) -> None:
        unknown = self.private_root / "unknown.json"
        unknown.write_bytes(
            commitment.canonical_bytes({"protocol": "unknown-receipt-v9"})
        )

        with self.assertRaisesRegex(ValueError, "protocol is unknown"):
            enrollment.find_pending_receipts(self.private_root, self.public_root)

    def test_lost_postpublication_ack_preserves_receipt_and_retries_idempotently(
        self,
    ) -> None:
        with patch.object(
            enrollment,
            "_commitment_path",
            side_effect=OSError("injected acknowledgement failure"),
        ):
            with self.assertRaises(enrollment.EnrollmentCommitmentPending) as raised:
                self.enroll()

        self.predictor.assert_called_once()
        self.assertEqual(len(list(self.private_root.glob("*.json"))), 1)
        self.assertEqual(len(list(self.public_root.glob("*.json"))), 1)

        retried = enrollment.commit_saved_receipt(
            raised.exception.receipt_path,
            self.public_root,
            clock=lambda: datetime(2030, 1, 1, tzinfo=UTC),
        )

        self.predictor.assert_called_once()
        self.assertTrue(retried.commitment_path.is_file())
        self.assertEqual(len(list(self.public_root.glob("*.json"))), 1)

    def test_capture_failure_creates_neither_artifact_and_cleans_request_staging(
        self,
    ) -> None:
        self.predictor.side_effect = ValueError("injected prediction failure")

        with self.assertRaisesRegex(ValueError, "injected prediction failure"):
            self.enroll()

        self.predictor.assert_called_once()
        self.assertEqual(list(self.private_root.iterdir()), [])
        self.assertEqual(list(self.public_root.iterdir()), [])
        self.assert_no_staging_files()

    def test_commitment_failure_retains_receipt_for_commit_only_retry(self) -> None:
        with patch.object(
            commitment, "_publish", side_effect=OSError("injected publication failure")
        ):
            with self.assertRaises(enrollment.EnrollmentCommitmentPending) as raised:
                self.enroll()

        self.predictor.assert_called_once()
        private_files = list(self.private_root.glob("*.json"))
        self.assertEqual(private_files, [raised.exception.receipt_path])
        self.assertEqual(list(self.public_root.iterdir()), [])
        receipt_raw = private_files[0].read_bytes()
        receipt = json.loads(receipt_raw)
        self.assertEqual(receipt_raw, capture.canonical_bytes(receipt))
        commitment._validate_receipt(receipt)
        self.assert_no_staging_files()

        retried = enrollment.commit_saved_receipt(
            raised.exception.receipt_path,
            self.public_root,
            clock=lambda: COMMITTED_AT,
        )

        self.predictor.assert_called_once()
        public_files = list(self.public_root.glob("*.json"))
        self.assertEqual(len(public_files), 1)
        published = json.loads(public_files[0].read_text(encoding="utf-8"))
        self.assertEqual(published["receipt_sha256"], sha256(receipt_raw).hexdigest())
        self.assertEqual(retried.commitment_path, public_files[0])
        self.assertEqual(retried.receipt_path, raised.exception.receipt_path)
        self.assert_no_staging_files()


if __name__ == "__main__":
    unittest.main()
