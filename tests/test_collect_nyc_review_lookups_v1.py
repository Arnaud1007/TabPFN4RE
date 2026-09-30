"""Synthetic, offline checks for one-home NYC source lookups."""

from __future__ import annotations

import csv
from contextlib import redirect_stdout
from hashlib import sha256
from io import StringIO
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import collect_nyc_review_lookups_v1 as lookup  # noqa: E402
import profile_nyc_rolling_snapshot as profile  # noqa: E402
from scripts import review_nyc_sample as review  # noqa: E402


def _jsonl(rows: list[dict]) -> bytes:
    return ("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n").encode()


class LookupTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.raw = Path(temporary.name) / "data" / "raw" / "nyc_dof"
        self.raw.mkdir(parents=True)
        self.review_dir = self.raw / "manual-review-v1"
        self.review_dir.mkdir()
        rows = []
        for borough, block in ((1, 10), (2, 20), (5, 30)):
            row = dict.fromkeys(profile.HEADER, "")
            row.update(
                {
                    "BOROUGH": str(borough),
                    "BLOCK": str(block),
                    "LOT": "1",
                    "SALE DATE": "01/01/2026",
                    "SALE PRICE": "123456",
                }
            )
            rows.append(row)
        stream = StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=profile.HEADER)
        writer.writeheader()
        writer.writerows(rows)
        source_body = stream.getvalue().encode()
        self.source = self.raw / "source.csv"
        self.source.write_bytes(source_body)
        source_hash = sha256(source_body).hexdigest()
        sample_rows = [
            {
                "ordinal": ordinal,
                "rank": sha256(
                    f"nyc-review-v1|{source_hash}|42|{ordinal}".encode()
                ).hexdigest(),
                "structural_cell": f"{row['BOROUGH']}:candidate",
            }
            for ordinal, row in enumerate(rows, 1)
        ]
        sample_body = _jsonl(sample_rows)
        self.sample = self.raw / "sample.jsonl"
        self.sample.write_bytes(sample_body)
        self.ledger = self.review_dir / "reviews.jsonl"
        self.ledger.write_bytes(b"")
        self.manifest = self.review_dir / "manifest.json"
        self.manifest.write_text(
            json.dumps(
                {
                    "ledger_id": "synthetic-ledger",
                    "protocol": review.PROTOCOL,
                    "source_sha256": source_hash,
                    "sample_sha256": sha256(sample_body).hexdigest(),
                    "created_at": "2026-09-01T00:00:00Z",
                }
            ),
            encoding="utf-8",
        )
        codes = [
            {"doc__type": kind, "doc__type_description": kind}
            for kind in ("DEED", "DEEDP", "DEEDO", "DEED, RC", "CDEC")
        ]
        code_body = json.dumps(codes).encode()
        self.codes = self.raw / "codes.json"
        self.codes.write_bytes(code_body)
        self.run_dir = self.raw / "lookup-v1-test"
        for module, name, value in (
            (review, "RAW_ROOT", self.raw),
            (review, "SOURCE_SHA256", source_hash),
            (review, "SAMPLE_SHA256", sha256(sample_body).hexdigest()),
            (review, "SOURCE_ROWS", 3),
            (review, "SAMPLE_COUNT", 3),
            (lookup, "CODE_TABLE_SHA256", sha256(code_body).hexdigest()),
            (lookup, "CODE_ROWS", 5),
        ):
            applied = patch.object(module, name, value)
            applied.start()
            self.addCleanup(applied.stop)
        for module, name in (
            (review.private_io, "verify_acl"),
            (lookup, "_secure_directory"),
            (lookup, "_verify_directory_acl"),
        ):
            applied = patch.object(module, name, return_value=None)
            applied.start()
            self.addCleanup(applied.stop)

    def _run(self, opener):
        return lookup.run_lookup(
            self.source,
            self.sample,
            self.ledger,
            self.manifest,
            self.codes,
            self.run_dir,
            opener=opener,
            sleep=lambda _: None,
        )

    def _responses(self, *, duplicate_master=False, saturated_bbl=False):
        calls = []

        def opener(url, timeout):
            self.assertEqual(timeout, 30)
            calls.append(url)
            query = parse_qs(urlsplit(url).query)
            where = query["$where"][0]
            if where.startswith("borough="):
                borough = where.split("=")[1].split()[0]
                block = where.split("block=")[1].split()[0]
                base = {
                    "document_id": "D1",
                    "borough": borough,
                    "block": block,
                    "lot": "1",
                }
                return json.dumps([base] * (251 if saturated_bbl else 1)).encode()
            if "bnx9-e6tj" in url:
                row = {
                    "document_id": "D1",
                    "doc_type": "DEED",
                    "document_date": "2026-01-02",
                }
                return json.dumps([row, row] if duplicate_master else [row]).encode()
            return json.dumps(
                [
                    {
                        "document_id": "D1",
                        "borough": "1",
                        "block": "10",
                        "lot": "1",
                        "unit": "",
                    }
                ]
            ).encode()

        return opener, calls

    def test_selects_lowest_ranked_unreviewed_acris_row(self):
        selected = lookup.choose_next(
            self.source, self.sample, self.ledger, self.manifest
        )
        self.assertIn(selected["borough"], (1, 2))
        self.assertEqual(
            selected["ordinal"],
            min(
                (1, 2),
                key=lambda n: sha256(
                    f"nyc-review-v1|{review.SOURCE_SHA256}|42|{n}".encode()
                ).hexdigest(),
            ),
        )
        self.assertNotIn("price", selected)

    def test_capture_replay_and_public_redaction(self):
        opener, calls = self._responses()
        result = self._run(opener)
        self.assertEqual(result["status"], "COMPLETE_ROUTE_ONLY")
        self.assertEqual(result["request_intents"], 3)
        self.assertEqual(len(calls), 3)
        self.assertEqual(result["sale_labels_certified"], 0)
        self.assertNotIn("query_sha256", result)
        self.assertNotIn("D1", json.dumps(result))
        self.assertNotIn("123456", json.dumps(result))
        replayed = lookup.replay_lookup(
            self.source, self.sample, self.codes, self.run_dir
        )
        self.assertEqual(replayed, result)
        self.assertEqual(len(calls), 3)
        self.assertEqual(self._run(lambda *_: self.fail("network")), result)

    def test_tampered_source_stops_before_network_or_run_creation(self):
        self.source.write_bytes(self.source.read_bytes() + b"x")
        with self.assertRaises(ValueError):
            self._run(lambda *_: self.fail("network"))
        self.assertFalse(self.run_dir.exists())

    def test_bad_sample_rank_stops_before_network(self):
        body = self.sample.read_text(encoding="utf-8").replace(
            '"rank": "', '"rank": "x', 1
        )
        self.sample.write_text(body, encoding="utf-8")
        with patch.object(
            review, "SAMPLE_SHA256", sha256(self.sample.read_bytes()).hexdigest()
        ):
            with self.assertRaisesRegex(ValueError, "rank or cell"):
                self._run(lambda *_: self.fail("network"))
        self.assertFalse(self.run_dir.exists())

    def test_completed_first_rank_is_skipped(self):
        first = self._run(self._responses()[0])
        self.assertEqual(first["sale_labels_certified"], 0)
        selected = json.loads((self.run_dir / "state.json").read_text())["selected"]
        with patch.object(
            review,
            "_history",
            return_value={selected["ordinal"]: {"review_status": "complete"}},
        ):
            other = lookup.choose_next(
                self.source, self.sample, self.ledger, self.manifest
            )
        self.assertNotEqual(other["ordinal"], selected["ordinal"])

    def test_bad_code_table_stops_before_network_and_run_creation(self):
        self.codes.write_bytes(b"[]")
        with self.assertRaisesRegex(ValueError, "code table SHA"):
            self._run(lambda *_: self.fail("network"))
        self.assertFalse(self.run_dir.exists())

    def test_duplicate_master_is_unresolved_and_bytes_are_saved(self):
        opener, calls = self._responses(duplicate_master=True)
        result = self._run(opener)
        self.assertEqual(result["status"], "INCOMPLETE_ERROR")
        self.assertEqual(len(calls), 2)
        self.assertEqual(result["sale_labels_certified"], 0)
        self.assertTrue((self.run_dir / "response-002.bin").is_file())
        self.assertEqual(
            lookup.replay_lookup(self.source, self.sample, self.codes, self.run_dir),
            result,
        )

    def test_saturated_bbl_remains_unresolved_without_master_query(self):
        opener, calls = self._responses(saturated_bbl=True)
        result = self._run(opener)
        self.assertEqual(len(calls), 1)
        self.assertFalse(result["document_triage_finished"])
        self.assertEqual(result["sale_labels_certified"], 0)

    def test_offline_replay_rejects_response_tampering(self):
        self._run(self._responses()[0])
        path = self.run_dir / "response-001.bin"
        path.write_bytes(path.read_bytes() + b"x")
        with self.assertRaises(ValueError):
            lookup.replay_lookup(self.source, self.sample, self.codes, self.run_dir)

    def test_crash_after_intent_remains_unknown_and_never_retries(self):
        def interrupted(_url, _timeout):
            raise KeyboardInterrupt()

        with self.assertRaises(KeyboardInterrupt):
            self._run(interrupted)
        state = json.loads((self.run_dir / "state.json").read_text())
        self.assertEqual(state["intents"][0]["result"], "pending")
        result = lookup.replay_lookup(
            self.source, self.sample, self.codes, self.run_dir
        )
        self.assertEqual(result["status"], "INCOMPLETE_ERROR")
        self.assertEqual(self._run(lambda *_: self.fail("network")), result)

    def test_received_body_is_saved_before_parser_interruption(self):
        opener, _ = self._responses()
        with patch.object(lookup.acris, "_parse", side_effect=KeyboardInterrupt()):
            with self.assertRaises(KeyboardInterrupt):
                self._run(opener)
        self.assertTrue((self.run_dir / "response-001.bin").is_file())
        state = json.loads((self.run_dir / "state.json").read_text())
        self.assertEqual(state["intents"][0]["result"], "pending")

    def test_orphan_body_after_write_interruption_needs_reconciliation(self):
        original = lookup.acris._atomic_body

        def interrupted(path, body):
            original(path, body)
            raise KeyboardInterrupt()

        with patch.object(lookup.acris, "_atomic_body", side_effect=interrupted):
            with self.assertRaises(KeyboardInterrupt):
                self._run(self._responses()[0])
        self.assertTrue((self.run_dir / "response-001.bin").is_file())
        with self.assertRaisesRegex(ValueError, "orphan"):
            lookup.replay_lookup(self.source, self.sample, self.codes, self.run_dir)

    def test_non_deed_code_remains_context_without_linked_request(self):
        calls = []

        def opener(url, _timeout):
            calls.append(url)
            where = parse_qs(urlsplit(url).query)["$where"][0]
            if where.startswith("borough="):
                selected = json.loads((self.run_dir / "state.json").read_text())[
                    "selected"
                ]
                return json.dumps(
                    [
                        {
                            "document_id": "C1",
                            "borough": str(selected["borough"]),
                            "block": selected["block"],
                            "lot": selected["lot"],
                        }
                    ]
                ).encode()
            return b'[{"document_id":"C1","doc_type":"CDEC"}]'

        result = self._run(opener)
        self.assertEqual(len(calls), 2)
        self.assertEqual(result["status"], "COMPLETE_ROUTE_ONLY")
        self.assertFalse(result["document_triage_finished"])

    def test_multiple_linked_lots_and_blank_unit_remain_unresolved(self):
        def opener(url, _timeout):
            where = parse_qs(urlsplit(url).query)["$where"][0]
            selected = json.loads((self.run_dir / "state.json").read_text())["selected"]
            if where.startswith("borough="):
                return json.dumps(
                    [
                        {
                            "document_id": "D1",
                            "borough": str(selected["borough"]),
                            "block": selected["block"],
                            "lot": selected["lot"],
                        }
                    ]
                ).encode()
            if "bnx9-e6tj" in url:
                return b'[{"document_id":"D1","doc_type":"DEED"}]'
            return json.dumps(
                [
                    {
                        "document_id": "D1",
                        "borough": str(selected["borough"]),
                        "block": selected["block"],
                        "lot": selected["lot"],
                        "unit": "",
                    },
                    {
                        "document_id": "D1",
                        "borough": str(selected["borough"]),
                        "block": selected["block"],
                        "lot": str(int(selected["lot"]) + 1),
                        "unit": "2A",
                    },
                ]
            ).encode()

        result = self._run(opener)
        self.assertEqual(result["status"], "COMPLETE_ROUTE_ONLY")
        self.assertFalse(result["document_triage_finished"])
        self.assertTrue((self.run_dir / "response-003.bin").is_file())
        self.assertEqual(result["sale_labels_certified"], 0)
        self.assertEqual(
            lookup.replay_lookup(self.source, self.sample, self.codes, self.run_dir),
            result,
        )

    def test_blank_sale_date_is_unresolved_before_deed_lookup(self):
        selected = lookup._choose(
            [{"ordinal": 1, "rank": "first"}],
            {1: {"BOROUGH": "1", "BLOCK": "10", "LOT": "1", "SALE DATE": ""}},
            {},
        )
        self.assertEqual(selected["status"], "missing_date")
        with patch.object(
            lookup, "_live_selection", return_value=(selected, b"", "synthetic-ledger")
        ):
            result = self._run(lambda *_: self.fail("network"))
        self.assertEqual(result["status"], "INCOMPLETE_ERROR")
        self.assertEqual(result["request_intents"], 0)

    def test_missing_identity_makes_no_request(self):
        selected = {
            "ordinal": 1,
            "rank": "synthetic",
            "borough": 1,
            "block": "",
            "lot": "1",
            "sale_date": "01/01/2026",
            "status": "missing_identity",
        }
        with patch.object(
            lookup, "_live_selection", return_value=(selected, b"", "synthetic-ledger")
        ):
            result = self._run(lambda *_: self.fail("network"))
        self.assertEqual(result["status"], "INCOMPLETE_ERROR")
        self.assertEqual(result["request_intents"], 0)

    def test_saved_aggregate_tamper_is_rejected(self):
        self._run(self._responses()[0])
        path = self.run_dir / "state.json"
        state = json.loads(path.read_text())
        state["aggregate"] = {"status": "CERTIFIED"}
        path.write_text(json.dumps(state))
        with self.assertRaisesRegex(ValueError, "saved aggregate differs"):
            lookup.replay_lookup(self.source, self.sample, self.codes, self.run_dir)

    def test_non_object_private_state_is_rejected_cleanly(self):
        self._run(self._responses()[0])
        (self.run_dir / "state.json").write_text("[]", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "state must be an object"):
            lookup.replay_lookup(self.source, self.sample, self.codes, self.run_dir)

    def test_lookup_rejects_directory_outside_private_root(self):
        self.run_dir = self.raw.parent / "outside"
        with self.assertRaisesRegex(ValueError, "inside private raw data"):
            self._run(lambda *_: self.fail("network"))
        self.assertFalse(self.run_dir.exists())

    def test_hardlinked_source_is_rejected_before_network(self):
        alias = self.raw / "source-hardlink.csv"
        os.link(self.source, alias)
        with self.assertRaisesRegex(ValueError, "single-link"):
            self._run(lambda *_: self.fail("network"))
        self.assertFalse(self.run_dir.exists())

    def test_private_acl_failure_blocks_get(self):
        with patch.object(lookup, "_secure_directory", side_effect=ValueError("ACL")):
            with self.assertRaisesRegex(ValueError, "ACL"):
                self._run(lambda *_: self.fail("network"))

    def test_first_get_is_paced_and_global_lock_is_released(self):
        delays = []
        opener, calls = self._responses()
        result = lookup.run_lookup(
            self.source,
            self.sample,
            self.ledger,
            self.manifest,
            self.codes,
            self.run_dir,
            opener=opener,
            sleep=delays.append,
        )
        self.assertEqual(result["request_intents"], 3)
        self.assertEqual(len(calls), 3)
        self.assertIn(1, delays)
        self.assertFalse((self.raw / "nyc-source-lookup-v1-global.lock").exists())

    def test_existing_global_lock_blocks_concurrent_capture(self):
        lock = self.raw / "nyc-source-lookup-v1-global.lock"
        lock.write_text("synthetic owner", encoding="utf-8")
        with self.assertRaises(FileExistsError):
            self._run(lambda *_: self.fail("network"))
        self.assertFalse(self.run_dir.exists())

    def test_request_cap_stops_after_one_get_without_silent_completion(self):
        opener, calls = self._responses()
        with patch.object(lookup, "MAX_REQUESTS", 1):
            result = self._run(opener)
        self.assertEqual(len(calls), 1)
        self.assertEqual(result["request_intents"], 1)
        self.assertNotEqual(result["status"], "COMPLETE_ROUTE_ONLY")
        self.assertEqual(result["sale_labels_certified"], 0)

    def test_hostile_url_is_rejected_before_opener_and_kept_private(self):
        with patch.object(
            lookup.acris, "legals_bbl_url", return_value="https://example.org/steal"
        ):
            result = self._run(lambda *_: self.fail("network"))
        self.assertEqual(result["status"], "INCOMPLETE_ERROR")
        self.assertNotIn("example.org", json.dumps(result))
        self.assertFalse((self.run_dir / "response-001.bin").exists())

    def test_cli_capture_requires_private_review_inputs(self):
        arguments = [
            "collector",
            "capture",
            "--source",
            str(self.source),
            "--sample",
            str(self.sample),
            "--code-table",
            str(self.codes),
            "--private-run-dir",
            str(self.run_dir),
        ]
        with patch.object(sys, "argv", arguments):
            with self.assertRaises(SystemExit) as stopped:
                lookup.main()
        self.assertEqual(stopped.exception.code, 2)
        self.assertFalse(self.run_dir.exists())

    def test_direct_script_cli_help_loads_without_pythonpath(self):
        script = (
            Path(__file__).resolve().parents[1]
            / "scripts"
            / "collect_nyc_review_lookups_v1.py"
        )
        completed = subprocess.run(
            [sys.executable, str(script), "--help"],
            cwd=script.parents[1],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("capture", completed.stdout)

    def test_cli_replay_hides_private_incomplete_status(self):
        arguments = [
            "collector",
            "replay",
            "--source",
            str(self.source),
            "--sample",
            str(self.sample),
            "--code-table",
            str(self.codes),
            "--private-run-dir",
            str(self.run_dir),
        ]
        output = StringIO()
        aggregate = {"status": "INCOMPLETE_ERROR", "sale_labels_certified": 0}
        with (
            patch.object(sys, "argv", arguments),
            patch.object(lookup, "replay_lookup", return_value=aggregate),
        ):
            with redirect_stdout(output):
                lookup.main()
        self.assertEqual(
            json.loads(output.getvalue()),
            {
                "protocol": "nyc-source-lookup-v1",
                "projection": "private_only_v1",
                "manual_reviews_appended": 0,
                "sale_labels_certified": 0,
            },
        )

    def test_cli_exit_does_not_reveal_private_triage(self):
        arguments = [
            "collector",
            "replay",
            "--source",
            str(self.source),
            "--sample",
            str(self.sample),
            "--code-table",
            str(self.codes),
            "--private-run-dir",
            str(self.run_dir),
        ]
        aggregate = {
            "status": "COMPLETE_ROUTE_ONLY",
            "document_triage_finished": False,
            "sale_labels_certified": 0,
        }
        with (
            patch.object(sys, "argv", arguments),
            patch.object(lookup, "replay_lookup", return_value=aggregate),
        ):
            with redirect_stdout(StringIO()):
                lookup.main()


if __name__ == "__main__":
    unittest.main()
