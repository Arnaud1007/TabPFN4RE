"""Synthetic, private-fixture tests for the current-parcel linkage audit."""

from __future__ import annotations

from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZIP_DEFLATED, ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import audit_hcpa_parcel_links as links  # noqa: E402


FIELDS = (
    ("PIN", "C", 12),
    ("FOLIO", "C", 12),
    ("DOR_C", "C", 4),
    ("tUNITS", "F", 8),
    ("tBLDGS", "F", 8),
    ("HEAT_AR", "F", 8),
    ("SALE1_DOC", "C", 12),
    ("SALE2_DOC", "C", 12),
    ("SALE3_DOC", "C", 12),
)


def _dbf(rows: list[dict[str, str]], *, malformed: bool = False) -> bytes:
    header_length = 32 + len(FIELDS) * 32 + 1
    record_length = 1 + sum(width for _, _, width in FIELDS)
    header = bytearray(32)
    header[0] = 3
    struct.pack_into("<IHH", header, 4, len(rows), header_length, record_length)
    descriptors = bytearray()
    for name, field_type, width in FIELDS:
        descriptor = bytearray(32)
        descriptor[: len(name)] = name.encode("ascii")
        descriptor[11] = ord(field_type)
        descriptor[16] = width
        descriptors.extend(descriptor)
    records = [
        b" "
        + b"".join(
            row.get(name, "").encode("ascii").ljust(width) for name, _, width in FIELDS
        )
        for row in rows
    ]
    return (
        bytes(header)
        + bytes(descriptors)
        + (b"\x00" if malformed else b"\x0d")
        + b"".join(records)
        + b"\x1a"
    )


def _sample(
    ordinal: int, pin: str, folio: str, code: str = "0100", doc: str = ""
) -> dict:
    return {
        "record_ordinal": ordinal,
        "PIN": pin,
        "FOLIO": folio,
        "DOR_CODE": code,
        "DOC_NUM": doc,
    }


