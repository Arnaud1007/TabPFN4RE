"""The Indiana manual-review sample is fixed before any human decisions."""

from __future__ import annotations

import csv
import io
import tempfile
import unittest
from collections import Counter
from dataclasses import replace
from datetime import date
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

from scripts import sample_indiana_audit as sampler
from scripts.indiana_assessment_diagnostic import OLD_SPLIT_MEMBERSHIP
from scripts.indiana_historical_benchmark import Sale
from scripts.sample_indiana_audit import (
    AuditRecord,
    join_source_rows,
    load_candidates,
    select_audit_sample,
)


def _record(cell: str, number: int) -> AuditRecord:
    low = cell.startswith("low")
    trending = "Y" if cell.endswith("yes") else "N"
    price = Decimal(number + 1 if low else number + 200_000)
    return AuditRecord(
        sale=Sale(
            row_id=sha256(f"sale-{cell}-{number}".encode()).hexdigest(),
            sale_date=date(2025, 6, 1),
            price=price,
            county_id="49",
            zipcode="46204",
            acreage=None,
        ),
        sdf_id=f"form-{cell}-{number}",
        parcel_number=f"parcel-{cell}-{number}",
        valid_trending=trending,
    )


def _member(fields: tuple[str, ...], rows: list[dict[str, str]]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fields, delimiter="\t")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-16")


def _fixture(
    path: Path,
    *,
    duplicate: bool = False,
    missing_parcel: bool = False,
    blank_parcel: bool = False,
) -> None:
    disclosure = {
        "SDF_ID": "form-1",
        "Unique_Sales_ID": "sale-1",
        "P2_16_Valid_Trending": "Y",
    }
    disclosures = [disclosure, disclosure] if duplicate else [disclosure]
    parcels = (
        []
        if missing_parcel
        else [
            {
                "SDF_ID": "form-1",
                "A1_Parcel_Number": "" if blank_parcel else "parcel-1",
            }
        ]
    )
    with ZipFile(path, "w") as archive:
        archive.writestr(
            "SALEDISC.txt",
            _member(tuple(disclosure), disclosures),
        )
        archive.writestr(
            "SALEPARCEL.txt",
            _member(("SDF_ID", "A1_Parcel_Number"), parcels),
        )


