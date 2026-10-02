"""Synthetic, offline contracts for the pinned NYC archive/current comparison.

Every row here is invented. No captured NYC source row is opened by this suite.
"""

from __future__ import annotations

import csv
from hashlib import sha256
import json
import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import compare_nyc_archive_snapshot_v1 as comparison  # noqa: E402


ARCHIVE_FIELDS = (
    "neighborhood",
    "building_class_category",
    "lot",
    "ease_ment",
    "building_class_at_present",
    "address",
    "apartment_number",
    "borough",
    "residential_units",
    "commercial_units",
    "total_units",
    "gross_square_feet",
    "block",
    "tax_class_at_time_of_sale",
    "building_class_at_time_of",
    "land_square_feet",
    "sale_date",
    "tax_class_at_present",
    "sale_price",
    "year_built",
    "zip_code",
)


def _csv_bytes(header: tuple[str, ...], rows: list[tuple[str, ...]]) -> bytes:
    buffer = StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(header)
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def _row(
    marker: str,
    *,
    sale_date: str = "2026-09-28",
    price: str = "100",
    address: str | None = None,
) -> tuple[str, ...]:
    fields = [""] * 21
    fields[0] = "2"
    fields[4] = marker
    fields[5] = "1"
    fields[8] = address if address is not None else f"SYNTHETIC {marker} ST"
    fields[19] = price
    fields[20] = sale_date
    return tuple(fields)


class ArchiveSchemaTests(unittest.TestCase):
    def test_archive_header_is_explicit_exact_21_column_source_order(self) -> None:
        self.assertEqual(comparison.ARCHIVE_HEADER, ARCHIVE_FIELDS)
        self.assertEqual(len(comparison.CURRENT_HEADER), 21)

    def test_archive_mapping_is_positional_and_lossless(self) -> None:
        source = tuple(f"synthetic-{index}" for index in range(21))
        expected_order = (
            7,
            0,
            1,
            17,
            12,
            2,
            3,
            4,
            5,
            6,
            20,
            8,
            9,
            10,
            15,
            11,
            19,
            13,
            14,
            18,
            16,
        )
        self.assertEqual(
            comparison.reorder_archive_row(source),
            tuple(source[index] for index in expected_order),
        )

    def test_archive_header_drift_and_row_width_are_rejected(self) -> None:
        source = tuple(str(index) for index in range(21))
        changed = list(ARCHIVE_FIELDS)
        changed[13], changed[14] = changed[14], changed[13]
        with self.assertRaises(ValueError):
            comparison.reorder_archive_row(source, header=tuple(changed))
        with self.assertRaises(ValueError):
            comparison.reorder_archive_row(source[:-1])

    def test_scanner_accepts_exact_headers_and_preserves_source_cell_bytes(
        self,
    ) -> None:
        current = _row("007", address="  RUE ÉTÉ, 🏠  ")
        archive = tuple(
            current[index]
            for index in (
                1,
                2,
                5,
                6,
                7,
                8,
                9,
                0,
                11,
                12,
                13,
                15,
                4,
                17,
                18,
                14,
                20,
                3,
                19,
                16,
                10,
            )
        )
        self.assertEqual(
            comparison.scan_csv(
                _csv_bytes(ARCHIVE_FIELDS, [archive]),
                source="archive",
                expected_rows=1,
            ),
            [current],
        )
        self.assertEqual(
            comparison.scan_csv(
                _csv_bytes(comparison.CURRENT_HEADER, [current]),
                source="current",
                expected_rows=1,
            ),
            [current],
        )

    def test_scanner_rejects_changed_header_count_width_and_encoding(self) -> None:
        row = _row("12")
        valid = _csv_bytes(comparison.CURRENT_HEADER, [row])
        cases = (
            (valid, "current", 2),
            (_csv_bytes(comparison.CURRENT_HEADER, [row[:-1]]), "current", 1),
            (
                _csv_bytes(tuple(reversed(comparison.CURRENT_HEADER)), [row]),
                "current",
                1,
            ),
            (_csv_bytes(ARCHIVE_FIELDS[:-1], [row[:-1]]), "archive", 1),
            (valid + b"\xff", "current", 1),
        )
        for body, source, count in cases:
            with self.subTest(source=source, count=count, body_length=len(body)):
                with self.assertRaises(ValueError):
                    comparison.scan_csv(body, source=source, expected_rows=count)
        with self.assertRaises(ValueError):
            comparison.scan_csv(valid, source="unknown", expected_rows=1)

    def test_scanner_rejects_byte_cell_row_and_null_limits(self) -> None:
        row = _row("12")
        valid = _csv_bytes(comparison.CURRENT_HEADER, [row])
        for count in (-1, True, comparison.MAX_ROWS + 1):
            with self.subTest(count=count):
                with self.assertRaises(ValueError):
                    comparison.scan_csv(valid, source="current", expected_rows=count)
        with patch.object(comparison, "MAX_CSV_BYTES", len(valid) - 1):
            with self.assertRaises(ValueError):
                comparison.scan_csv(valid, source="current", expected_rows=1)
        with patch.object(comparison, "MAX_FIELD_CHARS", 2):
            with self.assertRaises(ValueError):
                comparison.scan_csv(valid, source="current", expected_rows=1)
        with patch.object(comparison, "MAX_CELL_CHARS", 2):
            with self.assertRaises(ValueError):
                comparison.scan_csv(valid, source="current", expected_rows=1)
        with patch.object(comparison, "MAX_ROWS", 1):
            with self.assertRaises(ValueError):
                comparison.scan_csv(
                    _csv_bytes(comparison.CURRENT_HEADER, [row, row]),
                    source="current",
                    expected_rows=1,
                )
        with self.assertRaises(ValueError):
            comparison.scan_csv(valid + b"\x00", source="current", expected_rows=1)


