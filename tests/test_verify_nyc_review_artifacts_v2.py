"""Synthetic lifecycle tests for the create-only NYC verified-export pilot."""

from __future__ import annotations

import json
import io
import os
import subprocess
import sys
import tempfile
import unittest
from hashlib import sha256
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import verify_nyc_review_artifacts_v2 as runner  # noqa: E402


def synthetic_row(code, block):
    values = [""] * 21
    values[0], values[4], values[5] = code, str(block), "1"
    values[19], values[20] = "750000", "09/15/2025"
    return tuple(values)


class PilotRunnerTest(unittest.TestCase):
    def setUp(self):
        self.real_preflight = runner._preflight
        self.real_environment_sha = runner._environment_sha
        self.real_code_hashes = runner._code_hashes
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "raw" / "nyc_dof"
        self.root.mkdir(parents=True)
        if os.name != "nt":
            self.root.chmod(0o700)
        self.run = self.root / "verified-export-pilot-v1-20260930T180000Z-a1b2c3d4e5f6"
        self.inputs = {
            "capture_manifest_sha256": "a" * 64,
            "csv_snapshot_sha256": "b" * 64,
            "v3_result_sha256": "c" * 64,
            "csv_manifest": {"rows": 82345},
            "borough_entries": {"Bronx": {"sha256": "g" * 64}},
            "v3_status": {},
        }
        self.private = {
            "protocol": runner.PROTOCOL,
            "pilot_ordinals": list(range(1, 11)),
            "rows": [
                {
                    "ordinal": i,
                    "borough": "Bronx",
                    "status": "unmatched",
                    "workbook_row_number": None,
                    "difference_positions": [],
                    "csv_source_sha256": "b" * 64,
                    "workbook_source_sha256": "g" * 64,
                }
                for i in range(1, 11)
            ],
            "sample_sha256": runner.SAMPLE_SHA256,
            "capture_manifest_sha256": "a" * 64,
            "csv_snapshot_sha256": "b" * 64,
            "v3_result_sha256": "c" * 64,
            "label_status": "unqualified",
            "sale_labels_certified": 0,
        }
        patches = (
            patch.object(runner, "PRIVATE_ROOT", self.root),
            patch.object(runner, "_preflight", return_value=self.inputs),
            patch.object(
                runner,
                "_provenance",
                return_value={"code_commit": "d" * 40, "dirty_tree": False},
            ),
            patch.object(runner, "_remote_pushed", return_value=True),
            patch.object(runner, "_code_hashes", return_value={"test.py": "e" * 64}),
            patch.object(runner, "_environment_sha", return_value="f" * 64),
            patch.object(runner, "secure_directory", side_effect=self._secure),
            patch.object(runner, "verify_acl", side_effect=self._acl),
            patch.object(runner, "_check_ancestors", return_value=None),
        )
        for item in patches:
            item.start()
            self.addCleanup(item.stop)

    @staticmethod
    def _secure(path):
        if os.name != "nt":
            path.chmod(0o700)

    @staticmethod
    def _acl(path):
        if os.name != "nt" and path.stat().st_mode & 0o077:
            raise ValueError("ACL invalid")

    def test_intent_exists_before_sample_and_source_aggregate(self):
        def aggregate(inputs):
            self.assertTrue((self.run / "intent.json").is_file())
            self.assertEqual(
                json.loads((self.run / "intent.json").read_bytes())["run_id"],
                self.run.name,
            )
            return self.private

        with patch.object(runner, "_aggregate", side_effect=aggregate):
            public = runner.analyze(self.run)
        self.assertEqual(public, runner.public_projection())
        self.assertEqual(
            {x.name for x in self.run.iterdir()},
            {"intent.json", "result.json", "public.json", "hash_manifest.json"},
        )

    def test_no_overwrite_and_byte_identical_replay(self):
        with patch.object(runner, "_aggregate", return_value=self.private):
            runner.analyze(self.run)
            first = {x.name: x.read_bytes() for x in self.run.iterdir()}
            with self.assertRaises(FileExistsError):
                runner.analyze(self.run)
            self.assertEqual(runner.replay(self.run), runner.public_projection())
            self.assertEqual(
                first, {x.name: x.read_bytes() for x in self.run.iterdir()}
            )

    def test_incomplete_run_never_replays(self):
        with patch.object(
            runner, "_aggregate", side_effect=ValueError("synthetic failure")
        ):
            with self.assertRaises(ValueError):
                runner.analyze(self.run)
        self.assertTrue((self.run / "intent.json").exists())
        self.assertTrue((self.run / "failure.json").exists())
        with self.assertRaises(ValueError):
            runner.replay(self.run)

    def test_interruption_or_timeout_is_marked_incomplete(self):
        for error, category in (
            (KeyboardInterrupt(), "interrupted"),
            (TimeoutError(), "timeout"),
        ):
            target = (
                self.run
                if category == "interrupted"
                else self.root
                / "verified-export-pilot-v1-20260930T180001Z-a1b2c3d4e5f6"
            )
            with patch.object(runner, "_aggregate", side_effect=error):
                with self.assertRaises(type(error)):
                    runner.analyze(target)
            self.assertEqual(
                json.loads((target / "failure.json").read_bytes())["category"], category
            )
            with self.assertRaises(ValueError):
                runner.replay(target)

    def test_public_is_fixed_private_only_and_zero_labels(self):
        first = runner.public_projection()
        self.assertEqual(first["sale_labels_certified"], 0)
        self.assertEqual(
            [item["borough"] for item in first["boroughs"]],
            ["Bronx", "Brooklyn", "Queens", "Staten Island"],
        )
        serialized = json.dumps(first)
        for forbidden in (
            "ordinal",
            "count",
            "status_counts",
            "difference_positions",
            "750000",
        ):
            self.assertNotIn(forbidden, serialized)
        self.assertTrue(all(item["findings"] is None for item in first["boroughs"]))

    def test_dirty_or_unpushed_code_blocks_before_new_run(self):
        with patch.object(
            runner,
            "_provenance",
            return_value={"code_commit": "d" * 40, "dirty_tree": True},
        ):
            with self.assertRaises(ValueError):
                runner.analyze(self.run)
        with patch.object(runner, "_remote_pushed", return_value=False):
            with self.assertRaises(ValueError):
                runner.analyze(self.run)
        self.assertFalse(self.run.exists())

    def test_wrong_run_path_rejected(self):
        for target in (self.root / "elsewhere", self.root.parent / self.run.name):
            with self.assertRaises(ValueError):
                runner.analyze(target)

    def test_private_sample_hash_count_duplicates_and_link_guard(self):
        sample = self.root / "synthetic-sample.jsonl"
        body = b"".join(
            json.dumps({"ordinal": i}).encode() + b"\n" for i in range(1, 201)
        )
        sample.write_bytes(body)
        with (
            patch.object(runner, "SAMPLE_PATH", sample),
            patch.object(runner, "SAMPLE_SHA256", sha256(body).hexdigest()),
        ):
            self.assertEqual(runner._read_sample(), set(range(1, 201)))
            sample.write_bytes(body.replace(b'"ordinal": 200', b'"ordinal": 199'))
            with self.assertRaises(ValueError):
                runner._read_sample()
            sample.write_bytes(body)
            companion = self.root / "sample-link.jsonl"
            os.link(sample, companion)
            with self.assertRaises(ValueError):
                runner._read_sample()

    def test_wrong_sample_count_rejected_with_matching_hash(self):
        sample = self.root / "synthetic-short.jsonl"
        body = b'{"ordinal": 1}\n'
        sample.write_bytes(body)
        with (
            patch.object(runner, "SAMPLE_PATH", sample),
            patch.object(runner, "SAMPLE_SHA256", sha256(body).hexdigest()),
        ):
            with self.assertRaises(ValueError):
                runner._read_sample()

    def test_preflight_rejects_wrong_source_hash_and_date_system(self):
        valid = {
            **self.inputs,
            "csv_snapshot_sha256": runner.v1.profile.APPROVED_SNAPSHOT_SHA256,
            "capture_manifest_sha256": runner.v1.CAPTURE_MANIFEST_SHA,
            "v3_result_sha256": runner.v1.V3_ARTIFACT_SHA["result.json"],
        }
        status = {
            name: {"date_system": "1900_default"} for name, _, _ in runner.SELECTED
        }
        with (
            patch.object(runner.v1, "_preflight", return_value=valid),
            patch.object(runner.v1, "_verify_v3", return_value=status),
        ):
            self.assertEqual(self.real_preflight()["v3_status"], status)
            with patch.object(
                runner.v1,
                "_preflight",
                return_value={**valid, "csv_snapshot_sha256": "wrong"},
            ):
                with self.assertRaises(ValueError):
                    self.real_preflight()
            bad = {**status, "Bronx": {"date_system": "1904"}}
            with patch.object(runner.v1, "_verify_v3", return_value=bad):
                with self.assertRaises(ValueError):
                    self.real_preflight()

    def test_workbook_scanner_failure_is_not_valid_result(self):
        mapping = {i: "2" for i in range(1, 201)}
        with (
            patch.object(runner, "_read_sample", return_value=set(mapping)),
            patch.object(runner, "_sample_boroughs", return_value=mapping),
            patch.object(runner.core, "select_pilot", return_value=tuple(range(1, 11))),
            patch.object(runner.v1, "_csv_rows", return_value=[]),
            patch.object(runner.v1, "_xlsx_rows", side_effect=ValueError("formula")),
        ):
            with self.assertRaises(ValueError):
                runner._aggregate(self.inputs)

    def test_acl_and_reparse_rejected_before_new_run(self):
        with patch.object(runner, "verify_acl", side_effect=ValueError("ACL invalid")):
            with self.assertRaises(ValueError):
                runner.analyze(self.run)
        self.assertFalse(self.run.exists())
        with patch.object(runner.v1.earlier, "_reparse", return_value=True):
            with self.assertRaises(FileExistsError):
                runner.analyze(self.run)
        self.assertFalse(self.run.exists())

    def test_private_result_rejects_extra_source_values(self):
        bad = {
            **self.private,
            "rows": [
                {**self.private["rows"][0], "sale_price": "750000"},
                *self.private["rows"][1:],
            ],
        }
        with patch.object(runner, "_aggregate", return_value=bad):
            with self.assertRaises(ValueError):
                runner.analyze(self.run)
        self.assertTrue((self.run / "failure.json").exists())

    def test_replay_rejects_mutated_saved_result(self):
        with patch.object(runner, "_aggregate", return_value=self.private):
            runner.analyze(self.run)
            result = self.run / "result.json"
            result.write_bytes(result.read_bytes() + b" ")
            with self.assertRaises(ValueError):
                runner.replay(self.run)

    def test_full_aggregate_on_synthetic_borough_rows(self):
        selected = (1, 2, 3, 51, 52, 101, 102, 151, 152, 153)
        mapping = {i: str(2 + (i - 1) // 50) for i in range(1, 201)}
        frames = {
            code: [
                (ordinal, synthetic_row(code, ordinal))
                for ordinal in selected
                if mapping[ordinal] == code
            ]
            for code in "2345"
        }
        chosen_frame = tuple(
            (name, code, len(frames[code])) for name, code, _ in runner.SELECTED
        )
        inputs = {
            **self.inputs,
            "borough_entries": {
                name: {"sha256": chr(95 + int(code)) * 64}
                for name, code, _ in runner.SELECTED
            },
        }
        with (
            patch.object(runner, "SELECTED", chosen_frame),
            patch.object(runner, "_read_sample", return_value=set(mapping)),
            patch.object(runner, "_sample_boroughs", return_value=mapping),
            patch.object(runner.core, "select_pilot", return_value=selected),
            patch.object(
                runner.v1,
                "_csv_rows",
                side_effect=lambda inputs, code, timer, start: frames[code],
            ),
            patch.object(
                runner.v1,
                "_xlsx_rows",
                side_effect=lambda inputs, name, code, timer, start: [
                    (1000 + ordinal, values) for ordinal, values in frames[code]
                ],
            ),
        ):
            result = runner._aggregate(inputs)
        self.assertEqual(len(result["rows"]), 10)
        self.assertEqual(result["pilot_ordinals"], list(selected))
        self.assertTrue(
            all(item["status"] == "raw_full_21_concordance" for item in result["rows"])
        )
        runner._validate_private(result, inputs)

    def test_sample_borough_scan_requires_full_counts_and_sample_membership(self):
        expected = {"1": 1, "2": 2, "3": 1, "4": 1, "5": 1, "unknown": 0}
        records = ["1", "2", "2", "3", "4", "5"]
        inputs = {
            "csv_manifest": {
                "raw_filename": "synthetic.csv",
                "rows": 6,
                "bytes": 10,
                "sha256": "a" * 64,
            }
        }
        sample = {1, 2, 4, 5, 6}

        def checked(path, size, digest, scan, timer, start):
            return scan(io.BytesIO())

        def scanner(handle, expected_rows, receive, **kwargs):
            for i, code in enumerate(records, 1):
                receive(i, (code,))
            return {"rows": len(records)}

        with (
            patch.object(runner.v1, "CSV_COUNTS", expected),
            patch.object(runner.v1, "_checked_scan", side_effect=checked),
            patch.object(runner.v1.scanner, "scan_pinned_csv", side_effect=scanner),
        ):
            self.assertEqual(
                runner._sample_boroughs(inputs, sample, lambda: 0, 0),
                {1: "1", 2: "2", 4: "3", 5: "4", 6: "5"},
            )
            with self.assertRaises(ValueError):
                runner._sample_boroughs(inputs, sample | {7}, lambda: 0, 0)
            records.pop()
            with self.assertRaises(ValueError):
                runner._sample_boroughs(inputs, sample, lambda: 0, 0)

    def test_environment_lock_and_code_hashes_validate(self):
        lock = {
            "schema_version": 1,
            "sample_sha256": runner.SAMPLE_SHA256,
            "csv_snapshot_sha256": runner.v1.profile.APPROVED_SNAPSHOT_SHA256,
            "capture_manifest_sha256": runner.v1.CAPTURE_MANIFEST_SHA,
            "v3_result_sha256": runner.v1.V3_ARTIFACT_SHA["result.json"],
        }
        body = runner._json_bytes(lock)
        with patch.object(runner, "_pinned_bytes", return_value=body):
            self.assertEqual(self.real_environment_sha(), sha256(body).hexdigest())
            self.assertIn(
                "scripts/nyc_verified_export_core.py", self.real_code_hashes()
            )
        with patch.object(
            runner,
            "_pinned_bytes",
            return_value=runner._json_bytes({**lock, "sample_sha256": "wrong"}),
        ):
            with self.assertRaises(ValueError):
                self.real_environment_sha()

    def test_replay_rejects_tampered_hash_manifest_and_extra_file(self):
        with patch.object(runner, "_aggregate", return_value=self.private):
            runner.analyze(self.run)
            (self.run / "extra.json").write_text("{}")
            with self.assertRaises(ValueError):
                runner.replay(self.run)
            (self.run / "extra.json").unlink()
            path = self.run / "hash_manifest.json"
            manifest = json.loads(path.read_bytes())
            path.write_bytes(
                runner._json_bytes({**manifest, "result_sha256": "0" * 64})
            )
            with self.assertRaises(ValueError):
                runner.replay(self.run)

    def test_plan_cli_has_no_private_read(self):
        output = io.StringIO()
        with patch.object(sys, "argv", ["pilot", "plan"]), redirect_stdout(output):
            runner.main()
        self.assertEqual(json.loads(output.getvalue()), runner.plan())

    def test_cli_git_timeout_has_generic_error(self):
        error_output = io.StringIO()
        with (
            patch.object(sys, "argv", ["pilot", "analyze", str(self.run)]),
            patch.object(
                runner, "_preflight", side_effect=subprocess.TimeoutExpired("git", 10)
            ),
            redirect_stderr(error_output),
            self.assertRaises(SystemExit) as observed,
        ):
            runner.main()
        self.assertEqual(observed.exception.code, 2)
        self.assertEqual(
            error_output.getvalue(),
            "NYC verified-export pilot failed: TimeoutExpired\n",
        )
        self.assertFalse(self.run.exists())

    def test_private_validator_rejects_bad_positions_and_incomplete_rows(self):
        bad_row = {
            **self.private["rows"][0],
            "status": "unique_candidate_with_field_disagreement",
            "workbook_row_number": 101,
            "difference_positions": [20],
        }
        for bad in (
            {**self.private, "rows": self.private["rows"][:9]},
            {**self.private, "rows": [bad_row, *self.private["rows"][1:]]},
            {
                **self.private,
                "rows": [
                    {
                        **self.private["rows"][0],
                        "workbook_row_number": "PRIVATE ADDRESS",
                    },
                    *self.private["rows"][1:],
                ],
            },
            {
                **self.private,
                "rows": [
                    {**self.private["rows"][0], "borough": ["Bronx"]},
                    *self.private["rows"][1:],
                ],
            },
            {
                **self.private,
                "rows": [
                    {**self.private["rows"][0], "status": ["unmatched"]},
                    *self.private["rows"][1:],
                ],
            },
            {**self.private, "sale_labels_certified": False},
        ):
            with self.assertRaises(ValueError):
                runner._validate_private(bad, self.inputs)


if __name__ == "__main__":
    unittest.main()
