"""Synthetic, offline contracts for comparing the pinned NYC v61 and v62 archives.

All property rows in this test module are invented. The captured source rows remain
in Git-ignored private storage and are never imported into these tests.
"""

from __future__ import annotations

import csv
from hashlib import sha256
import json
import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import compare_nyc_adjacent_archives_v1 as comparison  # noqa: E402
import compare_nyc_archive_snapshot_v1 as prior_comparison  # noqa: E402


def _row(
    marker: str,
    *,
    sale_date: str = "2026-09-28",
    price: str = "100",
    address: str | None = None,
) -> tuple[str, ...]:
    fields = [""] * 21
    fields[0] = "2"
    fields[7] = marker
    fields[8] = address if address is not None else f"SYNTHETIC {marker} ST"
    fields[19] = price
    fields[20] = sale_date
    return tuple(fields)


def _archive_csv(rows: list[tuple[str, ...]]) -> bytes:
    reverse = tuple(
        prior_comparison.ARCHIVE_FIELDS_IN_CURRENT_ORDER.index(name)
        for name in prior_comparison.ARCHIVE_HEADER
    )
    buffer = StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(prior_comparison.ARCHIVE_HEADER)
    writer.writerows(tuple(row[index] for index in reverse) for row in rows)
    return buffer.getvalue().encode("utf-8")


def _source_manifest(version: int, body: bytes) -> bytes:
    digest = sha256(body).hexdigest()
    stage_names = (
        "list_before",
        "status_before",
        "csv",
        "status_after",
        "list_after",
    )
    requests = []
    for stage in stage_names:
        is_csv = stage == "csv"
        requests.append(
            {
                "stage": stage,
                "file": "archive.csv" if is_csv else f"{stage}.json",
                "sha256": digest if is_csv else "a" * 64,
                "bytes": len(body) if is_csv else 20,
                "url": (
                    "https://data.cityofnewyork.us/api/archival.csv"
                    f"?id=usep-8jbt&version={version}&method=export"
                    if is_csv
                    else "https://data.cityofnewyork.us/api/archival"
                    + (
                        "?id=usep-8jbt&version=1"
                        if stage in {"list_before", "list_after"}
                        else f"?id=usep-8jbt&version={version}&method=status"
                    )
                ),
            }
        )
    return json.dumps(
        {
            "protocol": (
                "nyc-ready-rolling-archive-v61-v1"
                if version == 61
                else "nyc-ready-rolling-archive-v2"
            ),
            "version": version,
            "source_snapshot_sha256": digest,
            "requests": requests,
        },
        sort_keys=True,
    ).encode("utf-8")