class DateAndMultisetTests(unittest.TestCase):
    def test_calendar_date_normalization_has_strict_bounds_and_midnight(self) -> None:
        for source in (
            "2026-09-28",
            "09/28/2026",
            "2026-09-28T00:00:00",
            "2026-09-28T00:00:00.000",
            "2026-09-28 00:00:00.000000",
        ):
            with self.subTest(source=source):
                self.assertEqual(comparison.canonical_date(source), "2026-09-28")
        self.assertEqual(comparison.canonical_date("1900-01-01"), "1900-01-01")
        self.assertEqual(comparison.canonical_date("2026-10-02"), "2026-10-02")
        for invalid in (
            "",
            "2026-02-30",
            "02/30/2026",
            "1899-12-31",
            "2026-10-03",
            "2026-09-28T00:00:01",
            "2026-09-28T00:00:00.000001",
            "2026-09-28Z",
            "09/28/26",
            " 2026-09-28 ",
        ):
            with self.subTest(invalid=invalid):
                self.assertIsNone(comparison.canonical_date(invalid))

    def test_full_row_multiset_counts_duplicates_and_residuals(self) -> None:
        a = _row("A")
        b = _row("B")
        result = comparison.compare_rows([a, a, b], [a, b, b])
        self.assertEqual(result["archive_rows"], 3)
        self.assertEqual(result["current_rows"], 3)
        self.assertEqual(result["raw_full_row_multiset_matches"], 2)
        self.assertEqual(result["archive_raw_residual_rows"], 1)
        self.assertEqual(result["current_raw_residual_rows"], 1)
        self.assertEqual(result["date_canonical_full_row_multiset_matches"], 2)

    def test_date_tier_excludes_invalid_dates_and_changes_date_only(self) -> None:
        archive = [
            _row("A", sale_date="09/28/2026", address="  SYNTHETIC A ST  "),
            _row("B", sale_date="2026-02-30"),
            _row("C", sale_date="2026-10-02", price="0100"),
        ]
        current = [
            _row("A", sale_date="2026-09-28"),
            _row("B", sale_date="2026-02-30"),
            _row("C", sale_date="2026-10-02T00:00:00", price="100"),
        ]
        result = comparison.compare_rows(archive, current)
        self.assertEqual(result["raw_full_row_multiset_matches"], 1)
        self.assertEqual(result["date_canonical_full_row_multiset_matches"], 1)
        self.assertEqual(result["archive_invalid_date_rows"], 1)
        self.assertEqual(result["current_invalid_date_rows"], 1)
        self.assertEqual(result["archive_date_eligible_rows"], 2)
        self.assertEqual(result["current_date_eligible_rows"], 2)
        self.assertEqual(result["archive_date_residual_rows"], 1)
        self.assertEqual(result["current_date_residual_rows"], 1)

    def test_public_projection_contains_no_row_values_or_fingerprints(self) -> None:
        private = comparison.compare_rows(
            [_row("PRIVATE", address="PRIVATE ADDRESS", price="777777")],
            [_row("PRIVATE", address="PRIVATE ADDRESS", price="777777")],
        )
        public = comparison.public_projection(private)
        encoded = json.dumps(public, sort_keys=True)
        self.assertEqual(public["archive_rows"], 1)
        self.assertEqual(public["current_rows"], 1)
        self.assertEqual(public["sale_labels_certified"], 0)
        self.assertFalse(public["historical_asof_eligible"])
        for private_value in (
            "PRIVATE ADDRESS",
            "777777",
            "PRIVATE",
            "ledger",
            "ordinal",
            "row_sha256",
        ):
            self.assertNotIn(private_value, encoded)
        self.assertNotEqual(public.get("raw_full_row_multiset_matches"), 1)

    def test_invalid_row_structure_and_public_counters_fail_closed(self) -> None:
        with self.assertRaises(ValueError):
            comparison.compare_rows([("too", "short")], [])
        with self.assertRaises(ValueError):
            comparison.compare_rows([(*_row("A")[:-1], 12)], [])
        with patch.object(comparison, "MAX_ROWS", 0):
            with self.assertRaises(ValueError):
                comparison.compare_rows([_row("A")], [])
        for private in (
            {"archive_rows": 1, "current_rows": 1},
            {
                "archive_rows": 1,
                "current_rows": 1,
                "raw_full_row_multiset_matches": -1,
                "date_canonical_full_row_multiset_matches": 0,
            },
            {
                "archive_rows": 1,
                "current_rows": 1,
                "raw_full_row_multiset_matches": 2,
                "date_canonical_full_row_multiset_matches": 0,
            },
        ):
            with self.subTest(private=private):
                with self.assertRaises(ValueError):
                    comparison.public_projection(private)


class OfflineRunTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.private_root = self.root / "data/raw/nyc_dof"
        self.private_root.mkdir(parents=True)
        self.archive_run = self.private_root / "ready-archive-v2-20261002T210520Z"
        self.archive_run.mkdir()
        public_archive = self.root / "runs/archive/manifest.json"
        public_archive.parent.mkdir(parents=True)
        snapshot_manifest = self.root / "runs/snapshot/snapshot.json"
        snapshot_manifest.parent.mkdir(parents=True)
        environment_lock = self.root / "locks/environment.json"
        environment_lock.parent.mkdir(parents=True)
        environment_lock.write_bytes(b'{"python":"3.11"}\n')
        self.output = (
            self.private_root / "archive-current-v1-20261002T213000Z-000000000001"
        )

        current = _row("A", address="SYNTHETIC ONLY", price="777")
        reverse_indices = (
            1,
            2,
            5,
            6,
            7,
            8,
            9,
            0,
            11,
            12,
            13,
            15,
            4,
            17,
            18,
            14,
            20,
            3,
            19,
            16,
            10,
        )
        archive = tuple(current[index] for index in reverse_indices)
        archive_body = _csv_bytes(ARCHIVE_FIELDS, [archive])
        current_body = _csv_bytes(comparison.CURRENT_HEADER, [current])
        (self.archive_run / "archive.csv").write_bytes(archive_body)
        (self.private_root / "snapshot.csv").write_bytes(current_body)
        archive_sha = sha256(archive_body).hexdigest()
        current_sha = sha256(current_body).hexdigest()
        archive_manifest_body = json.dumps(
            {
                "protocol": "nyc-ready-rolling-archive-v2",
                "version": 62,
                "requests": [
                    {
                        "stage": "csv",
                        "file": "archive.csv",
                        "sha256": archive_sha,
                        "bytes": len(archive_body),
                    }
                ],
            }
        ).encode("utf-8")
        public_archive.write_bytes(archive_manifest_body)
        (self.archive_run / "manifest.json").write_bytes(archive_manifest_body)
        snapshot_manifest.write_text(
            json.dumps(
                {
                    "source_id": "nyc_dof_rolling_usep_8jbt",
                    "sha256": current_sha,
                    "bytes": len(current_body),
                    "rows": 1,
                    "raw_filename": "snapshot.csv",
                }
            ),
            encoding="utf-8",
        )
        pinned = {
            "ROOT": self.root,
            "PRIVATE_ROOT": self.private_root,
            "ARCHIVE_RUN": self.archive_run,
            "ARCHIVE_MANIFEST": public_archive,
            "SNAPSHOT_MANIFEST": snapshot_manifest,
            "ENVIRONMENT_LOCK": environment_lock,
            "ARCHIVE_SHA256": archive_sha,
            "CURRENT_SHA256": current_sha,
            "ARCHIVE_MANIFEST_SHA256": sha256(archive_manifest_body).hexdigest(),
            "SNAPSHOT_MANIFEST_SHA256": sha256(
                snapshot_manifest.read_bytes()
            ).hexdigest(),
            "ENVIRONMENT_LOCK_SHA256": sha256(
                environment_lock.read_bytes()
            ).hexdigest(),
            "ARCHIVE_BYTES": len(archive_body),
            "CURRENT_BYTES": len(current_body),
            "ARCHIVE_ROWS": 1,
            "CURRENT_ROWS": 1,
        }
        for name, value in pinned.items():
            mocked = patch.object(comparison, name, value)
            mocked.start()
            self.addCleanup(mocked.stop)
        for mocked in (
            patch.object(comparison, "_git_state", return_value=("a" * 40, False)),
            patch.object(comparison, "_remote_tracking_commit", return_value="a" * 40),
            patch.object(
                comparison, "_code_hashes", return_value={"synthetic": "b" * 64}
            ),
            patch.object(
                comparison.subprocess,
                "run",
                return_value=SimpleNamespace(returncode=0),
            ),
            patch.object(comparison.private_review_io, "secure_directory"),
            patch.object(comparison.private_review_io, "verify_acl"),
        ):
            mocked.start()
            self.addCleanup(mocked.stop)

    def test_compare_replay_is_offline_create_only_and_aggregate_only(self) -> None:
        scanner = comparison.scan_csv

        def scan_after_intent(body: bytes, *, source: str, expected_rows: int):
            self.assertTrue((self.output / "intent.json").is_file())
            return scanner(body, source=source, expected_rows=expected_rows)

        with patch.object(
            comparison, "scan_csv", side_effect=scan_after_intent
        ) as scan:
            public = comparison.compare(self.output)
        self.assertEqual(scan.call_count, 2)
        self.assertEqual(public["archive_rows"], 1)
        self.assertEqual(public["current_rows"], 1)
        self.assertEqual(public["raw_overlap_bucket"], "suppressed_1_to_4")
        self.assertEqual(comparison.replay(self.output), public)
        self.assertEqual(
            {item.name for item in self.output.iterdir()},
            {"intent.json", "result.json", "public.json", "hash_manifest.json"},
        )
        self.assertNotIn("SYNTHETIC ONLY", (self.output / "result.json").read_text())
        self.assertNotIn("777", (self.output / "public.json").read_text())
        with self.assertRaises(FileExistsError):
            comparison.compare(self.output)

    def test_replay_rejects_saved_artifact_and_source_tampering(self) -> None:
        comparison.compare(self.output)
        public_path = self.output / "public.json"
        original = public_path.read_bytes()
        public_path.write_bytes(original.replace(b"PENDING", b"ACCEPTED"))
        with self.assertRaises(ValueError):
            comparison.replay(self.output)
        public_path.write_bytes(original)

        source_path = self.archive_run / "archive.csv"
        source_path.write_bytes(source_path.read_bytes() + b"\n")
        with self.assertRaises(ValueError):
            comparison.replay(self.output)

    def test_source_hash_mismatch_marks_run_incomplete_before_csv_parse(self) -> None:
        source_path = self.archive_run / "archive.csv"
        source_path.write_bytes(source_path.read_bytes() + b"\n")
        with patch.object(comparison, "scan_csv") as scan:
            with self.assertRaises(ValueError):
                comparison.compare(self.output)
        scan.assert_not_called()
        failure = json.loads((self.output / "failure.json").read_bytes())
        self.assertEqual(failure["status"], "incomplete")
        self.assertFalse((self.output / "public.json").exists())
        with self.assertRaises(ValueError):
            comparison.replay(self.output)

    def test_manifest_hash_mismatch_rejects_before_run_reservation(self) -> None:
        comparison.ARCHIVE_MANIFEST.write_bytes(b"{}")
        with patch.object(comparison, "_compute") as compute:
            with self.assertRaises(ValueError):
                comparison.compare(self.output)
        compute.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_unpushed_code_rejects_before_csv_open_or_run_reservation(self) -> None:
        with (
            patch.object(comparison, "_remote_tracking_commit", return_value="c" * 40),
            patch.object(comparison, "_compute") as compute,
        ):
            with self.assertRaisesRegex(ValueError, "push"):
                comparison.compare(self.output)
        compute.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_interrupted_run_has_no_valid_result_or_private_exception_text(
        self,
    ) -> None:
        with patch.object(
            comparison, "_compute", side_effect=ValueError("PRIVATE ROW")
        ):
            with self.assertRaisesRegex(ValueError, "PRIVATE ROW"):
                comparison.compare(self.output)
        failure = json.loads((self.output / "failure.json").read_bytes())
        self.assertEqual(failure["status"], "incomplete")
        self.assertNotIn("PRIVATE ROW", json.dumps(failure))
        self.assertFalse((self.output / "result.json").exists())
        self.assertFalse((self.output / "public.json").exists())
        with self.assertRaises(ValueError):
            comparison.replay(self.output)


if __name__ == "__main__":
    unittest.main()
