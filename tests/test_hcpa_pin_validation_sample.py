"""Synthetic contract tests for ADR 0017's disjoint private sample."""

from __future__ import annotations

from hashlib import sha256
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "select_hcpa_pin_validation_sample.py"
)
SPEC = spec_from_file_location("select_hcpa_pin_validation_sample", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
selector = module_from_spec(SPEC)
SPEC.loader.exec_module(selector)

FIELDS = (
    ("PIN", 29),
    ("FOLIO", 10),
    ("S_DATE", 8),
    ("QU", 1),
    ("S_AMT", 12),
    ("VI", 1),
    ("REA_CD", 3),
    ("S_TYPE", 3),
    ("DOR_CODE", 4),
    ("DOC_NUM", 12),
    ("OR_BK", 8),
    ("OR_PG", 8),
    ("GRANTOR", 20),
    ("STR", 20),
)
YEARS = (1999, 2005, 2015, 2022, 2025)


def rows_per_cell(count: int = 5) -> list[dict[str, str]]:
    rows = []
    for year in YEARS:
        for qu in ("Q", "U"):
            for index in range(count):
                rows.append(
                    {
                        "PIN": f"P{year}{qu}{index}",
                        "FOLIO": f"F{year}{qu}{index}",
                        "S_DATE": f"{year}0601",
                        "QU": qu,
                        "S_AMT": "250000",
                        "VI": "I",
                        "REA_CD": "A",
                        "S_TYPE": "WD",
                        "DOR_CODE": "0100",
                        "DOC_NUM": "123",
                        "OR_BK": "5",
                        "OR_PG": "7",
                        "GRANTOR": "PRIVATE SELLER",
                        "STR": "SECRET STREET",
                    }
                )
    return rows


def dbf_bytes(rows: list[dict[str, str]], *, bad_marker: bool = False) -> bytes:
    row_size = 1 + sum(width for _, width in FIELDS)
    header_size = 32 + 32 * len(FIELDS) + 1
    header = bytearray(32)
    header[0] = 3
    header[4:8] = len(rows).to_bytes(4, "little")
    header[8:10] = header_size.to_bytes(2, "little")
    header[10:12] = row_size.to_bytes(2, "little")
    descriptors = bytearray()
    for name, width in FIELDS:
        descriptor = bytearray(32)
        descriptor[: len(name)] = name.encode("ascii")
        descriptor[11] = ord("D" if name == "S_DATE" else "C")
        descriptor[16] = width
        descriptors.extend(descriptor)
    records = bytearray()
    for index, row in enumerate(rows):
        records.extend(b"?" if bad_marker and index == 0 else b" ")
        for name, width in FIELDS:
            value = row[name].encode("ascii")
            assert len(value) <= width
            records.extend(value.ljust(width, b" "))
    return bytes(header + descriptors + b"\r" + records + b"\x1a")


def archive_bytes(path: Path, rows: list[dict[str, str]], **kwargs) -> int:
    dbf = dbf_bytes(rows, **kwargs)
    with ZipFile(path, "w") as zipped:
        member = ZipInfo("allsales.dbf", date_time=(2026, 9, 28, 0, 0, 0))
        member.compress_type = ZIP_DEFLATED
        zipped.writestr(member, dbf)
    return len(dbf)


class HcpaPinValidationSampleTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.private = self.root / "data" / "raw" / "hcpa"
        self.private.mkdir(parents=True)
        self.archive = self.private / "source.zip"
        self.old_sample = self.private / "old.jsonl"
        self.output = self.private / "new.jsonl"
        self.manifest = self.root / "aggregate.json"
        self.rows = rows_per_cell()
        self.member_bytes = archive_bytes(self.archive, self.rows)
        self.excluded = self._write_old_sample([1 + cell * 5 for cell in range(10)])

    def _write_old_sample(self, ordinals: list[int]) -> bytes:
        data = b"".join(
            (
                json.dumps(
                    {
                        "record_ordinal": ordinal,
                        **{
                            key: self.rows[ordinal - 1][key]
                            for key in ("PIN", "FOLIO", "S_DATE", "QU")
                        },
                    },
                    sort_keys=True,
                )
                + "\n"
            ).encode("utf-8")
            for ordinal in ordinals
        )
        self.old_sample.write_bytes(data)
        return data

    def select(
        self,
        *,
        archive_sha: str | None = None,
        sample_sha: str | None = None,
        expected_exclusion_rows: int = 10,
        rows_per_cell: int = 2,
        output: Path | None = None,
        manifest: Path | None = None,
    ):
        with patch.object(selector, "PRIVATE_ROOT", self.private):
            return selector.select_sample(
                self.archive,
                self.old_sample,
                output or self.output,
                manifest or self.manifest,
                expected_archive_sha256=archive_sha
                or sha256(self.archive.read_bytes()).hexdigest(),
                expected_exclusion_sha256=sample_sha
                or sha256(self.old_sample.read_bytes()).hexdigest(),
                expected_member_bytes=self.member_bytes,
                expected_exclusion_rows=expected_exclusion_rows,
                rows_per_cell=rows_per_cell,
            )

    def test_exact_rank_quotas_disjointness_and_replay(self) -> None:
        result = self.select()
        output = [json.loads(line) for line in self.output.read_text().splitlines()]
        self.assertEqual(len(output), 20)
        self.assertEqual(len({row["record_ordinal"] for row in output}), 20)
        self.assertTrue(
            {row["record_ordinal"] for row in output}.isdisjoint(
                {1 + cell * 5 for cell in range(10)}
            )
        )
        source_sha = sha256(self.archive.read_bytes()).hexdigest()
        for cell in range(10):
            ordinals = list(range(1 + cell * 5, 6 + cell * 5))
            remaining = ordinals[1:]
            expected = sorted(
                remaining,
                key=lambda ordinal: (
                    int.from_bytes(
                        sha256(
                            f"hcpa-pin-validation-v1|{source_sha}|43|{ordinal}".encode(
                                "ascii"
                            )
                        ).digest(),
                        "big",
                    ),
                    ordinal,
                ),
            )[:2]
            self.assertEqual(
                [row["record_ordinal"] for row in output[cell * 2 : cell * 2 + 2]],
                expected,
            )
        self.assertEqual(result["excluded_sample_rows_reconciled"], 10)
        self.assertEqual(
            result["sample_sha256"], sha256(self.output.read_bytes()).hexdigest()
        )
        self.assertEqual(result["sample_rows"], 20)
        self.assertEqual(result["ranking_version"], "hcpa-pin-validation-v1")
        second = self.select(
            output=self.private / "replay.jsonl", manifest=self.root / "replay.json"
        )
        self.assertEqual(second, result)
        self.assertEqual(
            (self.private / "replay.jsonl").read_bytes(), self.output.read_bytes()
        )

    def test_output_is_private_and_minimal_and_manifest_aggregate(self) -> None:
        self.select()
        content = self.output.read_text()
        self.assertNotIn("PRIVATE SELLER", content)
        self.assertNotIn("SECRET STREET", content)
        self.assertNotIn("250000", content)
        self.assertEqual(
            set(json.loads(content.splitlines()[0])),
            {"record_ordinal", "PIN", "FOLIO", "S_DATE", "QU"},
        )
        aggregate = self.manifest.read_text()
        self.assertNotIn("P1999", aggregate)
        self.assertNotIn("F1999", aggregate)
        self.assertEqual(len(json.loads(aggregate)["cell_counts"]), 10)

    def test_short_cell_and_invalid_dates_fail_without_outputs(self) -> None:
        self.rows = [
            row
            for row in self.rows
            if not (
                row["S_DATE"] == "20250601"
                and row["QU"] == "U"
                and row["PIN"] != "P2025U0"
            )
        ]
        self.member_bytes = archive_bytes(self.archive, self.rows)
        old_rows = [1 + cell * 5 for cell in range(9)] + [len(self.rows)]
        self._write_old_sample(old_rows)
        with self.assertRaisesRegex(ValueError, "Insufficient|quota"):
            self.select()
        self.assertFalse(self.output.exists())
        self.assertFalse(self.manifest.exists())

    def test_exclusion_identity_mismatch_duplicate_and_wrong_count_fail(self) -> None:
        payload = [json.loads(line) for line in self.excluded.splitlines()]
        payload[0]["PIN"] = "WRONG"
        self.old_sample.write_text("\n".join(json.dumps(row) for row in payload) + "\n")
        with self.assertRaisesRegex(ValueError, "reconcile|mismatch"):
            self.select()
        self.assertFalse(self.output.exists())
        payload[0]["PIN"] = self.rows[0]["PIN"]
        payload[1]["record_ordinal"] = payload[0]["record_ordinal"]
        self.old_sample.write_text("\n".join(json.dumps(row) for row in payload) + "\n")
        with self.assertRaisesRegex(ValueError, "duplicate"):
            self.select()
        self._write_old_sample([1])
        with self.assertRaisesRegex(ValueError, "count"):
            self.select()

    def test_checksum_and_dbf_corruption_fail_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "SHA-256|checksum"):
            self.select(archive_sha="0" * 64)
        with self.assertRaisesRegex(ValueError, "SHA-256|checksum"):
            self.select(sample_sha="0" * 64)
        self.member_bytes = archive_bytes(self.archive, self.rows, bad_marker=True)
        with self.assertRaisesRegex(ValueError, "record marker"):
            self.select()
        self.assertFalse(self.output.exists())
        self.assertFalse(self.manifest.exists())

    def test_bad_date_and_qualification_are_excluded(self) -> None:
        self.rows[1]["S_DATE"] = "20230230"
        self.rows[2]["QU"] = "X"
        self.member_bytes = archive_bytes(self.archive, self.rows)
        self._write_old_sample([1 + cell * 5 for cell in range(10)])
        result = self.select()
        self.assertEqual(result["excluded_counts"]["date_outside_or_invalid"], 1)
        self.assertEqual(result["excluded_counts"]["qualification_other"], 1)

    def test_overwrite_and_public_sample_path_are_rejected(self) -> None:
        self.output.write_text("original")
        with self.assertRaises(FileExistsError):
            self.select()
        self.assertEqual(self.output.read_text(), "original")
        self.output.unlink()
        with self.assertRaisesRegex(ValueError, "private"):
            self.select(output=self.root / "public.jsonl")
        self.assertFalse(self.manifest.exists())

    def test_source_sample_alias_and_symlinked_root_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "differ"):
            self.select(output=self.old_sample)
        with patch.object(Path, "is_symlink", return_value=True):
            with self.assertRaisesRegex(ValueError, "symlink|redirect"):
                self.select()

    def test_malformed_exclusions_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            self.select(sample_sha="invalid")
        self.old_sample.write_bytes(b"not JSON\n")
        with self.assertRaisesRegex(ValueError, "Malformed exclusion JSONL"):
            self.select()
        self.old_sample.write_bytes(b"null\n")
        with self.assertRaisesRegex(ValueError, "count"):
            self.select()
        malformed = [
            {
                "record_ordinal": True,
                **{key: self.rows[0][key] for key in ("PIN", "FOLIO", "S_DATE", "QU")},
            }
        ]
        self.old_sample.write_text(json.dumps(malformed[0]) + "\n")
        with self.assertRaisesRegex(ValueError, "Malformed exclusion ordinal"):
            self.select(expected_exclusion_rows=1)
        malformed[0]["record_ordinal"] = 999
        self.old_sample.write_text(json.dumps(malformed[0]) + "\n")
        with self.assertRaisesRegex(ValueError, "exceeds DBF"):
            self.select(expected_exclusion_rows=1)
        self.assertFalse(self.output.exists())

    def test_bad_header_field_type_and_end_marker_are_rejected(self) -> None:
        baseline = dbf_bytes(self.rows)

        def set_member(content: bytes, name: str = "allsales.dbf") -> None:
            with ZipFile(self.archive, "w") as zipped:
                zipped.writestr(name, content, compress_type=ZIP_DEFLATED)
            self.member_bytes = len(content)

        bad = bytearray(baseline)
        bad[0] = 0
        set_member(bad)
        with self.assertRaisesRegex(ValueError, "dBASE III"):
            self.select()
        bad = bytearray(baseline)
        bad[32 + 2 * 32 + 11] = ord("C")
        set_member(bad)
        with self.assertRaisesRegex(ValueError, "unexpected type"):
            self.select()
        bad = bytearray(baseline)
        bad[-1] = 0
        set_member(bad)
        with self.assertRaisesRegex(ValueError, "end-of-file marker"):
            self.select()
        set_member(baseline, "wrong.dbf")
        with self.assertRaisesRegex(ValueError, "exactly one"):
            self.select()
        self.assertFalse(self.output.exists())

    def test_second_atomic_install_failure_rolls_back_first(self) -> None:
        real_link = selector.os.link
        calls = 0

        def fail_second(source, destination):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("simulated second install failure")
            return real_link(source, destination)

        with patch.object(selector.os, "link", side_effect=fail_second):
            with self.assertRaisesRegex(OSError, "simulated"):
                self.select()
        self.assertFalse(self.output.exists())
        self.assertFalse(self.manifest.exists())
        self.assertEqual(list(self.private.glob(".hcpa-pin-validation-*")), [])


if __name__ == "__main__":
    unittest.main()
