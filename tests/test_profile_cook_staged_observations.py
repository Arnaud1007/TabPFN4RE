"""Synthetic tests for the private Cook source-quality runner."""

from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from hashlib import sha256
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import profile_cook_staged_observations as runner
from tests.test_cook_quality import CAPTURE_HASH, observation


def _observations():
    return (
        observation("private-row-one", doc_no="same", sale_price="7.25"),
        observation("private-row-two", doc_no="same", pin="00000000000002"),
    )


class CookQualityRunnerTests(unittest.TestCase):
    def test_build_outputs_are_deterministic_and_public_allowlisted(self) -> None:
        first = runner.build_outputs(
            _observations(), expected_rows=2, expected_capture_sha256=CAPTURE_HASH
        )
        second = runner.build_outputs(
            _observations(), expected_rows=2, expected_capture_sha256=CAPTURE_HASH
        )
        self.assertEqual(first, second)
        findings, counts = first
        self.assertEqual(len(findings.splitlines()), 2)
        self.assertNotIn(b"7.25", findings)
        self.assertNotIn(b"same", findings)
        self.assertNotIn(b"00000000000002", findings)
        summary = runner.public_summary(findings)
        self.assertEqual(set(summary), runner.PUBLIC_FIELDS)
        self.assertEqual(summary["certified_sale_labels"], 0)
        self.assertIs(summary["historical_asof_eligible"], False)
        self.assertNotIn("private-row-one", json.dumps(summary))
        self.assertNotIn("attention_count", summary)
        self.assertNotIn("counts", summary)
        self.assertNotIn("private_counts_sha256", summary)

    def test_private_runner_is_create_only_and_verifies_exact_bytes(self) -> None:
        with TemporaryDirectory() as directory:
            base = Path(directory)
            raw, public = base / "raw", base / "public"
            raw.mkdir()
            public.mkdir()
            with (
                patch.object(runner, "RAW_ROOT", raw),
                patch.object(
                    runner, "_source_observations", return_value=_observations()
                ),
                patch.object(runner, "SAMPLE_ROWS", 2),
                patch.object(runner, "CAPTURE_SHA256", CAPTURE_HASH),
                patch.object(runner.private_io, "secure_directory"),
                patch.object(runner.private_io, "verify_acl"),
            ):
                result = runner.run(public / "aggregate.json")
                self.assertEqual(result, runner.verify(raw / runner.RUN_NAME))
                self.assertEqual(set(result), runner.PUBLIC_FIELDS)
                self.assertEqual(result["sample_rows"], 2)
                self.assertNotIn(
                    "private-row-one", (public / "aggregate.json").read_text()
                )
                with self.assertRaises(FileExistsError):
                    runner.run(public / "another.json")
                self.assertFalse((public / "another.json").exists())

    def test_tampered_or_incomplete_private_run_cannot_verify(self) -> None:
        with TemporaryDirectory() as directory:
            base = Path(directory)
            raw, public = base / "raw", base / "public"
            raw.mkdir()
            public.mkdir()
            with (
                patch.object(runner, "RAW_ROOT", raw),
                patch.object(
                    runner, "_source_observations", return_value=_observations()
                ),
                patch.object(runner, "SAMPLE_ROWS", 2),
                patch.object(runner, "CAPTURE_SHA256", CAPTURE_HASH),
                patch.object(runner.private_io, "secure_directory"),
                patch.object(runner.private_io, "verify_acl"),
            ):
                runner.run(public / "aggregate.json")
                private = raw / runner.RUN_NAME
                finding_path = private / "findings.jsonl"
                original = finding_path.read_bytes()
                finding_path.write_bytes(original + b" ")
                with self.assertRaises(ValueError):
                    runner.verify(private)
                finding_path.write_bytes(original)
                (private / "complete.json").unlink()
                with self.assertRaises(ValueError):
                    runner.verify(private)

    def test_staged_hash_and_order_must_match_before_publishing(self) -> None:
        rows = _observations()
        content = b"".join(
            runner._encoded({"ordinal": index, "observation": row.to_record()})
            for index, row in enumerate(rows, start=1)
        )
        with (
            patch.object(
                runner.stage,
                "verify",
                return_value={
                    "private_observations_sha256": sha256(content).hexdigest(),
                    "sample_rows": 2,
                    "capture_manifest_sha256": CAPTURE_HASH,
                },
            ),
            patch.object(runner, "SAMPLE_ROWS", 2),
            patch.object(runner, "CAPTURE_SHA256", CAPTURE_HASH),
            patch.object(runner, "STAGED_SHA256", sha256(content).hexdigest()),
            patch.object(runner.review, "_bounded", return_value=content),
            patch.object(runner.private_io, "private_path", return_value=Path("x")),
            patch.object(runner.private_io, "verify_acl"),
        ):
            self.assertEqual(runner._source_observations(), rows)
        for tampered in (
            content + b"\n",
            content.replace(b'"ordinal": 1', b'"ordinal": 2', 1),
        ):
            with self.subTest(tampered=tampered[:50]):
                with (
                    patch.object(
                        runner.stage,
                        "verify",
                        return_value={
                            "private_observations_sha256": sha256(content).hexdigest(),
                            "sample_rows": 2,
                            "capture_manifest_sha256": CAPTURE_HASH,
                        },
                    ),
                    patch.object(runner, "SAMPLE_ROWS", 2),
                    patch.object(runner, "CAPTURE_SHA256", CAPTURE_HASH),
                    patch.object(runner, "STAGED_SHA256", sha256(content).hexdigest()),
                    patch.object(runner.review, "_bounded", return_value=tampered),
                    patch.object(
                        runner.private_io, "private_path", return_value=Path("x")
                    ),
                    patch.object(runner.private_io, "verify_acl"),
                ):
                    with self.assertRaises(ValueError):
                        runner._source_observations()

    def test_cli_has_generic_failure_and_only_public_success(self) -> None:
        findings, counts = runner.build_outputs(
            _observations(), expected_rows=2, expected_capture_sha256=CAPTURE_HASH
        )
        summary = runner.public_summary(findings)
        stdout, stderr = io.StringIO(), io.StringIO()
        with (
            patch.object(runner, "run", return_value=summary),
            redirect_stdout(stdout),
        ):
            self.assertEqual(runner.main(["run", "--output", "result.json"]), 0)
        self.assertEqual(json.loads(stdout.getvalue()), summary)
        with (
            patch.object(runner, "verify", side_effect=ValueError("private PIN")),
            redirect_stderr(stderr),
        ):
            self.assertEqual(runner.main(["verify", "--run-dir", "run"]), 1)
        self.assertNotIn("PIN", stderr.getvalue())

    def test_public_hash_binds_findings_without_exposing_count_hash(self) -> None:
        findings, counts = runner.build_outputs(
            _observations(), expected_rows=2, expected_capture_sha256=CAPTURE_HASH
        )
        summary = runner.public_summary(findings)
        self.assertEqual(
            summary["private_findings_sha256"], sha256(findings).hexdigest()
        )
        self.assertNotIn("private_counts_sha256", summary)
        self.assertEqual(
            runner._complete(findings, counts)["counts_sha256"],
            sha256(counts).hexdigest(),
        )


if __name__ == "__main__":
    unittest.main()