class AdjacentArchiveRowTests(unittest.TestCase):
    def test_duplicate_rows_are_a_multiset_and_residuals_are_symmetric(self) -> None:
        a = _row("A")
        b = _row("B")
        result = comparison.compare_archive_rows([a, a, b], [a, b, b])
        self.assertEqual(result["v61_rows"], 3)
        self.assertEqual(result["v62_rows"], 3)
        self.assertEqual(result["raw_full_row_multiset_matches"], 2)
        self.assertEqual(result["v61_raw_residual_rows"], 1)
        self.assertEqual(result["v62_raw_residual_rows"], 1)
        self.assertEqual(result["date_canonical_full_row_multiset_matches"], 2)

    def test_date_only_variants_match_only_at_date_tier(self) -> None:
        v61 = [_row("A", sale_date="09/28/2026")]
        v62 = [_row("A", sale_date="2026-09-28T00:00:00.000")]
        result = comparison.compare_archive_rows(v61, v62)
        self.assertEqual(result["raw_full_row_multiset_matches"], 0)
        self.assertEqual(result["date_canonical_full_row_multiset_matches"], 1)
        self.assertEqual(result["v61_date_residual_rows"], 0)
        self.assertEqual(result["v62_date_residual_rows"], 0)

    def test_invalid_dates_are_counted_without_date_tier_matching(self) -> None:
        invalid = _row("A", sale_date="2026-02-30")
        result = comparison.compare_archive_rows([invalid], [invalid])
        self.assertEqual(result["raw_full_row_multiset_matches"], 1)
        self.assertEqual(result["date_canonical_full_row_multiset_matches"], 0)
        self.assertEqual(result["v61_invalid_date_rows"], 1)
        self.assertEqual(result["v62_invalid_date_rows"], 1)
        self.assertEqual(result["v61_date_eligible_rows"], 0)
        self.assertEqual(result["v62_date_eligible_rows"], 0)

    def test_nondate_cell_change_is_not_a_date_only_match(self) -> None:
        result = comparison.compare_archive_rows(
            [_row("A", sale_date="09/28/2026", price="100")],
            [_row("A", sale_date="2026-09-28", price="0100")],
        )
        self.assertEqual(result["raw_full_row_multiset_matches"], 0)
        self.assertEqual(result["date_canonical_full_row_multiset_matches"], 0)

    def test_malformed_canonical_rows_fail_closed(self) -> None:
        for bad in (("short",), (*_row("A")[:-1], 12)):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    comparison.compare_archive_rows([bad], [])

    def test_public_projection_suppresses_row_values_and_small_counts(self) -> None:
        private = comparison.compare_archive_rows(
            [_row("PRIVATE", address="PRIVATE ADDRESS", price="777777")],
            [_row("PRIVATE", address="PRIVATE ADDRESS", price="777777")],
        )
        public = comparison.public_projection(private)
        encoded = json.dumps(public, sort_keys=True)
        self.assertEqual(public["v61_rows"], 1)
        self.assertEqual(public["v62_rows"], 1)
        self.assertEqual(public["raw_overlap_bucket"], "suppressed_1_to_4")
        self.assertEqual(public["date_overlap_bucket"], "suppressed_1_to_4")
        self.assertEqual(public["sale_labels_certified"], 0)
        self.assertFalse(public["historical_asof_eligible"])
        for private_value in (
            "PRIVATE ADDRESS",
            "777777",
            "PRIVATE",
            "row_sha256",
            "ordinal",
            "raw_full_row_multiset_matches",
        ):
            self.assertNotIn(private_value, encoded)

    def test_public_projection_rejects_missing_or_impossible_counters(self) -> None:
        valid = comparison.compare_archive_rows([_row("A")], [_row("A")])
        for changed in (
            {"raw_full_row_multiset_matches": -1},
            {"date_canonical_full_row_multiset_matches": 2},
            {"v61_rows": True},
        ):
            with self.subTest(changed=changed):
                with self.assertRaises(ValueError):
                    comparison.public_projection({**valid, **changed})
        with self.assertRaises(ValueError):
            comparison.public_projection({"v61_rows": 1, "v62_rows": 1})


