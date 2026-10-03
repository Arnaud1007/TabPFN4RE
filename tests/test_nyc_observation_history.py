"""A pinned NYC capture can enter a private observation history without new labels."""

from __future__ import annotations

import csv
from hashlib import sha256
from io import StringIO
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import tabpfn4realestate.data.nyc_observation_history as history
from tabpfn4realestate.data.nyc_observation_history import record_snapshot


HEADER = (
    "BOROUGH", "NEIGHBORHOOD", "BUILDING CLASS CATEGORY", "TAX CLASS AT PRESENT",
    "BLOCK", "LOT", "EASE-MENT", "BUILDING CLASS AT PRESENT", "ADDRESS",
    "APARTMENT NUMBER", "ZIP CODE", "RESIDENTIAL UNITS", "COMMERCIAL UNITS",
    "TOTAL UNITS", "LAND SQUARE FEET", "GROSS SQUARE FEET", "YEAR BUILT",
    "TAX CLASS AT TIME OF SALE", "BUILDING CLASS AT TIME OF SALE",
    "SALE PRICE", "SALE DATE",
)


def _row(address: str, price: str = "100000") -> tuple[str, ...]:
    values = ["" for _ in HEADER]
    values[0] = "1"
    values[4] = "100"
    values[5] = "5"
    values[8] = address
    values[19] = price
    values[20] = "2026-08-01"
    return tuple(values)


class ObservationHistoryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.raw = self.root / "raw"
        self.raw.mkdir()
        self.ledger = self.root / "history"

    def capture(
        self,
        stamp: str,
        rows: tuple[tuple[str, ...], ...],
        *,
        manifest_updates: dict | None = None,
    ) -> Path:
        output = StringIO(newline="")
        writer = csv.writer(output, lineterminator="\n")
        writer.writerow(HEADER)
        writer.writerows(rows)
        payload = output.getvalue().encode("utf-8")
        index = len(list(self.root.glob("manifest-*")))
        name = f"nyc-usep-8jbt-{stamp.replace(':', '').replace('-', '')}-{index}.csv"
        (self.raw / name).write_bytes(payload)
        manifest = {
            "source_id": "nyc_dof_rolling_usep_8jbt",
            "raw_filename": name,
            "sha256": sha256(payload).hexdigest(),
            "bytes": len(payload),
            "rows": len(rows),
            "header_kind": "name",
            "capture_started_at_utc": stamp,
            "capture_completed_at_utc": stamp,
            "conservative_known_by_at_utc": stamp,
            "capture_status": "inventory_only_not_asof_eligible",
        }
        manifest.update(manifest_updates or {})
        path = self.root / f"manifest-{index}.json"
        path.write_text(json.dumps(manifest), encoding="utf-8")
        return path

    def record(self, path: Path) -> dict:
        return record_snapshot(path, raw_root=self.raw, ledger_root=self.ledger)

    def test_identical_reordered_captures_are_distinct_events_with_no_delta(self) -> None:
        a, b = _row("10 MAIN ST"), _row("20 SIDE ST")
        first = self.capture("2026-09-28T22:55:43Z", (a, b))
        second = self.capture("2026-10-03T10:13:06Z", (b, a))
        first_summary = self.record(first)
        second_summary = self.record(second)
        self.assertEqual(first_summary["capture_status"], "inventory_only")
        self.assertEqual(second_summary["added_occurrences_bucket"], "zero")
        self.assertEqual(second_summary["removed_occurrences_bucket"], "zero")
        self.assertEqual(len(list(self.ledger.glob("*.json"))), 2)

    def test_add_remove_and_duplicate_count_are_multiset_deltas(self) -> None:
        a, b = _row("10 MAIN ST"), _row("20 SIDE ST")
        self.record(self.capture("2026-09-28T22:55:43Z", (a, a, b)))
        summary = self.record(self.capture("2026-10-03T10:13:06Z", (a, _row("30 NEW ST"))))
        self.assertEqual(summary["added_occurrences_bucket"], "1_to_9")
        self.assertEqual(summary["removed_occurrences_bucket"], "1_to_9")
        entries = sorted(self.ledger.glob("*.json"))
        before = json.loads(entries[0].read_text(encoding="utf-8"))
        after = json.loads(entries[1].read_text(encoding="utf-8"))
        self.assertEqual(before["rows"], 3)
        self.assertEqual(after["rows"], 2)
        self.assertNotIn("representations", json.dumps(before))
        self.assertNotIn("representations", json.dumps(after))

    def test_price_change_is_unmatched_representation_not_certified_correction(self) -> None:
        self.record(self.capture("2026-09-28T22:55:43Z", (_row("10 MAIN ST"),)))
        summary = self.record(self.capture("2026-10-03T10:13:06Z", (_row("10 MAIN ST", "101000"),)))
        self.assertEqual(summary["added_occurrences_bucket"], "1_to_9")
        self.assertEqual(summary["removed_occurrences_bucket"], "1_to_9")
        self.assertEqual(summary["certified_sale_labels"], 0)
        self.assertNotIn("correction", json.dumps(summary).lower())

    def test_replay_is_idempotent_and_does_not_write_another_entry(self) -> None:
        capture = self.capture("2026-09-28T22:55:43Z", (_row("10 MAIN ST"),))
        first = self.record(capture)
        second = self.record(capture)
        self.assertEqual(second["observation_sha256"], first["observation_sha256"])
        self.assertEqual(second["write_status"], "replayed")
        self.assertEqual(len(list(self.ledger.glob("*.json"))), 1)

    def test_rejects_tampered_input_and_earlier_capture(self) -> None:
        first = self.capture("2026-09-28T22:55:43Z", (_row("10 MAIN ST"),))
        self.record(first)
        older = self.capture("2026-09-27T22:55:43Z", (_row("20 SIDE ST"),))
        with self.assertRaisesRegex(ValueError, "chronolog"):
            self.record(older)
        tampered = self.capture("2026-10-03T10:13:06Z", (_row("30 NEW ST"),))
        (self.raw / json.loads(tampered.read_text())["raw_filename"]).write_bytes(b"bad")
        with self.assertRaisesRegex(ValueError, "hash|size"):
            self.record(tampered)
        self.assertEqual(len(list(self.ledger.glob("*.json"))), 1)

    def test_rejects_manifest_path_escape_and_clock_inversion(self) -> None:
        unsafe = self.capture(
            "2026-09-28T22:55:43Z", (_row("10 MAIN ST"),),
            manifest_updates={"raw_filename": "../outside.csv"},
        )
        with self.assertRaisesRegex(ValueError, "filename"):
            self.record(unsafe)
        inverted = self.capture(
            "2026-10-03T10:13:06Z", (_row("10 MAIN ST"),),
            manifest_updates={"capture_started_at_utc": "2026-10-04T00:00:00Z"},
        )
        with self.assertRaisesRegex(ValueError, "time"):
            self.record(inverted)
        self.assertEqual(list(self.ledger.glob("*.json")), [])

    def test_incomplete_temp_file_is_ignored_and_public_summary_is_private_safe(self) -> None:
        self.ledger.mkdir()
        (self.ledger / ".interrupted.part").write_text("partial", encoding="utf-8")
        summary = self.record(self.capture("2026-09-28T22:55:43Z", (_row("10 MAIN ST"),)))
        public = json.dumps(summary)
        self.assertNotIn("MAIN ST", public)
        self.assertNotIn("100000", public)
        self.assertNotIn('"representations":', public)
        self.assertNotIn("distinct_representations", public)
        self.assertEqual(summary["first_public_availability_verified"], False)
        self.assertEqual(len(list(self.ledger.glob("*.json"))), 1)
        entry = next(self.ledger.glob("*.json")).read_text(encoding="utf-8")
        self.assertNotIn("MAIN ST", entry)
        self.assertNotIn("representations", entry)

    def test_rejects_wrong_source_status_and_schema_variant(self) -> None:
        for changes, message in (
            ({"source_id": "another-source"}, "source"),
            ({"capture_status": "certified"}, "completed"),
            ({"header_kind": "fieldName"}, "schema"),
            ({"rows": 2}, "row count"),
        ):
            with self.subTest(changes=changes):
                manifest = self.capture(
                    "2026-09-28T22:55:43Z", (_row("10 MAIN ST"),),
                    manifest_updates=changes,
                )
                with self.assertRaisesRegex(ValueError, message):
                    self.record(manifest)
        self.assertEqual(list(self.ledger.glob("*.json")), [])

    def test_rejects_wrong_csv_header_and_wrong_field_count(self) -> None:
        manifest = self.capture("2026-09-28T22:55:43Z", (_row("10 MAIN ST"),))
        path = self.raw / json.loads(manifest.read_text())["raw_filename"]
        broken = path.read_bytes().replace(b"BOROUGH", b"DISTRICT", 1)
        path.write_bytes(broken)
        record = json.loads(manifest.read_text())
        record["bytes"] = len(broken)
        record["sha256"] = sha256(broken).hexdigest()
        manifest.write_text(json.dumps(record), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "header"):
            self.record(manifest)
        self.assertEqual(list(self.ledger.glob("*.json")), [])

        malformed = self.capture("2026-10-03T10:13:06Z", (_row("20 SIDE ST"),))
        malformed_path = self.raw / json.loads(malformed.read_text())["raw_filename"]
        lines = malformed_path.read_text(encoding="utf-8").splitlines()
        wrong_fields = (lines[0] + "\n" + "1,20 SIDE ST\n").encode()
        malformed_path.write_bytes(wrong_fields)
        changed = json.loads(malformed.read_text())
        changed["bytes"] = len(wrong_fields)
        changed["sha256"] = sha256(wrong_fields).hexdigest()
        malformed.write_text(json.dumps(changed), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "field count"):
            self.record(malformed)

    def test_rejects_corrupted_private_history_before_appending(self) -> None:
        self.record(self.capture("2026-09-28T22:55:43Z", (_row("10 MAIN ST"),)))
        entry = next(self.ledger.glob("*.json"))
        entry.write_text("{broken", encoding="utf-8")
        later = self.capture("2026-10-03T10:13:06Z", (_row("20 SIDE ST"),))
        with self.assertRaisesRegex(ValueError, "entry"):
            self.record(later)
        self.assertEqual(len(list(self.ledger.glob("*.json"))), 1)

    def test_rechecks_prior_raw_capture_before_appending(self) -> None:
        first = self.capture("2026-09-28T22:55:43Z", (_row("10 MAIN ST"),))
        self.record(first)
        raw_name = json.loads(first.read_text())["raw_filename"]
        (self.raw / raw_name).write_bytes(b"changed")
        later = self.capture("2026-10-03T10:13:06Z", (_row("20 SIDE ST"),))
        with self.assertRaisesRegex(ValueError, "size|hash"):
            self.record(later)
        self.assertEqual(len(list(self.ledger.glob("*.json"))), 1)

    def test_rejects_tampered_prior_entry_metadata(self) -> None:
        self.record(self.capture("2026-09-28T22:55:43Z", (_row("10 MAIN ST"),)))
        entry = next(self.ledger.glob("*.json"))
        altered = json.loads(entry.read_text(encoding="utf-8"))
        altered["raw_sha256"] = "0" * 64
        entry.write_text(json.dumps(altered), encoding="utf-8")
        later = self.capture("2026-10-03T10:13:06Z", (_row("20 SIDE ST"),))
        with self.assertRaisesRegex(ValueError, "pinned capture"):
            self.record(later)

    def test_rejects_prior_entry_with_extra_fields_or_wrong_filename(self) -> None:
        self.record(self.capture("2026-09-28T22:55:43Z", (_row("10 MAIN ST"),)))
        entry = next(self.ledger.glob("*.json"))
        original = json.loads(entry.read_text(encoding="utf-8"))
        later = self.capture("2026-10-03T10:13:06Z", (_row("20 SIDE ST"),))
        entry.write_text(json.dumps({**original, "unexpected": "x"}), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "fields"):
            self.record(later)
        entry.write_text(json.dumps(original), encoding="utf-8")
        renamed = entry.with_name("wrong-name.json")
        entry.rename(renamed)
        with self.assertRaisesRegex(ValueError, "filename"):
            self.record(later)
        self.assertEqual(len(list(self.ledger.glob("*.json"))), 1)

    def test_rejects_bounded_input_sizes_before_processing(self) -> None:
        capture = self.capture("2026-09-28T22:55:43Z", (_row("10 MAIN ST"),))
        with patch.object(history, "MAX_MANIFEST_BYTES", 8):
            with self.assertRaisesRegex(ValueError, "size"):
                self.record(capture)
        with patch.object(history, "MAX_CSV_BYTES", 8):
            with self.assertRaisesRegex(ValueError, "size"):
                self.record(capture)
        self.assertEqual(list(self.ledger.glob("*.json")), [])

    def test_failed_append_releases_write_lock(self) -> None:
        self.record(self.capture("2026-09-28T22:55:43Z", (_row("10 MAIN ST"),)))
        older = self.capture("2026-09-27T22:55:43Z", (_row("20 SIDE ST"),))
        with self.assertRaisesRegex(ValueError, "chronolog"):
            self.record(older)
        self.assertFalse((self.ledger / ".write.lock").exists())
        later = self.capture("2026-10-03T10:13:06Z", (_row("30 NEW ST"),))
        self.assertEqual(self.record(later)["write_status"], "recorded")

    def test_existing_write_lock_rejects_new_record(self) -> None:
        self.ledger.mkdir()
        (self.ledger / ".write.lock").write_text("running", encoding="utf-8")
        capture = self.capture("2026-09-28T22:55:43Z", (_row("10 MAIN ST"),))
        with self.assertRaisesRegex(FileExistsError, "lock"):
            self.record(capture)
        self.assertEqual(list(self.ledger.glob("*.json")), [])

    def test_rejects_duplicate_capture_time_without_overwrite(self) -> None:
        self.record(self.capture("2026-09-28T22:55:43Z", (_row("10 MAIN ST"),)))
        second = self.capture("2026-09-28T22:55:43Z", (_row("20 SIDE ST"),))
        with self.assertRaisesRegex(ValueError, "chronolog"):
            self.record(second)
        self.assertEqual(len(list(self.ledger.glob("*.json"))), 1)

    def test_equivalent_utc_spelling_is_same_capture_instant(self) -> None:
        self.record(self.capture("2026-09-28T22:55:43Z", (_row("10 MAIN ST"),)))
        second = self.capture("2026-09-28T22:55:43.000Z", (_row("20 SIDE ST"),))
        with self.assertRaisesRegex(ValueError, "chronolog"):
            self.record(second)

    def test_rejects_capture_timestamp_from_future(self) -> None:
        future = self.capture("2099-01-01T00:00:00Z", (_row("10 MAIN ST"),))
        with self.assertRaisesRegex(ValueError, "future"):
            self.record(future)

    def test_rejects_symlinked_private_root(self) -> None:
        link = self.root / "linked"
        capture = self.capture("2026-09-28T22:55:43Z", (_row("10 MAIN ST"),))
        original_is_symlink = Path.is_symlink

        def synthetic_link(path: Path) -> bool:
            return path == link or original_is_symlink(path)

        with patch.object(Path, "is_symlink", synthetic_link):
            with self.assertRaisesRegex(ValueError, "symlink"):
                record_snapshot(capture, raw_root=self.raw, ledger_root=link)

    def test_cli_records_offline_capture_with_aggregate_json(self) -> None:
        capture = self.capture("2026-09-28T22:55:43Z", (_row("10 MAIN ST"),))
        process = subprocess.run(
            [
                sys.executable, "-m", "tabpfn4realestate.data.nyc_observation_history",
                "--manifest", str(capture), "--raw-root", str(self.raw),
                "--ledger-root", str(self.ledger),
            ],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(process.returncode, 0, process.stderr)
        result = json.loads(process.stdout)
        self.assertEqual(result["write_status"], "recorded")
        self.assertNotIn("MAIN ST", process.stdout)


if __name__ == "__main__":
    unittest.main()
