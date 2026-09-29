"""Synthetic behavior tests for the private NYC source-review ledger."""

from __future__ import annotations

from contextlib import redirect_stdout
from hashlib import sha256
from importlib.util import module_from_spec, spec_from_file_location
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "review_nyc_sample.py"
spec = spec_from_file_location("review_nyc_sample", SCRIPT)
assert spec is not None and spec.loader is not None
review = module_from_spec(spec)
spec.loader.exec_module(review)

WHEN = "2026-09-28T12:00:00Z"


def item(kind="source_record", identifier="source", reference=None, **details):
    if reference is None:
        reference = "https://example.org/official/record"
    return {
        "evidence_id": identifier,
        "kind": kind,
        "reference": reference,
        "observed_at": WHEN,
        **details,
    }


def finding(value="unknown", *ids):
    return {
        "value": value,
        "evidence_ids": list(ids or ("source",)),
        "limitation": "Checked source does not establish this fact"
        if value == "unknown"
        else None,
    }


class NycSourceReviewTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.raw = self.root / "data" / "raw" / "nyc_dof"
        self.raw.mkdir(parents=True)
        self.private = self.raw / "manual-review-v1"
        self.source = self.raw / "source.csv"
        self.source.write_text(
            "BOROUGH,BLOCK,LOT,APARTMENT NUMBER,SALE DATE,SALE PRICE\n"
            "1,PRIVATE-1,1,,2026-01-01,100\n"
            "1,PRIVATE-2,2,,2026-01-02,0\n"
            "1,PRIVATE-3,3,,2026-01-03,bad\n",
            encoding="utf-8",
        )
        self.sample = self.raw / "sample.jsonl"
        self.sample.write_text(
            "".join(json.dumps({"ordinal": n}) + "\n" for n in (1, 2, 3)),
            encoding="utf-8",
        )
        self.source_sha = sha256(self.source.read_bytes()).hexdigest()
        self.sample_sha = sha256(self.sample.read_bytes()).hexdigest()
        self.ledger = self.private / "reviews.jsonl"
        self.manifest = self.private / "manifest.json"
        self.summary_path = self.root / "summary.json"
        self.patches = (
            patch.object(review, "RAW_ROOT", self.raw),
            patch.object(review, "SOURCE_SHA256", self.source_sha),
            patch.object(review, "SAMPLE_SHA256", self.sample_sha),
            patch.object(review, "SAMPLE_COUNT", 3),
            patch.object(review, "SOURCE_ROWS", 3),
        )
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)

    def initialize(self):
        return review.init_review(self.source, self.sample, self.ledger, self.manifest)

    def entry(
        self,
        *,
        ordinal=1,
        entry_id="entry-1",
        revision=1,
        supersedes=None,
        status="partial",
        rubric=None,
        evidence=None,
    ):
        return {
            "entry_id": entry_id,
            "ledger_id": self.identity,
            "protocol": review.PROTOCOL,
            "source_sha256": self.source_sha,
            "sample_sha256": self.sample_sha,
            "ordinal": ordinal,
            "revision": revision,
            "supersedes_entry_id": supersedes,
            "review_status": status,
            "reviewer_code": "reviewer-a",
            "reviewed_at": WHEN,
            "attested": status == "complete",
            "evidence": evidence
            if evidence is not None
            else [
                item(reference="sha256:" + self.source_sha),
            ],
            "rubric": rubric
            if rubric is not None
            else {
                "economic_transfer_scope": finding(),
            },
        }

    def append(self, entry, prior=None):
        if prior is None:
            prior = sha256(self.ledger.read_bytes()).hexdigest()
        return review.append_review(
            self.source,
            self.sample,
            self.ledger,
            self.manifest,
            entry,
            self.identity,
            prior,
        )

    def complete_entry(self, *, ordinal=1, entry_id="complete-1"):
        evidence = [
            item(reference="sha256:" + self.source_sha),
            item("official_documentation", "definitions"),
            item(
                "unavailable_attempt",
                "instrument-attempt",
                attempted_at=WHEN,
                target="recorded_instrument",
                outcome="access_unavailable",
            ),
        ]
        rubric = {name: finding() for name in review.DIMENSIONS}
        rubric["property_unit_identity"] = finding(
            "unknown", "source", "instrument-attempt"
        )
        return self.entry(
            ordinal=ordinal,
            entry_id=entry_id,
            status="complete",
            evidence=evidence,
            rubric=rubric,
        )

    def test_init_is_private_unique_and_no_overwrite(self):
        result = self.initialize()
        self.identity = result["ledger_id"]
        self.assertTrue(self.identity)
        self.assertEqual(self.ledger.read_bytes(), b"")
        self.assertEqual(result["source_sha256"], self.source_sha)
        self.assertEqual(result["sample_sha256"], self.sample_sha)
        self.assertNotIn(
            self.identity,
            json.dumps(
                review.summarize_reviews(
                    self.source, self.sample, self.ledger, self.manifest
                )
            ),
        )
        with self.assertRaises(FileExistsError):
            self.initialize()
        self.assertEqual(
            json.loads(self.manifest.read_text())["ledger_id"], self.identity
        )

    def test_init_rejects_changed_inputs_and_malformed_sample(self):
        self.source.write_text(self.source.read_text() + "changed")
        with self.assertRaisesRegex(ValueError, "source.*hash"):
            self.initialize()
        self.source.write_text(self.source.read_text()[:-7])
        self.sample.write_text(self.sample.read_text() + "bad\n")
        with self.assertRaisesRegex(ValueError, "sample.*hash"):
            self.initialize()
        self.assertFalse(self.ledger.exists())

    def test_append_requires_exact_prior_hash_and_ledger_id(self):
        self.identity = self.initialize()["ledger_id"]
        entry = self.entry()
        result = self.append(entry)
        self.assertEqual(result["partial_records"], 1)
        self.assertEqual(result["unreviewed_records"], 2)
        self.assertEqual(
            result["ledger_sha256"], sha256(self.ledger.read_bytes()).hexdigest()
        )
        with self.assertRaisesRegex(ValueError, "prior.*hash"):
            self.append(self.entry(ordinal=2, entry_id="entry-2"), "0" * 64)
        with self.assertRaisesRegex(ValueError, "ledger ID"):
            review.append_review(
                self.source,
                self.sample,
                self.ledger,
                self.manifest,
                entry,
                "wrong",
                result["ledger_sha256"],
            )
        self.assertEqual(self.ledger.read_bytes().count(b"\n"), 1)

    def test_revisions_and_history_validation(self):
        self.identity = self.initialize()["ledger_id"]
        self.append(self.entry())
        self.append(
            self.entry(
                entry_id="entry-2",
                revision=2,
                supersedes="entry-1",
                status="complete",
                rubric=self.complete_entry()["rubric"],
                evidence=self.complete_entry()["evidence"],
            )
        )
        self.assertEqual(
            review.summarize_reviews(
                self.source, self.sample, self.ledger, self.manifest
            )["complete_records"],
            1,
        )
        for bad in (
            self.entry(entry_id="entry-2", revision=3, supersedes="entry-2"),
            self.entry(entry_id="entry-3", revision=3, supersedes="entry-1"),
            self.entry(ordinal=99, entry_id="entry-4"),
        ):
            with self.assertRaises(ValueError):
                self.append(bad)
        self.ledger.write_bytes(self.ledger.read_bytes()[:-1])
        with self.assertRaisesRegex(ValueError, "ledger"):
            review.summarize_reviews(
                self.source, self.sample, self.ledger, self.manifest
            )

    def test_complete_unknowns_need_attestation_and_source_checks(self):
        self.identity = self.initialize()["ledger_id"]
        candidate = self.complete_entry()
        self.assertEqual(self.append(candidate)["complete_records"], 1)
        for field, value in (
            ("attested", False),
            ("rubric", {}),
            ("evidence", candidate["evidence"][:1]),
        ):
            altered = self.complete_entry(ordinal=2, entry_id="another")
            altered[field] = value
            with self.assertRaises(ValueError):
                self.append(altered)
        altered = self.complete_entry(ordinal=2, entry_id="another")
        altered["rubric"]["attribute_vintage"]["limitation"] = " "
        with self.assertRaisesRegex(ValueError, "limitation"):
            self.append(altered)

    def test_generic_urls_cannot_support_strong_conclusions(self):
        self.identity = self.initialize()["ledger_id"]
        checks = (
            ("property_unit_identity", "match", "recorded_instrument"),
            ("economic_transfer_scope", "single_property", "recorded_instrument"),
            ("repeated_consideration", "distinct_transfer", "recorded_instrument"),
            ("source_correction", "documented_correction", "correction_record"),
            ("property_class", "single_family", "official_documentation"),
            ("evidence_quality", "high", "official_documentation"),
            (
                "source_correction",
                "no_correction_in_checked_history",
                "correction_record",
            ),
        )
        for dimension, value, needed in checks:
            with self.subTest(dimension=dimension, value=value):
                candidate = self.entry(rubric={dimension: finding(value, "source")})
                specialized = item(needed, "special")
                if needed == "correction_record":
                    specialized.update(
                        checked_history={
                            "from": "2025-01-01",
                            "through": "2026-01-01",
                            "version_ids": ["v1", "v2"],
                        }
                    )
                candidate["evidence"].append(specialized)
                candidate["rubric"][dimension] = finding(value, "source", "special")
                with self.assertRaisesRegex(
                    ValueError, "verified local artifact protocol"
                ):
                    self.append(candidate)

    def test_v1_rejects_strong_identity_timing_and_asof_findings(self):
        self.identity = self.initialize()["ledger_id"]
        for dimension, value in (
            ("source_row_identity", "match"),
            ("source_row_identity", "mismatch"),
            ("sale_date_vs_contract", "same"),
            ("sale_date_vs_closing", "before"),
            ("sale_date_vs_recording", "after"),
            ("first_row_availability", "upper_bound_only"),
            ("first_row_availability", "first_publication_verified"),
            ("attribute_vintage", "historical_asof_supported"),
        ):
            with self.subTest(dimension=dimension, value=value):
                entry = self.entry(rubric={dimension: finding(value)})
                with self.assertRaisesRegex(
                    ValueError, "verified local artifact protocol"
                ):
                    self.append(entry)
        self.assertEqual(self.ledger.read_bytes(), b"")

    def test_unavailable_attempt_is_structured_and_relevant(self):
        self.identity = self.initialize()["ledger_id"]
        valid = self.complete_entry()
        self.assertEqual(self.append(valid)["complete_records"], 1)
        for key in ("attempted_at", "target", "outcome"):
            entry = self.complete_entry(ordinal=2, entry_id="second")
            del entry["evidence"][2][key]
            with self.subTest(missing=key):
                with self.assertRaisesRegex(ValueError, "attempt"):
                    self.append(entry)
        entry = self.complete_entry(ordinal=2, entry_id="second")
        entry["rubric"]["property_unit_identity"] = finding()
        with self.assertRaisesRegex(ValueError, "relevant unknown"):
            self.append(entry)
        entry = self.complete_entry(ordinal=2, entry_id="second")
        entry["evidence"][2]["attempted_at"] = "2026-09-29T00:00:00Z"
        with self.assertRaisesRegex(ValueError, "attempt"):
            self.append(entry)

    def test_correction_history_cannot_extend_beyond_observation(self):
        self.identity = self.initialize()["ledger_id"]
        correction = item(
            "correction_record",
            "history",
            checked_history={
                "from": "2025-01-01",
                "through": "2026-09-29",
                "version_ids": ["v1"],
            },
        )
        entry = self.entry(
            evidence=[item(reference="sha256:" + self.source_sha), correction]
        )
        with self.assertRaisesRegex(ValueError, "history.*observation"):
            self.append(entry)

    def test_orphan_init_is_preserved_and_new_init_gets_new_identity(self):
        self.identity = self.initialize()["ledger_id"]
        original_manifest = self.manifest.read_bytes()
        self.ledger.unlink()
        inspected = review.inspect_orphan(
            self.source, self.sample, self.ledger, self.manifest
        )
        self.assertEqual(inspected["status"], "abandoned_manifest_only")
        self.assertEqual(self.manifest.read_bytes(), original_manifest)
        self.assertFalse(self.ledger.exists())
        with self.assertRaises(FileExistsError):
            self.initialize()
        next_ledger = self.private / "reviews-next.jsonl"
        next_manifest = self.private / "manifest-next.json"
        restarted = review.init_review(
            self.source, self.sample, next_ledger, next_manifest
        )
        self.assertNotEqual(restarted["ledger_id"], self.identity)
        self.assertEqual(next_ledger.read_bytes(), b"")
        self.assertEqual(self.manifest.read_bytes(), original_manifest)
        self.assertFalse(self.ledger.exists())
        self.manifest.unlink()
        with self.assertRaisesRegex(ValueError, "manifest"):
            review.inspect_orphan(self.source, self.sample, self.ledger, self.manifest)

    def test_price_semantics_from_pinned_source_and_unit_na_guard(self):
        self.identity = self.initialize()["ledger_id"]
        definition = item("official_documentation", "definitions")
        for ordinal, value in (
            (1, "reported_positive"),
            (2, "reported_zero"),
            (3, "invalid"),
        ):
            candidate = self.entry(
                ordinal=ordinal,
                entry_id=f"entry-{ordinal}",
                evidence=[item(reference="sha256:" + self.source_sha), definition],
                rubric={"price_semantics": finding(value, "source", "definitions")},
            )
            self.append(candidate)
        bad = self.entry(
            entry_id="bad",
            revision=2,
            supersedes="entry-1",
            evidence=[item(reference="sha256:" + self.source_sha), definition],
            rubric={
                "price_semantics": finding("reported_zero", "source", "definitions")
            },
        )
        with self.assertRaisesRegex(ValueError, "price"):
            self.append(bad)
        bad = self.entry(
            entry_id="bad",
            revision=2,
            supersedes="entry-1",
            rubric={"property_unit_identity": finding("not_applicable")},
        )
        with self.assertRaises(ValueError):
            self.append(bad)

    def test_future_time_bad_reference_and_missing_ordinal_rejected(self):
        self.identity = self.initialize()["ledger_id"]
        future = self.entry()
        future["reviewed_at"] = "2099-01-01T00:00:00Z"
        with self.assertRaisesRegex(ValueError, "future"):
            self.append(future)
        for bad in ("http://example.org/x", "https://user:pass@example.org/x", ""):
            candidate = self.entry(
                evidence=[item("official_documentation", reference=bad)]
            )
            with self.assertRaises(ValueError):
                self.append(candidate)
        candidate = self.entry(
            rubric={"source_row_identity": finding("unknown", "absent")}
        )
        with self.assertRaises(ValueError):
            self.append(candidate)
        self.assertFalse(self.ledger.read_bytes())

    def test_summary_after_report_failure_and_create_new(self):
        self.identity = self.initialize()["ledger_id"]
        self.append(self.entry())
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(
                review.main(
                    [
                        "summary",
                        str(self.source),
                        str(self.sample),
                        str(self.ledger),
                        str(self.manifest),
                        "-",
                        str(self.summary_path),
                    ]
                ),
                0,
            )
        report = json.loads(self.summary_path.read_text())
        self.assertEqual(report["partial_records"], 1)
        self.assertNotIn("PRIVATE", output.getvalue() + self.summary_path.read_text())
        self.assertNotIn("entry-1", output.getvalue() + self.summary_path.read_text())
        with self.assertRaises(FileExistsError):
            review.main(
                [
                    "summary",
                    str(self.source),
                    str(self.sample),
                    str(self.ledger),
                    str(self.manifest),
                    "-",
                    str(self.summary_path),
                ]
            )

    def test_paths_lock_and_short_write(self):
        self.identity = self.initialize()["ledger_id"]
        lock = self.ledger.with_name(self.ledger.name + ".lock")
        lock.write_text("held")
        with self.assertRaises(FileExistsError):
            self.append(self.entry())
        lock.unlink()
        with self.assertRaises(ValueError):
            review.append_review(
                self.source,
                self.sample,
                self.root / "public.jsonl",
                self.manifest,
                self.entry(),
                self.identity,
                sha256(b"").hexdigest(),
            )
        external = self.root / "external.jsonl"
        external.write_text("kept")
        link = self.private / "link.jsonl"
        try:
            link.symlink_to(external)
        except OSError:
            pass
        else:
            with self.assertRaises(ValueError):
                review.append_review(
                    self.source,
                    self.sample,
                    link,
                    self.manifest,
                    self.entry(),
                    self.identity,
                    sha256(b"").hexdigest(),
                )
            self.assertEqual(external.read_text(), "kept")
        with patch.object(review.private_io.os, "write", return_value=0):
            with self.assertRaises(OSError):
                self.append(self.entry())
        self.assertEqual(self.ledger.read_bytes(), b"")

    def test_independent_identity_and_archive_metadata_are_not_automatic_matches(self):
        self.identity = self.initialize()["ledger_id"]
        checked = item(
            "independent_dof_export",
            "checked",
            row_identity={
                "borough": "1",
                "block": "PRIVATE-1",
                "lot": "1",
                "apartment_number": "",
                "sale_date": "2026-01-01",
                "sale_price": "100",
            },
            identity_checked=True,
        )
        source = item(reference="sha256:" + self.source_sha)
        candidate = self.entry(
            evidence=[source, checked],
            rubric={"source_row_identity": finding("mismatch", "source", "checked")},
        )
        with self.assertRaisesRegex(ValueError, "verified local artifact protocol"):
            self.append(candidate)
        checked["row_identity"]["sale_price"] = "101"
        with self.assertRaisesRegex(ValueError, "verified local artifact protocol"):
            self.append(candidate)
        archive = item(
            "archived_row_snapshot",
            "archive",
            snapshot_sha256="b" * 64,
            official_revision_date="2026-01-01",
            row_identity={**checked["row_identity"], "sale_price": "100"},
            identity_checked=True,
        )
        for missing in (
            "snapshot_sha256",
            "official_revision_date",
            "row_identity",
            "identity_checked",
        ):
            broken = dict(archive)
            del broken[missing]
            with self.subTest(missing=missing):
                with self.assertRaises(ValueError):
                    self.append(self.entry(evidence=[source, broken]))
        broken = dict(archive, official_revision_date="2026-10-01")
        with self.assertRaisesRegex(ValueError, "postdate"):
            self.append(self.entry(evidence=[source, broken]))
        log = item("publication_log", "log", names_row=True)
        with self.assertRaisesRegex(ValueError, "earlier"):
            self.append(self.entry(evidence=[source, log]))

    def test_structural_invalid_inputs_fail_cleanly(self):
        self.identity = self.initialize()["ledger_id"]
        bad_entry = self.entry()
        bad_entry["review_status"] = []
        with self.assertRaises(ValueError):
            self.append(bad_entry)
        bad_entry = self.entry()
        bad_entry["evidence"][0]["kind"] = []
        with self.assertRaises(ValueError):
            self.append(bad_entry)
        bad_entry = self.entry()
        bad_entry["rubric"]["economic_transfer_scope"]["evidence_ids"] = [[]]
        with self.assertRaises(ValueError):
            self.append(bad_entry)
        bad_entry = self.entry()
        bad_entry["evidence"][0]["observed_at"] = "2026-09-29T00:00:00Z"
        with self.assertRaisesRegex(ValueError, "observed after"):
            self.append(bad_entry)
        self.assertEqual(self.ledger.read_bytes(), b"")

    def test_manifest_and_history_tampering_do_not_get_repaired(self):
        self.identity = self.initialize()["ledger_id"]
        self.append(self.entry())
        original = self.manifest.read_bytes()
        self.manifest.write_bytes(
            original.replace(self.identity.encode(), b"ledger-tampered")
        )
        with self.assertRaisesRegex(ValueError, "ledger ID"):
            review.summarize_reviews(
                self.source, self.sample, self.ledger, self.manifest
            )
        self.manifest.write_bytes(original)
        line = self.ledger.read_bytes()
        self.ledger.write_bytes(line + line)
        with self.assertRaisesRegex(ValueError, "Duplicate review entry"):
            review.summarize_reviews(
                self.source, self.sample, self.ledger, self.manifest
            )
        self.ledger.unlink()
        with self.assertRaisesRegex(ValueError, "missing"):
            review.summarize_reviews(
                self.source, self.sample, self.ledger, self.manifest
            )

    def test_helper_rejects_acl_hard_link_and_summary_overlap(self):
        self.identity = self.initialize()["ledger_id"]
        with patch.object(
            review.private_io, "verify_acl", side_effect=ValueError("ACL")
        ):
            with self.assertRaisesRegex(ValueError, "ACL"):
                review.summarize_reviews(
                    self.source, self.sample, self.ledger, self.manifest
                )
        linked = self.private / "linked.json"
        try:
            linked.hardlink_to(self.manifest)
        except OSError:
            pass
        else:
            with self.assertRaisesRegex(ValueError, "single-link"):
                review.private_io.private_path(linked, self.private, must_exist=True)
            linked.unlink()
        with self.assertRaises(FileExistsError):
            review.private_io.summary_target(self.manifest, (self.source,))
        with self.assertRaises(ValueError):
            future = self.root / "future.json"
            review.private_io.summary_target(future, (future, self.manifest))


if __name__ == "__main__":
    unittest.main()
