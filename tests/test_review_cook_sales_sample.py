"""Synthetic contract tests for the private Cook source-review ledger."""

from __future__ import annotations

from contextlib import redirect_stdout
from datetime import datetime, timezone
from hashlib import sha256
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import review_cook_sales_sample as review


CAPTURE_COMPLETED_AT = "2026-10-03T00:42:14.862412Z"


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def finding(value: str = "unknown", *ids: str) -> dict:
    return {
        "value": value,
        "evidence_ids": list(ids or ("source",)),
        "limitation": "Checked material does not establish this fact"
        if value == "unknown"
        else None,
    }


class CookReviewLedgerTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.raw = Path(temporary.name) / "data" / "raw" / "cook_county"
        self.raw.mkdir(parents=True)
        self.capture = self.raw / "synthetic-capture"
        self.capture.mkdir()
        self.rows = [
            {
                "row_id": "PRIVATE-ROW-ONE",
                "pin": "00000000000001",
                "doc_no": "PRIVATE-DOC",
                "sale_price": "100000",
                "is_multisale": True,
            },
            {
                "row_id": "PRIVATE-ROW-TWO",
                "pin": "00000000000002",
                "doc_no": "PRIVATE-DOC",
                "sale_price": "0",
                "is_multisale": True,
            },
        ]
        self.cell = type("Cell", (), {"slug": "synthetic"})()
        for index, row in enumerate(self.rows):
            (self.capture / f"rows-synthetic-{index}.json").write_text(
                json.dumps([row]), encoding="utf-8"
            )
        self.manifest_path = self.capture / "manifest.json"
        self.write_capture_manifest([row["row_id"] for row in self.rows])
        self.metadata_path = self.capture / "metadata-before.json"
        self.metadata_path.write_bytes(b'{"columns": [{"fieldName": "sale_price"}]}')
        self.metadata_sha = sha256(self.metadata_path.read_bytes()).hexdigest()
        self.review_dir = self.raw / "manual-review-v1"
        self.ledger = self.review_dir / "reviews.jsonl"
        self.review_time = None
        self.patches = (
            patch.object(review, "RAW_ROOT", self.raw),
            patch.object(review, "CAPTURE_NAME", self.capture.name),
            patch.object(review, "CAPTURE_SHA256", self.capture_sha),
            patch.object(review, "SOURCE_METADATA_SHA256", self.metadata_sha),
            patch.object(review, "SAMPLE_COUNT", 2),
            patch.object(review.capture, "CELLS", (self.cell,)),
            patch.object(
                review.capture,
                "verify_capture",
                return_value={"sample_rows": 2, "historical_asof_eligible": False},
            ),
            patch.object(review.private_io, "secure_directory"),
            patch.object(review.private_io, "verify_acl"),
        )
        for setting in self.patches:
            setting.start()
            self.addCleanup(setting.stop)

    def write_capture_manifest(self, row_ids: list[str]) -> None:
        self.manifest_path.write_text(
            json.dumps(
                {
                    "sample_row_ids": row_ids,
                    "capture_status": "complete",
                    "completed_at": CAPTURE_COMPLETED_AT,
                }
            ),
            encoding="utf-8",
        )
        self.capture_sha = sha256(self.manifest_path.read_bytes()).hexdigest()

    def initialize(self) -> dict:
        result = review.init_review()
        self.identity = json.loads(
            (self.review_dir / "manifest.json").read_text(encoding="utf-8")
        )["ledger_id"]
        self.review_time = now_utc()
        return result

    def evidence(self, *, include_attempt: bool = False) -> list[dict]:
        assert self.review_time is not None
        items = [
            {
                "evidence_id": "source",
                "kind": "source_record",
                "reference": "sha256:" + review.row_hash(self.rows[0]),
                "observed_at": self.review_time,
            },
            {
                "evidence_id": "definition",
                "kind": "official_documentation",
                "reference": "sha256:" + self.metadata_sha,
                "observed_at": self.review_time,
            },
        ]
        if include_attempt:
            items.append(
                {
                    "evidence_id": "attempt",
                    "kind": "unavailable_attempt",
                    "reference": "https://example.org/official/clerk",
                    "observed_at": self.review_time,
                    "attempted_at": self.review_time,
                    "target": "recorded_instrument",
                    "outcome": "access_unavailable",
                }
            )
        return items

    def entry(
        self,
        *,
        status: str = "partial",
        entry_id: str = "review-one",
        revision: int = 1,
        supersedes: str | None = None,
        evidence: list[dict] | None = None,
        rubric: dict | None = None,
    ) -> dict:
        assert self.review_time is not None
        return {
            "entry_id": entry_id,
            "ledger_id": self.identity,
            "protocol": review.PROTOCOL,
            "capture_sha256": self.capture_sha,
            "ordinal": 1,
            "row_sha256": review.row_hash(self.rows[0]),
            "revision": revision,
            "supersedes_entry_id": supersedes,
            "review_status": status,
            "reviewer_code": "reviewer-a",
            "reviewed_at": self.review_time,
            "attested": status == "complete",
            "evidence": evidence if evidence is not None else self.evidence(),
            "rubric": rubric
            if rubric is not None
            else {"economic_transfer_scope": finding()},
        }

    def complete_entry(self) -> dict:
        rubric = {
            name: finding("unknown", "source", "attempt") for name in review.DIMENSIONS
        }
        rubric["published_price_state"] = finding(
            "reported_positive", "source", "definition"
        )
        return self.entry(
            status="complete",
            rubric=rubric,
            evidence=self.evidence(include_attempt=True),
        )

    def append(self, entry: dict, *, expected: str | None = None) -> dict:
        prior = expected or sha256(self.ledger.read_bytes()).hexdigest()
        return review.append_review(entry, expected_ledger_sha256=prior)

    def test_init_binds_exact_capture_and_creates_private_worklist(self) -> None:
        result = self.initialize()
        manifest = json.loads((self.review_dir / "manifest.json").read_text())
        worklist = [
            json.loads(line)
            for line in (self.review_dir / "worklist.jsonl").read_text().splitlines()
        ]
        self.assertEqual(result["sample_count"], 2)
        self.assertEqual(result["complete_records"], 0)
        self.assertEqual(result["certified_sale_labels"], 0)
        self.assertEqual(manifest["capture_sha256"], self.capture_sha)
        self.assertEqual([row["ordinal"] for row in worklist], [1, 2])
        self.assertEqual(
            [row["row_sha256"] for row in worklist],
            [review.row_hash(row) for row in self.rows],
        )
        self.assertEqual(
            [row["priority_flags"] for row in worklist],
            [["multisale", "repeated_document"]] * 2,
        )
        self.assertEqual(self.ledger.read_bytes(), b"")
        with self.assertRaises(FileExistsError):
            review.init_review()

    def test_changed_capture_hash_or_membership_blocks_init(self) -> None:
        self.write_capture_manifest(["PRIVATE-ROW-TWO", "PRIVATE-ROW-ONE"])
        with self.assertRaises(ValueError):
            review.init_review()
        with patch.object(review, "CAPTURE_SHA256", self.capture_sha):
            with self.assertRaises(ValueError):
                review.init_review()
        self.assertFalse(self.review_dir.exists())

    def test_capture_completion_must_match_frozen_chronology_constant(self) -> None:
        self.manifest_path.write_text(
            json.dumps(
                {
                    "sample_row_ids": [row["row_id"] for row in self.rows],
                    "capture_status": "complete",
                    "completed_at": "2026-10-03T00:40:00Z",
                }
            ),
            encoding="utf-8",
        )
        changed_hash = sha256(self.manifest_path.read_bytes()).hexdigest()
        with patch.object(review, "CAPTURE_SHA256", changed_hash):
            with self.assertRaises(ValueError):
                review.init_review()
        self.assertFalse(self.review_dir.exists())

    def test_swapped_or_duplicate_rows_block_init(self) -> None:
        (self.capture / "rows-synthetic-1.json").write_text(json.dumps([self.rows[0]]))
        with self.assertRaises(ValueError):
            review.init_review()
        self.assertFalse(self.review_dir.exists())

    def test_partial_append_and_replay_keep_identifiers_private(self) -> None:
        self.initialize()
        result = self.append(self.entry())
        self.assertEqual(result["partial_records"], 1)
        self.assertEqual(result["unreviewed_records"], 1)
        self.assertEqual(result, review.summarize_reviews())
        public = json.dumps(result)
        for secret in (
            "PRIVATE-ROW",
            "PRIVATE-DOC",
            "review-one",
            "reviewer-a",
            "ordinal",
            "pin",
        ):
            self.assertNotIn(secret, public)

    def test_complete_requires_attestation_full_rubric_and_checked_attempt(
        self,
    ) -> None:
        self.initialize()
        result = self.append(self.complete_entry())
        self.assertEqual(result["complete_records"], 1)
        self.assertEqual(result["certified_sale_labels"], 0)
        missing = self.complete_entry()
        missing["evidence"] = self.evidence()
        with self.assertRaises(ValueError):
            review.validate_entry(missing, self.rows[0], self.identity, [])
        missing = self.complete_entry()
        missing["attested"] = False
        with self.assertRaises(ValueError):
            review.validate_entry(missing, self.rows[0], self.identity, [])
        asserted_instrument = self.complete_entry()
        asserted_instrument["evidence"][2] = {
            "evidence_id": "attempt",
            "kind": "recorded_instrument",
            "reference": "https://example.org/official/unverified-instrument",
            "observed_at": self.review_time,
        }
        with self.assertRaises(ValueError):
            review.validate_entry(asserted_instrument, self.rows[0], self.identity, [])

    def test_source_only_cannot_affirm_transfer_close_or_publication(self) -> None:
        self.initialize()
        for dimension, value in (
            ("economic_transfer_scope", "single_property"),
            ("sale_date_vs_closing", "same"),
            ("first_row_availability", "first_publication_verified"),
            ("arm_length_status", "qualified"),
        ):
            with self.subTest(dimension=dimension):
                entry = self.entry(rubric={dimension: finding(value, "source")})
                with self.assertRaises(ValueError):
                    self.append(entry)

    def test_unsampled_ordinal_and_wrong_row_hash_fail(self) -> None:
        self.initialize()
        wrong = self.entry()
        wrong["ordinal"] = 3
        with self.assertRaises(ValueError):
            self.append(wrong)
        wrong = self.entry()
        wrong["row_sha256"] = "f" * 64
        with self.assertRaises(ValueError):
            self.append(wrong)

    def test_published_price_state_must_match_pinned_row_and_cite_definition(
        self,
    ) -> None:
        self.initialize()
        wrong = self.entry(
            rubric={
                "published_price_state": finding(
                    "reported_zero", "source", "definition"
                )
            }
        )
        with self.assertRaises(ValueError):
            self.append(wrong)
        missing_definition = self.entry(
            rubric={"published_price_state": finding("reported_positive", "source")}
        )
        with self.assertRaises(ValueError):
            self.append(missing_definition)
        fake_definition = self.entry(
            rubric={
                "published_price_state": finding(
                    "reported_positive", "source", "definition"
                )
            }
        )
        fake_definition["evidence"][1]["reference"] = (
            "https://example.org/official-looking/definition"
        )
        with self.assertRaises(ValueError):
            self.append(fake_definition)
        valid = self.entry(
            rubric={
                "published_price_state": finding(
                    "reported_positive", "source", "definition"
                )
            }
        )
        self.assertEqual(self.append(valid)["partial_records"], 1)

    def test_unknown_requires_limitation_and_evidence_reference(self) -> None:
        self.initialize()
        missing = self.entry()
        missing["rubric"]["economic_transfer_scope"]["limitation"] = ""
        with self.assertRaises(ValueError):
            self.append(missing)
        missing = self.entry()
        missing["rubric"]["economic_transfer_scope"]["evidence_ids"] = ["absent"]
        with self.assertRaises(ValueError):
            self.append(missing)

    def test_revision_and_compare_and_swap_preserve_history(self) -> None:
        self.initialize()
        first = self.entry()
        self.append(first)
        old_hash = sha256(b"").hexdigest()
        with self.assertRaises(ValueError):
            self.append(self.entry(entry_id="wrong-hash"), expected=old_hash)
        with self.assertRaises(ValueError):
            self.append(self.entry(entry_id="duplicate"))
        second = self.entry(entry_id="review-two", revision=2, supersedes="review-one")
        self.assertEqual(self.append(second)["partial_records"], 1)
        self.assertEqual(len(self.ledger.read_text().splitlines()), 2)

    def test_truncated_history_and_orphan_init_never_self_repair(self) -> None:
        self.initialize()
        self.ledger.write_bytes(b'{"truncated":')
        before = self.ledger.read_bytes()
        with self.assertRaises(ValueError):
            review.summarize_reviews()
        self.assertEqual(self.ledger.read_bytes(), before)
        with self.assertRaises(FileExistsError):
            review.init_review()

    def test_orphan_review_directory_is_preserved(self) -> None:
        self.review_dir.mkdir()
        marker = self.review_dir / "manifest.json"
        marker.write_bytes(b"incomplete-init")
        with self.assertRaises(FileExistsError):
            review.init_review()
        self.assertEqual(marker.read_bytes(), b"incomplete-init")

    def test_future_review_time_and_unstructured_attempt_fail(self) -> None:
        self.initialize()
        entry = self.entry()
        entry["reviewed_at"] = "2999-01-01T00:00:00Z"
        with self.assertRaises(ValueError):
            self.append(entry)
        entry = self.complete_entry()
        del entry["evidence"][2]["attempted_at"]
        with self.assertRaises(ValueError):
            self.append(entry)

    def test_malformed_evidence_and_rubric_fail_cleanly(self) -> None:
        self.initialize()
        invalid = self.entry()
        invalid["evidence"][0]["kind"] = ["source_record"]
        with self.assertRaises(ValueError):
            self.append(invalid)
        invalid = self.entry()
        invalid["rubric"]["economic_transfer_scope"]["evidence_ids"] = [["source"]]
        with self.assertRaises(ValueError):
            self.append(invalid)
        invalid = self.entry()
        invalid["evidence"][1]["reference"] = "http://insecure.example/definition"
        with self.assertRaises(ValueError):
            self.append(invalid)
        invalid = self.entry()
        invalid["evidence"][0]["reference"] = "sha256:" + "0" * 64
        with self.assertRaises(ValueError):
            self.append(invalid)

    def test_tampered_worklist_and_malformed_ledger_block_replay(self) -> None:
        self.initialize()
        worklist = self.review_dir / "worklist.jsonl"
        original = worklist.read_bytes()
        worklist.write_bytes(original + b"tampered")
        with self.assertRaises(ValueError):
            review.summarize_reviews()
        worklist.write_bytes(original)
        for payload in (b"[]\n", b'{"entry_id": []}\n'):
            with self.subTest(payload=payload):
                self.ledger.write_bytes(payload)
                with self.assertRaises(ValueError):
                    review.summarize_reviews()

    def test_tampered_pinned_metadata_blocks_init(self) -> None:
        self.metadata_path.write_bytes(b"changed official metadata")
        with self.assertRaises(ValueError):
            review.init_review()
        self.assertFalse(self.review_dir.exists())

    def test_review_and_source_observation_cannot_predate_capture_or_ledger(
        self,
    ) -> None:
        self.initialize()
        early = self.entry()
        early["reviewed_at"] = "2026-10-02T00:00:00Z"
        early["evidence"][0]["observed_at"] = "2026-10-02T00:00:00Z"
        with self.assertRaises(ValueError):
            self.append(early)
        before_ledger = self.entry()
        before_ledger["reviewed_at"] = CAPTURE_COMPLETED_AT
        before_ledger["evidence"][0]["observed_at"] = CAPTURE_COMPLETED_AT
        before_ledger["evidence"][1]["observed_at"] = CAPTURE_COMPLETED_AT
        with self.assertRaises(ValueError):
            self.append(before_ledger)
        source_predates_capture = self.entry()
        source_predates_capture["evidence"][0]["observed_at"] = "2026-10-02T00:00:00Z"
        with self.assertRaises(ValueError):
            self.append(source_predates_capture)
        metadata_predates_capture = self.entry()
        metadata_predates_capture["evidence"][1]["observed_at"] = "2026-10-02T00:00:00Z"
        with self.assertRaises(ValueError):
            self.append(metadata_predates_capture)

    def test_existing_lock_and_atomic_write_failure_preserve_ledger(self) -> None:
        self.initialize()
        lock = self.review_dir / "reviews.jsonl.lock"
        lock.write_bytes(b"occupied")
        with self.assertRaises(FileExistsError):
            review.summarize_reviews()
        self.assertEqual(lock.read_bytes(), b"occupied")
        lock.unlink()
        with patch.object(
            review.private_io, "atomic_replace", side_effect=OSError("disk")
        ):
            with self.assertRaises(OSError):
                self.append(self.entry())
        self.assertEqual(self.ledger.read_bytes(), b"")

    def test_cli_init_append_and_replay_write_new_public_summaries(self) -> None:
        first = self.raw.parent.parent.parent / "first-summary.json"
        second = self.raw.parent.parent.parent / "second-summary.json"
        third = self.raw.parent.parent.parent / "third-summary.json"
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(review.main(["init", "--output", str(first)]), 0)
        self.identity = json.loads((self.review_dir / "manifest.json").read_text())[
            "ledger_id"
        ]
        self.review_time = now_utc()
        self.assertEqual(json.loads(first.read_text())["complete_records"], 0)
        candidate = self.review_dir / "candidate.json"
        candidate.write_text(json.dumps(self.entry()), encoding="utf-8")
        with redirect_stdout(output):
            self.assertEqual(
                review.main(
                    [
                        "append",
                        "--entry",
                        str(candidate),
                        "--expected-ledger-sha256",
                        sha256(b"").hexdigest(),
                        "--output",
                        str(second),
                    ]
                ),
                0,
            )
            self.assertEqual(review.main(["summary", "--output", str(third)]), 0)
        self.assertEqual(json.loads(second.read_text()), json.loads(third.read_text()))
        self.assertNotIn("PRIVATE-ROW", output.getvalue())
        self.assertNotIn("PRIVATE-DOC", output.getvalue())
        self.assertEqual(review.main(["summary", "--output", str(third)]), 1)

    def test_private_hardlink_and_unverified_acl_fail(self) -> None:
        self.initialize()
        with patch.object(
            review.private_io, "verify_acl", side_effect=ValueError("ACL")
        ):
            with self.assertRaises(ValueError):
                review.summarize_reviews()
        self.ledger.unlink()
        os.link(self.manifest_path, self.ledger)
        with self.assertRaises(ValueError):
            review.summarize_reviews()


if __name__ == "__main__":
    unittest.main()
