"""Synthetic DBF fixtures for the HCPA code-table metadata audit."""

from __future__ import annotations

from hashlib import sha256
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZIP_STORED, ZipFile


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "audit_hcpa_code_table.py"
spec = spec_from_file_location("audit_hcpa_code_table", SCRIPT)
assert spec is not None and spec.loader is not None
audit = module_from_spec(spec)
spec.loader.exec_module(audit)


def make_dbf(
    rows: list[tuple[str, str, bool]],
    *,
    fields: tuple[tuple[str, int], ...] = (("DORCODE", 4), ("DORDESCR", 50)),
    version: int = 3,
    record_count: int | None = None,
    end_marker: bytes = b"\x1a",
) -> bytes:
    header_length = 32 + 32 * len(fields) + 1
    row_length = 1 + sum(width for _, width in fields)
    header = bytearray(32)
    header[0] = version
    header[4:8] = (len(rows) if record_count is None else record_count).to_bytes(
        4, "little"
    )
    header[8:10] = header_length.to_bytes(2, "little")
    header[10:12] = row_length.to_bytes(2, "little")
    descriptors = bytearray()
    for name, width in fields:
        field = bytearray(32)
        field[: len(name)] = name.encode("ascii")
        field[11] = ord("C")
        field[16] = width
        descriptors.extend(field)
    records = bytearray()
    for code, label, deleted in rows:
        records.extend(b"*" if deleted else b" ")
        values = {"DORCODE": code, "DORDESCR": label}
        for name, width in fields:
            encoded = values.get(name, "").encode("ascii")
            if len(encoded) > width:
                raise ValueError("Fixture value exceeds width")
            records.extend(encoded.ljust(width, b" "))
    return bytes(header + descriptors + b"\r" + records + end_marker)


class HcpaCodeTableTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.archive = self.root / "parcel.zip"
        self.output = self.root / "report.json"
        self.member = make_dbf(
            [
                ("0100", "Residential single family", False),
                ("0400", "Residential condominium", False),
                ("0800", "Multifamily", False),
                ("9999", "Deleted private example", True),
            ]
        )
        self.write_archive()

    def write_archive(self, *, second_member: bytes | None = None) -> None:
        with ZipFile(self.archive, "w", ZIP_STORED) as zipped:
            zipped.writestr("parcel_09_25_2026/parcel_dor_names.dbf", self.member)
            zipped.writestr("parcel_09_25_2026/parcel.dbf", b"PRIVATE PARCEL ROW")
            if second_member is not None:
                zipped.writestr("another/parcel_dor_names.dbf", second_member)
        self.archive_hash = sha256(self.archive.read_bytes()).hexdigest()

    def read(self, expected_sha256: str | None = None) -> dict:
        return audit.audit_code_table(
            self.archive, expected_sha256 or self.archive_hash
        )

    def test_aggregate_hashes_labels_and_no_private_rows(self) -> None:
        report = self.read()
        self.assertEqual(
            set(report),
            {
                "source_archive_sha256",
                "member",
                "dbf_sha256",
                "dbf_bytes",
                "dbf_version",
                "header_record_count",
                "active_rows",
                "deleted_rows",
                "fields",
                "selected_code_labels",
            },
        )
        self.assertEqual(report["source_archive_sha256"], self.archive_hash)
        self.assertEqual(report["dbf_sha256"], sha256(self.member).hexdigest())
        self.assertEqual(report["member"], "parcel_09_25_2026/parcel_dor_names.dbf")
        self.assertEqual(report["header_record_count"], 4)
        self.assertEqual(report["active_rows"], 3)
        self.assertEqual(report["deleted_rows"], 1)
        self.assertEqual(
            report["fields"],
            [
                {"name": "DORCODE", "type": "C", "width": 4},
                {"name": "DORDESCR", "type": "C", "width": 50},
            ],
        )
        self.assertEqual(
            report["selected_code_labels"],
            {
                "0100": "Residential single family",
                "0400": "Residential condominium",
                "0800": "Multifamily",
            },
        )
        self.assertNotIn("9999", report["selected_code_labels"])
        self.assertNotIn("private", json.dumps(report).lower())
        self.assertNotIn(str(self.archive), json.dumps(report))

    def test_missing_selected_code_is_explicit(self) -> None:
        self.member = make_dbf([("0100", "Single family", False)])
        self.write_archive()
        report = self.read()
        self.assertEqual(
            report["selected_code_labels"],
            {"0100": "Single family", "0400": None, "0800": None},
        )

    def test_hash_validation_precedes_dbf_read(self) -> None:
        with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
            self.read("0" * 64)
        with self.assertRaisesRegex(ValueError, "SHA-256 format"):
            self.read("wrong")

    def test_zip_read_uses_the_same_open_file_as_hash_validation(self) -> None:
        with patch.object(audit, "ZipFile", wraps=ZipFile) as zipped:
            report = self.read()
        self.assertEqual(report["source_archive_sha256"], self.archive_hash)
        self.assertTrue(hasattr(zipped.call_args.args[0], "read"))

    def test_mutation_detected_after_zip_read(self) -> None:
        with patch.object(
            audit, "_hash_stream", side_effect=[self.archive_hash, "0" * 64]
        ):
            with self.assertRaisesRegex(ValueError, "changed during the audit"):
                self.read()

    def test_rejects_duplicate_active_code(self) -> None:
        self.member = make_dbf([("0100", "One", False), ("0100", "Two", False)])
        self.write_archive()
        with self.assertRaisesRegex(ValueError, "Duplicate active code"):
            self.read()

    def test_deleted_code_can_be_reused_by_active_row(self) -> None:
        self.member = make_dbf([("0100", "Old", True), ("0100", "Current", False)])
        self.write_archive()
        self.assertEqual(self.read()["selected_code_labels"]["0100"], "Current")

    def test_source_special_codes_are_valid_but_not_reported(self) -> None:
        self.member = make_dbf(
            [
                ("HH", "Special source category", False),
                ("NN", "Another source category", False),
                ("0100", "Single family", False),
            ]
        )
        self.write_archive()
        report = self.read()
        self.assertEqual(report["active_rows"], 3)
        self.assertNotIn("Special source category", json.dumps(report))
        self.assertNotIn("Another source category", json.dumps(report))

    def test_rejects_header_count_truncation_and_trailing_data(self) -> None:
        for member in (
            make_dbf([("0100", "One", False)], record_count=2),
            make_dbf([("0100", "One", False)], end_marker=b"\x1aTRAIL"),
            make_dbf([("0100", "One", False)], end_marker=b""),
        ):
            with self.subTest(member_length=len(member)):
                self.member = member
                self.write_archive()
                with self.assertRaisesRegex(ValueError, "DBF (size|end)"):
                    self.read()

    def test_rejects_bad_header_fields_and_row_marker(self) -> None:
        good = make_dbf([("0100", "One", False)])
        malformed = (
            make_dbf([("0100", "One", False)], version=4),
            make_dbf([("0100", "One", False)], fields=(("DORCODE", 4),)),
            good[:96] + b"!" + good[97:],
            good[:97] + b"!" + good[98:],
        )
        for member in malformed:
            with self.subTest(
                member_length=len(member), member_hash=sha256(member).hexdigest()
            ):
                self.member = member
                self.write_archive()
                with self.assertRaises(ValueError):
                    self.read()

    def test_rejects_non_digit_and_nonprintable_codes_and_labels(self) -> None:
        for code, label in (("A100", "One"), ("0100", "Bad\x01label"), ("", "Empty")):
            with self.subTest(code=code, label=label):
                self.member = make_dbf([(code, label, False)])
                self.write_archive()
                with self.assertRaises(ValueError):
                    self.read()

    def test_rejects_multiple_code_table_members(self) -> None:
        self.write_archive(second_member=self.member)
        with self.assertRaisesRegex(ValueError, "exactly one"):
            self.read()

    def test_cli_writes_atomically_and_refuses_overwrite(self) -> None:
        code = audit.main(
            [
                "--archive",
                str(self.archive),
                "--archive-sha256",
                self.archive_hash,
                "--output",
                str(self.output),
            ]
        )
        self.assertEqual(code, 0)
        original = self.output.read_bytes()
        self.assertEqual(json.loads(original), self.read())
        self.assertEqual(
            audit.main(
                [
                    "--archive",
                    str(self.archive),
                    "--archive-sha256",
                    self.archive_hash,
                    "--output",
                    str(self.output),
                ]
            ),
            2,
        )
        self.assertEqual(self.output.read_bytes(), original)
        self.assertEqual(list(self.root.glob("*.tmp")), [])

    def test_cli_failure_does_not_leave_output(self) -> None:
        self.assertEqual(
            audit.main(
                [
                    "--archive",
                    str(self.archive),
                    "--archive-sha256",
                    "0" * 64,
                    "--output",
                    str(self.output),
                ]
            ),
            2,
        )
        self.assertFalse(self.output.exists())
        self.assertEqual(list(self.root.glob("*.tmp")), [])

    def test_subprocess_cli_ignores_other_zip_members(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--archive",
                str(self.archive),
                "--archive-sha256",
                self.archive_hash,
                "--output",
                str(self.output),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertNotIn("PRIVATE PARCEL ROW", self.output.read_text(encoding="utf-8"))

    def test_maximum_supported_row_count(self) -> None:
        self.member = make_dbf(
            [(f"{index:04d}", "Safe label", False) for index in range(10_000)]
        )
        self.write_archive()
        report = self.read()
        self.assertEqual(report["active_rows"], 10_000)
        self.assertEqual(report["selected_code_labels"]["0100"], "Safe label")


if __name__ == "__main__":
    unittest.main()
