"""Synthetic tests for the append-only private HCPA manual-review ledger."""

from __future__ import annotations

from hashlib import sha256
from importlib.util import module_from_spec, spec_from_file_location
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from contextlib import contextmanager, redirect_stdout
from datetime import datetime, timezone


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "review_hcpa_sample.py"
spec = spec_from_file_location("review_hcpa_sample", SCRIPT)
assert spec is not None and spec.loader is not None
review = module_from_spec(spec)
spec.loader.exec_module(review)

HASH = "a" * 64
WHEN = "2026-09-28T12:00:00Z"


def evidence(
    kind: str = "source_record", identifier: str = "source", source_hash: str = HASH
) -> dict:
    reference = (
        "sha256:" + source_hash
        if kind == "source_record"
        else "https://example.org/official/evidence"
    )
    return {
        "evidence_id": identifier,
        "kind": kind,
        "reference": reference,
        "observed_at": WHEN,
    }


def finding(value: str = "unknown", *, identifier: str = "source") -> dict:
    return {
        "value": value,
        "evidence_ids": [identifier],
        "limitation": "No independent record establishes this fact"
        if value == "unknown"
        else None,
    }


def complete_rubric() -> dict:
    return {dimension: finding() for dimension in review.REQUIRED_DIMENSIONS}


class HcpaReviewTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.private = self.root / "data" / "raw" / "hcpa"
        self.private.mkdir(parents=True)
        self.sample = self.private / "sample.jsonl"
        self.ledger = self.private / "reviews.jsonl"
        rows = [
            {"record_ordinal": 1, "PIN": "PRIVATE-ONE", "S_AMT": "123456"},
            {"record_ordinal": 2, "PIN": "PRIVATE-TWO", "S_AMT": "654321"},
            {"record_ordinal": 3, "PIN": "PRIVATE-THREE", "S_AMT": "246810"},
        ]
        self.sample.write_text(
            "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
        )
        self.sample_sha = sha256(self.sample.read_bytes()).hexdigest()

    def entry(
        self,
        *,
        ordinal: int = 1,
        entry_id: str = "review-1",
        revision: int = 1,
        supersedes: str | None = None,
        status: str = "partial",
        rubric: dict | None = None,
        sample_sha: str | None = None,
        evidences: list[dict] | None = None,
    ) -> dict:
        return {
            "entry_id": entry_id,
            "sample_sha256": sample_sha or self.sample_sha,
            "record_ordinal": ordinal,
            "revision": revision,
            "supersedes_entry_id": supersedes,
            "review_status": status,
            "reviewer_code": "reviewer-a",
            "reviewed_at": WHEN,
            "attested": status == "complete",
            "evidence": (
                [
                    evidence(source_hash=self.sample_sha),
                    evidence("unavailable_attempt", "clerk_attempt"),
                ]
                if status == "complete" and evidences is None
                else [evidence(source_hash=self.sample_sha)]
                if evidences is None
                else evidences
            ),
            "rubric": {"document_identity": finding()} if rubric is None else rubric,
        }

    def append(self, entry: dict) -> dict:
        with patch.object(review, "PRIVATE_ROOT", self.private):
            return review.append_review(
                self.sample, self.sample_sha, self.ledger, entry
            )

    def summary(self) -> dict:
        with patch.object(review, "PRIVATE_ROOT", self.private):
            return review.summarize_reviews(self.sample, self.sample_sha, self.ledger)

    def test_partial_append_preserves_sample_and_reports_aggregate_only(self) -> None:
        original = self.sample.read_bytes()
        result = self.append(self.entry())
        self.assertEqual(self.sample.read_bytes(), original)
        self.assertEqual(result["sample_sha256"], self.sample_sha)
        self.assertEqual(result["reviewed_records"], 1)
        self.assertEqual(result["partial_records"], 1)
        self.assertEqual(result["complete_records"], 0)
        self.assertEqual(result["unreviewed_records"], 2)
        self.assertEqual(
            result["ledger_sha256"], sha256(self.ledger.read_bytes()).hexdigest()
        )
        public = json.dumps(result)
        for private in (
            "PRIVATE",
            "123456",
            "review-1",
            "record_ordinal",
            "reviewer-a",
        ):
            self.assertNotIn(private, public)

    def test_complete_unknowns_need_evidence_limitation_and_attestation(self) -> None:
        complete = self.entry(status="complete", rubric=complete_rubric())
        result = self.append(complete)
        self.assertEqual(result["complete_records"], 1)
        self.assertEqual(result["unknown_counts"]["date_vs_closing"], 1)
        self.assertEqual(result["unknown_counts"]["reuse_rights"], 1)
        self.assertEqual(self.summary(), result)
        broken = self.entry(
            ordinal=2, entry_id="review-2", status="complete", rubric=complete_rubric()
        )
        broken["rubric"]["date_vs_closing"]["limitation"] = None
        with self.assertRaisesRegex(ValueError, "unknown.*limitation"):
            self.append(broken)
        broken["rubric"]["date_vs_closing"] = finding()
        broken["attested"] = False
        with self.assertRaisesRegex(ValueError, "attest"):
            self.append(broken)
        self.assertEqual(self.summary()["complete_records"], 1)

    def test_partial_does_not_become_complete_just_because_all_fields_exist(
        self,
    ) -> None:
        result = self.append(self.entry(rubric=complete_rubric()))
        self.assertEqual(result["partial_records"], 1)
        self.assertEqual(result["complete_records"], 0)
        incomplete = self.entry(ordinal=2, entry_id="review-2", status="complete")
        with self.assertRaisesRegex(ValueError, "rubric"):
            self.append(incomplete)

    def test_revisions_are_append_only_and_point_to_latest_entry(self) -> None:
        self.append(self.entry())
        first = self.ledger.read_bytes()
        self.append(
            self.entry(
                entry_id="review-2",
                revision=2,
                supersedes="review-1",
                status="complete",
                rubric=complete_rubric(),
            )
        )
        self.assertTrue(self.ledger.read_bytes().startswith(first))
        self.assertEqual(self.summary()["review_entries"], 2)
        self.assertEqual(self.summary()["complete_records"], 1)
        self.assertEqual(self.summary()["superseded_entries"], 1)
        for invalid in (
            self.entry(entry_id="review-2", revision=3, supersedes="review-2"),
            self.entry(entry_id="review-3", revision=2, supersedes="review-2"),
            self.entry(entry_id="review-4", revision=3, supersedes="review-1"),
        ):
            with self.assertRaises(ValueError):
                self.append(invalid)
        self.assertEqual(self.summary()["review_entries"], 2)

    def test_wrong_hash_unsampled_ordinal_and_bad_sample_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "sample hash"):
            self.append(self.entry(sample_sha=HASH))
        with self.assertRaisesRegex(ValueError, "sampled ordinal"):
            self.append(self.entry(ordinal=99))
        self.sample.write_text(self.sample.read_text() + "not-json\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "sample hash"):
            self.append(self.entry())
        self.assertFalse(self.ledger.exists())

    def test_evidence_reference_and_source_type_controls(self) -> None:
        for bad_evidence in (
            {**evidence(), "reference": "http://unsafe.example/evidence"},
            {**evidence(), "reference": "sha256:short"},
            {**evidence(), "kind": "invented"},
            {**evidence(), "observed_at": "yesterday"},
            {
                **evidence("clerk_index"),
                "reference": "https://user:secret@example.org/official/evidence",
            },
        ):
            with self.subTest(bad_evidence=bad_evidence):
                with self.assertRaisesRegex(ValueError, "evidence"):
                    self.append(self.entry(evidences=[bad_evidence]))
        bad = self.entry()
        bad["rubric"]["document_identity"]["evidence_ids"] = ["absent"]
        with self.assertRaisesRegex(ValueError, "evidence"):
            self.append(bad)
        self.assertFalse(self.ledger.exists())

    def test_closing_execution_recording_and_rights_cannot_be_inferred(self) -> None:
        checks = {
            "document_identity": ("clerk_index", "match"),
            "parcel_unit_identity": ("clerk_index", "match"),
            "date_vs_closing": ("closing_record", "same"),
            "date_vs_deed_execution": ("clerk_instrument", "same"),
            "date_vs_recording": ("clerk_index", "before"),
            "price_scope": ("clerk_instrument", "single_property"),
            "property_class": ("clerk_index", "condominium"),
            "qualification_code": ("official_documentation", "corroborated"),
            "reason_code": ("official_documentation", "corroborated"),
            "multi_parcel_consideration": (
                "clerk_instrument",
                "single_parcel_confirmed",
            ),
            "reuse_rights": ("rights_document", "permitted"),
        }
        for dimension, (kind, value) in checks.items():
            with self.subTest(dimension=dimension):
                rubric = complete_rubric()
                rubric[dimension] = finding(value)
                with self.assertRaisesRegex(ValueError, "evidence"):
                    self.append(self.entry(status="complete", rubric=rubric))
                specialized = evidence(kind, "specialized")
                rubric[dimension] = finding(value, identifier="specialized")
                result = self.append(
                    self.entry(
                        status="complete",
                        rubric=rubric,
                        evidences=[
                            evidence(source_hash=self.sample_sha),
                            evidence("unavailable_attempt", "clerk_attempt"),
                            specialized,
                        ],
                    )
                )
                self.assertEqual(result["complete_records"], 1)
                self.ledger.unlink()

    def test_malformed_ledger_is_rejected_without_overwrite(self) -> None:
        self.ledger.write_bytes(b"partial-corrupt")
        original = self.ledger.read_bytes()
        with self.assertRaisesRegex(ValueError, "ledger"):
            self.append(self.entry())
        self.assertEqual(self.ledger.read_bytes(), original)

    def test_paths_outside_private_root_and_symlink_redirect_are_rejected(self) -> None:
        with patch.object(review, "PRIVATE_ROOT", self.private):
            with self.assertRaisesRegex(ValueError, "private"):
                review.append_review(
                    self.sample,
                    self.sample_sha,
                    self.root / "tracked.jsonl",
                    self.entry(),
                )
            real_resolve = Path.resolve
            redirected = self.root / "tracked-area"

            def resolve_with_redirect(path: Path, *args, **kwargs) -> Path:
                if path == self.private:
                    return redirected
                return real_resolve(path, *args, **kwargs)

            with patch.object(Path, "resolve", resolve_with_redirect):
                with self.assertRaisesRegex(ValueError, "redirect"):
                    review.append_review(
                        self.sample, self.sample_sha, self.ledger, self.entry()
                    )
            link = self.private / "linked.jsonl"
            target = self.root / "outside.jsonl"
            target.write_text("outside")
            try:
                link.symlink_to(target)
            except OSError:
                return
            with self.assertRaisesRegex(ValueError, "redirect|symlink"):
                review.append_review(self.sample, self.sample_sha, link, self.entry())
            self.assertEqual(target.read_text(), "outside")

    def test_exclusive_lock_refuses_concurrent_writer(self) -> None:
        lock = self.private / "reviews.jsonl.lock"
        lock.write_text("held")
        with self.assertRaisesRegex(FileExistsError, "lock"):
            self.append(self.entry())
        self.assertFalse(self.ledger.exists())

    def test_lock_records_owner_for_manual_crash_recovery(self) -> None:
        original = review._sample_ordinals
        captured = []

        def inspect_lock(sample: Path, sample_sha256: str) -> set[int]:
            lock = self.private / "reviews.jsonl.lock"
            metadata = json.loads(lock.read_text(encoding="utf-8"))
            captured.append(metadata)
            return original(sample, sample_sha256)

        with patch.object(review, "_sample_ordinals", side_effect=inspect_lock):
            self.append(self.entry())
        self.assertEqual(captured[0]["pid"], os.getpid())
        self.assertTrue(captured[0]["hostname"])
        self.assertTrue(captured[0]["created_at_utc"].endswith("Z"))
        self.assertFalse((self.private / "reviews.jsonl.lock").exists())

    def test_invalid_input_types_fail_as_validation_errors(self) -> None:
        bad = self.entry()
        bad["review_status"] = []
        with self.assertRaises(ValueError):
            self.append(bad)
        bad = self.entry()
        bad["rubric"]["document_identity"]["value"] = []
        with self.assertRaises(ValueError):
            self.append(bad)
        bad = self.entry()
        bad["evidence"][0]["kind"] = []
        with self.assertRaises(ValueError):
            self.append(bad)
        self.assertFalse(self.ledger.exists())

    def test_cli_writes_aggregate_summary_to_new_file(self) -> None:
        entry_path = self.private / "entry.json"
        entry_path.write_text(json.dumps(self.entry()), encoding="utf-8")
        summary = self.root / "aggregate.json"
        output = io.StringIO()
        with (
            patch.object(review, "PRIVATE_ROOT", self.private),
            redirect_stdout(output),
        ):
            self.assertEqual(
                review.main(
                    [
                        "append",
                        str(self.sample),
                        str(self.ledger),
                        str(entry_path),
                        str(summary),
                        "--sample-sha256",
                        self.sample_sha,
                    ]
                ),
                0,
            )
        self.assertEqual(json.loads(output.getvalue()), json.loads(summary.read_text()))
        self.assertEqual(json.loads(summary.read_text())["partial_records"], 1)
        self.assertNotIn("PRIVATE-ONE", summary.read_text())
        with patch.object(review, "PRIVATE_ROOT", self.private):
            with self.assertRaises(FileExistsError):
                review.main(
                    [
                        "append",
                        str(self.sample),
                        str(self.ledger),
                        str(entry_path),
                        str(summary),
                        "--sample-sha256",
                        self.sample_sha,
                    ]
                )
        self.assertEqual(self.summary()["review_entries"], 1)

    def test_cli_replays_existing_ledger_into_new_aggregate_file(self) -> None:
        self.append(self.entry())
        summary = self.root / "replayed.json"
        output = io.StringIO()
        with (
            patch.object(review, "PRIVATE_ROOT", self.private),
            redirect_stdout(output),
        ):
            self.assertEqual(
                review.main(
                    [
                        "summary",
                        str(self.sample),
                        str(self.ledger),
                        "-",
                        str(summary),
                        "--sample-sha256",
                        self.sample_sha,
                    ]
                ),
                0,
            )
        self.assertEqual(json.loads(summary.read_text()), self.summary())
        self.assertEqual(json.loads(output.getvalue()), self.summary())
        self.assertNotIn("PRIVATE-ONE", summary.read_text())

    def test_malformed_existing_history_and_sample_are_rejected(self) -> None:
        original = self.sample.read_bytes()
        duplicate = json.loads(original.splitlines()[0])
        self.sample.write_bytes(original + json.dumps(duplicate).encode() + b"\n")
        duplicate_sha = sha256(self.sample.read_bytes()).hexdigest()
        with patch.object(review, "PRIVATE_ROOT", self.private):
            with self.assertRaisesRegex(ValueError, "repeated ordinals"):
                review.summarize_reviews(self.sample, duplicate_sha, self.ledger)
        self.sample.write_bytes(original)
        bad_entry = self.entry(sample_sha=HASH)
        self.ledger.write_text(json.dumps(bad_entry) + "\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "sample hash"):
            self.summary()
        self.ledger.write_text(
            json.dumps(self.entry()) + "\n" + json.dumps(self.entry()) + "\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "Duplicate review entry"):
            self.summary()

    def test_invalid_entry_structure_and_invalid_evidence_are_rejected(self) -> None:
        candidates = []
        missing = self.entry()
        del missing["reviewer_code"]
        candidates.append(missing)
        bad_revision = self.entry()
        bad_revision["revision"] = True
        candidates.append(bad_revision)
        bad_attestation = self.entry()
        bad_attestation["reviewed_at"] = "2026-09-28"
        candidates.append(bad_attestation)
        empty_sources = self.entry()
        empty_sources["evidence"] = []
        candidates.append(empty_sources)
        duplicate_sources = self.entry()
        duplicate_sources["evidence"].append(evidence())
        candidates.append(duplicate_sources)
        empty_rubric = self.entry()
        empty_rubric["rubric"] = {}
        candidates.append(empty_rubric)
        bad_value = self.entry()
        bad_value["rubric"]["document_identity"]["value"] = "definitely"
        candidates.append(bad_value)
        empty_refs = self.entry()
        empty_refs["rubric"]["document_identity"]["evidence_ids"] = []
        candidates.append(empty_refs)
        for candidate in candidates:
            with self.subTest(candidate=candidate.get("entry_id")):
                with self.assertRaises(ValueError):
                    self.append(candidate)
        self.assertFalse(self.ledger.exists())

    def test_summary_path_cannot_overwrite_private_inputs(self) -> None:
        entry_path = self.private / "entry.json"
        entry_path.write_text(json.dumps(self.entry()), encoding="utf-8")
        with patch.object(review, "PRIVATE_ROOT", self.private):
            with self.assertRaisesRegex(ValueError, "summary"):
                review.main(
                    [
                        "append",
                        str(self.sample),
                        str(self.ledger),
                        str(entry_path),
                        str(self.sample),
                        "--sample-sha256",
                        self.sample_sha,
                    ]
                )
        self.assertFalse(self.ledger.exists())
        self.assertTrue(self.sample.exists())
        with patch.object(review, "PRIVATE_ROOT", self.private):
            with self.assertRaisesRegex(ValueError, "summary"):
                review.main(
                    [
                        "append",
                        str(self.sample),
                        str(self.ledger),
                        str(entry_path),
                        str(self.ledger),
                        "--sample-sha256",
                        self.sample_sha,
                    ]
                )
        self.assertFalse(self.ledger.exists())

    def test_complete_review_requires_hcpa_and_clerk_check_or_documented_attempt(
        self,
    ) -> None:
        rubric = complete_rubric()
        without_clerk = self.entry(
            status="complete",
            rubric=rubric,
            evidences=[evidence(source_hash=self.sample_sha)],
        )
        with self.assertRaisesRegex(ValueError, "Clerk"):
            self.append(without_clerk)
        without_hcpa = self.entry(
            status="complete",
            rubric=rubric,
            evidences=[evidence("unavailable_attempt", "clerk_attempt")],
        )
        for finding_data in without_hcpa["rubric"].values():
            finding_data["evidence_ids"] = ["clerk_attempt"]
        with self.assertRaisesRegex(ValueError, "HCPA"):
            self.append(without_hcpa)

    def test_malformed_https_evidence_is_rejected_without_echoing_reference(
        self,
    ) -> None:
        bad = self.entry(
            evidences=[
                {
                    **evidence("clerk_index"),
                    "reference": "https://[PRIVATE-ADDRESS",
                }
            ]
        )
        bad["rubric"]["document_identity"]["evidence_ids"] = ["source"]
        with self.assertRaisesRegex(ValueError, "evidence") as caught:
            self.append(bad)
        self.assertNotIn("PRIVATE-ADDRESS", str(caught.exception))

    def test_hcpa_evidence_must_reference_this_exact_frozen_sample(self) -> None:
        wrong = self.entry(evidences=[evidence(source_hash=HASH)])
        with self.assertRaisesRegex(ValueError, "sample"):
            self.append(wrong)
        self.assertFalse(self.ledger.exists())

    def test_hard_link_to_outside_file_is_rejected_before_append(self) -> None:
        outside = self.root / "tracked.jsonl"
        outside.write_text("tracked data", encoding="utf-8")
        os.link(outside, self.ledger)
        self.assertGreater(self.ledger.stat().st_nlink, 1)
        with self.assertRaisesRegex(ValueError, "hard link"):
            self.append(self.entry())
        self.assertEqual(outside.read_text(), "tracked data")
        self.assertEqual(self.ledger.read_text(), "tracked data")

    def test_hard_linked_sample_and_entry_are_rejected(self) -> None:
        outside_sample = self.root / "tracked-sample.jsonl"
        os.link(self.sample, outside_sample)
        with self.assertRaisesRegex(ValueError, "hard link"):
            self.append(self.entry())
        outside_sample.unlink()
        private_entry = self.private / "entry.json"
        outside_entry = self.root / "tracked-entry.json"
        outside_entry.write_text(json.dumps(self.entry()), encoding="utf-8")
        os.link(outside_entry, private_entry)
        with patch.object(review, "PRIVATE_ROOT", self.private):
            with self.assertRaisesRegex(ValueError, "hard link"):
                review.main(
                    [
                        "append",
                        str(self.sample),
                        str(self.ledger),
                        str(private_entry),
                        str(self.root / "aggregate.json"),
                        "--sample-sha256",
                        self.sample_sha,
                    ]
                )
        self.assertFalse(self.ledger.exists())

    def test_short_os_writes_are_completed_before_success(self) -> None:
        real_write = os.write
        calls = []

        def short_write(descriptor: int, data: bytes) -> int:
            calls.append(len(data))
            return real_write(descriptor, data[:7])

        with patch.object(review.os, "write", side_effect=short_write):
            result = self.append(self.entry())
        self.assertGreater(len(calls), 1)
        self.assertEqual(result, self.summary())
        self.assertEqual(result["review_entries"], 1)

    def test_failed_replace_preserves_previous_ledger_bytes(self) -> None:
        self.append(self.entry())
        old = self.ledger.read_bytes()
        revised = self.entry(
            entry_id="review-2",
            revision=2,
            supersedes="review-1",
            status="complete",
            rubric=complete_rubric(),
        )
        with patch.object(review.os, "replace", side_effect=OSError("simulated crash")):
            with self.assertRaisesRegex(OSError, "simulated crash"):
                self.append(revised)
        self.assertEqual(self.ledger.read_bytes(), old)
        self.assertEqual(self.summary()["review_entries"], 1)
        self.assertFalse(list(self.private.glob(".hcpa-review-ledger-*")))

    def test_write_or_fsync_failure_closes_temp_before_cleanup(self) -> None:
        self.ledger.write_bytes(b"original\n")
        real_temp = review.tempfile.NamedTemporaryFile
        real_unlink = Path.unlink
        state = {"open": False}

        @contextmanager
        def tracked_temp(*args, **kwargs):
            try:
                with real_temp(*args, **kwargs) as stream:
                    state["open"] = True
                    yield stream
            finally:
                state["open"] = False

        def windows_unlink(path: Path, *args, **kwargs):
            if path.name.startswith(".hcpa-review-ledger-") and state["open"]:
                raise PermissionError("Windows cannot unlink an open temp file")
            return real_unlink(path, *args, **kwargs)

        for failure_point in ("write", "fsync"):
            with self.subTest(failure_point=failure_point):
                with (
                    patch.object(review.tempfile, "NamedTemporaryFile", tracked_temp),
                    patch.object(Path, "unlink", windows_unlink),
                ):
                    if failure_point == "write":
                        failure = patch.object(
                            review,
                            "_write_all",
                            side_effect=OSError("injected write error"),
                        )
                    else:
                        failure = patch.object(
                            review.os,
                            "fsync",
                            side_effect=OSError("injected fsync error"),
                        )
                    with failure:
                        with self.assertRaisesRegex(
                            OSError, f"injected {failure_point} error"
                        ):
                            review._write_ledger_atomic(self.ledger, b"replacement\n")
                self.assertEqual(self.ledger.read_bytes(), b"original\n")
                self.assertFalse(list(self.private.glob(".hcpa-review-ledger-*")))

    def test_summary_write_or_fsync_failure_cleans_temp_after_close(self) -> None:
        destination = self.root / "aggregate.json"
        real_temp = review.tempfile.NamedTemporaryFile
        real_unlink = Path.unlink
        state = {"open": False}

        @contextmanager
        def tracked_temp(*args, **kwargs):
            try:
                with real_temp(*args, **kwargs) as stream:
                    state["open"] = True
                    yield stream
            finally:
                state["open"] = False

        def windows_unlink(path: Path, *args, **kwargs):
            if path.name.startswith(".hcpa-review-") and state["open"]:
                raise PermissionError("Windows cannot unlink an open temp file")
            return real_unlink(path, *args, **kwargs)

        for failure_point in ("write", "fsync"):
            with self.subTest(failure_point=failure_point):
                with (
                    patch.object(review.tempfile, "NamedTemporaryFile", tracked_temp),
                    patch.object(Path, "unlink", windows_unlink),
                ):
                    if failure_point == "write":
                        failure = patch.object(
                            review,
                            "_write_all",
                            side_effect=OSError("injected write error"),
                        )
                    else:
                        failure = patch.object(
                            review.os,
                            "fsync",
                            side_effect=OSError("injected fsync error"),
                        )
                    with failure:
                        with self.assertRaisesRegex(
                            OSError, f"injected {failure_point} error"
                        ):
                            review._write_summary_new(destination, {"count": 1}, ())
                self.assertFalse(destination.exists())
                self.assertFalse(list(self.root.glob(".hcpa-review-*")))

    def test_historical_ledger_replays_after_clock_moves_backward(self) -> None:
        self.append(self.entry())

        class EarlierClock(datetime):
            @classmethod
            def now(cls, tz=None):
                return datetime(2026, 9, 28, 11, 0, tzinfo=timezone.utc)

        with patch.object(review, "datetime", EarlierClock):
            self.assertEqual(self.summary()["review_entries"], 1)
            with self.assertRaisesRegex(ValueError, "future"):
                self.append(self.entry(entry_id="review-2", ordinal=2))

    def test_evidence_must_precede_review_and_both_must_not_be_future_dated(
        self,
    ) -> None:
        late_evidence = self.entry()
        late_evidence["evidence"][0]["observed_at"] = "2026-09-28T12:00:01Z"
        with self.assertRaisesRegex(ValueError, "evidence.*review"):
            self.append(late_evidence)
        future_review = self.entry()
        future_review["reviewed_at"] = "2099-01-01T00:00:00Z"
        with self.assertRaisesRegex(ValueError, "future"):
            self.append(future_review)
        self.assertFalse(self.ledger.exists())

    def test_cli_retries_identical_last_entry_after_summary_write_failure(self) -> None:
        entry_path = self.private / "entry.json"
        entry_path.write_text(json.dumps(self.entry()), encoding="utf-8")
        first_summary = self.root / "failed-summary.json"
        arguments = [
            "append",
            str(self.sample),
            str(self.ledger),
            str(entry_path),
            str(first_summary),
            "--sample-sha256",
            self.sample_sha,
        ]
        with patch.object(review, "PRIVATE_ROOT", self.private):
            with patch.object(
                review, "_write_summary_new", side_effect=OSError("summary failure")
            ):
                with self.assertRaisesRegex(OSError, "summary failure"):
                    review.main(arguments)
        self.assertEqual(self.summary()["review_entries"], 1)
        self.assertFalse(first_summary.exists())
        retry_summary = self.root / "recovered-summary.json"
        arguments[4] = str(retry_summary)
        with (
            patch.object(review, "PRIVATE_ROOT", self.private),
            redirect_stdout(io.StringIO()),
        ):
            review.main(arguments)
        self.assertEqual(self.summary()["review_entries"], 1)
        self.assertEqual(json.loads(retry_summary.read_text()), self.summary())
        changed = self.entry()
        changed["reviewer_code"] = "reviewer-b"
        entry_path.write_text(json.dumps(changed), encoding="utf-8")
        arguments[4] = str(self.root / "changed-summary.json")
        with patch.object(review, "PRIVATE_ROOT", self.private):
            with self.assertRaisesRegex(ValueError, "Duplicate review entry"):
                review.main(arguments)
        self.assertFalse((self.root / "changed-summary.json").exists())
        self.assertEqual(self.summary()["review_entries"], 1)


if __name__ == "__main__":
    unittest.main()
