"""A pinned NYC capture can enter a private observation history without new labels."""

from __future__ import annotations

import csv
from hashlib import sha256
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

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
        name = f"nyc-usep-8jbt-{stamp.replace(':', '').replace('-', '')}.csv"
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
        path = self.root / f"manifest-{len(list(self.root.glob('manifest-*')))}.json"
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
        self.assertEqual(sum(before["representations"].values()), 3)
        self.assertEqual(sum(after["representations"].values()), 2)
        self.assertEqual(max(before["representations"].values()), 2)

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
        self.assertNotIn("representations", public)
        self.assertEqual(summary["first_public_availability_verified"], False)
        self.assertEqual(len(list(self.ledger.glob("*.json"))), 1)


if __name__ == "__main__":
    unittest.main()
