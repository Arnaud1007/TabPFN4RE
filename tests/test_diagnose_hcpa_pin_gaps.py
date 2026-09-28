"""Synthetic, private-only fixtures for bounded HCPA identity gap diagnosis."""

from __future__ import annotations

from hashlib import sha256
from contextlib import redirect_stderr
from dataclasses import replace
from io import StringIO
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZIP_DEFLATED, ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import audit_hcpa_pin_crosswalk as crosswalk  # noqa: E402
import diagnose_hcpa_pin_gaps as gaps  # noqa: E402


PIN_A = "A-BC-DE-FG-HIJ-KLMNOP-QRSTU.V"
PIN_B = "B-CD-EF-GH-IJK-LMNOPQ-RSTUV.W"
PIN_C = "C-DE-FG-HI-JKL-MNOPQR-STUVW.X"
PIN_D = "D-EF-GH-IJ-KLM-NOPQRS-TUVWX.Y"


def _sample(ordinal: int, pin: str, folio: str, when="20250901") -> dict:
    return {
        "record_ordinal": ordinal,
        "PIN": pin,
        "FOLIO": folio,
        "S_DATE": when,
        "QU": "Q",
    }


def _dbf(fields, rows, *, year=2025, month=9, day=12) -> bytes:
    header_length = 32 + len(fields) * 32 + 1
    record_length = 1 + sum(width for _, width in fields)
    header = bytearray(32)
    header[0:4] = bytes((3, year - 1900, month, day))
    struct.pack_into("<IHH", header, 4, len(rows), header_length, record_length)
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


def _digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


class GapDiagnosticTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.private = Path(self.temp.name) / "data" / "raw" / "hcpa"
        self.private.mkdir(parents=True)
        self.public = Path(self.temp.name) / "runs"
        self.public.mkdir()
        self.fixture_index = 0
        for module in (crosswalk, gaps):
            patcher = patch.object(module, "PRIVATE_ROOT", self.private)
            patcher.start()
            self.addCleanup(patcher.stop)

    def fixture(self, samples, old_2025, current_2026, *, header_date=(2025, 9, 12)):
        self.fixture_index += 1
        suffix = str(self.fixture_index)
        old_zip = self.private / f"2025-{suffix}.zip"
        current_zip = self.private / f"2026-{suffix}.zip"
        with ZipFile(old_zip, "w", ZIP_DEFLATED) as zipped:
            zipped.writestr(
                "2025_10_parcel.dbf",
                _dbf(
                    (("PIN", 29), ("FOLIO", 10), ("STRAP", 22)),
                    old_2025,
                    year=header_date[0],
                    month=header_date[1],
                    day=header_date[2],
                ),
            )
        with ZipFile(current_zip, "w", ZIP_DEFLATED) as zipped:
            zipped.writestr(
                "parcel.dbf",
                _dbf((("PIN", 25), ("FOLIO", 20)), current_2026),
            )
        sample = self.private / f"validation-{suffix}.jsonl"
        old_sample = self.private / f"excluded-{suffix}.jsonl"
        sample.write_text(
            "".join(json.dumps(row) + "\n" for row in samples), encoding="utf-8"
        )
        old_sample.write_text(
            json.dumps(_sample(1001, PIN_C, "0000000099")) + "\n", encoding="utf-8"
        )
        prior_flags = self.private / f"crosswalk_flags-{suffix}.jsonl"
        prior = self.public / f"crosswalk-{suffix}.json"
        sources = (old_zip, current_zip, sample, old_sample)
        hashes = tuple(_digest(path) for path in sources)
        crosswalk.audit_crosswalk(
            *sources,
            prior_flags,
            prior,
            *hashes,
            expected_rows=len(samples),
            expected_old_rows=1,
        )
        flags = self.private / f"gap_flags-{suffix}.jsonl"
        aggregate = self.public / f"gap-{suffix}.json"
        return gaps.GapInputs(
            archive_2025=gaps.PinnedFile(old_zip, hashes[0]),
            archive_2026=gaps.PinnedFile(current_zip, hashes[1]),
            sample=gaps.PinnedFile(sample, hashes[2]),
            old_sample=gaps.PinnedFile(old_sample, hashes[3]),
            prior_aggregate=gaps.PinnedFile(prior, _digest(prior)),
            private_flags=flags,
            aggregate=aggregate,
        )

    def diagnose(self, args, *, expected_rows):
        return gaps.diagnose_gaps(
            replace(args, expected_rows=expected_rows, expected_old_rows=1)
        )

    def test_reconciles_overlapping_gaps_without_promoting_one_key_lead(self):
        samples = [
            _sample(1, PIN_A, "0000000001", "20250911"),
            _sample(2, PIN_B, "0000000002", "20250912"),
            _sample(3, PIN_C, "0000000003", "20250913"),
        ]
        args = self.fixture(
            samples,
            [
                {
                    "PIN": PIN_A,
                    "FOLIO": "0000000001",
                    "STRAP": crosswalk.transform_pin(PIN_A),
                },
                {
                    "PIN": PIN_D,
                    "FOLIO": "0000000002",
                    "STRAP": crosswalk.transform_pin(PIN_D),
                },
            ],
            [
                {"PIN": crosswalk.transform_pin(PIN_A), "FOLIO": "0000000001"},
                {"PIN": "", "FOLIO": "0000000002"},
                {"PIN": "", "FOLIO": "0000000003"},
            ],
        )
        result = self.diagnose(args, expected_rows=3)
        self.assertEqual(
            result["intersection"],
            {
                "old_exact_current_nonblank": 1,
                "old_exact_current_blank": 0,
                "old_no_exact_current_nonblank": 0,
                "old_no_exact_current_blank": 2,
            },
        )
        self.assertEqual(result["old_no_exact"]["folio_only_lead"], 1)
        self.assertEqual(result["old_no_exact"]["no_lead"], 1)
        self.assertEqual(result["old_no_exact"]["folio_lead_pin_nonblank_different"], 1)
        self.assertEqual(result["old_no_exact"]["folio_lead_strap_disagree"], 1)
        self.assertEqual(
            result["old_no_exact"]["sale_date_vs_old_dbf_header"],
            {"before": 0, "on": 1, "after": 1},
        )
        self.assertEqual(result["current_blank"]["raw_all_spaces"], 2)
        self.assertEqual(result["current_blank"]["unique_folio"], 2)
        self.assertEqual(result["current_blank"]["overlap_old_no_exact"], 2)
        self.assertEqual(result["current_blank"]["old_folio_only_lead"], 1)
        self.assertEqual(result["current_blank"]["old_no_lead"], 1)
        self.assertEqual(result["automatic_join_status"], "BLOCKED")
        public = args.aggregate.read_text(encoding="utf-8")
        for forbidden in (
            PIN_A,
            PIN_B,
            PIN_C,
            "0000000001",
            "record_ordinal",
            "sale_price",
        ):
            self.assertNotIn(forbidden, public)
        private = [
            json.loads(line)
            for line in args.private_flags.read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual(len(private), 3)
        self.assertTrue(all("record_ordinal" in row for row in private))

    def test_repeated_sale_identity_is_not_a_collision(self):
        samples = [_sample(1, PIN_A, "0000000001"), _sample(2, PIN_A, "0000000001")]
        args = self.fixture(
            samples,
            [
                {
                    "PIN": PIN_A,
                    "FOLIO": "0000000001",
                    "STRAP": crosswalk.transform_pin(PIN_A),
                }
            ],
            [{"PIN": crosswalk.transform_pin(PIN_A), "FOLIO": "0000000001"}],
        )
        result = self.diagnose(args, expected_rows=2)
        self.assertEqual(result["intersection"]["old_exact_current_nonblank"], 2)
        self.assertEqual(result["sample"]["distinct_source_identities"], 1)

    def test_exact_2025_control_can_overlap_current_blank(self):
        args = self.fixture(
            [_sample(777123, PIN_A, "1234567890")],
            [
                {
                    "PIN": PIN_A,
                    "FOLIO": "1234567890",
                    "STRAP": crosswalk.transform_pin(PIN_A),
                }
            ],
            [{"PIN": "", "FOLIO": "1234567890"}],
        )
        result = self.diagnose(args, expected_rows=1)
        self.assertEqual(result["intersection"]["old_exact_current_blank"], 1)
        self.assertEqual(result["current_blank"]["old_exact"], 1)
        public = args.aggregate.read_text(encoding="utf-8")
        for forbidden in (
            "777123",
            "1234567890",
            PIN_A,
            "record_ordinal",
            "private_flags",
            "sale_price",
            "address",
            str(args.private_flags),
        ):
            self.assertNotIn(forbidden, public)

    def test_rejects_private_flags_outside_ignored_raw_storage(self):
        args = self.fixture(
            [_sample(1, PIN_A, "0000000001")],
            [
                {
                    "PIN": PIN_A,
                    "FOLIO": "0000000001",
                    "STRAP": crosswalk.transform_pin(PIN_A),
                }
            ],
            [{"PIN": crosswalk.transform_pin(PIN_A), "FOLIO": "0000000001"}],
        )
        args = replace(args, private_flags=self.public / "forbidden_flags.jsonl")
        with self.assertRaisesRegex(ValueError, "private"):
            self.diagnose(args, expected_rows=1)
        self.assertFalse(args.private_flags.exists())
        self.assertFalse(args.aggregate.exists())

    def test_rejects_nonspace_blank_pin_bytes(self):
        args = self.fixture(
            [_sample(1, PIN_A, "0000000001")],
            [
                {
                    "PIN": PIN_A,
                    "FOLIO": "0000000001",
                    "STRAP": crosswalk.transform_pin(PIN_A),
                }
            ],
            [{"PIN": "\t", "FOLIO": "0000000001"}],
        )
        with self.assertRaisesRegex(ValueError, "non-space controls"):
            self.diagnose(args, expected_rows=1)
        self.assertFalse(args.aggregate.exists())

    def test_malformed_2025_folio_lead_is_diagnostic_only(self):
        args = self.fixture(
            [_sample(1, PIN_A, "0000000001")],
            [{"PIN": "MALFORMED", "FOLIO": "0000000001", "STRAP": ""}],
            [{"PIN": crosswalk.transform_pin(PIN_A), "FOLIO": "0000000001"}],
        )
        result = self.diagnose(args, expected_rows=1)
        self.assertEqual(result["old_no_exact"]["folio_lead_pin_malformed"], 1)
        self.assertEqual(result["old_no_exact"]["folio_lead_strap_blank"], 1)
        self.assertEqual(result["automatic_join_status"], "BLOCKED")

    def test_blank_2025_folio_lead_with_matching_strap_remains_unconfirmed(self):
        args = self.fixture(
            [_sample(1, PIN_A, "0000000001")],
            [
                {
                    "PIN": "",
                    "FOLIO": "0000000001",
                    "STRAP": crosswalk.transform_pin(PIN_A),
                }
            ],
            [{"PIN": crosswalk.transform_pin(PIN_A), "FOLIO": "0000000001"}],
        )
        result = self.diagnose(args, expected_rows=1)
        self.assertEqual(result["old_no_exact"]["folio_lead_pin_blank"], 1)
        self.assertEqual(result["old_no_exact"]["folio_lead_strap_agree"], 1)
        self.assertEqual(result["intersection"]["old_no_exact_current_nonblank"], 1)
        self.assertEqual(result["automatic_join_status"], "BLOCKED")

    def test_conflicting_old_candidates_and_missing_current_candidate_fail(self):
        old_conflict = self.fixture(
            [_sample(1, PIN_A, "0000000001")],
            [
                {
                    "PIN": PIN_A,
                    "FOLIO": "0000000002",
                    "STRAP": crosswalk.transform_pin(PIN_A),
                },
                {
                    "PIN": PIN_B,
                    "FOLIO": "0000000001",
                    "STRAP": crosswalk.transform_pin(PIN_B),
                },
            ],
            [{"PIN": crosswalk.transform_pin(PIN_A), "FOLIO": "0000000001"}],
        )
        with self.assertRaisesRegex(ValueError, "Conflicting or ambiguous 2025"):
            self.diagnose(old_conflict, expected_rows=1)
        self.assertFalse(old_conflict.aggregate.exists())

        missing_current = self.fixture(
            [_sample(1, PIN_A, "0000000001")],
            [
                {
                    "PIN": PIN_A,
                    "FOLIO": "0000000001",
                    "STRAP": crosswalk.transform_pin(PIN_A),
                }
            ],
            [],
        )
        with self.assertRaisesRegex(ValueError, "Missing or ambiguous current"):
            self.diagnose(missing_current, expected_rows=1)
        self.assertFalse(missing_current.aggregate.exists())

    def test_current_nonblank_pin_disagreement_fails(self):
        args = self.fixture(
            [_sample(1, PIN_A, "0000000001")],
            [
                {
                    "PIN": PIN_A,
                    "FOLIO": "0000000001",
                    "STRAP": crosswalk.transform_pin(PIN_A),
                }
            ],
            [{"PIN": crosswalk.transform_pin(PIN_B), "FOLIO": "0000000001"}],
        )
        with self.assertRaisesRegex(ValueError, "Current PIN conflicts"):
            self.diagnose(args, expected_rows=1)
        self.assertFalse(args.aggregate.exists())

    def test_cli_preserves_frozen_defaults_and_has_explicit_failure(self):
        args = self.fixture(
            [_sample(1, PIN_A, "0000000001")],
            [
                {
                    "PIN": PIN_A,
                    "FOLIO": "0000000001",
                    "STRAP": crosswalk.transform_pin(PIN_A),
                }
            ],
            [{"PIN": crosswalk.transform_pin(PIN_A), "FOLIO": "0000000001"}],
        )
        names = (
            "archive-2025",
            "archive-2026",
            "sample",
            "old-sample",
            "prior-aggregate",
            "private-flags",
            "aggregate",
            "archive-2025-sha256",
            "archive-2026-sha256",
            "sample-sha256",
            "old-sample-sha256",
            "prior-aggregate-sha256",
        )
        values = (
            args.archive_2025.path,
            args.archive_2026.path,
            args.sample.path,
            args.old_sample.path,
            args.prior_aggregate.path,
            args.private_flags,
            args.aggregate,
            args.archive_2025.sha256,
            args.archive_2026.sha256,
            args.sample.sha256,
            args.old_sample.sha256,
            args.prior_aggregate.sha256,
        )
        argv = [
            item
            for name, value in zip(names, values)
            for item in (f"--{name}", str(value))
        ]
        with patch.object(gaps, "diagnose_gaps", return_value={}) as diagnosis:
            self.assertEqual(gaps.main(argv), 0)
            self.assertEqual(diagnosis.call_args.args, (args,))
            self.assertEqual(diagnosis.call_args.kwargs, {})
        stderr = StringIO()
        with patch.object(
            gaps, "diagnose_gaps", side_effect=ValueError("synthetic failure")
        ):
            with redirect_stderr(stderr):
                self.assertEqual(gaps.main(argv), 2)
        self.assertIn("synthetic failure", stderr.getvalue())

    def test_rejects_invalid_dbf_header_date(self):
        args = self.fixture(
            [_sample(1, PIN_A, "0000000001")],
            [
                {
                    "PIN": PIN_A,
                    "FOLIO": "0000000001",
                    "STRAP": crosswalk.transform_pin(PIN_A),
                }
            ],
            [{"PIN": crosswalk.transform_pin(PIN_A), "FOLIO": "0000000001"}],
            header_date=(2025, 2, 30),
        )
        with self.assertRaisesRegex(ValueError, "header date"):
            self.diagnose(args, expected_rows=1)
        self.assertFalse(args.aggregate.exists())

    def test_rejects_duplicate_prior_json_keys_and_existing_output(self):
        args = self.fixture(
            [_sample(1, PIN_A, "0000000001")],
            [
                {
                    "PIN": PIN_A,
                    "FOLIO": "0000000001",
                    "STRAP": crosswalk.transform_pin(PIN_A),
                }
            ],
            [{"PIN": crosswalk.transform_pin(PIN_A), "FOLIO": "0000000001"}],
        )
        prior_text = args.prior_aggregate.path.read_text(encoding="utf-8").rstrip()
        args.prior_aggregate.path.write_text(
            prior_text[:-1] + ',"sample":{}}\n', encoding="utf-8"
        )
        args = replace(
            args,
            prior_aggregate=gaps.PinnedFile(
                args.prior_aggregate.path, _digest(args.prior_aggregate.path)
            ),
        )
        with self.assertRaisesRegex(ValueError, "duplicate JSON keys"):
            self.diagnose(args, expected_rows=1)
        self.assertFalse(args.aggregate.exists())
        args.aggregate.write_text("existing", encoding="utf-8")
        with self.assertRaises(FileExistsError):
            self.diagnose(args, expected_rows=1)

    def test_rejects_prior_aggregate_mismatch_without_output(self):
        args = self.fixture(
            [_sample(1, PIN_A, "0000000001")],
            [
                {
                    "PIN": PIN_A,
                    "FOLIO": "0000000001",
                    "STRAP": crosswalk.transform_pin(PIN_A),
                }
            ],
            [{"PIN": crosswalk.transform_pin(PIN_A), "FOLIO": "0000000001"}],
        )
        prior = json.loads(args.prior_aggregate.path.read_text(encoding="utf-8"))
        prior["vintage_2025"]["exact_two_key"]["one"] = 0
        args.prior_aggregate.path.write_text(json.dumps(prior), encoding="utf-8")
        args = replace(
            args,
            prior_aggregate=gaps.PinnedFile(
                args.prior_aggregate.path, _digest(args.prior_aggregate.path)
            ),
        )
        with self.assertRaisesRegex(ValueError, "prior aggregate mismatch"):
            self.diagnose(args, expected_rows=1)
        self.assertFalse(args.private_flags.exists())
        self.assertFalse(args.aggregate.exists())

    def test_rejects_hash_schema_and_non_space_current_blank(self):
        args = self.fixture(
            [_sample(1, PIN_A, "0000000001")],
            [
                {
                    "PIN": PIN_A,
                    "FOLIO": "0000000001",
                    "STRAP": crosswalk.transform_pin(PIN_A),
                }
            ],
            [{"PIN": "", "FOLIO": "0000000001"}],
        )
        pinned_prior = args.prior_aggregate
        args = replace(args, prior_aggregate=replace(pinned_prior, sha256="0" * 64))
        with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
            self.diagnose(args, expected_rows=1)
        self.assertFalse(args.aggregate.exists())
        args = replace(args, prior_aggregate=pinned_prior)
        with ZipFile(args.archive_2026.path, "w", ZIP_DEFLATED) as zipped:
            zipped.writestr("parcel.dbf", _dbf((("PIN", 24), ("FOLIO", 20)), []))
        args = replace(
            args,
            archive_2026=gaps.PinnedFile(
                args.archive_2026.path, _digest(args.archive_2026.path)
            ),
        )
        with self.assertRaisesRegex(ValueError, "schema"):
            self.diagnose(args, expected_rows=1)

    def test_rejects_ambiguous_current_folio(self):
        args = self.fixture(
            [_sample(1, PIN_A, "0000000001")],
            [
                {
                    "PIN": PIN_A,
                    "FOLIO": "0000000001",
                    "STRAP": crosswalk.transform_pin(PIN_A),
                }
            ],
            [
                {"PIN": "", "FOLIO": "0000000001"},
                {"PIN": "", "FOLIO": "0000000001"},
            ],
        )
        with self.assertRaisesRegex(ValueError, "ambiguous current FOLIO"):
            self.diagnose(args, expected_rows=1)
        self.assertFalse(args.aggregate.exists())


if __name__ == "__main__":
    unittest.main()
