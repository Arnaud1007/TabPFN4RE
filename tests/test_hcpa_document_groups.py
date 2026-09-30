"""Synthetic, private-data-safe checks for the HCPA document-group audit."""

from __future__ import annotations

from contextlib import closing
from hashlib import sha256
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from zipfile import ZIP_STORED, ZipFile


SCRIPT = (
    Path(__file__).resolve().parents[1] / "scripts" / "profile_hcpa_document_groups.py"
)
sys.path.insert(0, str(SCRIPT.parent))
spec = spec_from_file_location("profile_hcpa_document_groups", SCRIPT)
assert spec is not None and spec.loader is not None
audit = module_from_spec(spec)
spec.loader.exec_module(audit)

FIELDS = (
    ("PIN", 12),
    ("FOLIO", 12),
    ("S_DATE", 8),
    ("S_AMT", 16),
    ("QU", 1),
    ("VI", 1),
    ("REA_CD", 2),
    ("S_TYPE", 2),
    ("DOR_CODE", 4),
    ("DOC_NUM", 12),
    ("OR_BK", 8),
    ("OR_PG", 8),
)


def make_dbf(rows: list[dict[str, str]]) -> bytes:
    row_length = 1 + sum(width for _, width in FIELDS)
    header_length = 32 + len(FIELDS) * 32 + 1
    header = bytearray(32)
    header[0] = 3
    header[4:8] = len(rows).to_bytes(4, "little")
    header[8:10] = header_length.to_bytes(2, "little")
    header[10:12] = row_length.to_bytes(2, "little")
    descriptors = bytearray()
    for name, width in FIELDS:
        descriptor = bytearray(32)
        descriptor[: len(name)] = name.encode("ascii")
        descriptor[11] = ord("C")
        descriptor[16] = width
        descriptors.extend(descriptor)
    records = bytearray()
    for row in rows:
        records.extend(b"*" if row.get("_deleted") else b" ")
        for name, width in FIELDS:
            value = row.get(name, "").encode("ascii")
            if len(value) > width:
                raise ValueError("Fixture field too wide")
            records.extend(value.ljust(width, b" "))
    return bytes(header + descriptors + b"\r" + records + b"\x1a")


def row(
    doc: str, amount: str, pin: str, folio: str, *, date="20200101", qu="Q"
) -> dict[str, str]:
    return {
        "DOC_NUM": doc,
        "S_AMT": amount,
        "PIN": pin,
        "FOLIO": folio,
        "S_DATE": date,
        "QU": qu,
    }


class HcpaDocumentGroupsTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.private = self.root / "data" / "raw" / "hcpa"
        self.private.mkdir(parents=True)
        self.archive = self.private / "source.zip"
        self.sample = self.private / "sample.jsonl"
        self.flags = self.private / "group-flags.jsonl"
        self.aggregate = self.root / "aggregate.json"
        self.rows = [
            row("A", "100", "P1", "F1"),
            row("A", "100.00", "P2", "F2", date="20200102"),
            row("A", "200", "P1", "F1", qu="U"),
            row("B", "300", "P3", "F3"),
            row("B", "300.00", "P3", "F3"),
            row("C", "400", "P4", "F4"),
            row("", "500", "P5", "F5"),
            row(" ", "600", "P6", "F6"),
            {**row("D", "700", "P7", "F7"), "_deleted": "1"},
        ]
        self.write_source()
        self.write_sample([1, 4, 6, 7])

    def write_source(self) -> None:
        member = make_dbf(self.rows)
        with ZipFile(self.archive, "w", ZIP_STORED) as zipped:
            zipped.writestr("allsales.dbf", member)
        self.member_bytes = len(member)
        self.archive_sha = sha256(self.archive.read_bytes()).hexdigest()

    def write_sample(self, ordinals: list[int]) -> None:
        entries = [
            {
                "record_ordinal": ordinal,
                **{
                    name: value.strip()
                    for name, value in self.rows[ordinal - 1].items()
                    if not name.startswith("_")
                },
            }
            for ordinal in ordinals
        ]
        self.sample.write_text(
            "".join(json.dumps(entry, sort_keys=True) + "\n" for entry in entries),
            encoding="utf-8",
        )
        self.sample_sha = sha256(self.sample.read_bytes()).hexdigest()

    def run_audit(
        self,
        *,
        free_disk_bytes: int = audit.MIN_FREE_DISK_BYTES + 1,
        **overrides: object,
    ) -> dict[str, object]:
        arguments = {
            "expected_archive_sha256": self.archive_sha,
            "expected_member_bytes": self.member_bytes,
            "expected_sample_sha256": self.sample_sha,
            "expected_sample_rows": 4,
        }
        arguments.update(overrides)
        disk_usage = SimpleNamespace(
            total=free_disk_bytes,
            used=0,
            free=free_disk_bytes,
        )
        with (
            patch.object(audit, "PRIVATE_ROOT", self.private),
            patch.object(audit.shutil, "disk_usage", return_value=disk_usage),
        ):
            return audit.profile_document_groups(
                self.archive, self.sample, self.flags, self.aggregate, **arguments
            )

    def test_low_disk_guard_rejects_before_creating_outputs(self) -> None:
        with self.assertRaisesRegex(ValueError, "Insufficient free disk"):
            self.run_audit(free_disk_bytes=audit.MIN_FREE_DISK_BYTES - 1)
        self.assertFalse(self.flags.exists())
        self.assertFalse(self.aggregate.exists())
        self.assertFalse(list(self.private.glob(".hcpa-document-groups-*")))

    def test_exact_group_counts_and_private_sample_flags(self) -> None:
        result = self.run_audit()
        self.assertEqual(result["header_record_count"], 9)
        self.assertEqual(result["active_rows"], 8)
        self.assertEqual(result["deleted_rows"], 1)
        self.assertEqual(result["blank_document_rows"], 2)
        self.assertEqual(result["document_groups"], 3)
        self.assertEqual(result["singleton_groups"], 1)
        self.assertEqual(result["repeated_groups"], 2)
        self.assertEqual(result["rows_in_repeated_groups"], 5)
        self.assertEqual(result["repeated_group_size_histogram"], {"2": 1, "3": 1})
        self.assertEqual(result["repeated_group_signals"]["conflicting_amount"], 1)
        self.assertEqual(result["repeated_group_signals"]["different_known_parcel"], 1)
        self.assertEqual(result["repeated_group_signals"]["conflicting_date"], 1)
        self.assertEqual(result["repeated_group_signals"]["mixed_qualification"], 1)
        self.assertEqual(result["repeated_group_signals"]["same_valid_amount"], 1)
        self.assertEqual(
            result["repeated_group_signals"]["has_repeated_valid_amount"], 2
        )
        self.assertEqual(
            result["sample_group_size_histogram"], {"1": 1, "2": 1, "3": 1, "blank": 1}
        )
        self.assertEqual(result["sample_blank_document_rows"], 1)
        self.assertEqual(result["sample_singleton_document_rows"], 1)
        self.assertEqual(result["sample_repeated_document_rows"], 2)
        self.assertEqual(
            result["sample_repeated_document_signals"]["conflicting_amount"], 1
        )
        self.assertEqual(
            result["sample_repeated_document_signals"]["has_repeated_valid_amount"], 2
        )
        flags = [json.loads(line) for line in self.flags.read_text().splitlines()]
        self.assertEqual([flag["record_ordinal"] for flag in flags], [1, 4, 6, 7])
        self.assertEqual([flag["group_size"] for flag in flags], [3, 2, 1, 0])
        self.assertTrue(flags[0]["conflicting_amount"])
        self.assertFalse(flags[1]["conflicting_amount"])
        self.assertEqual(json.loads(self.aggregate.read_text()), result)
        tracked_text = self.aggregate.read_text()
        for secret in ("P1", "F1", '"A"', '"B"', '"C"', "20200101", '"300"'):
            self.assertNotIn(secret, tracked_text)

    def test_empty_and_partial_parcel_identifiers_are_unknown_not_conflicts(
        self,
    ) -> None:
        self.rows = [
            row("X", "100", "P1", ""),
            row("X", "100.0", "", "F1"),
            row("X", "100", "P1", "F1"),
        ]
        self.write_source()
        self.write_sample([1, 2, 3])
        result = self.run_audit(expected_sample_rows=3)
        self.assertEqual(result["repeated_group_signals"]["different_known_parcel"], 0)
        self.assertEqual(result["repeated_group_signals"]["unknown_parcel"], 1)
        self.assertEqual(result["repeated_group_signals"]["same_valid_amount"], 1)

    def test_invalid_amount_does_not_create_false_amount_agreement(self) -> None:
        self.rows = [row("X", "NaN", "P1", "F1"), row("X", "1", "P1", "F1")]
        self.write_source()
        self.write_sample([1, 2])
        result = self.run_audit(expected_sample_rows=2)
        self.assertEqual(result["repeated_group_signals"]["invalid_amount"], 1)
        self.assertEqual(result["repeated_group_signals"]["same_valid_amount"], 0)
        self.assertEqual(result["repeated_group_signals"]["conflicting_amount"], 0)
        self.assertEqual(
            result["repeated_group_signals"]["has_repeated_valid_amount"], 0
        )

    def test_decimal_equality_handles_exponents_and_signed_zero(self) -> None:
        self.rows = [
            row("X", "100.00", "P1", "F1"),
            row("X", "1E+2", "P1", "F1"),
            row("Y", "-0", "P1", "F1"),
            row("Y", "0.0", "P1", "F1"),
        ]
        self.write_source()
        self.write_sample([1, 2, 3, 4])
        result = self.run_audit()
        self.assertEqual(
            result["repeated_group_signals"]["has_repeated_valid_amount"], 2
        )
        self.assertEqual(result["repeated_group_signals"]["same_valid_amount"], 2)

    def test_hash_mismatch_and_sample_mismatch_leave_no_output(self) -> None:
        with self.assertRaisesRegex(ValueError, "Archive checksum"):
            self.run_audit(expected_archive_sha256="0" * 64)
        with self.assertRaisesRegex(ValueError, "Sample checksum"):
            self.run_audit(expected_sample_sha256="0" * 64)
        self.assertFalse(self.flags.exists())
        self.assertFalse(self.aggregate.exists())

    def test_sample_ordinals_and_fields_must_match_source(self) -> None:
        self.rows[0]["S_AMT"] = "999"
        self.write_source()
        with self.assertRaisesRegex(ValueError, "Sample row differs"):
            self.run_audit()
        self.assertFalse(self.aggregate.exists())

    def test_invalid_record_marker_and_dbf_layout_fail_closed(self) -> None:
        with ZipFile(self.archive) as zipped:
            member = bytearray(zipped.read("allsales.dbf"))
        row_length = 1 + sum(width for _, width in FIELDS)
        header_length = 32 + len(FIELDS) * 32 + 1
        member[header_length + row_length] = ord("?")
        with ZipFile(self.archive, "w", ZIP_STORED) as zipped:
            zipped.writestr("allsales.dbf", member)
        self.member_bytes = len(member)
        self.archive_sha = sha256(self.archive.read_bytes()).hexdigest()
        with self.assertRaisesRegex(ValueError, "record marker"):
            self.run_audit()
        self.assertFalse(self.aggregate.exists())

    def test_replay_is_deterministic_and_existing_outputs_are_preserved(self) -> None:
        first = self.run_audit()
        first_bytes = (self.flags.read_bytes(), self.aggregate.read_bytes())
        with self.assertRaises(FileExistsError):
            self.run_audit()
        self.assertEqual(
            (self.flags.read_bytes(), self.aggregate.read_bytes()), first_bytes
        )
        self.flags.unlink()
        self.aggregate.unlink()
        second = self.run_audit()
        self.assertEqual(second, first)
        self.assertEqual(
            (self.flags.read_bytes(), self.aggregate.read_bytes()), first_bytes
        )

    def test_outputs_are_atomic_and_private_output_cannot_escape(self) -> None:
        outside = self.root / "outside-private.jsonl"
        with patch.object(audit, "PRIVATE_ROOT", self.private):
            with self.assertRaisesRegex(ValueError, "private"):
                audit.profile_document_groups(
                    self.archive,
                    self.sample,
                    outside,
                    self.aggregate,
                    expected_archive_sha256=self.archive_sha,
                    expected_member_bytes=self.member_bytes,
                    expected_sample_sha256=self.sample_sha,
                    expected_sample_rows=4,
                )
        self.assertFalse(self.aggregate.exists())
        with patch.object(
            audit.os, "link", side_effect=OSError("injected install failure")
        ):
            with self.assertRaisesRegex(OSError, "injected install failure"):
                self.run_audit()
        self.assertFalse(self.flags.exists())
        self.assertFalse(self.aggregate.exists())

    def test_second_output_install_failure_rolls_back_first(self) -> None:
        real_link = audit.os.link
        installs = 0

        def fail_second_install(source: Path, destination: Path) -> None:
            nonlocal installs
            installs += 1
            if installs == 2:
                raise OSError("injected second install failure")
            real_link(source, destination)

        with patch.object(audit.os, "link", side_effect=fail_second_install):
            with self.assertRaisesRegex(OSError, "injected second install failure"):
                self.run_audit()
        self.assertFalse(self.flags.exists())
        self.assertFalse(self.aggregate.exists())
        self.assertFalse(list(self.private.glob(".hcpa-document-groups-*")))

    def test_resource_cap_aborts_without_outputs(self) -> None:
        with patch.object(audit, "MAX_SPOOL_BYTES", 1):
            with self.assertRaisesRegex(ValueError, "spool"):
                self.run_audit()
        self.assertFalse(self.flags.exists())
        self.assertFalse(self.aggregate.exists())

    def test_page_limit_uses_actual_sqlite_page_size_and_is_verified(self) -> None:
        database = self.private / "different-page-size.sqlite"
        with closing(sqlite3.connect(database)) as connection:
            connection.execute("PRAGMA page_size=8192")
            self.assertEqual(connection.execute("PRAGMA page_size").fetchone()[0], 8192)
            with patch.object(audit, "MAX_SPOOL_BYTES", 100_000):
                audit._configure_spool_limit(connection)
            self.assertEqual(
                connection.execute("PRAGMA max_page_count").fetchone()[0],
                100_000 // 8192,
            )

    def test_budget_failures_after_insert_remove_spool_without_outputs(self) -> None:
        for failure in (
            TimeoutError("injected time cap"),
            ValueError("injected spool cap"),
        ):
            with self.subTest(failure=type(failure).__name__):
                observed_sizes: list[int] = []

                def fail_budget(spool: Path, deadline: float) -> None:
                    observed_sizes.append(spool.stat().st_size)
                    raise failure

                with patch.object(audit, "_check_budget", side_effect=fail_budget):
                    with self.assertRaisesRegex(type(failure), str(failure)):
                        self.run_audit()
                self.assertEqual(len(observed_sizes), 1)
                self.assertGreater(observed_sizes[0], 0)
                self.assertFalse(self.flags.exists())
                self.assertFalse(self.aggregate.exists())
                self.assertFalse(list(self.private.glob(".hcpa-document-groups-*")))

    def test_large_synthetic_group_stream(self) -> None:
        self.rows = [row("GIANT", "1", "P", "F") for _ in range(10_002)]
        self.write_source()
        self.write_sample([1, 2, 10_001, 10_002])
        result = self.run_audit()
        self.assertEqual(result["document_groups"], 1)
        self.assertEqual(result["rows_in_repeated_groups"], 10_002)
        self.assertEqual(result["max_group_size"], 10_002)
        self.assertEqual(result["repeated_group_size_histogram"], {"101+": 1})
        flags = [json.loads(line) for line in self.flags.read_text().splitlines()]
        self.assertEqual([flag["group_size"] for flag in flags], [10_002] * 4)


if __name__ == "__main__":
    unittest.main()
