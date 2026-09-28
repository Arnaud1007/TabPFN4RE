"""Synthetic controls for the disjoint HCPA PIN-format experiment."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from contextlib import redirect_stderr
from io import StringIO
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZIP_DEFLATED, ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import audit_hcpa_pin_crosswalk as crosswalk  # noqa: E402


FORMAT_A = "A-BC-DE-FG-HIJ-KLMNOP-QRSTU.V"
FORMAT_B = "B-CD-EF-GH-IJK-LMNOPQ-RSTUV.W"
STRAP_A = "FGDEBCHIJKLMNOPQRSTUVA"
STRAP_B = "GHEFCDIJKLMNOPQRSTUVWB"


def _dbf(fields: tuple[tuple[str, int], ...], rows: list[dict[str, str]]) -> bytes:
    header_length = 32 + len(fields) * 32 + 1
    row_length = 1 + sum(width for _, width in fields)
    header = bytearray(32)
    header[0] = 3
    struct.pack_into("<IHH", header, 4, len(rows), header_length, row_length)
    descriptors = bytearray()
    for name, width in fields:
        descriptor = bytearray(32)
        descriptor[: len(name)] = name.encode("ascii")
        descriptor[11] = ord("C")
        descriptor[16] = width
        descriptors.extend(descriptor)
    records = [
        b" "
        + b"".join(
            row.get(name, "").encode("ascii").ljust(width) for name, width in fields
        )
        for row in rows
    ]
    return bytes(header) + bytes(descriptors) + b"\x0d" + b"".join(records) + b"\x1a"


def _jsonl(rows: list[dict]) -> bytes:
    return "".join(json.dumps(row) + "\n" for row in rows).encode("utf-8")


def _sample(
    ordinal: int, pin: str, folio: str, date: str = "20250901", qu: str = "Q"
) -> dict:
    return {
        "record_ordinal": ordinal,
        "PIN": pin,
        "FOLIO": folio,
        "S_DATE": date,
        "QU": qu,
    }


class CrosswalkTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.private = self.root / "data" / "raw" / "hcpa"
        self.private.mkdir(parents=True)
        self.public = self.root / "runs"
        self.public.mkdir()
        patcher = patch.object(crosswalk, "PRIVATE_ROOT", self.private)
        patcher.start()
        self.addCleanup(patcher.stop)

    def fixture(
        self,
        samples: list[dict],
        old: list[dict],
        parcels_2025: list[dict[str, str]],
        parcels_2026: list[dict[str, str]],
    ) -> tuple:
        archive_2025 = self.private / "old.zip"
        archive_2026 = self.private / "current.zip"
        with ZipFile(archive_2025, "w", ZIP_DEFLATED) as zipped:
            zipped.writestr(
                "2025_10_parcel.dbf",
                _dbf((("PIN", 29), ("FOLIO", 10), ("STRAP", 22)), parcels_2025),
            )
        with ZipFile(archive_2026, "w", ZIP_DEFLATED) as zipped:
            zipped.writestr(
                "current/parcel.dbf",
                _dbf((("PIN", 25), ("FOLIO", 20)), parcels_2026),
            )
        sample = self.private / "validation.jsonl"
        old_sample = self.private / "old-sample.jsonl"
        sample.write_bytes(_jsonl(samples))
        old_sample.write_bytes(_jsonl(old))
        flags = self.private / "discrepancies.jsonl"
        aggregate = self.public / "aggregate.json"
        paths = (archive_2025, archive_2026, sample, old_sample, flags, aggregate)
        hashes = tuple(sha256(path.read_bytes()).hexdigest() for path in paths[:4])
        return (*paths, *hashes)

    def audit(
        self,
        samples: list[dict],
        old: list[dict],
        parcels_2025: list[dict[str, str]],
        parcels_2026: list[dict[str, str]],
    ):
        args = self.fixture(samples, old, parcels_2025, parcels_2026)
        report = crosswalk.audit_crosswalk(
            *args, expected_rows=len(samples), expected_old_rows=len(old)
        )
        return report, args[4], args[5]

    def test_transform_requires_exact_ascii_form(self):
        self.assertEqual(crosswalk.transform_pin(FORMAT_A), STRAP_A)
        self.assertIsNone(crosswalk.transform_pin(FORMAT_A.lower()))
        self.assertIsNone(crosswalk.transform_pin(FORMAT_A.replace("-", "", 1)))
        self.assertIsNone(crosswalk.transform_pin(FORMAT_A + " "))
        self.assertIsNone(crosswalk.transform_pin("A-ＢC-DE-FG-HIJ-KLMNOP-QRSTU.V"))
        self.assertIsNone(crosswalk.transform_pin(""))

    def test_repeated_sale_controls_count_rows_and_distinct_keys(self):
        report, flags_path, public_path = self.audit(
            [_sample(1, FORMAT_A, "0000000001"), _sample(2, FORMAT_A, "0000000001")],
            [_sample(3, FORMAT_B, "0000000002")],
            [{"PIN": FORMAT_A, "FOLIO": "0000000001", "STRAP": STRAP_A}],
            [{"PIN": STRAP_A, "FOLIO": "0000000001"}],
        )
        self.assertEqual(
            report["vintage_2025"]["exact_two_key"], {"zero": 0, "one": 2, "many": 0}
        )
        self.assertEqual(
            report["strap_control"],
            {
                "unique_exact_sale_rows": 2,
                "nonblank_strap_sale_rows": 2,
                "agree_sale_rows": 2,
                "nonblank_distinct_controls": 1,
                "agree_distinct_controls": 1,
                "malformed_sale_rows": 0,
            },
        )
        self.assertEqual(report["vintage_2026"]["unique_folio_nonblank_pin_rows"], 2)
        self.assertEqual(report["vintage_2026"]["pin_agrees_on_unique_folio_rows"], 2)
        self.assertEqual(
            report["vintage_2026"]["pin_disagrees_on_unique_folio_rows"], 0
        )
        self.assertEqual(report["transformed_collisions"], 0)
        self.assertEqual(report["automatic_join_status"], "BLOCKED")
        self.assertEqual(len(flags_path.read_text(encoding="utf-8").splitlines()), 2)
        public = public_path.read_text(encoding="utf-8")
        self.assertNotIn(FORMAT_A, public)
        self.assertNotIn("0000000001", public)
        self.assertNotIn("current/", public)
        self.assertEqual(report["source_2026"]["member"], "parcel.dbf")
        self.assertEqual(len(report["source_2025"]["schema_sha256"]), 64)
        self.assertEqual(len(report["source_2026"]["schema_sha256"]), 64)
        self.assertNotEqual(
            report["source_2025"]["schema_sha256"],
            report["source_2026"]["schema_sha256"],
        )

    def test_one_key_leads_missing_and_conflicts_not_promoted(self):
        report, flags_path, _ = self.audit(
            [_sample(1, FORMAT_A, "0000000001"), _sample(2, "BAD", "0000000002")],
            [_sample(3, FORMAT_B, "0000000003")],
            [
                {"PIN": FORMAT_A, "FOLIO": "0000000009", "STRAP": STRAP_A},
                {"PIN": FORMAT_B, "FOLIO": "0000000001", "STRAP": STRAP_B},
            ],
            [
                {"PIN": STRAP_A, "FOLIO": "0000000009"},
                {"PIN": STRAP_B, "FOLIO": "0000000001"},
                {"PIN": "", "FOLIO": "0000000002"},
            ],
        )
        self.assertEqual(
            report["vintage_2025"]["exact_two_key"], {"zero": 2, "one": 0, "many": 0}
        )
        self.assertEqual(report["vintage_2025"]["conflicting_rows"], 1)
        self.assertEqual(report["vintage_2026"]["conflicting_rows"], 1)
        self.assertEqual(report["vintage_2026"]["unique_folio_blank_pin_rows"], 1)
        self.assertEqual(report["vintage_2026"]["unique_folio_nonblank_pin_rows"], 1)
        self.assertEqual(report["vintage_2026"]["pin_agrees_on_unique_folio_rows"], 0)
        self.assertEqual(
            report["vintage_2026"]["pin_disagrees_on_unique_folio_rows"], 1
        )
        self.assertIn("current_pin_disagreement", report["automatic_join_blockers"])
        self.assertEqual(report["sample"]["malformed_pin_rows"], 1)
        flags = [
            json.loads(line)
            for line in flags_path.read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual(flags[0]["vintage_2025_status"], "identifier_conflict")
        self.assertEqual(flags[1]["transform_status"], "malformed")

    def test_rejects_overlap_and_duplicate_ordinals(self):
        args = self.fixture(
            [_sample(1, FORMAT_A, "0000000001")],
            [_sample(1, FORMAT_B, "0000000002")],
            [],
            [],
        )
        with self.assertRaisesRegex(ValueError, "overlap"):
            crosswalk.audit_crosswalk(*args, expected_rows=1, expected_old_rows=1)
        self.assertFalse(args[4].exists())
        args = self.fixture(
            [_sample(1, FORMAT_A, "0000000001"), _sample(1, FORMAT_B, "0000000002")],
            [_sample(3, FORMAT_A, "0000000003")],
            [],
            [],
        )
        with self.assertRaisesRegex(ValueError, "duplicate"):
            crosswalk.audit_crosswalk(*args, expected_rows=2, expected_old_rows=1)

    def test_rejects_unpinned_input_and_existing_output(self):
        args = list(
            self.fixture(
                [_sample(1, FORMAT_A, "0000000001")],
                [_sample(2, FORMAT_B, "0000000002")],
                [],
                [],
            )
        )
        args[6] = "0" * 64
        with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
            crosswalk.audit_crosswalk(*args, expected_rows=1, expected_old_rows=1)
        args[6] = sha256(args[0].read_bytes()).hexdigest()
        args[5].write_text("already present", encoding="utf-8")
        with self.assertRaises(FileExistsError):
            crosswalk.audit_crosswalk(*args, expected_rows=1, expected_old_rows=1)

    def test_rejects_nonprivate_flags_and_wrong_archive_schema(self):
        args = list(
            self.fixture(
                [_sample(1, FORMAT_A, "0000000001")],
                [_sample(2, FORMAT_B, "0000000002")],
                [],
                [],
            )
        )
        args[4] = self.public / "leak.jsonl"
        with self.assertRaisesRegex(ValueError, "private"):
            crosswalk.audit_crosswalk(*args, expected_rows=1, expected_old_rows=1)
        args[4] = self.private / "flags.jsonl"
        with ZipFile(args[0], "w", ZIP_DEFLATED) as zipped:
            zipped.writestr(
                "2025_10_parcel.dbf",
                _dbf((("PIN", 28), ("FOLIO", 10), ("STRAP", 22)), []),
            )
        args[6] = sha256(args[0].read_bytes()).hexdigest()
        with self.assertRaisesRegex(ValueError, "schema"):
            crosswalk.audit_crosswalk(*args, expected_rows=1, expected_old_rows=1)

    def test_blank_strap_duplicate_parcel_rows_and_redacted_folio(self):
        report, flags_path, _ = self.audit(
            [
                _sample(1, FORMAT_A, "0000000001"),
                _sample(2, FORMAT_B, "CONFID"),
            ],
            [_sample(3, FORMAT_A, "0000000003")],
            [
                {"PIN": FORMAT_A, "FOLIO": "0000000001", "STRAP": ""},
                {"PIN": FORMAT_B, "FOLIO": "0000000002", "STRAP": STRAP_B},
                {"PIN": FORMAT_B, "FOLIO": "0000000002", "STRAP": STRAP_B},
            ],
            [
                {"PIN": STRAP_A, "FOLIO": "0000000001"},
                {"PIN": STRAP_B, "FOLIO": "0000000002"},
                {"PIN": STRAP_B, "FOLIO": "0000000002"},
            ],
        )
        self.assertEqual(report["strap_control"]["unique_exact_sale_rows"], 1)
        self.assertEqual(report["strap_control"]["nonblank_strap_sale_rows"], 0)
        self.assertEqual(report["sample"]["redacted_folio_rows"], 1)
        self.assertEqual(
            report["vintage_2025"]["exact_two_key"], {"zero": 1, "one": 1, "many": 0}
        )
        self.assertEqual(report["vintage_2026"]["unique_folio_nonblank_pin_rows"], 1)
        flags = [
            json.loads(line)
            for line in flags_path.read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual(flags[0]["strap_control_status"], "blank_strap")
        self.assertEqual(flags[1]["vintage_2025_status"], "pin_only_lead")

    def test_ambiguous_exact_rows_are_not_controls(self):
        report, flags_path, _ = self.audit(
            [_sample(1, FORMAT_A, "0000000001")],
            [_sample(2, FORMAT_B, "0000000002")],
            [
                {"PIN": FORMAT_A, "FOLIO": "0000000001", "STRAP": STRAP_A},
                {"PIN": FORMAT_A, "FOLIO": "0000000001", "STRAP": STRAP_A},
            ],
            [
                {"PIN": STRAP_A, "FOLIO": "0000000001"},
                {"PIN": STRAP_A, "FOLIO": "0000000001"},
            ],
        )
        self.assertEqual(
            report["vintage_2025"]["exact_two_key"], {"zero": 0, "one": 0, "many": 1}
        )
        self.assertEqual(report["vintage_2025"]["duplicate_exact_key_rows"], 1)
        self.assertEqual(report["strap_control"]["unique_exact_sale_rows"], 0)
        self.assertEqual(report["vintage_2026"]["ambiguous_multiple_rows"], 1)
        self.assertEqual(report["format_rule_numeric_status"], "fails_numeric_criteria")
        flag = json.loads(flags_path.read_text(encoding="utf-8"))
        self.assertEqual(flag["vintage_2025_status"], "ambiguous_multiple")

    def test_200_distinct_controls_meet_numeric_criteria_only(self):
        samples = [
            _sample(i + 1, f"A-BC-DE-FG-HIJ-KLMNOP-{i:05d}.V", f"{i:010d}")
            for i in range(200)
        ]
        old = [_sample(201, FORMAT_B, "0000000201")]
        parcels_2025 = [
            {
                "PIN": row["PIN"],
                "FOLIO": row["FOLIO"],
                "STRAP": crosswalk.transform_pin(row["PIN"]),
            }
            for row in samples
        ]
        parcels_2026 = [
            {"PIN": row["STRAP"], "FOLIO": row["FOLIO"]} for row in parcels_2025
        ]
        report, _, _ = self.audit(samples, old, parcels_2025, parcels_2026)
        self.assertEqual(report["strap_control"]["nonblank_distinct_controls"], 200)
        self.assertEqual(
            report["format_rule_numeric_status"],
            "meets_numeric_criteria_pending_custodian",
        )
        self.assertEqual(report["automatic_join_status"], "BLOCKED")
        self.assertIn(
            "historical_availability_unverified", report["automatic_join_blockers"]
        )

    def test_disagreeing_controls_fail_numeric_criterion(self):
        samples = [
            _sample(i + 1, f"A-BC-DE-FG-HIJ-KLMNOP-{i:05d}.V", f"{i:010d}")
            for i in range(200)
        ]
        parcels_2025 = [
            {
                "PIN": row["PIN"],
                "FOLIO": row["FOLIO"],
                "STRAP": "WRONG" if index < 3 else crosswalk.transform_pin(row["PIN"]),
            }
            for index, row in enumerate(samples)
        ]
        report, _, _ = self.audit(
            samples, [_sample(201, FORMAT_B, "0000000201")], parcels_2025, []
        )
        self.assertEqual(report["strap_control"]["agree_sale_rows"], 197)
        self.assertEqual(report["format_rule_numeric_status"], "fails_numeric_criteria")

    def test_transformed_key_collision_is_immediate_failure(self):
        report, _, _ = self.audit(
            [_sample(1, FORMAT_A, "0000000001"), _sample(2, FORMAT_A, "0000000002")],
            [_sample(3, FORMAT_B, "0000000003")],
            [
                {"PIN": FORMAT_A, "FOLIO": "0000000001", "STRAP": STRAP_A},
                {"PIN": FORMAT_A, "FOLIO": "0000000002", "STRAP": STRAP_A},
            ],
            [
                {"PIN": STRAP_A, "FOLIO": "0000000001"},
                {"PIN": STRAP_A, "FOLIO": "0000000002"},
            ],
        )
        self.assertEqual(report["transformed_collisions"], 1)
        self.assertEqual(report["format_rule_numeric_status"], "fails_numeric_criteria")

    def test_malformed_sample_rows_fail_without_outputs(self):
        cases = (
            (
                [_sample(1, FORMAT_A, "0000000001", date="20270201")],
                "invalid sale date",
            ),
            ([_sample(1, FORMAT_A, "0000000001", qu="X")], "QU"),
            ([_sample(1, "\u0001", "0000000001")], "printable ASCII"),
            ([_sample(1, FORMAT_A, "0000000001") | {"FOLIO": None}], "required"),
            ([_sample(1, FORMAT_A, "0000000001") | {"S_AMT": "1"}], "unexpected"),
        )
        for samples, message in cases:
            with self.subTest(message=message):
                args = self.fixture(
                    samples, [_sample(2, FORMAT_B, "0000000002")], [], []
                )
                with self.assertRaisesRegex(ValueError, message):
                    crosswalk.audit_crosswalk(
                        *args, expected_rows=1, expected_old_rows=1
                    )
                self.assertFalse(args[4].exists())
                self.assertFalse(args[5].exists())

    def test_full_sample_cell_contract_is_enforced(self):
        dates = ("19991231", "20091231", "20191231", "20231231", "20260928")
        samples = [
            _sample(
                1 + index * 200 + qu_offset * 100 + repeat,
                FORMAT_A,
                f"{repeat:010d}",
                date=raw_date,
                qu=qu,
            )
            for index, raw_date in enumerate(dates)
            for qu_offset, qu in enumerate(("Q", "U"))
            for repeat in range(100)
        ]
        old = [_sample(i + 1001, FORMAT_B, f"{i:010d}") for i in range(200)]
        args = self.fixture(samples, old, [], [])
        with patch.object(crosswalk, "FROZEN_OLD_SAMPLE_SHA256", args[9]):
            with patch.object(crosswalk, "FROZEN_VALIDATION_SAMPLE_SHA256", args[8]):
                report = crosswalk.audit_crosswalk(*args)
        self.assertEqual(len(report["cell_counts"]), 10)
        self.assertTrue(all(count == 100 for count in report["cell_counts"].values()))

    def test_production_rejects_unregistered_old_sample(self):
        samples = [_sample(i + 1, FORMAT_A, f"{i:010d}") for i in range(1000)]
        old = [_sample(i + 1001, FORMAT_B, f"{i:010d}") for i in range(200)]
        args = self.fixture(samples, old, [], [])
        with self.assertRaisesRegex(ValueError, "frozen audit sample SHA-256"):
            crosswalk.audit_crosswalk(*args)
        self.assertFalse(args[4].exists())

    def test_production_rejects_unregistered_validation_sample(self):
        samples = [_sample(i + 1, FORMAT_A, f"{i:010d}") for i in range(1000)]
        old = [_sample(i + 1001, FORMAT_B, f"{i:010d}") for i in range(200)]
        args = self.fixture(samples, old, [], [])
        with patch.object(crosswalk, "FROZEN_OLD_SAMPLE_SHA256", args[9]):
            with self.assertRaisesRegex(ValueError, "frozen validation sample SHA-256"):
                crosswalk.audit_crosswalk(*args)
        self.assertFalse(args[4].exists())

    def test_rejects_duplicate_json_key(self):
        args = list(
            self.fixture(
                [_sample(1, FORMAT_A, "0000000001")],
                [_sample(2, FORMAT_B, "0000000002")],
                [],
                [],
            )
        )
        args[2].write_text(
            '{"record_ordinal":1,"record_ordinal":2}\n', encoding="utf-8"
        )
        args[8] = sha256(args[2].read_bytes()).hexdigest()
        with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
            crosswalk.audit_crosswalk(*args, expected_rows=1, expected_old_rows=1)

    def test_rejects_malformed_jsonl_and_invalid_hash_format(self):
        args = list(
            self.fixture(
                [_sample(1, FORMAT_A, "0000000001")],
                [_sample(2, FORMAT_B, "0000000002")],
                [],
                [],
            )
        )
        args[8] = "bad"
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            crosswalk.audit_crosswalk(*args, expected_rows=1, expected_old_rows=1)
        args[2].write_bytes(b"not-json\n")
        args[8] = sha256(args[2].read_bytes()).hexdigest()
        with self.assertRaisesRegex(ValueError, "JSONL"):
            crosswalk.audit_crosswalk(*args, expected_rows=1, expected_old_rows=1)

    def test_output_failure_rolls_back_private_flags(self):
        args = self.fixture(
            [_sample(1, FORMAT_A, "0000000001")],
            [_sample(2, FORMAT_B, "0000000002")],
            [],
            [],
        )
        original = crosswalk._write_once

        def fail_public(path, content, *, private):
            if not private:
                raise OSError("synthetic disk failure")
            return original(path, content, private=private)

        with patch.object(crosswalk, "_write_once", side_effect=fail_public):
            with self.assertRaisesRegex(OSError, "disk failure"):
                crosswalk.audit_crosswalk(*args, expected_rows=1, expected_old_rows=1)
        self.assertFalse(args[4].exists())
        self.assertFalse(args[5].exists())

    def test_cli_passes_frozen_defaults_and_reports_failure(self):
        args = self.fixture(
            [_sample(1, FORMAT_A, "0000000001")],
            [_sample(2, FORMAT_B, "0000000002")],
            [],
            [],
        )
        names = (
            "archive-2025",
            "archive-2026",
            "sample",
            "old-sample",
            "private-flags",
            "aggregate",
            "archive-2025-sha256",
            "archive-2026-sha256",
            "sample-sha256",
            "old-sample-sha256",
        )
        argv = [
            item
            for name, value in zip(names, args)
            for item in (f"--{name}", str(value))
        ]
        with patch.object(crosswalk, "audit_crosswalk", return_value={}) as audit:
            self.assertEqual(crosswalk.main(argv), 0)
            self.assertEqual(audit.call_args.args, args)
            self.assertEqual(audit.call_args.kwargs, {})
        stderr = StringIO()
        with patch.object(
            crosswalk, "audit_crosswalk", side_effect=ValueError("bad source")
        ):
            with redirect_stderr(stderr):
                self.assertEqual(crosswalk.main(argv), 2)
        self.assertIn("PIN crosswalk audit failed: bad source", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
