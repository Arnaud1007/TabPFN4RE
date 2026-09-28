"""Synthetic DBF contract tests for the private HCPA review sampler."""

from __future__ import annotations

from hashlib import sha256
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "sample_hcpa_audit.py"
spec = spec_from_file_location("sample_hcpa_audit", SCRIPT)
assert spec is not None and spec.loader is not None
sampler = module_from_spec(spec)
spec.loader.exec_module(sampler)

FIELDS = (
    ("PIN", 12),
    ("FOLIO", 12),
    ("S_DATE", 8),
    ("S_AMT", 12),
    ("QU", 1),
    ("VI", 1),
    ("REA_CD", 3),
    ("S_TYPE", 3),
    ("DOR_CODE", 4),
    ("DOC_NUM", 12),
    ("OR_BK", 8),
    ("OR_PG", 8),
    ("GRANTOR", 20),
    ("GRANTEE", 20),
    ("STR", 20),
    ("SUB", 20),
)
YEARS = (1999, 2005, 2015, 2022, 2025)


def make_rows(per_cell: int = 25) -> list[dict[str, str]]:
    rows = []
    for year in YEARS:
        for qualification in ("Q", "U"):
            for index in range(per_cell):
                rows.append(
                    {
                        "PIN": f"P{year}{qualification}{index}",
                        "FOLIO": f"F{year}{qualification}{index}",
                        "S_DATE": f"{year}0601",
                        "S_AMT": str(250000 + index),
                        "QU": qualification,
                        "VI": "V" if index < 3 else "I",
                        "REA_CD": "A",
                        "S_TYPE": "WD",
                        "DOR_CODE": "0100",
                        "DOC_NUM": f"D{year}{qualification}{index}",
                        "OR_BK": "123",
                        "OR_PG": "45",
                        "GRANTOR": "PRIVATE SELLER",
                        "GRANTEE": "PRIVATE BUYER",
                        "STR": "SECRET STREET",
                        "SUB": "SECRET SUBDIVISION",
                    }
                )
    return rows


def make_dbf(rows: list[dict[str, str]]) -> bytes:
    row_width = 1 + sum(width for _, width in FIELDS)
    header_width = 32 + 32 * len(FIELDS) + 1
    header = bytearray(32)
    header[0] = 3
    header[1:4] = bytes((126, 9, 28))
    header[4:8] = len(rows).to_bytes(4, "little")
    header[8:10] = header_width.to_bytes(2, "little")
    header[10:12] = row_width.to_bytes(2, "little")
    descriptors = bytearray()
    for name, width in FIELDS:
        field = bytearray(32)
        field[: len(name)] = name.encode("ascii")
        field[11] = ord("C")
        field[16] = width
        descriptors.extend(field)
    records = bytearray()
    for row in rows:
        records.extend(b" ")
        for name, width in FIELDS:
            value = row[name].encode("ascii")
            assert len(value) <= width
            records.extend(value.ljust(width, b" "))
    return bytes(header + descriptors + b"\r" + records + b"\x1a")


def make_archive(path: Path, rows: list[dict[str, str]]) -> tuple[str, int]:
    dbf = make_dbf(rows)
    with ZipFile(path, "w") as archive:
        member = ZipInfo("allsales.dbf", date_time=(2026, 9, 28, 0, 0, 0))
        member.compress_type = ZIP_DEFLATED
        archive.writestr(member, dbf)
    return sha256(path.read_bytes()).hexdigest(), len(dbf)


class HcpaAuditSamplerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.private = self.root / "data" / "raw" / "hcpa"
        self.private.mkdir(parents=True)
        self.archive = self.root / "source.zip"
        self.output = self.private / "sample.jsonl"
        self.manifest = self.root / "manifest.json"
        self.expected_sha, self.expected_size = make_archive(self.archive, make_rows())

    def sample(self, output: Path | None = None, manifest: Path | None = None):
        with patch.object(sampler, "PRIVATE_ROOT", self.private):
            return sampler.sample_archive(
                self.archive,
                output or self.output,
                manifest or self.manifest,
                expected_sha256=self.expected_sha,
                expected_member_bytes=self.expected_size,
            )

    def test_exact_quotas_determinism_and_edge_inclusion(self) -> None:
        first = self.sample()
        lines = [json.loads(line) for line in self.output.read_text().splitlines()]
        self.assertEqual(len(lines), 200)
        self.assertEqual(len({row["record_ordinal"] for row in lines}), 200)
        for year in YEARS:
            for qualification in ("Q", "U"):
                cell = [
                    row
                    for row in lines
                    if row["S_DATE"].startswith(str(year))
                    and row["QU"] == qualification
                ]
                self.assertEqual(len(cell), 20)
                self.assertEqual(sum(row["VI"] == "V" for row in cell), 3)
        self.assertEqual(
            first["sample_sha256"], sha256(self.output.read_bytes()).hexdigest()
        )
        self.assertEqual(first["ranking_version"], "hcpa-audit-v1")
        self.assertIn("hcpa-audit-v1|", first["ranking_formula"])
        second = self.sample(self.private / "again.jsonl", self.root / "again.json")
        self.assertEqual(
            self.output.read_bytes(), (self.private / "again.jsonl").read_bytes()
        )
        self.assertEqual(first, second)

    def test_output_has_only_allowed_fields_and_blank_review_slots(self) -> None:
        self.sample()
        content = self.output.read_text()
        for secret in (
            "PRIVATE SELLER",
            "PRIVATE BUYER",
            "SECRET STREET",
            "SECRET SUBDIVISION",
        ):
            self.assertNotIn(secret, content)
        row = json.loads(content.splitlines()[0])
        self.assertEqual(
            set(row),
            {
                "record_ordinal",
                "PIN",
                "FOLIO",
                "S_DATE",
                "S_AMT",
                "QU",
                "VI",
                "REA_CD",
                "S_TYPE",
                "DOR_CODE",
                "DOC_NUM",
                "OR_BK",
                "OR_PG",
                "manual_review",
            },
        )
        self.assertTrue(all(value is None for value in row["manual_review"].values()))
        self.assertTrue(
            {
                "document_match",
                "parcel_unit_identity",
                "price_scope_multi_parcel",
                "date_vs_deed_execution",
                "date_vs_recording",
                "date_vs_closing",
                "qualification_reason_interpretation",
                "duplicate_status",
                "evidence_quality",
            }.issubset(row["manual_review"])
        )
        manifest = json.loads(self.manifest.read_text())
        self.assertNotIn("PIN", manifest)
        self.assertNotIn("PRIVATE", self.manifest.read_text())

    def test_edge_reserve_is_capped_and_uses_documented_rank(self) -> None:
        rows = make_rows()
        for row in rows:
            if row["S_DATE"].startswith("1999") and row["QU"] == "Q":
                index = int(row["PIN"].removeprefix("P1999Q"))
                row["VI"] = "V" if index < 15 else "I"
        self.expected_sha, self.expected_size = make_archive(self.archive, rows)
        result = self.sample()
        self.assertEqual(result["cell_counts"]["before_2000_Q"]["edge_reserved"], 10)
        self.assertEqual(result["cell_counts"]["before_2000_Q"]["edge_eligible"], 15)
        selected = {
            row["record_ordinal"]
            for row in map(json.loads, self.output.read_text().splitlines())
        }
        ranked_edges = sorted(
            range(1, 16),
            key=lambda ordinal: sha256(
                f"hcpa-audit-v1|{self.expected_sha}|42|{ordinal}".encode("ascii")
            ).digest(),
        )[:10]
        self.assertTrue(set(ranked_edges).issubset(selected))

    def test_short_stratum_fails_without_any_output(self) -> None:
        rows = make_rows()
        rows = [
            row
            for row in rows
            if not (row["S_DATE"].startswith("1999") and row["QU"] == "Q")
        ][:]
        self.expected_sha, self.expected_size = make_archive(self.archive, rows)
        with self.assertRaisesRegex(ValueError, "quota"):
            self.sample()
        self.assertFalse(self.output.exists())
        self.assertFalse(self.manifest.exists())

    def test_bad_checksum_and_malformed_member_fail_without_outputs(self) -> None:
        self.expected_sha = "0" * 64
        with self.assertRaisesRegex(ValueError, "checksum"):
            self.sample()
        self.assertFalse(self.output.exists())
        self.assertFalse(self.manifest.exists())
        self.archive.write_bytes(b"not a ZIP")
        self.expected_sha = sha256(self.archive.read_bytes()).hexdigest()
        with self.assertRaises(Exception):
            self.sample()
        self.assertFalse(self.output.exists())
        self.assertFalse(self.manifest.exists())

    def test_existing_output_and_outside_private_root_are_rejected(self) -> None:
        self.output.write_text("existing")
        with self.assertRaises(FileExistsError):
            self.sample()
        self.assertEqual(self.output.read_text(), "existing")
        self.output.unlink()
        with self.assertRaisesRegex(ValueError, "private"):
            self.sample(self.root / "tracked.jsonl")
        self.assertFalse(self.manifest.exists())


if __name__ == "__main__":
    unittest.main()
