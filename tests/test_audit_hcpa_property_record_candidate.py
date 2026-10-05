"""RED contracts for one private HCPA property-record candidate checkpoint."""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from hashlib import sha256
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tests.test_hcpa_property_record_pdf import flate_pdf

try:
    from scripts import audit_hcpa_property_record_candidate as candidate_audit
except ImportError:
    candidate_audit = None


PIN = "U-12-34-56-ABC-DEF123-GHIJK.L"
STRAP = "563412ABCDEF123GHIJKLU"
DOCUMENT = "SYN-DOC-700"
OBSERVED_AT = "2026-10-05T20:00:00Z"
CANDIDATE_KEYS = {
    "protocol",
    "pdf_sha256",
    "pdf_bytes",
    "sample_sha256",
    "sample_bytes",
    "record_ordinal",
    "observed_at",
    "document_identity",
    "parcel_unit_identity",
    "property_class",
    "qualification_code",
    "candidate_only",
    "attested",
    "ledger_appended",
    "model_eligible",
    "date_semantics",
    "consideration_scope",
    "historical_availability",
    "reuse_rights",
}
STATE_FIELDS = (
    "document_identity",
    "parcel_unit_identity",
    "property_class",
    "qualification_code",
)


def sample_row(**changes: object) -> dict[str, object]:
    return {
        "record_ordinal": 7,
        "PIN": PIN,
        "DOC_NUM": DOCUMENT,
        "DOR_CODE": "0100",
        "QU": "U",
        **changes,
    }


def jsonl(*rows: dict[str, object]) -> bytes:
    return "".join(
        json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in rows
    ).encode("utf-8")


def property_pdf() -> bytes:
    return flate_pdf(
        (
            "BT (Parcel ID) Tj "
            f"({STRAP}) Tj "
            "(Document Number) Tj "
            f"({DOCUMENT}) Tj "
            "(DOR Code) Tj (0100) Tj "
            "(Qualification) Tj (U) Tj ET"
        ).encode("ascii")
    )


