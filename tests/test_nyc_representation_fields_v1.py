"""Synthetic acceptance tests for the protected NYC v2 field diagnostic."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import diagnose_nyc_representation_fields_v1 as runner  # noqa: E402
import diagnose_nyc_representations_v2 as v2  # noqa: E402
import nyc_representation_core as core  # noqa: E402

SELECTED = (("Bronx", "2"), ("Brooklyn", "3"), ("Queens", "4"), ("Staten Island", "5"))


def sale(
    borough: str,
    block: int,
    *,
    date: str,
    building_class: str = "A1",
    address: str = "SYNTHETIC PRIVATE STREET",
):
    values = [""] * 21
    values[0] = borough
    values[4] = str(block)
    values[5] = "1"
    values[8] = address
    values[18] = building_class
    values[19] = "750000"
    values[20] = date
    return tuple(values)


def borough_result(
    name: str,
    code: str,
    *,
    total: int = 105,
    mismatches: int = 0,
    class_start: int = 1,
    address_mismatches: int = 0,
):
    csv = [
        (index, sale(code, index, date="09/15/2025")) for index in range(1, total + 1)
    ]
    xlsx = [
        (
            10_000 + index,
            sale(
                code,
                index,
                date="2025-09-15",
                building_class=(
                    "B2" if class_start <= index < class_start + mismatches else "A1"
                ),
                address=(
                    "SYNTHETIC DIFFERENT STREET"
                    if index <= address_mismatches
                    else "SYNTHETIC PRIVATE STREET"
                ),
            ),
        )
        for index in range(1, total + 1)
    ]
    return core.analyze_borough(
        csv, xlsx, borough=name, borough_code=code, date_system="1900_default"
    )


def v2_fixture(*, total: int = 105, mismatches: int = 0):
    boroughs = [
        borough_result(name, code, total=total, mismatches=mismatches)
        for name, code in SELECTED
    ]
    private = {
        "protocol": v2.PROTOCOL,
        "capture_manifest_sha256": v2.v1.CAPTURE_MANIFEST_SHA,
        "csv_snapshot_sha256": v2.v1.profile.APPROVED_SNAPSHOT_SHA256,
        "v3_result_sha256": v2.v1.V3_ARTIFACT_SHA["result.json"],
        "v1_result_sha256": v2.V1_ARTIFACT_SHA["result.json"],
        "csv_source_rows": total * 4,
        "excluded_manhattan_csv_rows": 0,
        "csv_frame_rows": total * 4,
        "xlsx_frame_rows": total * 4,
        "boroughs": boroughs,
        "label_status": "unqualified",
        "sale_labels_certified": 0,
    }
    public = v2._public_projection(private)
    old_public = {
        "boroughs": [
            {
                "borough": name,
                "csv_rows": total,
                "xlsx_rows": total,
                "counts": None if name == "Staten Island" else {"unique_key_pairs": 0},
            }
            for name, _ in SELECTED
        ]
    }
    return private, public, old_public


class FieldExtractionTest(unittest.TestCase):
    def setUp(self):
        patched = patch.object(
            runner, "SELECTED", tuple((name, code, 105) for name, code in SELECTED)
        )
        patched.start()
        self.addCleanup(patched.stop)

    def test_extracts_only_fixed_aggregate_families_and_ranks_privately(self):
        private, _, _ = v2_fixture(mismatches=100)
        result = runner._derive(private)
        bronx = result["boroughs"][0]
        source = private["boroughs"][0]
        self.assertEqual(bronx["borough"], "Bronx")
        self.assertEqual(bronx["isolated_pairs"], 105)
        self.assertEqual(bronx["fields"], source["counts"]["fields"])
        self.assertEqual(bronx["overlap"], source["counts"]["overlap"])
        self.assertEqual(bronx["parse_failures"], source["counts"]["parse_failures"])
        self.assertEqual(bronx["lexical_forms"], source["counts"]["lexical_forms"])
        self.assertEqual(bronx["ranked_columns"][0]["header"], "SALE DATE")
        self.assertEqual(bronx["ranked_columns"][0]["count"], 105)
        self.assertEqual(
            bronx["ranked_columns"][1]["header"], "BUILDING CLASS AT TIME OF SALE"
        )
        self.assertEqual(bronx["ranked_columns"][1]["count"], 100)
        serialized = json.dumps(result)
        for forbidden in (
            "ledger",
            "ordinal",
            "row_sha256",
            "key_sha256",
            "SYNTHETIC PRIVATE STREET",
        ):
            self.assertNotIn(forbidden, serialized)
        self.assertEqual(result["sale_labels_certified"], 0)

    def test_partitions_and_index_bounds_reject_tampering(self):
        private, _, _ = v2_fixture()
        for mutation in (
            lambda item: item["counts"]["fields"].__setitem__("other_19_mismatches", 1),
            lambda item: item["counts"]["fields"]["column_disagreements"].__setitem__(
                18, 106
            ),
            lambda item: item["counts"]["fields"]["column_disagreements"].__setitem__(
                18, 1
            ),
            lambda item: item["counts"]["fields"]["column_disagreements"].__setitem__(
                7, 1
            ),
            lambda item: item["counts"]["statuses"].__setitem__(
                "xlsx_isolated_candidate", 104
            ),
            lambda item: item["counts"]["fields"].__setitem__(
                "canonical_date_unparseable", True
            ),
        ):
            with self.subTest(mutation=mutation):
                changed = copy.deepcopy(private)
                mutation(changed["boroughs"][0])
                with self.assertRaises(ValueError):
                    runner._derive(changed)

    def test_typed_pair_parse_failure_is_not_source_failure(self):
        private, _, _ = v2_fixture()
        result = runner._derive(private)
        bronx = result["boroughs"][0]
        self.assertEqual(bronx["fields"]["canonical_date_unparseable"], 0)
        self.assertEqual(bronx["parse_failures"]["csv_date"], 0)
        self.assertEqual(bronx["csv_rows"], 105)
        self.assertEqual(bronx["isolated_pairs"], 105)

    def test_rejects_extra_borough_or_wrong_frame_and_never_certifies_labels(self):
        private, _, _ = v2_fixture()
        for mutation in (
            lambda item: item["boroughs"].pop(),
            lambda item: item.__setitem__("csv_frame_rows", 419),
            lambda item: item.__setitem__("sale_labels_certified", 1),
            lambda item: item["boroughs"][0].__setitem__("borough", "Manhattan"),
        ):
            with self.subTest(mutation=mutation):
                changed = copy.deepcopy(private)
                mutation(changed)
                with self.assertRaises(ValueError):
                    runner._derive(changed)


class PrivateOnlyPublicationTest(unittest.TestCase):
    def projection(self, *, total=310, mismatches=0, old_count=0):
        private, public, old = v2_fixture(total=total, mismatches=mismatches)
        old["boroughs"][0]["counts"]["unique_key_pairs"] = old_count
        with patch.object(
            runner, "SELECTED", tuple((name, code, total) for name, code in SELECTED)
        ):
            derived = runner._derive(private)
        return derived, runner._public_projection(derived, public, old)

    def test_very_different_private_aggregates_have_identical_public_output(self):
        variants = (
            (105, 0, 0),
            (310, 199, 0),
            (310, 200, 199),
            (310, 306, 204),
        )
        public_bytes = [
            v2._json_bytes(
                self.projection(
                    total=total, mismatches=mismatches, old_count=old_count
                )[1]
            )
            for total, mismatches, old_count in variants
        ]
        self.assertEqual(len(set(public_bytes)), 1)

    def test_all_boroughs_have_fixed_private_only_status(self):
        _, public = self.projection(total=310, mismatches=200)
        self.assertEqual(
            [item["borough"] for item in public["boroughs"]],
            [name for name, _ in SELECTED],
        )
        for item in public["boroughs"]:
            with self.subTest(borough=item["borough"]):
                self.assertEqual(
                    item,
                    {
                        "borough": item["borough"],
                        "flags": None,
                        "disagreement_headers": None,
                        "suppression_reason": "private_only_v1",
                    },
                )

    def test_private_field_names_counts_and_source_totals_are_never_public(self):
        private, public = self.projection(total=310, mismatches=200)
        self.assertEqual(private["boroughs"][0]["fields"]["other_19_mismatches"], 200)
        self.assertEqual(
            private["boroughs"][0]["ranked_columns"][0]["header"], "SALE DATE"
        )
        serialized = json.dumps(public)
        for forbidden in (
            "SALE DATE",
            "BUILDING CLASS AT TIME OF SALE",
            "SYNTHETIC PRIVATE STREET",
            '"fields"',
            '"overlap"',
            '"parse_failures"',
            '"lexical_forms"',
            '"ranked_columns"',
            '"ledger"',
            '"csv_rows"',
            '"xlsx_rows"',
            '"isolated_pairs"',
            '"column_disagreements"',
        ):
            self.assertNotIn(forbidden, serialized)

    def test_staten_island_never_releases_breakdown(self):
        _, projected = self.projection(mismatches=200)
        staten = projected["boroughs"][3]
        self.assertEqual(staten["borough"], "Staten Island")
        self.assertEqual(staten["suppression_reason"], "private_only_v1")
        self.assertIsNone(staten["flags"])
        self.assertIsNone(staten["disagreement_headers"])
        self.assertNotIn("310", json.dumps(staten))

    def test_private_column_rank_is_not_public(self):
        private, _, old = v2_fixture(total=310)
        private["boroughs"][0] = borough_result(
            "Bronx",
            "2",
            total=310,
            mismatches=201,
            class_start=105,
            address_mismatches=200,
        )
        public = v2._public_projection(private)
        with patch.object(
            runner, "SELECTED", tuple((name, code, 310) for name, code in SELECTED)
        ):
            derived = runner._derive(private)
        self.assertEqual(derived["boroughs"][0]["fields"]["other_19_mismatches"], 305)
        projection = runner._public_projection(derived, public, old)
        self.assertIsNone(projection["boroughs"][0]["disagreement_headers"])
        self.assertNotIn("ADDRESS", json.dumps(projection))
        self.assertNotIn("SALE DATE", json.dumps(projection))


class PinnedV2IntegrityTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.pinned = (
            self.root / "representation-diagnostic-v2-20260930T152830Z-460cba306f9d"
        )
        self.pinned.mkdir()
        self.tracked = self.root / "tracked-v2-public.json"
        private, public, _ = v2_fixture()
        self.private = private
        self.public = public
        intent = {
            "protocol": v2.PROTOCOL,
            "run_id": self.pinned.name,
            "code_commit": "cbbc14e3f3351b75a32956e4841f219fba314745",
            "dirty_tree": False,
            "capture_manifest_sha256": private["capture_manifest_sha256"],
            "csv_snapshot_sha256": private["csv_snapshot_sha256"],
            "v3_result_sha256": private["v3_result_sha256"],
            "v1_result_sha256": private["v1_result_sha256"],
        }
        bodies = {
            "intent.json": v2._json_bytes(intent),
            "result.json": v2._json_bytes(private),
            "public.json": v2._json_bytes(public),
        }
        bodies["hash_manifest.json"] = v2._json_bytes(
            v2._hash_manifest(
                self.pinned,
                bodies["intent.json"],
                bodies["result.json"],
                bodies["public.json"],
            )
        )
        self.expected = {
            name: hashlib.sha256(body).hexdigest() for name, body in bodies.items()
        }
        for name, body in bodies.items():
            (self.pinned / name).write_bytes(body)
        self.tracked.write_bytes(bodies["public.json"])
        for patched in (
            patch.object(runner, "V2_DIR", self.pinned),
            patch.object(runner, "PRIVATE_ROOT", self.root),
            patch.object(runner, "V2_ARTIFACT_SHA", self.expected),
            patch.object(runner, "TRACKED_V2_PUBLIC", self.tracked),
            patch.object(
                runner,
                "SELECTED",
                tuple((name, code, 105) for name, code in SELECTED),
            ),
            patch.object(runner, "verify_acl"),
        ):
            patched.start()
            self.addCleanup(patched.stop)

    def test_accepts_four_pinned_artifacts_without_source_scanners(self):
        with (
            patch.object(v2.v1, "_csv_rows", side_effect=AssertionError("source read")),
            patch.object(
                v2.v1, "_xlsx_rows", side_effect=AssertionError("source read")
            ),
        ):
            private, public = runner._verify_v2()
        self.assertEqual(
            private["boroughs"][0]["counts"]["statuses"]["csv_isolated_candidate"], 105
        )
        self.assertEqual(public, self.public)

    def test_rejects_unexpected_inventory_and_digest_drift(self):
        (self.pinned / "extra.json").write_text("{}", encoding="utf-8")
        with self.assertRaises(ValueError):
            runner._verify_v2()
        (self.pinned / "extra.json").unlink()
        (self.pinned / "result.json").write_bytes(
            (self.pinned / "result.json").read_bytes() + b" "
        )
        with self.assertRaises(ValueError):
            runner._verify_v2()

    def test_rejects_noncanonical_json_even_with_updated_digest(self):
        body = (self.pinned / "intent.json").read_bytes() + b" "
        (self.pinned / "intent.json").write_bytes(body)
        self.expected["intent.json"] = hashlib.sha256(body).hexdigest()
        with self.assertRaises(ValueError):
            runner._verify_v2()

    def test_rejects_arithmetic_tamper_even_with_updated_hashes(self):
        changed = copy.deepcopy(self.private)
        changed["boroughs"][0]["counts"]["fields"]["column_disagreements"][7] = 1
        body = v2._json_bytes(changed)
        (self.pinned / "result.json").write_bytes(body)
        self.expected["result.json"] = hashlib.sha256(body).hexdigest()
        manifest = v2._hash_manifest(
            self.pinned,
            (self.pinned / "intent.json").read_bytes(),
            body,
            (self.pinned / "public.json").read_bytes(),
        )
        manifest_body = v2._json_bytes(manifest)
        (self.pinned / "hash_manifest.json").write_bytes(manifest_body)
        self.expected["hash_manifest.json"] = hashlib.sha256(manifest_body).hexdigest()
        with self.assertRaises(ValueError):
            runner._verify_v2()

    def test_rejects_tracked_public_drift_and_acl_failure(self):
        self.tracked.write_bytes(self.tracked.read_bytes() + b" ")
        with self.assertRaises(ValueError):
            runner._verify_v2()
        self.tracked.write_bytes((self.pinned / "public.json").read_bytes())
        with patch.object(runner, "verify_acl", side_effect=ValueError("ACL")):
            with self.assertRaises(ValueError):
                runner._verify_v2()

    def test_rejects_hard_linked_and_reparse_artifacts(self):
        target = self.pinned / "result.json"
        external = self.root / "hard-link.json"
        try:
            os.link(target, external)
        except OSError:
            self.skipTest("hard links unavailable on this filesystem")
        with self.assertRaises(ValueError):
            runner._verify_v2()
        external.unlink()
        with patch.object(
            v2.v1.earlier, "_reparse", side_effect=lambda path: Path(path) == target
        ):
            with self.assertRaises(ValueError):
                runner._verify_v2()


class TrackedPreflightTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.lock = self.root / "lock.json"
        self.v1_public = self.root / "v1-public.json"
        self.v2_public = self.root / "v2-public.json"
        self.lock.write_bytes(v2._json_bytes({"synthetic": True}))
        self.v1_public.write_bytes(v2._json_bytes(self._public()))
        self.v2_public.write_bytes(v2._json_bytes(self._public()))
        self.v1_hash = hashlib.sha256(self.v1_public.read_bytes()).hexdigest()
        self.artifact_hashes = {
            **runner.V2_ARTIFACT_SHA,
            "public.json": hashlib.sha256(self.v2_public.read_bytes()).hexdigest(),
        }
        for patched in (
            patch.object(runner, "ENVIRONMENT_LOCK", self.lock),
            patch.object(runner, "V1_PUBLIC_PATH", self.v1_public),
            patch.object(runner, "TRACKED_V2_PUBLIC", self.v2_public),
            patch.object(runner, "V1_PUBLIC_SHA", self.v1_hash),
            patch.object(runner, "V2_ARTIFACT_SHA", self.artifact_hashes),
        ):
            patched.start()
            self.addCleanup(patched.stop)

    @staticmethod
    def _public():
        return {
            "boroughs": [{"borough": name} for name, _ in SELECTED],
            "sale_labels_certified": 0,
            **{name: "a" * 64 for name in runner.SOURCE_HASH_FIELDS},
        }

    def test_preflight_reads_only_tracked_metadata_and_lock(self):
        with (
            patch.object(
                runner, "_verify_v2", side_effect=AssertionError("private read")
            ),
            patch.object(v2.v1, "_csv_rows", side_effect=AssertionError("source read")),
            patch.object(
                v2.v1, "_xlsx_rows", side_effect=AssertionError("source read")
            ),
        ):
            inputs = runner._preflight()
        self.assertEqual(inputs["v1_public_sha256"], self.v1_hash)
        self.assertEqual(
            inputs["v2_public_sha256"], self.artifact_hashes["public.json"]
        )
        self.assertEqual(
            inputs["environment_lock_sha256"],
            hashlib.sha256(self.lock.read_bytes()).hexdigest(),
        )
        self.assertEqual(inputs["v1_public"], self._public())
        self.assertEqual(
            inputs["source_hashes"],
            {name: "a" * 64 for name in runner.SOURCE_HASH_FIELDS},
        )

    def test_preflight_rejects_digest_schema_and_label_drift(self):
        self.v1_public.write_bytes(self.v1_public.read_bytes() + b" ")
        with self.assertRaises(ValueError):
            runner._preflight()
        self.v1_public.write_bytes(v2._json_bytes(self._public()))

        reversed_public = self._public()
        reversed_public["boroughs"].reverse()
        self.v1_public.write_bytes(v2._json_bytes(reversed_public))
        with patch.object(
            runner,
            "V1_PUBLIC_SHA",
            hashlib.sha256(self.v1_public.read_bytes()).hexdigest(),
        ):
            with self.assertRaises(ValueError):
                runner._preflight()
        self.v1_public.write_bytes(v2._json_bytes(self._public()))

        labelled = self._public()
        labelled["sale_labels_certified"] = 1
        self.v2_public.write_bytes(v2._json_bytes(labelled))
        self.artifact_hashes["public.json"] = hashlib.sha256(
            self.v2_public.read_bytes()
        ).hexdigest()
        with self.assertRaises(ValueError):
            runner._preflight()

    def test_preflight_rejects_header_and_noncanonical_lock(self):
        with patch.object(runner, "FIELD_NAMES", ("WRONG",)):
            with self.assertRaises(ValueError):
                runner._preflight()
        self.lock.write_bytes(b"{}")
        with self.assertRaises(ValueError):
            runner._preflight()


class RemoteCommitTest(unittest.TestCase):
    def test_accepts_only_exact_current_branch_head_on_origin(self):
        commit = "a" * 40
        origin = subprocess.CompletedProcess(
            [], 0, stdout=runner.APPROVED_ORIGIN_URL + "\n"
        )
        branch = subprocess.CompletedProcess([], 0, stdout="audit/u0\n")
        matching = subprocess.CompletedProcess(
            [], 0, stdout=f"{commit}\trefs/heads/audit/u0\n"
        )
        with patch.object(
            runner.subprocess, "run", side_effect=(origin, branch, matching)
        ) as run:
            self.assertTrue(runner._remote_pushed(commit))
        self.assertEqual(run.call_count, 3)

    def test_rejects_invalid_branch_remote_failure_and_wrong_head(self):
        commit = "a" * 40
        changed_origin = subprocess.CompletedProcess(
            [], 0, stdout="https://github.com/other/repo.git\n"
        )
        with patch.object(runner.subprocess, "run", return_value=changed_origin) as run:
            self.assertFalse(runner._remote_pushed(commit))
        self.assertEqual(run.call_count, 1)

        origin = subprocess.CompletedProcess(
            [], 0, stdout=runner.APPROVED_ORIGIN_URL + "\n"
        )
        invalid = subprocess.CompletedProcess([], 0, stdout="bad branch!\n")
        with patch.object(
            runner.subprocess, "run", side_effect=(origin, invalid)
        ) as run:
            self.assertFalse(runner._remote_pushed(commit))
        self.assertEqual(run.call_count, 2)

        branch = subprocess.CompletedProcess([], 0, stdout="audit/u0\n")
        failed = subprocess.CompletedProcess([], 1, stdout="")
        wrong = subprocess.CompletedProcess(
            [], 0, stdout=f"{'b' * 40}\trefs/heads/audit/u0\n"
        )
        for remote in (failed, wrong):
            with self.subTest(remote=remote):
                with patch.object(
                    runner.subprocess, "run", side_effect=(origin, branch, remote)
                ):
                    self.assertFalse(runner._remote_pushed(commit))


class FieldRunnerTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "nyc_dof"
        self.root.mkdir()
        self.output = self.root / "field-diagnostic-v1-20260930T160000Z-000000000001"
        self.lock = self.root / "environment-lock.json"
        self.lock.write_bytes(v2._json_bytes({}))
        self.private = {
            "protocol": runner.PROTOCOL,
            "boroughs": [],
            "label_status": "unqualified",
            "sale_labels_certified": 0,
        }
        self.public = {
            "protocol": runner.PROTOCOL,
            "boroughs": [],
            "label_status": "unqualified",
            "sale_labels_certified": 0,
        }
        self.inputs = {
            "v2_result_sha256": "a" * 64,
            "v2_public_sha256": "b" * 64,
            "v1_public_sha256": "c" * 64,
            "v1_public": {"boroughs": []},
            "v2_public": {"boroughs": []},
            "source_hashes": {name: "a" * 64 for name in runner.SOURCE_HASH_FIELDS},
        }
        for patched in (
            patch.object(runner, "PRIVATE_ROOT", self.root),
            patch.object(runner, "ENVIRONMENT_LOCK", self.lock),
            patch.object(runner, "secure_directory"),
            patch.object(runner, "verify_acl"),
            patch.object(runner, "_preflight", side_effect=self._synthetic_preflight),
            patch.object(runner, "_aggregate", return_value=self.private),
            patch.object(runner, "_public_projection", return_value=self.public),
            patch.object(runner, "_remote_pushed", return_value=True),
            patch.object(
                runner,
                "_provenance",
                return_value={"code_commit": "e" * 40, "dirty_tree": False},
            ),
        ):
            patched.start()
            self.addCleanup(patched.stop)

    def _synthetic_preflight(self):
        if not self.lock.is_file():
            raise ValueError("Environment lock is missing")
        return {
            **self.inputs,
            "environment_lock_sha256": hashlib.sha256(
                self.lock.read_bytes()
            ).hexdigest(),
        }

    def test_plan_never_reads_protected_v2_or_original_sources(self):
        with (
            patch.object(
                runner, "_verify_v2", side_effect=AssertionError("private read")
            ),
            patch.object(v2.v1, "_csv_rows", side_effect=AssertionError("source read")),
            patch.object(
                v2.v1, "_xlsx_rows", side_effect=AssertionError("source read")
            ),
        ):
            result = runner.plan()
        self.assertEqual(result["protocol"], runner.PROTOCOL)
        self.assertEqual(result["status"], "plan_only_no_private_read")

    def test_intent_is_durable_before_first_protected_read(self):
        def after_intent(*args, **kwargs):
            intent = json.loads((self.output / "intent.json").read_bytes())
            self.assertEqual(intent["protocol"], runner.PROTOCOL)
            self.assertFalse(intent["dirty_tree"])
            self.assertEqual(
                {name: intent[name] for name in runner.SOURCE_HASH_FIELDS},
                self.inputs["source_hashes"],
            )
            return self.private

        with patch.object(runner, "_aggregate", side_effect=after_intent):
            runner.analyze(self.output)

    def test_clean_tree_and_lock_required_before_reservation(self):
        self.lock.unlink()
        with self.assertRaises(ValueError):
            runner.analyze(self.output)
        self.assertFalse(self.output.exists())
        self.lock.write_bytes(v2._json_bytes({}))
        with patch.object(
            runner,
            "_provenance",
            return_value={"code_commit": "e" * 40, "dirty_tree": True},
        ):
            with self.assertRaises(ValueError):
                runner.analyze(self.output)
        self.assertFalse(self.output.exists())

    def test_commit_must_be_pushed_before_reservation(self):
        with patch.object(runner, "_remote_pushed", return_value=False):
            with self.assertRaises(ValueError):
                runner.analyze(self.output)
        self.assertFalse(self.output.exists())

    def test_analyze_create_only_replay_and_no_source_scanners(self):
        with (
            patch.object(v2.v1, "_csv_rows", side_effect=AssertionError("source read")),
            patch.object(
                v2.v1, "_xlsx_rows", side_effect=AssertionError("source read")
            ),
        ):
            self.assertEqual(runner.analyze(self.output), self.public)
            self.assertEqual(runner.replay(self.output), self.public)
        with self.assertRaises(FileExistsError):
            runner.analyze(self.output)

    def test_interruption_is_incomplete_and_does_not_publish_result(self):
        with patch.object(runner, "_aggregate", side_effect=KeyboardInterrupt()):
            with self.assertRaises(KeyboardInterrupt):
                runner.analyze(self.output)
        self.assertEqual(
            json.loads((self.output / "failure.json").read_bytes())["status"],
            "incomplete",
        )
        self.assertFalse((self.output / "result.json").exists())
        self.assertFalse((self.output / "public.json").exists())
        with self.assertRaises(ValueError):
            runner.replay(self.output)

    def test_timeout_is_incomplete_and_private_error_text_is_not_saved(self):
        with patch.object(
            runner, "_aggregate", side_effect=TimeoutError("PRIVATE STREET")
        ):
            with self.assertRaises(TimeoutError):
                runner.analyze(self.output)
        failure = json.loads((self.output / "failure.json").read_bytes())
        self.assertEqual(failure["category"], "timeout")
        self.assertNotIn("PRIVATE STREET", json.dumps(failure))
        self.assertFalse((self.output / "public.json").exists())

    def test_replay_rejects_lock_code_and_saved_artifact_drift(self):
        runner.analyze(self.output)
        self.assertEqual(runner.replay(self.output), self.public)
        self.lock.write_bytes(v2._json_bytes({"changed": True}))
        with self.assertRaisesRegex(ValueError, "provenance differs"):
            runner.replay(self.output)
        self.lock.write_bytes(v2._json_bytes({}))
        self.assertEqual(runner.replay(self.output), self.public)

        with patch.object(runner, "_code_hashes", return_value={"changed": "0" * 64}):
            with self.assertRaisesRegex(ValueError, "provenance differs"):
                runner.replay(self.output)
        self.assertEqual(runner.replay(self.output), self.public)

        (self.output / "public.json").write_bytes(
            (self.output / "public.json").read_bytes() + b" "
        )
        with self.assertRaisesRegex(ValueError, "not canonical"):
            runner.replay(self.output)

    def test_replay_rejects_missing_saved_artifact(self):
        runner.analyze(self.output)
        (self.output / "hash_manifest.json").unlink()
        with self.assertRaisesRegex(ValueError, "inventory differs"):
            runner.replay(self.output)

    def test_cli_error_does_not_expose_private_exception_text(self):
        with (
            patch.object(
                sys,
                "argv",
                [
                    "diagnose_nyc_representation_fields_v1.py",
                    "analyze",
                    str(self.output),
                ],
            ),
            patch.object(runner, "analyze", side_effect=ValueError("PRIVATE STREET")),
            redirect_stdout(StringIO()) as stdout,
            patch("sys.stderr", new_callable=StringIO) as stderr,
        ):
            with self.assertRaises(SystemExit):
                runner.main()
        self.assertEqual(stdout.getvalue(), "")
        self.assertNotIn("PRIVATE STREET", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