class IndianaAuditSampleTests(unittest.TestCase):
    def test_source_lookup_formula_prefixes_are_rejected_before_csv(self) -> None:
        safe = _record("low_yes", 0)
        for unsafe in (
            "=1+1",
            "+1+1",
            "-1+1",
            "@SUM(1)",
            "\t=1+1",
            " =1+1",
            "\x00=1+1",
            "\r+1+1",
            "\u200b=1+1",
            "\u00a0-1+1",
            " \x00@SUM(1)",
        ):
            for field in ("sdf_id", "parcel_number"):
                with self.subTest(field=field, unsafe=repr(unsafe)):
                    malicious = replace(safe, **{field: unsafe})
                    with self.assertRaisesRegex(ValueError, "unsafe lookup"):
                        sampler._private_csv((malicious,))

    def test_four_cells_have_fixed_edges_and_hash_ranked_middle(self) -> None:
        records = tuple(
            _record(cell, number)
            for cell in ("low_yes", "low_no", "high_yes", "high_no")
            for number in range(80)
        )
        selected = select_audit_sample(records)
        self.assertEqual(len(selected), 200)
        self.assertEqual(len({record.sale.row_id for record in selected}), 200)
        self.assertEqual(
            Counter(
                (record.sale.price <= 117_000, record.valid_trending)
                for record in selected
            ),
            {(True, "Y"): 50, (True, "N"): 50, (False, "Y"): 50, (False, "N"): 50},
        )
        for cell in ("low_yes", "low_no", "high_yes", "high_no"):
            group = [_record(cell, number) for number in range(80)]
            chosen = {
                record.sale.row_id
                for record in selected
                if record.sdf_id.startswith(f"form-{cell}-")
            }
            self.assertTrue({record.sale.row_id for record in group[:10]} <= chosen)
            self.assertTrue({record.sale.row_id for record in group[-10:]} <= chosen)
            remaining = group[10:-10]
            ranked = sorted(
                remaining,
                key=lambda record: (
                    sha256(f"42:{record.sale.row_id}".encode()).hexdigest(),
                    record.sale.row_id,
                ),
            )
            self.assertEqual(
                chosen - {record.sale.row_id for record in group[:10] + group[-10:]},
                {record.sale.row_id for record in ranked[:30]},
            )
        self.assertEqual(selected, select_audit_sample(tuple(reversed(records))))

    def test_rejects_duplicate_row_ids_and_underfilled_cell(self) -> None:
        records = tuple(
            _record(cell, number)
            for cell in ("low_yes", "low_no", "high_yes", "high_no")
            for number in range(50)
        )
        with self.assertRaisesRegex(ValueError, "duplicate"):
            select_audit_sample((*records, records[0]))
        with self.assertRaisesRegex(ValueError, "at least 50"):
            select_audit_sample(records[:-1])

    def test_exact_raw_join_rejects_duplicate_or_missing_rows(self) -> None:
        sale = Sale(
            row_id=sha256(b"sale-1").hexdigest(),
            sale_date=date(2025, 6, 1),
            price=Decimal("100000"),
            county_id="49",
            zipcode="46204",
            acreage=None,
        )
        with tempfile.TemporaryDirectory() as directory:
            archive_path = Path(directory) / "source.zip"
            _fixture(archive_path)
            self.assertEqual(
                join_source_rows(archive_path, (sale,))[0].parcel_number, "parcel-1"
            )
            _fixture(archive_path, duplicate=True)
            with self.assertRaisesRegex(ValueError, "duplicate"):
                join_source_rows(archive_path, (sale,))
            _fixture(archive_path, missing_parcel=True)
            with self.assertRaisesRegex(ValueError, "missing"):
                join_source_rows(archive_path, (sale,))
            _fixture(archive_path, blank_parcel=True)
            with self.assertRaisesRegex(ValueError, "blank parcel"):
                join_source_rows(archive_path, (sale,))

    def test_wrong_source_hash_fails_before_archive_parsing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            archive_path = Path(directory) / "source.zip"
            _fixture(archive_path)
            with self.assertRaisesRegex(ValueError, "checksum"):
                load_candidates(archive_path, "0" * 64)

    def test_private_worklist_public_aggregate_and_create_only(self) -> None:
        records = tuple(
            _record(cell, number)
            for cell in ("low_yes", "low_no", "high_yes", "high_no")
            for number in range(55)
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            private_dir = root / "data/raw/indiana_sdf/audit_sample_v1"
            public_path = root / "runs/diagnostic/audit_sample_manifest.json"
            private_dir.parent.mkdir(parents=True)
            public_path.parent.mkdir(parents=True)
            source = root / "source.zip"
            source.write_bytes(b"fixture")
            with (
                patch.object(sampler, "PRIVATE_DIR", private_dir),
                patch.object(sampler, "PUBLIC_OUTPUT", public_path),
                patch.object(sampler, "_clean_commit", return_value="a" * 40),
                patch.object(
                    sampler,
                    "_verify_diagnostic",
                    return_value=("f" * 64, OLD_SPLIT_MEMBERSHIP),
                ),
                patch.object(sampler, "load_candidates", return_value=records),
                patch.object(
                    sampler,
                    "_membership_hash",
                    return_value=OLD_SPLIT_MEMBERSHIP["validation"],
                ),
            ):
                manifest = sampler.run_sample(source)
                first_public = public_path.read_bytes()
                with self.assertRaises(FileExistsError):
                    sampler.run_sample(source)
            sample = (private_dir / "sample.csv").read_bytes()
            self.assertEqual(
                len(list(csv.DictReader(io.StringIO(sample.decode())))), 200
            )
            self.assertEqual(manifest["reviewed_rows"], 0)
            self.assertEqual(manifest["pending_rows"], 200)
            self.assertEqual(
                manifest["private_sample_sha256"], sha256(sample).hexdigest()
            )
            self.assertEqual(first_public, public_path.read_bytes())
            self.assertIn(b"form-low_yes-0", sample)
            self.assertNotIn(b"form-low_yes-0", first_public)
            self.assertNotIn(b"parcel-low_yes-0", first_public)
            self.assertNotIn(b"sale_price_usd", first_public)

    def test_resume_verifies_intent_sample_and_code_commit(self) -> None:
        records = tuple(
            _record(cell, number)
            for cell in ("low_yes", "low_no", "high_yes", "high_no")
            for number in range(55)
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            private_dir = root / "data/raw/indiana_sdf/audit_sample_v1"
            public_path = root / "runs/diagnostic/audit_sample_manifest.json"
            private_dir.parent.mkdir(parents=True)
            public_path.parent.mkdir(parents=True)
            source = root / "source.zip"
            source.write_bytes(b"fixture")
            with (
                patch.object(sampler, "PRIVATE_DIR", private_dir),
                patch.object(sampler, "PUBLIC_OUTPUT", public_path),
                patch.object(sampler, "_clean_commit", return_value="a" * 40) as commit,
                patch.object(
                    sampler,
                    "_verify_diagnostic",
                    return_value=("f" * 64, OLD_SPLIT_MEMBERSHIP),
                ),
                patch.object(sampler, "load_candidates", return_value=records),
                patch.object(
                    sampler,
                    "_membership_hash",
                    return_value=OLD_SPLIT_MEMBERSHIP["validation"],
                ),
            ):
                with patch.object(
                    sampler, "write_summary_new", side_effect=OSError("injected")
                ):
                    with self.assertRaisesRegex(OSError, "injected"):
                        sampler.run_sample(source)
                intent = (private_dir / "intent.json").read_bytes()
                sample = (private_dir / "sample.csv").read_bytes()
                self.assertFalse(public_path.exists())
                commit.return_value = "b" * 40
                with self.assertRaisesRegex(ValueError, "intent"):
                    sampler.run_sample(source)
                commit.return_value = "a" * 40
                sampler.run_sample(source)
                self.assertEqual(intent, (private_dir / "intent.json").read_bytes())
                self.assertEqual(sample, (private_dir / "sample.csv").read_bytes())
                self.assertTrue(public_path.exists())

    def test_empty_secured_directory_resumes_but_tampered_sample_fails(self) -> None:
        records = tuple(
            _record(cell, number)
            for cell in ("low_yes", "low_no", "high_yes", "high_no")
            for number in range(55)
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            private_dir = root / "data/raw/indiana_sdf/audit_sample_v1"
            public_path = root / "runs/diagnostic/audit_sample_manifest.json"
            private_dir.mkdir(parents=True)
            sampler.secure_directory(private_dir)
            public_path.parent.mkdir(parents=True)
            source = root / "source.zip"
            source.write_bytes(b"fixture")
            with (
                patch.object(sampler, "PRIVATE_DIR", private_dir),
                patch.object(sampler, "PUBLIC_OUTPUT", public_path),
                patch.object(sampler, "_clean_commit", return_value="a" * 40),
                patch.object(
                    sampler,
                    "_verify_diagnostic",
                    return_value=("f" * 64, OLD_SPLIT_MEMBERSHIP),
                ),
                patch.object(sampler, "load_candidates", return_value=records),
                patch.object(
                    sampler,
                    "_membership_hash",
                    return_value=OLD_SPLIT_MEMBERSHIP["validation"],
                ),
            ):
                with patch.object(
                    sampler, "write_summary_new", side_effect=OSError("injected")
                ):
                    with self.assertRaisesRegex(OSError, "injected"):
                        sampler.run_sample(source)
                sample_path = private_dir / "sample.csv"
                sample_path.write_bytes(b"tampered")
                with self.assertRaisesRegex(ValueError, "sample"):
                    sampler.run_sample(source)
                self.assertFalse(public_path.exists())
                self.assertEqual(sample_path.read_bytes(), b"tampered")

    def test_pre_intent_interruption_and_conflicting_private_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            private_dir = Path(directory) / "audit_sample_v1"
            with patch.object(sampler, "PRIVATE_DIR", private_dir):
                with patch.object(
                    sampler, "new_file", side_effect=OSError("injected intent failure")
                ):
                    with self.assertRaisesRegex(OSError, "injected intent failure"):
                        sampler._prepare_private_files(b"intent", b"sample")
                self.assertEqual(list(private_dir.iterdir()), [])
                result = sampler._prepare_private_files(b"intent", b"sample")
                self.assertEqual(result.read_bytes(), b"sample")
        for filename, content, message in (
            ("sample.csv", b"unbound", "without frozen intent"),
            ("intent.json", b"wrong", "intent differs"),
            ("unrelated.txt", b"conflict", "conflicting files"),
        ):
            with self.subTest(filename=filename):
                with tempfile.TemporaryDirectory() as directory:
                    private_dir = Path(directory) / "audit_sample_v1"
                    private_dir.mkdir()
                    sampler.secure_directory(private_dir)
                    offending = private_dir / filename
                    offending.write_bytes(content)
                    with patch.object(sampler, "PRIVATE_DIR", private_dir):
                        with self.assertRaisesRegex(ValueError, message):
                            sampler._prepare_private_files(b"intent", b"sample")
                    self.assertEqual(offending.read_bytes(), content)
                    self.assertEqual(
                        {entry.name for entry in private_dir.iterdir()}, {filename}
                    )


if __name__ == "__main__":
    unittest.main()