class SourceManifestTests(unittest.TestCase):
    def test_manifest_validates_exact_version_and_csv_identity(self) -> None:
        body = _archive_csv([_row("A")])
        for version in (61, 62):
            with self.subTest(version=version):
                manifest = comparison.validate_source_manifest(
                    _source_manifest(version, body),
                    version=version,
                    expected_sha=sha256(body).hexdigest(),
                    expected_bytes=len(body),
                )
                self.assertEqual(manifest["version"], version)

    def test_manifest_rejects_wrong_version_hash_bytes_and_csv_path(self) -> None:
        body = _archive_csv([_row("A")])
        valid = json.loads(_source_manifest(61, body))
        cases = []
        for field, value in (
            ("version", 62),
            ("source_snapshot_sha256", "0" * 64),
            ("protocol", "nyc-ready-rolling-archive-v2"),
        ):
            changed = {**valid, field: value}
            cases.append(changed)
        for field, value in (
            ("bytes", len(body) + 1),
            ("sha256", "0" * 64),
            ("file", "../archive.csv"),
            ("url", "https://example.invalid/archive.csv"),
        ):
            changed = json.loads(json.dumps(valid))
            changed["requests"][2][field] = value
            cases.append(changed)
        changed = json.loads(json.dumps(valid))
        changed["requests"].append(changed["requests"][2])
        cases.append(changed)
        for malformed in cases:
            with self.subTest(malformed=malformed):
                with self.assertRaises(ValueError):
                    comparison.validate_source_manifest(
                        json.dumps(malformed).encode("utf-8"),
                        version=61,
                        expected_sha=sha256(body).hexdigest(),
                        expected_bytes=len(body),
                    )

    def test_manifest_rejects_malformed_json_and_non_object(self) -> None:
        body = _archive_csv([_row("A")])
        for malformed in (b"{broken", b"[]", b"null", b"\xff"):
            with self.subTest(malformed=malformed):
                with self.assertRaises(ValueError):
                    comparison.validate_source_manifest(
                        malformed,
                        version=61,
                        expected_sha=sha256(body).hexdigest(),
                        expected_bytes=len(body),
                    )


class OfflineRunTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.private_root = self.root / "data/raw/nyc_dof"
        self.private_root.mkdir(parents=True)
        self.v61_run = self.private_root / "ready-archive-v61-20261002T230327Z"
        self.v62_run = self.private_root / "ready-archive-v2-20261002T210520Z"
        self.v61_run.mkdir()
        self.v62_run.mkdir()
        self.v61_manifest = self.root / "runs/v61/manifest.json"
        self.v62_manifest = self.root / "runs/v62/manifest.json"
        self.v61_manifest.parent.mkdir(parents=True)
        self.v62_manifest.parent.mkdir(parents=True)
        self.environment_lock = self.root / "locks/environment.json"
        self.environment_lock.parent.mkdir(parents=True)
        self.environment_lock.write_bytes(b'{"python":"3.11"}\n')
        self.output = (
            self.private_root / "archive-adjacent-v1-20261003T010000Z-000000000001"
        )

        v61_body = _archive_csv([_row("A", address="SYNTHETIC ONLY", price="777")])
        v62_body = _archive_csv(
            [_row("A", address="SYNTHETIC ONLY", price="777"), _row("B")]
        )
        (self.v61_run / "archive.csv").write_bytes(v61_body)
        (self.v62_run / "archive.csv").write_bytes(v62_body)
        v61_manifest_body = _source_manifest(61, v61_body)
        v62_manifest_body = _source_manifest(62, v62_body)
        self.v61_manifest.write_bytes(v61_manifest_body)
        self.v62_manifest.write_bytes(v62_manifest_body)
        (self.v61_run / "manifest.json").write_bytes(v61_manifest_body)
        (self.v62_run / "manifest.json").write_bytes(v62_manifest_body)
        pinned = {
            "ROOT": self.root,
            "PRIVATE_ROOT": self.private_root,
            "V61_RUN": self.v61_run,
            "V62_RUN": self.v62_run,
            "V61_MANIFEST": self.v61_manifest,
            "V62_MANIFEST": self.v62_manifest,
            "ENVIRONMENT_LOCK": self.environment_lock,
            "V61_SHA256": sha256(v61_body).hexdigest(),
            "V62_SHA256": sha256(v62_body).hexdigest(),
            "V61_MANIFEST_SHA256": sha256(v61_manifest_body).hexdigest(),
            "V62_MANIFEST_SHA256": sha256(v62_manifest_body).hexdigest(),
            "ENVIRONMENT_LOCK_SHA256": sha256(
                self.environment_lock.read_bytes()
            ).hexdigest(),
            "V61_BYTES": len(v61_body),
            "V62_BYTES": len(v62_body),
            "V61_ROWS": 1,
            "V62_ROWS": 2,
        }
        for name, value in pinned.items():
            mocked = patch.object(comparison, name, value)
            mocked.start()
            self.addCleanup(mocked.stop)
        for mocked in (
            patch.object(comparison, "_git_state", return_value=("a" * 40, False)),
            patch.object(comparison, "_remote_tracking_commit", return_value="a" * 40),
            patch.object(
                comparison, "_code_hashes", return_value={"synthetic": "b" * 64}
            ),
            patch.object(
                comparison.subprocess,
                "run",
                return_value=SimpleNamespace(returncode=0),
            ),
            patch.object(comparison.private_review_io, "secure_directory"),
            patch.object(comparison.private_review_io, "verify_acl"),
        ):
            mocked.start()
            self.addCleanup(mocked.stop)

    def test_plan_does_not_read_source_rows(self) -> None:
        with patch.object(comparison, "_pinned_bytes") as read:
            plan = comparison.plan()
        read.assert_not_called()
        self.assertEqual(plan["v61_rows"], 1)
        self.assertEqual(plan["v62_rows"], 2)
        self.assertEqual(plan["sale_labels_certified"], 0)

    def test_compare_replay_are_create_only_offline_and_aggregate_only(self) -> None:
        scanner = comparison.scan_csv

        def scan_after_intent(body: bytes, *, source: str, expected_rows: int):
            self.assertTrue((self.output / "intent.json").is_file())
            return scanner(body, source=source, expected_rows=expected_rows)

        with patch.object(
            comparison, "scan_csv", side_effect=scan_after_intent
        ) as scan:
            public = comparison.compare(self.output)
        self.assertEqual(scan.call_count, 2)
        self.assertEqual(public["v61_rows"], 1)
        self.assertEqual(public["v62_rows"], 2)
        self.assertEqual(public["raw_overlap_bucket"], "suppressed_1_to_4")
        self.assertEqual(comparison.replay(self.output), public)
        self.assertEqual(
            {item.name for item in self.output.iterdir()},
            {"intent.json", "result.json", "public.json", "hash_manifest.json"},
        )
        self.assertNotIn("SYNTHETIC ONLY", (self.output / "result.json").read_text())
        self.assertNotIn("777", (self.output / "public.json").read_text())
        with self.assertRaises(FileExistsError):
            comparison.compare(self.output)

    def test_replay_rejects_saved_public_and_source_tampering(self) -> None:
        comparison.compare(self.output)
        public_path = self.output / "public.json"
        original = public_path.read_bytes()
        public_path.write_bytes(original.replace(b"PENDING", b"ACCEPTED"))
        with self.assertRaises(ValueError):
            comparison.replay(self.output)
        public_path.write_bytes(original)

        source = self.v61_run / "archive.csv"
        source.write_bytes(source.read_bytes() + b"\n")
        with self.assertRaises(ValueError):
            comparison.replay(self.output)

    def test_replay_requires_the_pinned_python_runtime(self) -> None:
        comparison.compare(self.output)
        with patch.object(comparison, "_PINNED_PYTHON", (3, 11, 5)):
            with self.assertRaisesRegex(ValueError, "runtime"):
                comparison.replay(self.output)

    def test_source_hash_mismatch_marks_run_incomplete_before_csv_parse(self) -> None:
        source = self.v62_run / "archive.csv"
        source.write_bytes(source.read_bytes() + b"\n")
        with patch.object(comparison, "scan_csv") as scan:
            with self.assertRaises(ValueError):
                comparison.compare(self.output)
        scan.assert_not_called()
        failure = json.loads((self.output / "failure.json").read_bytes())
        self.assertEqual(failure["status"], "incomplete")
        self.assertFalse((self.output / "public.json").exists())
        with self.assertRaises(ValueError):
            comparison.replay(self.output)

    def test_manifest_tampering_rejects_before_run_reservation(self) -> None:
        self.v61_manifest.write_bytes(b"{}")
        with patch.object(comparison, "_compute") as compute:
            with self.assertRaises(ValueError):
                comparison.compare(self.output)
        compute.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_unpushed_code_rejects_before_csv_open_or_run_reservation(self) -> None:
        with (
            patch.object(comparison, "_remote_tracking_commit", return_value="c" * 40),
            patch.object(comparison, "_compute") as compute,
        ):
            with self.assertRaisesRegex(ValueError, "push"):
                comparison.compare(self.output)
        compute.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_dirty_code_and_wrong_runtime_reject_before_run_reservation(self) -> None:
        with patch.object(comparison, "_git_state", return_value=("a" * 40, True)):
            with self.assertRaisesRegex(ValueError, "clean"):
                comparison.compare(self.output)
        self.assertFalse(self.output.exists())
        with patch.object(comparison, "_PINNED_PYTHON", (0, 0, 0)):
            with self.assertRaisesRegex(ValueError, "runtime"):
                comparison.compare(self.output)
        self.assertFalse(self.output.exists())

    def test_output_path_and_git_ignore_guards_reject_before_source_read(self) -> None:
        with patch.object(comparison, "_manifests") as manifests:
            for target in (
                self.root / self.output.name,
                self.private_root / "archive-adjacent-v1-invalid",
            ):
                with self.subTest(target=target):
                    with self.assertRaises(ValueError):
                        comparison.compare(target)
            with (
                patch.object(
                    comparison.subprocess,
                    "run",
                    return_value=SimpleNamespace(returncode=1),
                ),
                self.assertRaisesRegex(ValueError, "Git-ignored"),
            ):
                comparison.compare(self.output)
        manifests.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_replay_rejects_rehashed_intent_and_result_tampering(self) -> None:
        comparison.compare(self.output)
        intent_path = self.output / "intent.json"
        result_path = self.output / "result.json"
        hashes_path = self.output / "hash_manifest.json"
        original_intent = intent_path.read_bytes()
        original_result = result_path.read_bytes()
        original_hashes = hashes_path.read_bytes()

        changed_intent = json.loads(original_intent)
        changed_intent["code_commit"] = "c" * 40
        intent_path.write_bytes(comparison._encoded(changed_intent))
        hashes = json.loads(original_hashes)
        hashes["intent_sha256"] = sha256(intent_path.read_bytes()).hexdigest()
        hashes_path.write_bytes(comparison._encoded(hashes))
        with self.assertRaises(ValueError):
            comparison.replay(self.output)

        intent_path.write_bytes(original_intent)
        changed_result = json.loads(original_result)
        changed_result["sale_labels_certified"] = 1
        result_path.write_bytes(comparison._encoded(changed_result))
        hashes = json.loads(original_hashes)
        hashes["result_sha256"] = sha256(result_path.read_bytes()).hexdigest()
        hashes_path.write_bytes(comparison._encoded(hashes))
        with self.assertRaises(ValueError):
            comparison.replay(self.output)

    def test_replay_rejects_extra_artifact(self) -> None:
        comparison.compare(self.output)
        (self.output / "unregistered.json").write_text("{}", encoding="utf-8")
        with self.assertRaises(ValueError):
            comparison.replay(self.output)

    def test_interrupted_run_has_no_valid_result_or_exception_text(self) -> None:
        with patch.object(
            comparison, "_compute", side_effect=ValueError("PRIVATE ROW")
        ):
            with self.assertRaisesRegex(ValueError, "PRIVATE ROW"):
                comparison.compare(self.output)
        failure = json.loads((self.output / "failure.json").read_bytes())
        self.assertEqual(failure["status"], "incomplete")
        self.assertNotIn("PRIVATE ROW", json.dumps(failure))
        self.assertFalse((self.output / "result.json").exists())
        self.assertFalse((self.output / "public.json").exists())
        with self.assertRaises(ValueError):
            comparison.replay(self.output)


if __name__ == "__main__":
    unittest.main()