class HcpaPropertyRecordCandidateTests(unittest.TestCase):
    def setUp(self) -> None:
        if candidate_audit is None:
            self.fail(
                "scripts.audit_hcpa_property_record_candidate must implement "
                "the private candidate checkpoint"
            )
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        acl = patch.object(candidate_audit, "verify_acl", return_value=None)
        acl.start()
        self.addCleanup(acl.stop)
        self.private_root = self.root / "data" / "raw" / "hcpa"
        self.public_root = self.root / "runs"
        self.private_root.mkdir(parents=True)
        self.public_root.mkdir()
        self.pdf = property_pdf()
        self.sample = jsonl(sample_row())
        self.pdf_sha = sha256(self.pdf).hexdigest()
        self.sample_sha = sha256(self.sample).hexdigest()

    def build(self, **changes: object) -> dict[str, object]:
        arguments = {
            "pdf_bytes": self.pdf,
            "pdf_sha256": self.pdf_sha,
            "sample_bytes": self.sample,
            "sample_sha256": self.sample_sha,
            "record_ordinal": 7,
            "observed_at": OBSERVED_AT,
            **changes,
        }
        return candidate_audit.build_candidate(**arguments)

    def test_builds_one_closed_private_candidate_without_transaction_claims(
        self,
    ) -> None:
        result = self.build()

        self.assertEqual(set(result), CANDIDATE_KEYS)
        self.assertEqual(result["protocol"], "hcpa-property-record-candidate-v1")
        self.assertEqual(result["pdf_sha256"], self.pdf_sha)
        self.assertEqual(result["pdf_bytes"], len(self.pdf))
        self.assertEqual(result["sample_sha256"], self.sample_sha)
        self.assertEqual(result["sample_bytes"], len(self.sample))
        self.assertEqual(result["record_ordinal"], 7)
        self.assertEqual(result["observed_at"], OBSERVED_AT)
        for field in STATE_FIELDS:
            self.assertEqual(result[field], "match")
        self.assertIs(result["candidate_only"], True)
        for field in ("attested", "ledger_appended", "model_eligible"):
            self.assertIs(result[field], False)
        for field in (
            "date_semantics",
            "consideration_scope",
            "historical_availability",
            "reuse_rights",
        ):
            self.assertEqual(result[field], "unknown")

    def test_rejects_hash_mismatch_malformed_jsonl_and_invalid_target_ordinal(
        self,
    ) -> None:
        duplicate_key = (
            b'{"record_ordinal":7,"record_ordinal":7,"PIN":"synthetic",'
            b'"DOC_NUM":"synthetic","DOR_CODE":"0100","QU":"U"}\n'
        )
        malformed_cases = (
            {"pdf_sha256": "0" * 64},
            {"sample_sha256": "0" * 64},
            {
                "sample_bytes": self.sample.removesuffix(b"\n"),
                "sample_sha256": sha256(self.sample.removesuffix(b"\n")).hexdigest(),
            },
            {
                "sample_bytes": duplicate_key,
                "sample_sha256": sha256(duplicate_key).hexdigest(),
            },
            {"record_ordinal": 0},
            {"record_ordinal": -1},
            {"record_ordinal": True},
            {"record_ordinal": 7.0},
            {"record_ordinal": 8},
        )
        for changes in malformed_cases:
            with self.subTest(changes=changes):
                with self.assertRaises(ValueError):
                    self.build(**changes)

    def test_rejects_missing_fields_duplicate_target_and_non_object_rows(self) -> None:
        for missing in ("PIN", "DOC_NUM", "DOR_CODE", "QU"):
            row = sample_row()
            del row[missing]
            raw = jsonl(row)
            with self.subTest(missing=missing), self.assertRaises(ValueError):
                self.build(sample_bytes=raw, sample_sha256=sha256(raw).hexdigest())

        duplicate = jsonl(sample_row(), sample_row(DOC_NUM="OTHER"))
        with self.assertRaises(ValueError):
            self.build(
                sample_bytes=duplicate,
                sample_sha256=sha256(duplicate).hexdigest(),
            )
        non_object = b"[]\n"
        with self.assertRaises(ValueError):
            self.build(
                sample_bytes=non_object,
                sample_sha256=sha256(non_object).hexdigest(),
            )

    def test_private_candidate_write_is_create_only_and_rejects_links(self) -> None:
        result = self.build()
        destination = self.private_root / "candidate.json"

        candidate_audit.write_private_candidate_new(
            destination, result, self.private_root
        )

        expected = candidate_audit.canonical_bytes(result)
        self.assertEqual(destination.read_bytes(), expected)

        different = self.private_root / "different.json"
        different.write_bytes(b"prior immutable evidence\n")
        with self.assertRaises(FileExistsError):
            candidate_audit.write_private_candidate_new(
                different, result, self.private_root
            )
        self.assertEqual(different.read_bytes(), b"prior immutable evidence\n")
        with self.assertRaises(FileExistsError):
            candidate_audit.write_private_candidate_new(
                destination, result, self.private_root
            )
        self.assertEqual(destination.read_bytes(), expected)

        outside = self.root / "outside.json"
        outside.write_bytes(expected)
        linked = self.private_root / "linked.json"
        try:
            linked.hardlink_to(outside)
        except (OSError, NotImplementedError) as error:
            self.skipTest(f"Hard links unavailable: {error}")
        with self.assertRaises(ValueError):
            candidate_audit.write_private_candidate_new(
                linked, result, self.private_root
            )
        self.assertEqual(outside.read_bytes(), expected)

    def test_aggregate_is_private_free_and_cannot_imply_attestation(self) -> None:
        result = self.build()

        aggregate = candidate_audit.aggregate_candidate(result)

        self.assertEqual(
            set(aggregate),
            {
                "protocol",
                "candidate_protocol",
                "sample_sha256",
                "sample_bytes",
                "candidate_count",
                "state_counts",
            },
        )
        self.assertEqual(aggregate["candidate_count"], 1)
        self.assertEqual(
            aggregate["state_counts"],
            {
                field: {"match": 1, "mismatch": 0, "unknown": 0}
                for field in STATE_FIELDS
            },
        )
        serialized = json.dumps(aggregate, sort_keys=True)
        for forbidden in (
            "record_ordinal",
            "observed_at",
            "attested",
            "ledger_appended",
            "model_eligible",
            PIN,
            STRAP,
            DOCUMENT,
            OBSERVED_AT,
            self.pdf_sha,
            str(self.private_root),
        ):
            self.assertNotIn(forbidden, serialized)

    def test_cli_builds_pinned_create_only_outputs_and_reports_generic_failure(
        self,
    ) -> None:
        pdf_path = self.private_root / "property.pdf"
        sample_path = self.private_root / "sample.jsonl"
        private_output = self.private_root / "candidate.json"
        aggregate_output = self.public_root / "aggregate.json"
        pdf_path.write_bytes(self.pdf)
        sample_path.write_bytes(self.sample)
        argv = [
            "build",
            "--pdf",
            str(pdf_path),
            "--pdf-sha256",
            self.pdf_sha,
            "--sample",
            str(sample_path),
            "--sample-sha256",
            self.sample_sha,
            "--record-ordinal",
            "7",
            "--observed-at",
            OBSERVED_AT,
            "--private-output",
            str(private_output),
            "--aggregate-output",
            str(aggregate_output),
        ]
        output = io.StringIO()
        error = io.StringIO()
        with (
            patch.object(candidate_audit, "PRIVATE_ROOT", self.private_root),
            redirect_stdout(output),
            redirect_stderr(error),
        ):
            self.assertEqual(candidate_audit.main(argv), 0)
        self.assertTrue(private_output.is_file())
        self.assertTrue(aggregate_output.is_file())
        self.assertEqual(error.getvalue(), "")
        self.assertEqual(
            json.loads(output.getvalue()),
            json.loads(aggregate_output.read_text()),
        )

        output = io.StringIO()
        error = io.StringIO()
        with (
            patch.object(candidate_audit, "PRIVATE_ROOT", self.private_root),
            redirect_stdout(output),
            redirect_stderr(error),
        ):
            self.assertEqual(candidate_audit.main(argv), 2)
        self.assertEqual(output.getvalue(), "")
        self.assertIn("unavailable", error.getvalue().lower())
        for private in (
            str(pdf_path),
            str(sample_path),
            str(private_output),
            PIN,
            DOCUMENT,
        ):
            self.assertNotIn(private, error.getvalue())

    def test_cli_recovers_after_aggregate_publication_failure(self) -> None:
        pdf_path = self.private_root / "property.pdf"
        sample_path = self.private_root / "sample.jsonl"
        private_output = self.private_root / "candidate.json"
        aggregate_output = self.public_root / "aggregate.json"
        pdf_path.write_bytes(self.pdf)
        sample_path.write_bytes(self.sample)
        argv = [
            "build",
            "--pdf",
            str(pdf_path),
            "--pdf-sha256",
            self.pdf_sha,
            "--sample",
            str(sample_path),
            "--sample-sha256",
            self.sample_sha,
            "--record-ordinal",
            "7",
            "--observed-at",
            OBSERVED_AT,
            "--private-output",
            str(private_output),
            "--aggregate-output",
            str(aggregate_output),
        ]
        with (
            patch.object(candidate_audit, "PRIVATE_ROOT", self.private_root),
            patch.object(
                candidate_audit,
                "_write_public_new",
                side_effect=OSError("simulated aggregate failure"),
            ),
            redirect_stdout(io.StringIO()),
            redirect_stderr(io.StringIO()),
        ):
            self.assertEqual(candidate_audit.main(argv), 2)
        self.assertTrue(private_output.is_file())
        self.assertFalse(aggregate_output.exists())
        with (
            patch.object(candidate_audit, "PRIVATE_ROOT", self.private_root),
            redirect_stdout(io.StringIO()),
            redirect_stderr(io.StringIO()),
        ):
            self.assertEqual(candidate_audit.main(argv), 0)
        self.assertTrue(aggregate_output.is_file())

    def test_deeply_nested_json_is_a_controlled_input_error(self) -> None:
        nesting = 2_000
        nested = b"[" * nesting + b"0" + b"]" * nesting + b"\n"
        with self.assertRaises(ValueError):
            self.build(
                sample_bytes=nested,
                sample_sha256=sha256(nested).hexdigest(),
            )


if __name__ == "__main__":
    unittest.main()