class TestParcelLinks(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.private = self.root / "data" / "raw" / "hcpa"
        self.private.mkdir(parents=True)
        self.run = self.root / "runs"
        self.run.mkdir()
        patcher = patch.object(links, "PRIVATE_ROOT", self.private)
        patcher.start()
        self.addCleanup(patcher.stop)

    def fixture(
        self,
        rows: list[dict[str, str]],
        samples: list[dict],
        *,
        malformed: bool = False,
    ):
        archive = self.private / "parcel.zip"
        with ZipFile(archive, "w", ZIP_DEFLATED) as zipped:
            zipped.writestr("vintage/parcel.dbf", _dbf(rows, malformed=malformed))
        sample = self.private / "sample.jsonl"
        sample.write_text(
            "".join(json.dumps(row) + "\n" for row in samples), encoding="utf-8"
        )
        groups = self.private / "groups.jsonl"
        groups.write_text(
            "".join(
                json.dumps(
                    {
                        "record_ordinal": row["record_ordinal"],
                        "group_size": 2 if row["record_ordinal"] == 1 else 1,
                    }
                )
                + "\n"
                for row in samples
            ),
            encoding="utf-8",
        )
        flags, aggregate = self.private / "flags.jsonl", self.run / "aggregate.json"
        args = (
            archive,
            sample,
            groups,
            flags,
            aggregate,
            sha256(archive.read_bytes()).hexdigest(),
            sha256(sample.read_bytes()).hexdigest(),
            sha256(groups.read_bytes()).hexdigest(),
        )
        return args, flags, aggregate

    def audit(self, rows: list[dict[str, str]], samples: list[dict]):
        args, flags, aggregate = self.fixture(rows, samples)
        result = links.audit_parcel_links(*args, expected_sample_rows=len(samples))
        return result, flags, aggregate

    def test_two_key_matches_and_scope_clues_are_aggregate_only(self):
        rows = [
            {
                "PIN": "001",
                "FOLIO": "A",
                "DOR_C": "0100",
                "tUNITS": "1",
                "tBLDGS": "1",
                "HEAT_AR": "1500",
                "SALE1_DOC": "DEED-1",
            },
            {
                "PIN": "002",
                "FOLIO": "B",
                "DOR_C": "0400",
                "tUNITS": "2",
                "tBLDGS": "2",
                "SALE2_DOC": "OTHER",
            },
            {
                "PIN": "003",
                "FOLIO": "C",
                "DOR_C": "0100",
                "tBLDGS": "bad",
                "HEAT_AR": "-1",
            },
        ]
        samples = [
            _sample(1, "001", "A", doc="DEED-1"),
            _sample(2, "002", "B", doc="DEED-2"),
            _sample(3, "003", "C"),
        ]
        result, flags, aggregate = self.audit(rows, samples)
        self.assertEqual(
            result["sample"]["two_key_matches"], {"zero": 0, "one": 3, "many": 0}
        )
        self.assertEqual(
            result["sample"]["dor_code"], {"agree": 2, "disagree": 1, "missing": 0}
        )
        self.assertEqual(
            result["sample"]["unit_clues"],
            {"zero": 0, "one": 1, "multiple": 1, "unknown": 1, "invalid": 0},
        )
        self.assertEqual(
            result["sample"]["building_clues"],
            {"zero": 0, "one": 1, "multiple": 1, "unknown": 0, "invalid": 1},
        )
        self.assertEqual(
            result["sample"]["sale_document_match"], {"yes": 1, "no": 1, "unknown": 1}
        )
        self.assertEqual(result["repeated_instrument_sample"]["rows"], 1)
        self.assertNotIn("DEED-1", aggregate.read_text(encoding="utf-8"))
        self.assertNotIn('"001"', aggregate.read_text(encoding="utf-8"))
        self.assertEqual(len(flags.read_text(encoding="utf-8").splitlines()), 3)

    def test_missing_ids_conflicts_and_duplicate_keys_are_quarantined(self):
        rows = [
            {"PIN": "A", "FOLIO": "1"},
            {"PIN": "A", "FOLIO": "2"},
            {"PIN": "A", "FOLIO": "1"},
            {"PIN": "B", "FOLIO": "9"},
        ]
        samples = [
            _sample(1, "A", "1"),
            _sample(2, "A", "3"),
            _sample(3, "", "9"),
            _sample(4, "", ""),
        ]
        result, flags, _ = self.audit(rows, samples)
        self.assertEqual(
            result["sample"]["two_key_matches"], {"zero": 3, "one": 0, "many": 1}
        )
        self.assertEqual(result["sample"]["identifier_conflict_rows"], 0)
        self.assertEqual(result["sample"]["incomplete_key_rows"], 2)
        self.assertEqual(result["parcel"]["duplicate_two_key_rows"], 1)
        self.assertEqual(
            result["sample"]["folio_only_candidates"], {"zero": 3, "one": 1, "many": 0}
        )
        self.assertEqual(
            result["sample"]["pin_only_candidates"], {"zero": 2, "one": 1, "many": 1}
        )
        self.assertEqual(
            [json.loads(line)["status"] for line in flags.read_text().splitlines()],
            [
                "ambiguous_multiple",
                "pin_only_lead",
                "incomplete_key",
                "incomplete_key",
            ],
        )

    def test_corrupt_dbf_and_bad_source_hash_create_no_outputs(self):
        args, flags, aggregate = self.fixture(
            [{"PIN": "A", "FOLIO": "1"}], [_sample(1, "A", "1")], malformed=True
        )
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            links.audit_parcel_links(
                *(*args[:5], "0" * 64, *args[6:]), expected_sample_rows=1
            )
        with self.assertRaisesRegex(ValueError, "terminator"):
            links.audit_parcel_links(*args, expected_sample_rows=1)
        self.assertFalse(flags.exists())
        self.assertFalse(aggregate.exists())

    def test_private_output_containment_and_no_overwrite(self):
        args, flags, aggregate = self.fixture(
            [{"PIN": "A", "FOLIO": "1"}], [_sample(1, "A", "1")]
        )
        with self.assertRaisesRegex(ValueError, "private"):
            links.audit_parcel_links(
                *(*args[:3], self.root / "public-flags.jsonl", *args[4:]),
                expected_sample_rows=1,
            )
        self.assertFalse(aggregate.exists())
        links.audit_parcel_links(*args, expected_sample_rows=1)
        with self.assertRaises(FileExistsError):
            links.audit_parcel_links(*args, expected_sample_rows=1)
        self.assertTrue(flags.exists())

    def test_private_hardlink_and_symlink_inputs_are_rejected(self):
        args, _, aggregate = self.fixture(
            [{"PIN": "A", "FOLIO": "1"}], [_sample(1, "A", "1")]
        )
        linked = self.private / "linked-sample.jsonl"
        os.link(args[1], linked)
        with self.assertRaisesRegex(ValueError, "linked"):
            links.audit_parcel_links(*args, expected_sample_rows=1)
        self.assertFalse(aggregate.exists())

    def test_open_handle_identity_and_nested_private_output_are_rejected(self):
        first = self.private / "first.bin"
        second = self.private / "second.bin"
        first.write_bytes(b"first")
        second.write_bytes(b"second")
        with first.open("rb") as source, self.assertRaisesRegex(ValueError, "changed"):
            links._revalidate_open_file(second, source)
        args, _, aggregate = self.fixture(
            [{"PIN": "A", "FOLIO": "1"}], [_sample(1, "A", "1")]
        )
        nested = self.private / "nested"
        nested.mkdir()
        with self.assertRaisesRegex(ValueError, "directly"):
            links.audit_parcel_links(
                *(*args[:3], nested / "flags.jsonl", *args[4:]), expected_sample_rows=1
            )
        self.assertFalse(aggregate.exists())

    def test_redacted_folio_and_one_sided_conflict_cannot_be_accepted(self):
        rows = [
            {"PIN": "A", "FOLIO": "1", "SALE3_DOC": "DEED-X"},
            {"PIN": "A", "FOLIO": "2"},
            {"PIN": "C", "FOLIO": "CONFID"},
        ]
        samples = [
            _sample(1, "A", "1", doc="DEED-X"),
            _sample(2, "C", "CONFID"),
            _sample(3, "A", "9"),
        ]
        result, flags, _ = self.audit(rows, samples)
        self.assertEqual(
            result["sample"]["two_key_matches"], {"zero": 2, "one": 1, "many": 0}
        )
        self.assertEqual(result["sample"]["identifier_conflict_rows"], 1)
        self.assertEqual(result["sample"]["incomplete_key_rows"], 1)
        self.assertEqual(result["sample"]["unique_current_candidates"], 0)
        self.assertEqual(result["parcel"]["incomplete_key_rows"], 1)
        self.assertEqual(
            [json.loads(line)["status"] for line in flags.read_text().splitlines()],
            ["identifier_conflict", "incomplete_key", "pin_only_lead"],
        )

    def test_complete_sale_key_with_folio_only_lead_is_not_joined(self):
        result, flags, _ = self.audit(
            [{"PIN": "PARCEL-FORM", "FOLIO": "00001"}],
            [_sample(1, "SALE-FORM", "00001")],
        )
        self.assertEqual(
            result["sample"]["two_key_matches"], {"zero": 1, "one": 0, "many": 0}
        )
        self.assertEqual(
            result["sample"]["folio_only_candidates"], {"zero": 0, "one": 1, "many": 0}
        )
        self.assertEqual(result["sample"]["unique_current_candidates"], 0)
        self.assertEqual(
            json.loads(flags.read_text().splitlines()[0])["status"],
            "folio_only_lead",
        )

    def test_one_key_leads_are_separate_from_conflicting_keys(self):
        rows = [
            {"PIN": "OTHER", "FOLIO": "1"},
            {"PIN": "B", "FOLIO": "OTHER"},
            {"PIN": "C", "FOLIO": "OTHER-2"},
            {"PIN": "OTHER-2", "FOLIO": "3"},
        ]
        samples = [
            _sample(1, "A", "1"),
            _sample(2, "B", "2"),
            _sample(3, "C", "3"),
        ]
        result, flags, _ = self.audit(rows, samples)
        self.assertEqual(
            result["sample"]["two_key_matches"], {"zero": 3, "one": 0, "many": 0}
        )
        self.assertEqual(result["sample"]["identifier_conflict_rows"], 1)
        self.assertEqual(result["sample"]["folio_only_status_rows"], 1)
        self.assertEqual(result["sample"]["pin_only_status_rows"], 1)
        self.assertEqual(
            [json.loads(line)["status"] for line in flags.read_text().splitlines()],
            ["folio_only_lead", "pin_only_lead", "identifier_conflict"],
        )

    def test_heated_area_accepts_positive_fraction_but_rejects_negative_and_nonfinite(
        self,
    ):
        rows = [
            {"PIN": str(i), "FOLIO": str(i), "HEAT_AR": area}
            for i, area in enumerate(("1500", "0.5", "0", "", "-1", "NaN", "bad"), 1)
        ]
        result, _, _ = self.audit(
            rows, [_sample(i, str(i), str(i)) for i in range(1, 8)]
        )
        self.assertEqual(
            result["sample"]["heated_area_clues"],
            {"zero": 1, "positive": 2, "unknown": 1, "invalid": 3},
        )

    def test_unavailable_parcel_document_references_remain_unknown(self):
        rows = [
            {"PIN": "A", "FOLIO": "1"},
            {"PIN": "B", "FOLIO": "2", "SALE2_DOC": "DIFFERENT"},
            {"PIN": "C", "FOLIO": "3", "SALE3_DOC": "MATCH"},
        ]
        samples = [
            _sample(1, "A", "1", doc="SALE-1"),
            _sample(2, "B", "2", doc="SALE-2"),
            _sample(3, "C", "3", doc="MATCH"),
        ]
        result, _, _ = self.audit(rows, samples)
        self.assertEqual(
            result["sample"]["sale_document_match"], {"yes": 1, "no": 1, "unknown": 1}
        )

    def test_dbf_truncation_version_end_marker_fail(self):
        cases = [
            (lambda data: data[:-1], "row count or size"),
            (lambda data: bytes([4]) + data[1:], "dBASE III"),
            (lambda data: data[:-1] + b"X", "end marker"),
        ]
        for change, expected in cases:
            with self.subTest(expected=expected):
                data = change(_dbf([{"PIN": "A", "FOLIO": "1"}]))
                with self.assertRaisesRegex(ValueError, expected):
                    links._scan(BytesIO(data), len(data), [_sample(1, "A", "1")])

    def test_count_clues_distinguish_missing_zero_and_invalid(self):
        cases = [
            ("", "unknown"),
            ("0", "zero"),
            ("1.000000", "one"),
            ("2", "multiple"),
            ("-1", "invalid"),
            ("1.5", "invalid"),
            ("NaN", "invalid"),
            ("abc", "invalid"),
        ]
        for raw, expected in cases:
            with self.subTest(raw=raw):
                self.assertEqual(links._clue(raw), expected)

    def test_sample_and_document_flag_validation(self):
        sample = _sample(1, "A", "1")
        with self.assertRaisesRegex(ValueError, "duplicate"):
            links._load_sample((json.dumps(sample) + "\n").encode() * 2, 2)
        with self.assertRaisesRegex(ValueError, "omit"):
            links._repeated_ordinals(
                b'{"record_ordinal": 1, "group_size": 1}\n', {1, 2}
            )
        with self.assertRaisesRegex(ValueError, "Malformed"):
            links._jsonl_rows(b"{", "sample")

    def test_zip_member_entry_limit(self):
        archive = self.private / "many.zip"
        with ZipFile(archive, "w", ZIP_DEFLATED) as zipped:
            for index in range(101):
                zipped.writestr(f"other-{index}", b"x")
            zipped.writestr("parcel.dbf", _dbf([{"PIN": "A", "FOLIO": "1"}]))
        with ZipFile(archive) as zipped, self.assertRaisesRegex(ValueError, "entries"):
            links._member(zipped)


if __name__ == "__main__":
    unittest.main()
