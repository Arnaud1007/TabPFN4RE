"""Synthetic, offline contract tests for the immutable NYC ACRIS v2 route."""

from __future__ import annotations

import csv
from hashlib import sha256
from io import BytesIO, StringIO
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import audit_nyc_acris_matches as v1  # noqa: E402
import audit_nyc_acris_matches_v2 as pilot  # noqa: E402
import profile_nyc_rolling_snapshot as profile  # noqa: E402

REAL_SECURE_DIRECTORY = pilot._secure_directory
REAL_VERIFY_DIRECTORY_ACL = (
    pilot._verify_directory_acl if hasattr(pilot, "_verify_directory_acl") else None
)


def fixture_inputs(root: Path):
    rows = []
    for borough in range(1, 6):
        row = dict.fromkeys(profile.HEADER, "")
        row.update(
            {
                "BOROUGH": str(borough),
                "BLOCK": "10",
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
    snapshot = stream.getvalue().encode()
    csv_path = root / "rolling.csv"
    csv_path.write_bytes(snapshot)
    snapshot_hash = sha256(snapshot).hexdigest()
    ledger = []
    for ordinal, row in enumerate(rows, 1):
        ledger.append(
            {
                "ordinal": ordinal,
                "rank": sha256(
                    f"nyc-review-v1|{snapshot_hash}|42|{ordinal}".encode()
                ).hexdigest(),
                "structural_cell": f"{row['BOROUGH']}:candidate",
            }
        )
    ledger_bytes = ("\n".join(json.dumps(x) for x in ledger) + "\n").encode()
    ledger_path = root / "ledger.jsonl"
    ledger_path.write_bytes(ledger_bytes)
    codes = [
        {"doc__type": x, "doc__type_description": x}
        for x in ("DEED", "DEEDP", "DEEDO", "DEED, RC", "CDEC")
    ]
    code_bytes = json.dumps(codes).encode()
    code_path = root / "codes.json"
    code_path.write_bytes(code_bytes)
    return (
        csv_path,
        ledger_path,
        code_path,
        snapshot_hash,
        sha256(ledger_bytes).hexdigest(),
        sha256(code_bytes).hexdigest(),
    )


class PilotV2Tests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "data" / "raw" / "nyc_dof"
        self.root.mkdir(parents=True)
        (self.snapshot, self.ledger, self.codes, snap_hash, ledger_hash, code_hash) = (
            fixture_inputs(self.root)
        )
        for module, name, value in (
            (profile, "PRIVATE_ROOT", self.root),
            (v1, "SNAPSHOT_SHA256", snap_hash),
            (v1, "SNAPSHOT_ROWS", 5),
            (v1, "LEDGER_SHA256", ledger_hash),
            (v1, "LEDGER_ROWS", 5),
            (pilot, "CODE_TABLE_SHA256", code_hash),
            (pilot, "CODE_ROWS", 5),
        ):
            bound = patch.object(module, name, value)
            bound.start()
            self.addCleanup(bound.stop)
        acl = patch.object(pilot, "_secure_directory", return_value=None)
        acl.start()
        self.addCleanup(acl.stop)
        verify_acl = patch.object(pilot, "_verify_directory_acl", return_value=None)
        verify_acl.start()
        self.addCleanup(verify_acl.stop)
        self.run_dir = self.root / "pilot-v2"

    def run_pilot(self, opener):
        return pilot.run_pilot(
            self.snapshot,
            self.ledger,
            self.codes,
            self.run_dir,
            opener=opener,
            sleep=lambda _: None,
        )

    def test_verifies_three_private_inputs_before_any_request(self):
        self.codes.write_bytes(b"[]")
        with self.assertRaisesRegex(ValueError, "code table SHA"):
            self.run_pilot(lambda *_: self.fail("network"))
        self.assertFalse(self.run_dir.exists())

    def test_four_exact_bbls_first_and_code_filter_cdec_unresolved(self):
        calls = []

        def opener(url, _timeout):
            calls.append(url)
            query = parse_qs(urlsplit(url).query)
            where = query["$where"][0]
            if where.startswith("borough="):
                borough = where.split("=")[1].split()[0]
                return json.dumps(
                    [
                        {
                            "document_id": f"D{borough}",
                            "borough": borough,
                            "block": "10",
                            "lot": "1",
                        },
                        {
                            "document_id": f"C{borough}",
                            "borough": borough,
                            "block": "10",
                            "lot": "1",
                        },
                    ]
                ).encode()
            if "bnx9-e6tj" in url:
                ids = pilot._requested_ids(url)
                self.assertNotIn("document_amt", query["$select"][0])
                return json.dumps(
                    [
                        {
                            "document_id": x,
                            "doc_type": "CDEC" if x.startswith("C") else "DEED",
                            "document_date": "2026-01-02",
                        }
                        for x in ids
                    ]
                ).encode()
            return json.dumps(
                [
                    {
                        "document_id": pilot._requested_ids(url)[0],
                        "borough": "1",
                        "block": "10",
                        "lot": "1",
                        "unit": "",
                    }
                ]
            ).encode()

        result = self.run_pilot(opener)
        self.assertEqual(result["status"], "COMPLETE_ROUTE_ONLY")
        self.assertEqual(len(calls), 12)  # 4 BBL + 4 Master batches + 4 linked deeds
        self.assertTrue(all("8h5j-fqxa" in url for url in calls[:4]))
        self.assertTrue(all("bnx9-e6tj" in url for url in calls[4:8]))
        self.assertEqual(result["http_requests"], 12)
        self.assertFalse(result["document_triage_finished"])
        self.assertTrue(result["manual_review_pending"])
        self.assertNotIn("counts_by_borough", result)
        self.assertNotIn("CDEC", json.dumps(result))
        self.assertNotIn("D1", json.dumps(result))
        self.assertEqual(self.run_pilot(lambda *_: self.fail("network")), result)

    def test_batch_complete_and_duplicate_master_fails_closed(self):
        bodies = []

        def opener(url, _timeout):
            where = parse_qs(urlsplit(url).query)["$where"][0]
            if where.startswith("borough="):
                borough = where.split("=")[1].split()[0]
                return json.dumps(
                    [
                        {
                            "document_id": f"D{borough}{j}",
                            "borough": borough,
                            "block": "10",
                            "lot": "1",
                        }
                        for j in range(11)
                    ]
                ).encode()
            if "bnx9-e6tj" in url:
                ids = pilot._requested_ids(url)
                bodies.append(ids)
                return json.dumps(
                    [{"document_id": x, "doc_type": "CDEC"} for x in ids]
                ).encode()
            self.fail("No linked deed should be queried")

        result = self.run_pilot(opener)
        self.assertEqual(result["status"], "COMPLETE_ROUTE_ONLY")
        self.assertEqual([len(x) for x in bodies], [10, 10, 10, 10, 1, 1, 1, 1])

        state = json.loads((self.run_dir / "state.json").read_text())
        master = next(x for x in state["intents"] if x["phase"] == "master")
        body_path = self.run_dir / master["body_file"]
        duplicate = json.dumps(
            [{"document_id": bodies[0][0]}, {"document_id": bodies[0][0]}]
        ).encode()
        body_path.write_bytes(duplicate)
        master["body_sha256"] = sha256(duplicate).hexdigest()
        (self.run_dir / "state.json").write_text(json.dumps(state))
        with self.assertRaisesRegex(ValueError, "summary|aggregate|evidence"):
            self.run_pilot(lambda *_: self.fail("network"))

    def test_saturation_is_retained_and_unresolved(self):
        def opener(url, _timeout):
            where = parse_qs(urlsplit(url).query)["$where"][0]
            if where.startswith("borough="):
                borough = where.split("=")[1].split()[0]
                return json.dumps(
                    [
                        {
                            "document_id": f"D{n}",
                            "borough": borough,
                            "block": "10",
                            "lot": "1",
                        }
                        for n in range(251)
                    ]
                ).encode()
            self.fail("saturated BBL must not yield Master requests")

        result = self.run_pilot(opener)
        self.assertEqual(result["status"], "COMPLETE_ROUTE_ONLY")
        self.assertTrue(result["four_bbl_queries_finished"])
        self.assertFalse(result["document_triage_finished"])
        self.assertEqual(len(list(self.run_dir.glob("response-*.bin"))), 4)
        state = json.loads((self.run_dir / "state.json").read_text())
        self.assertEqual(
            {item["reason"] for item in state["intents"]}, {"saturated_bbl"}
        )

    def test_multi_lot_blank_unit_and_partial_interest_stay_private(self):
        def opener(url, _timeout):
            where = parse_qs(urlsplit(url).query)["$where"][0]
            if where.startswith("borough="):
                borough = where.split("=")[1].split()[0]
                return json.dumps(
                    [
                        {
                            "document_id": f"D{borough}",
                            "borough": borough,
                            "block": "10",
                            "lot": "1",
                        }
                    ]
                ).encode()
            identifier = pilot._requested_ids(url)[0]
            if "bnx9-e6tj" in url:
                return json.dumps(
                    [
                        {
                            "document_id": identifier,
                            "doc_type": "DEED",
                            "percent_trans": "50",
                        }
                    ]
                ).encode()
            return json.dumps(
                [
                    {
                        "document_id": identifier,
                        "borough": "1",
                        "block": "10",
                        "lot": "1",
                        "unit": "",
                    },
                    {
                        "document_id": identifier,
                        "borough": "1",
                        "block": "11",
                        "lot": "1",
                        "unit": "A",
                        "partial_lot": "Y",
                    },
                ]
            ).encode()

        result = self.run_pilot(opener)
        assessment = json.loads((self.run_dir / "state.json").read_text())[
            "private_assessment"
        ]
        self.assertEqual(assessment["1"]["disposition"], "provisional_primary_queue")
        self.assertEqual(
            set(assessment["1"]["flags"]),
            {
                "partial_interest",
                "multiple_lots",
                "blank_or_missing_unit",
                "conflicting_units",
                "partial_lot",
            },
        )
        self.assertNotIn("multiple_lots", json.dumps(result))
        self.assertNotIn("D1", json.dumps(result))

    def test_master_budget_retains_uninspected_ids_privately(self):
        def opener(url, _timeout):
            where = parse_qs(urlsplit(url).query)["$where"][0]
            if where.startswith("borough="):
                borough = where.split("=")[1].split()[0]
                return json.dumps(
                    [
                        {
                            "document_id": f"D{borough}_{n:02d}",
                            "borough": borough,
                            "block": "10",
                            "lot": "1",
                        }
                        for n in range(81)
                    ]
                ).encode()
            if "bnx9-e6tj" in url:
                return json.dumps(
                    [
                        {"document_id": x, "doc_type": "CDEC"}
                        for x in pilot._requested_ids(url)
                    ]
                ).encode()
            self.fail("No primary deed")

        result = self.run_pilot(opener)
        self.assertEqual(result["status"], "PARTIAL_BUDGET")
        self.assertEqual(result["http_requests"], 34)
        state = json.loads((self.run_dir / "state.json").read_text())
        self.assertTrue(
            any(
                x["not_inspected_budget_ids"]
                for x in state["private_assessment"].values()
            )
        )
        self.assertFalse(
            set(state["private_assessment"]["1"]["not_inspected_budget_ids"])
            & set(state["private_assessment"]["1"]["attempted_master_unresolved_ids"])
        )

    def test_failed_master_is_attempted_and_not_mislabelled_budget(self):
        def opener(url, _timeout):
            where = parse_qs(urlsplit(url).query)["$where"][0]
            if where.startswith("borough="):
                borough = where.split("=")[1].split()[0]
                return json.dumps(
                    [
                        {
                            "document_id": f"D{borough}",
                            "borough": borough,
                            "block": "10",
                            "lot": "1",
                        }
                    ]
                ).encode()
            if "bnx9-e6tj" in url:
                identifiers = pilot._requested_ids(url)
                if identifiers == ["D1"]:
                    raise TimeoutError("private address")
                return json.dumps(
                    [{"document_id": item, "doc_type": "CDEC"} for item in identifiers]
                ).encode()
            self.fail("No linked deed expected")

        result = self.run_pilot(opener)
        self.assertEqual(result["status"], "INCOMPLETE_ERROR")
        assessment = json.loads((self.run_dir / "state.json").read_text())[
            "private_assessment"
        ]["1"]
        self.assertEqual(assessment["attempted_master_unresolved_ids"], ["D1"])
        self.assertEqual(assessment["not_inspected_budget_ids"], [])

    def test_linked_saturation_has_private_document_reason(self):
        def opener(url, _timeout):
            where = parse_qs(urlsplit(url).query)["$where"][0]
            if where.startswith("borough="):
                borough = where.split("=")[1].split()[0]
                return json.dumps(
                    [
                        {
                            "document_id": f"D{borough}",
                            "borough": borough,
                            "block": "10",
                            "lot": "1",
                        }
                    ]
                ).encode()
            identifier = pilot._requested_ids(url)[0]
            if "bnx9-e6tj" in url:
                return json.dumps(
                    [{"document_id": identifier, "doc_type": "DEED"}]
                ).encode()
            return json.dumps(
                [
                    {
                        "document_id": identifier,
                        "borough": "1",
                        "block": "10",
                        "lot": "1",
                        "unit": "A",
                    }
                ]
                * 101
            ).encode()

        result = self.run_pilot(opener)
        self.assertEqual(result["status"], "COMPLETE_ROUTE_ONLY")
        self.assertFalse(result["document_triage_finished"])
        state = json.loads((self.run_dir / "state.json").read_text())
        linked = [item for item in state["intents"] if item["phase"] == "linked"]
        self.assertEqual(len(linked), 4)
        self.assertEqual({item["reason"] for item in linked}, {"saturated_document"})

    def test_failure_body_saved_before_validation_and_other_bbls_attempted(self):
        calls = []

        def opener(url, _timeout):
            calls.append(url)
            if len(calls) == 1:
                return b'{"private_name":"SHOULD_NOT_PRINT"}'
            return b"[]"

        result = self.run_pilot(opener)
        self.assertEqual(result["status"], "INCOMPLETE_ERROR")
        self.assertEqual(len(calls), 4)
        self.assertNotIn("SHOULD_NOT_PRINT", json.dumps(result))
        self.assertIn(
            b"SHOULD_NOT_PRINT", (self.run_dir / "response-001.bin").read_bytes()
        )
        self.assertEqual(self.run_pilot(lambda *_: self.fail("network")), result)

    def test_http_error_body_saved_and_no_retry(self):
        def opener(url, _timeout):
            raise HTTPError(url, 500, "private message", {}, BytesIO(b"private body"))

        result = self.run_pilot(opener)
        self.assertEqual(result["status"], "INCOMPLETE_ERROR")
        self.assertEqual(result["http_requests"], 4)
        self.assertNotIn("private", json.dumps(result))
        self.assertTrue(list(self.run_dir.glob("response-*.bin")))
        self.assertEqual(self.run_pilot(lambda *_: self.fail("network")), result)

    def test_http_error_body_read_failure_has_fixed_no_body_reason(self):
        class BrokenBody:
            def read(self, _limit):
                raise OSError("private address in source exception")

        def opener(url, _timeout):
            raise HTTPError(url, 500, "private message", {}, BrokenBody())

        result = self.run_pilot(opener)
        self.assertEqual(result["status"], "INCOMPLETE_ERROR")
        self.assertNotIn("private", json.dumps(result))
        state = json.loads((self.run_dir / "state.json").read_text())
        self.assertEqual(
            {x["reason"] for x in state["intents"]}, {"http_error_body_unavailable"}
        )
        self.assertEqual(self.run_pilot(lambda *_: self.fail("network")), result)

    def test_truncated_body_is_incomplete_and_saved_with_bounded_length(self):
        result = self.run_pilot(lambda *_: b"x" * (pilot.MAX_RESPONSE_BYTES + 90))
        self.assertEqual(result["status"], "INCOMPLETE_ERROR")
        state = json.loads((self.run_dir / "state.json").read_text())
        self.assertEqual(
            {x["reason"] for x in state["intents"]}, {"response_truncated"}
        )
        self.assertEqual(
            len((self.run_dir / "response-001.bin").read_bytes()),
            pilot.MAX_RESPONSE_BYTES + 1,
        )
        self.assertEqual(self.run_pilot(lambda *_: self.fail("network")), result)

    def test_oversized_saved_response_is_rejected_even_with_matching_hash(self):
        self.run_pilot(lambda *_: b"[]")
        path = self.run_dir / "state.json"
        state = json.loads(path.read_text())
        body = b"x" * (pilot.MAX_RESPONSE_BYTES + 2)
        (self.run_dir / state["intents"][0]["body_file"]).write_bytes(body)
        state["intents"][0]["body_sha256"] = sha256(body).hexdigest()
        path.write_text(json.dumps(state))
        with self.assertRaisesRegex(ValueError, "body cap"):
            self.run_pilot(lambda *_: self.fail("network"))

    def test_invalid_saturated_response_is_schema_error_not_saturation(self):
        invalid = json.dumps(
            [{"document_id": "BAD'ID", "borough": "4", "block": "10", "lot": "1"}] * 251
        ).encode()
        result = self.run_pilot(lambda *_: invalid)
        self.assertEqual(result["status"], "INCOMPLETE_ERROR")
        state = json.loads((self.run_dir / "state.json").read_text())
        self.assertEqual({x["reason"] for x in state["intents"]}, {"schema_error"})

    def test_crash_intent_without_body_is_unknown_and_not_retried(self):
        self.run_pilot(lambda *_: b"[]")
        state_path = self.run_dir / "state.json"
        state = json.loads(state_path.read_text())
        state["intents"][-1].pop("body_file")
        state["intents"][-1].pop("body_sha256")
        state["intents"][-1]["result"] = "pending"
        state.pop("aggregate")
        state.pop("private_assessment")
        state_path.write_text(json.dumps(state))
        result = self.run_pilot(lambda *_: self.fail("network"))
        self.assertEqual(result["status"], "INCOMPLETE_ERROR")
        self.assertEqual(result["http_requests"], 4)

    def test_crash_after_final_intent_replays_without_saved_summary_or_network(self):
        expected = self.run_pilot(lambda *_: b"[]")
        path = self.run_dir / "state.json"
        state = json.loads(path.read_text())
        self.assertTrue(all(item["result"] != "pending" for item in state["intents"]))
        state.pop("aggregate")
        state.pop("private_assessment")
        path.write_text(json.dumps(state))
        actual = self.run_pilot(lambda *_: self.fail("network retry"))
        self.assertEqual(actual, expected)
        self.assertEqual(actual["http_requests"], 4)

    def test_crash_before_first_request_never_reports_complete(self):
        self.run_pilot(lambda *_: b"[]")
        path = self.run_dir / "state.json"
        state = json.loads(path.read_text())
        state["intents"] = []
        state.pop("aggregate")
        state.pop("private_assessment")
        path.write_text(json.dumps(state))
        result = self.run_pilot(lambda *_: self.fail("network retry"))
        self.assertEqual(result["status"], "INCOMPLETE_ERROR")
        self.assertEqual(result["http_requests"], 0)

    def test_new_run_directory_is_restricted_before_raw_write(self):
        with tempfile.TemporaryDirectory() as root:
            run = Path(root) / "secured"
            run.mkdir(mode=0o700)
            REAL_SECURE_DIRECTORY(run)
            if REAL_VERIFY_DIRECTORY_ACL is not None:
                REAL_VERIFY_DIRECTORY_ACL(run)
            if os.name != "nt":
                self.assertEqual(run.stat().st_mode & 0o077, 0)
        with patch.object(
            pilot, "_secure_directory", side_effect=ValueError("private ACL")
        ):
            with self.assertRaisesRegex(ValueError, "private ACL"):
                self.run_pilot(lambda *_: self.fail("network"))

    def test_replay_rechecks_acl_read_only(self):
        self.run_pilot(lambda *_: b"[]")
        with patch.object(
            pilot,
            "_verify_directory_acl",
            side_effect=ValueError("Private run directory ACL verification failed"),
        ) as check:
            with self.assertRaisesRegex(ValueError, "ACL verification"):
                self.run_pilot(lambda *_: self.fail("network"))
        check.assert_called_once_with(self.run_dir)

    def test_redirect_rejected_without_following_target(self):
        destinations = []

        class FakeOpener:
            def __init__(self, handlers):
                self.handlers = handlers

            def open(self, url, timeout):
                destinations.append(url)
                return self.handlers[0].redirect_request(
                    Request(url),
                    None,
                    302,
                    "Found",
                    {},
                    "https://other.example/private",
                )

        with patch.object(
            pilot, "build_opener", side_effect=lambda *handlers: FakeOpener(handlers)
        ):
            with self.assertRaisesRegex(ValueError, "redirect"):
                pilot._http_get(pilot.legals_bbl_url(1, 10, 1), 30)
        self.assertEqual(len(destinations), 1)

    def test_exact_date_order_and_malformed_suffix_are_not_false_near_matches(self):
        def key(value, identifier):
            return pilot._date_key("01/01/2026", {"document_date": value}, identifier)

        self.assertLess(key("2026-01-02", "NEAR"), key("2024-01-02", "FAR"))
        self.assertLess(key("2024-01-02", "FAR"), key("2026-01-02-private", "INVALID"))
        self.assertEqual(key("2026-01-02T00:00:00.000", "TIMESTAMP")[0], 0)
        with self.assertRaisesRegex(ValueError, "sale date"):
            pilot._date_key("not-a-date", {}, "X")

    def test_duplicate_document_is_fetched_once_for_two_selected_bbls(self):
        calls = []

        def opener(url, _timeout):
            calls.append(url)
            where = parse_qs(urlsplit(url).query)["$where"][0]
            if where.startswith("borough="):
                borough = where.split("=")[1].split()[0]
                return json.dumps(
                    [
                        {
                            "document_id": "SHARED"
                            if borough in ("1", "2")
                            else f"C{borough}",
                            "borough": borough,
                            "block": "10",
                            "lot": "1",
                        }
                    ]
                ).encode()
            if "bnx9-e6tj" in url:
                return json.dumps(
                    [
                        {
                            "document_id": x,
                            "doc_type": "DEED" if x == "SHARED" else "CDEC",
                        }
                        for x in pilot._requested_ids(url)
                    ]
                ).encode()
            return json.dumps(
                [
                    {
                        "document_id": "SHARED",
                        "borough": "1",
                        "block": "10",
                        "lot": "1",
                        "unit": "A",
                    }
                ]
            ).encode()

        result = self.run_pilot(opener)
        self.assertEqual(result["status"], "COMPLETE_ROUTE_ONLY")
        self.assertEqual(len(calls), 8)  # 4 BBL + 3 distinct Master + one linked
        self.assertEqual(sum("bnx9-e6tj" in x for x in calls), 3)
        state = json.loads((self.run_dir / "state.json").read_text())
        self.assertEqual(
            state["private_assessment"]["1"]["primary_inspection_ids"], ["SHARED"]
        )
        self.assertEqual(
            state["private_assessment"]["2"]["primary_inspection_ids"], ["SHARED"]
        )

    def test_invalid_code_table_shape_and_missing_required_codes(self):
        for payload in (
            b"{}",
            b"[{}]",
            json.dumps(
                [{"doc__type": x} for x in ("DEED", "DEEDP", "DEEDO", "CDEC", "OTHER")]
            ).encode(),
        ):
            with self.subTest(payload=payload):
                self.codes.write_bytes(payload)
                with patch.object(
                    pilot, "CODE_TABLE_SHA256", sha256(payload).hexdigest()
                ):
                    with self.assertRaisesRegex(ValueError, "code table"):
                        self.run_pilot(lambda *_: self.fail("network"))

    def test_response_guards_fail_closed_on_malformed_and_saturated_data(self):
        with self.assertRaises(ValueError):
            pilot.master_batch_url(["SAFE", "unsafe' OR true"])
        with self.assertRaises(ValueError):
            pilot.master_batch_url(["SAME", "SAME"])
        with self.assertRaisesRegex(ValueError, "malformed"):
            pilot._parse(b"not-json", "bbl", (1, 10, 1))
        with self.assertRaisesRegex(ValueError, "malformed"):
            pilot._parse(b"[1]", "bbl", (1, 10, 1))
        with self.assertRaisesRegex(ValueError, "identifier"):
            pilot._parse(b'[{"document_id":"BAD\'ID"}]', "master", ["GOOD"])
        duplicate = json.dumps([{"document_id": "D"}, {"document_id": "D"}]).encode()
        with self.assertRaisesRegex(ValueError, "duplicated"):
            pilot._parse(duplicate, "master", ["D"])
        with self.assertRaisesRegex(ValueError, "truncated"):
            pilot._parse(b"x" * (1024 * 1024 + 1), "bbl", (1, 10, 1))
        with patch.object(pilot, "MAX_URL_LENGTH", 10):
            with self.assertRaisesRegex(ValueError, "URL"):
                pilot.master_batch_url(["D"])
        with self.assertRaises(ValueError):
            pilot.master_batch_url([f"D{x}" for x in range(11)])
        wrong_bbl = b'[{"document_id":"D","borough":"2","block":"10","lot":"1"}]'
        with self.assertRaisesRegex(ValueError, "contradicts"):
            pilot._parse(wrong_bbl, "bbl", (1, 10, 1))

    def test_saved_evidence_tampering_is_rejected_offline(self):
        self.run_pilot(lambda *_: b"[]")
        path = self.run_dir / "state.json"
        original = json.loads(path.read_text())
        changes = (
            (lambda x: x.update(protocol="wrong"), "protocol"),
            (lambda x: x["intents"][0].update(sequence=99), "sequence"),
            (
                lambda x: x["intents"][0].update(url=pilot.legals_bbl_url(4, 99, 1)),
                "query sequence",
            ),
            (lambda x: x["intents"][0].update(body_file="../ledger.jsonl"), "filename"),
            (lambda x: x["intents"][0].update(body_sha256="0" * 64), "hash"),
        )
        for mutate, message in changes:
            with self.subTest(message=message):
                altered = json.loads(json.dumps(original))
                mutate(altered)
                path.write_text(json.dumps(altered))
                with self.assertRaisesRegex(ValueError, message):
                    self.run_pilot(lambda *_: self.fail("network"))
        path.write_text(json.dumps(original))
        with self.assertRaisesRegex(ValueError, "summary"):
            altered = json.loads(json.dumps(original))
            altered["aggregate"]["http_requests"] = 42
            path.write_text(json.dumps(altered))
            self.run_pilot(lambda *_: self.fail("network"))

    def test_client_rate_limit_timeout_and_bounded_error_category(self):
        now = [0.0]
        calls = []

        def clock():
            return now[0]

        def sleep(seconds):
            now[0] += seconds

        def opener(url, timeout):
            calls.append((now[0], timeout))
            return b"[]"

        client = pilot.BoundedClient(opener, clock, sleep, max_requests=2)
        client.get(pilot.legals_bbl_url(1, 10, 1))
        client.get(pilot.legals_bbl_url(2, 10, 1))
        self.assertEqual(calls, [(0.0, 30), (1.0, 30)])
        self.assertRaisesRegex(
            ValueError, "request cap", client.get, pilot.legals_bbl_url(3, 10, 1)
        )
        self.assertRaisesRegex(
            ValueError,
            "URL",
            pilot.BoundedClient(lambda *_: b"[]").get,
            "https://data.cityofnewyork.us/resource/8h5j-fqxa.json?" + "x" * 4096,
        )
        self.assertRaisesRegex(
            ValueError,
            "API URL",
            pilot.BoundedClient(lambda *_: b"[]").get,
            "https://evil.example/resource/8h5j-fqxa.json",
        )
        self.assertEqual(pilot._status_for(TimeoutError("private")), "timeout")
        self.assertEqual(
            pilot._status_for(URLError(TimeoutError("private"))), "timeout"
        )
        self.assertEqual(pilot._status_for(OSError("private")), "io_error")
        self.assertEqual(pilot._status_for(ValueError("private")), "validation_error")

    def test_missing_selected_identity_is_incomplete_without_replacement(self):
        selected = v1.verify_and_select(self.snapshot, self.ledger)
        selected[0] = {**selected[0], "status": "missing_identity"}
        state = {"protocol": pilot.PROTOCOL, "selected": selected, "intents": []}
        aggregate, _, pending = pilot._derive(state, selected, self.root)
        self.assertEqual(aggregate["status"], "INCOMPLETE_ERROR")
        self.assertFalse(aggregate["four_bbl_queries_finished"])
        self.assertEqual(len([x for x in pending if x[0] == "bbl"]), 3)
