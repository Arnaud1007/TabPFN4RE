"""Tests for the private append-only HCPA release observation ledger."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import scripts.hcpa_release_observation_ledger as ledger


def make_capture(
    root: Path,
    run: str,
    family: str,
    filename: str,
    content: bytes,
    observed: str,
) -> Path:
    run_dir = root / run
    run_dir.mkdir()
    archive = run_dir / filename
    archive.write_bytes(content)
    manifest = {
        "status": "observed_not_qualified",
        "family": family,
        "filename": filename,
        "capture_completed_at_utc": observed,
        "raw_zip_bytes": len(content),
        "raw_zip_sha256": sha256(content).hexdigest(),
        "listing_html_sha256": "a" * 64,
        "first_public_availability_verified": False,
        "certified_sale_labels": 0,
        "g_us_gate": "PENDING",
    }
    path = run_dir / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


class HcpaReleaseObservationLedgerTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "prospective-releases"
        self.root.mkdir()
        self.ledger = self.root / "observations.jsonl"
        patches = (
            patch.object(ledger, "verify_acl", lambda _path: None),
            patch.object(ledger, "real_directory", lambda _path, _parent: None),
        )
        for mocked in patches:
            mocked.start()
            self.addCleanup(mocked.stop)

    def append(
        self,
        run: str,
        family: str,
        filename: str,
        content: bytes,
        observed: str,
    ) -> dict:
        manifest = make_capture(self.root, run, family, filename, content, observed)
        return ledger.append_observation(self.ledger, manifest, self.root)

    def test_classifies_first_repeat_new_release_rename_and_correction(self) -> None:
        first = self.append(
            "a",
            "allsales",
            "allsales_09_18_2026.zip",
            b"PK\x03\x04a",
            "2026-10-05T09:00:00Z",
        )
        repeat = self.append(
            "b",
            "allsales",
            "allsales_09_18_2026.zip",
            b"PK\x03\x04a",
            "2026-10-06T09:00:00Z",
        )
        correction = self.append(
            "c",
            "allsales",
            "allsales_09_18_2026.zip",
            b"PK\x03\x04b",
            "2026-10-07T09:00:00Z",
        )
        renamed = self.append(
            "d",
            "allsales",
            "allsales_09_25_2026.zip",
            b"PK\x03\x04b",
            "2026-10-08T09:00:00Z",
        )
        new = self.append(
            "e",
            "allsales",
            "allsales_10_02_2026.zip",
            b"PK\x03\x04c",
            "2026-10-09T09:00:00Z",
        )
        self.assertEqual(
            [x["diff_status"] for x in (first, repeat, correction, renamed, new)],
            [
                "first_observation",
                "unchanged",
                "same_name_content_changed",
                "renamed_same_content",
                "new_release",
            ],
        )
        self.assertIsNone(first["predecessor_entry_id"])
        self.assertEqual(repeat["predecessor_entry_id"], first["entry_id"])
        self.assertEqual(new["predecessor_entry_id"], renamed["entry_id"])
        self.assertEqual(len(ledger.replay(self.ledger, self.root)), 5)

    def test_family_chains_are_independent_and_replay_is_deterministic(self) -> None:
        sales = self.append(
            "a",
            "allsales",
            "allsales_09_18_2026.zip",
            b"PK\x03\x04x",
            "2026-10-05T09:00:00Z",
        )
        parcels = self.append(
            "b",
            "parcels",
            "parcels_10_02_2026.zip",
            b"PK\x03\x04x",
            "2026-10-05T09:01:00Z",
        )
        self.assertIsNone(sales["predecessor_entry_id"])
        self.assertIsNone(parcels["predecessor_entry_id"])
        once = ledger.replay(self.ledger, self.root)
        twice = ledger.replay(self.ledger, self.root)
        self.assertEqual(once, twice)
        self.assertEqual(once[1]["previous_entry_sha256"], once[0]["entry_sha256"])

    def test_rejects_time_regression_tampering_and_incomplete_capture(self) -> None:
        self.append(
            "a",
            "allsales",
            "allsales_09_18_2026.zip",
            b"PK\x03\x04a",
            "2026-10-05T09:00:00Z",
        )
        before = self.ledger.read_bytes()
        with self.assertRaises(ValueError):
            self.append(
                "b",
                "allsales",
                "allsales_09_25_2026.zip",
                b"PK\x03\x04b",
                "2026-10-05T08:59:59Z",
            )
        self.assertEqual(self.ledger.read_bytes(), before)
        incomplete = make_capture(
            self.root,
            "c",
            "parcels",
            "parcels_10_02_2026.zip",
            b"PK\x03\x04c",
            "2026-10-06T09:00:00Z",
        )
        (incomplete.parent / ".incomplete").write_text("incomplete")
        with self.assertRaises(ValueError):
            ledger.append_observation(self.ledger, incomplete, self.root)
        payload = json.loads(self.ledger.read_text().splitlines()[0])
        payload["file_bytes"] += 1
        self.ledger.write_text(json.dumps(payload) + "\n")
        with self.assertRaises(ValueError):
            ledger.replay(self.ledger, self.root)

    def test_rejects_manifest_or_archive_mismatch_and_replays_duplicate(self) -> None:
        manifest = make_capture(
            self.root,
            "a",
            "allsales",
            "allsales_09_18_2026.zip",
            b"PK\x03\x04a",
            "2026-10-05T09:00:00Z",
        )
        first = ledger.append_observation(self.ledger, manifest, self.root)
        before = self.ledger.read_bytes()
        replayed = ledger.append_observation(self.ledger, manifest, self.root)
        self.assertEqual(replayed, first)
        self.assertEqual(self.ledger.read_bytes(), before)
        (manifest.parent / "allsales_09_18_2026.zip").write_bytes(b"changed")
        with self.assertRaises(ValueError):
            ledger.verify_capture(manifest, self.root)
        self.assertEqual(self.ledger.read_bytes(), before)

    def test_microsecond_observations_in_one_second_remain_ordered(self) -> None:
        first = self.append(
            "a",
            "allsales",
            "allsales_09_18_2026.zip",
            b"PK\x03\x04a",
            "2026-10-05T09:00:00.000001Z",
        )
        second = self.append(
            "b",
            "parcels",
            "parcels_10_02_2026.zip",
            b"PK\x03\x04b",
            "2026-10-05T09:00:00.000002Z",
        )
        self.assertNotEqual(first["entry_id"], second["entry_id"])
        self.assertEqual(len(ledger.replay(self.ledger, self.root)), 2)

    def test_atomic_failure_preserves_prior_ledger(self) -> None:
        self.append(
            "a",
            "allsales",
            "allsales_09_18_2026.zip",
            b"PK\x03\x04a",
            "2026-10-05T09:00:00Z",
        )
        before = self.ledger.read_bytes()
        manifest = make_capture(
            self.root,
            "b",
            "parcels",
            "parcels_10_02_2026.zip",
            b"PK\x03\x04b",
            "2026-10-06T09:00:00Z",
        )
        with patch.object(ledger, "atomic_replace", side_effect=OSError("disk")):
            with self.assertRaises(OSError):
                ledger.append_observation(self.ledger, manifest, self.root)
        self.assertEqual(self.ledger.read_bytes(), before)

    def test_stale_ledger_lock_file_is_harmless_but_live_lock_excludes(self) -> None:
        lock = self.root / "observations.jsonl.lock"
        lock.write_bytes(b"\0")
        first = self.append(
            "a",
            "allsales",
            "allsales_09_18_2026.zip",
            b"PK\x03\x04a",
            "2026-10-05T09:00:00Z",
        )
        self.assertEqual(first["diff_status"], "first_observation")
        with ledger.advisory_lock(lock, self.root):
            manifest = make_capture(
                self.root,
                "b",
                "parcels",
                "parcels_10_02_2026.zip",
                b"PK\x03\x04b",
                "2026-10-06T09:00:00Z",
            )
            with self.assertRaises(OSError):
                ledger.append_observation(self.ledger, manifest, self.root)

    def test_summary_has_exact_privacy_safe_schema(self) -> None:
        self.append(
            "secret-owner-address",
            "allsales",
            "allsales_09_18_2026.zip",
            b"PK\x03\x04secret row",
            "2026-10-05T09:00:00Z",
        )
        summary = ledger.summarize(self.ledger, self.root)
        self.assertEqual(
            set(summary),
            {
                "schema_version",
                "ledger_sha256",
                "observation_count",
                "counts_by_family",
                "counts_by_diff_status",
                "latest_by_family",
                "certified_sale_labels",
                "g_us_gate",
            },
        )
        serialized = json.dumps(summary)
        self.assertNotIn("secret-owner-address", serialized)
        self.assertNotIn("secret row", serialized)
        self.assertEqual(summary["certified_sale_labels"], 0)
        self.assertEqual(summary["g_us_gate"], "PENDING")

    def test_rejects_invalid_manifest_and_corrupt_ledger_shapes(self) -> None:
        manifest = make_capture(
            self.root,
            "a",
            "allsales",
            "allsales_09_18_2026.zip",
            b"PK\x03\x04a",
            "2026-10-05T09:00:00Z",
        )
        original = json.loads(manifest.read_text())
        mutations = (
            {**original, "family": "other"},
            {**original, "status": "qualified"},
            {**original, "capture_completed_at_utc": "not-a-time"},
            {**original, "listing_html_sha256": "bad"},
            {**original, "raw_zip_bytes": 0},
        )
        for index, value in enumerate(mutations):
            with self.subTest(index=index):
                manifest.write_text(json.dumps(value), encoding="utf-8")
                with self.assertRaises(ValueError):
                    ledger.verify_capture(manifest, self.root)
        manifest.write_text(json.dumps(original), encoding="utf-8")
        ledger.append_observation(self.ledger, manifest, self.root)
        entry = json.loads(self.ledger.read_text())
        for index, value in enumerate(
            (
                {**entry, "extra": True},
                {**entry, "schema_version": "other"},
                {**entry, "file_sha256": "bad"},
                {**entry, "file_bytes": 0},
                {**entry, "diff_status": "invented"},
            )
        ):
            with self.subTest(ledger_index=index):
                self.ledger.write_text(json.dumps(value) + "\n", encoding="ascii")
                with self.assertRaises(ValueError):
                    ledger.replay(self.ledger, self.root)


if __name__ == "__main__":
    unittest.main()
