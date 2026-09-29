"""Contract tests for the frozen four-row ACRIS source-qualification pilot."""

from __future__ import annotations

import csv
from hashlib import sha256
from io import StringIO
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import audit_nyc_acris_matches as pilot  # noqa: E402
import profile_nyc_rolling_snapshot as profile  # noqa: E402


def _csv(records: list[dict[str, str]]) -> bytes:
    stream = StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=profile.HEADER)
    writer.writeheader()
    writer.writerows(records)
    return stream.getvalue().encode()


def _row(borough: int, block: str = "10", lot: str = "1") -> dict[str, str]:
    return dict.fromkeys(profile.HEADER, "") | {
        "BOROUGH": str(borough),
        "BLOCK": block,
        "LOT": lot,
        "SALE DATE": "01/01/2026",
        "SALE PRICE": "123456",
        "ADDRESS": "Private fixture address",
    }


def _ledger(rows: list[dict[str, str]]) -> bytes:
    entries = []
    for ordinal, row in enumerate(rows, 1):
        rank = sha256(
            f"nyc-review-v1|{pilot.SNAPSHOT_SHA256}|42|{ordinal}".encode()
        ).hexdigest()
        entries.append(
            {
                "ordinal": ordinal,
                "rank": rank,
                "structural_cell": f"{row['BOROUGH']}:candidate",
                "primary_bucket": "structural",
                "edge_flags": {},
            }
        )
    return ("\n".join(json.dumps(row) for row in entries) + "\n").encode()


class PilotTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.raw = self.root / "data" / "raw" / "nyc_dof"
        self.raw.mkdir(parents=True)
        self.csv_path = self.raw / "rolling.csv"
        self.ledger_path = self.raw / "ledger.jsonl"
        self.run = self.raw / "pilot-run"
        self.rows = [_row(b) for b in range(1, 6)] + [_row(1, "11")]
        self.prepare()
        root_patch = patch.object(profile, "PRIVATE_ROOT", self.raw)
        root_patch.start()
        self.addCleanup(root_patch.stop)

    def prepare(self):
        body = _csv(self.rows)
        self.csv_path.write_bytes(body)
        csv_patch = patch.object(pilot, "SNAPSHOT_SHA256", sha256(body).hexdigest())
        csv_patch.start()
        self.addCleanup(csv_patch.stop)
        count_patch = patch.object(pilot, "SNAPSHOT_ROWS", len(self.rows))
        count_patch.start()
        self.addCleanup(count_patch.stop)
        ledger = _ledger(self.rows)
        self.ledger_path.write_bytes(ledger)
        ledger_patch = patch.object(pilot, "LEDGER_SHA256", sha256(ledger).hexdigest())
        ledger_patch.start()
        self.addCleanup(ledger_patch.stop)
        selected_patch = patch.object(pilot, "LEDGER_ROWS", len(self.rows))
        selected_patch.start()
        self.addCleanup(selected_patch.stop)

    def test_selection_uses_min_rank_per_borough_and_ignores_staten_island(self):
        selected = pilot.verify_and_select(self.csv_path, self.ledger_path)
        self.assertEqual([item["borough"] for item in selected], [1, 2, 3, 4])
        self.assertEqual(len(selected), 4)
        self.assertEqual(
            selected[0]["ordinal"],
            min(
                (1, 6),
                key=lambda ordinal: sha256(
                    f"nyc-review-v1|{pilot.SNAPSHOT_SHA256}|42|{ordinal}".encode()
                ).hexdigest(),
            ),
        )

    def test_missing_numeric_identity_is_not_replaced(self):
        self.rows[1]["BLOCK"] = "unknown"
        self.prepare()
        selected = pilot.verify_and_select(self.csv_path, self.ledger_path)
        self.assertEqual(selected[1]["status"], "missing_identity")

    def test_source_or_ledger_tamper_rejected(self):
        self.csv_path.write_bytes(self.csv_path.read_bytes() + b"extra")
        with self.assertRaisesRegex(ValueError, "Snapshot SHA"):
            pilot.verify_and_select(self.csv_path, self.ledger_path)
        self.prepare()
        self.ledger_path.write_bytes(self.ledger_path.read_bytes() + b"extra")
        with self.assertRaisesRegex(ValueError, "ledger SHA"):
            pilot.verify_and_select(self.csv_path, self.ledger_path)

    def test_rank_or_structural_cell_tamper_rejected_even_with_new_hash(self):
        entries = [
            json.loads(line) for line in self.ledger_path.read_text().splitlines()
        ]
        entries[0]["rank"] = "0" * 64
        body = ("\n".join(json.dumps(row) for row in entries) + "\n").encode()
        self.ledger_path.write_bytes(body)
        with patch.object(pilot, "LEDGER_SHA256", sha256(body).hexdigest()):
            with self.assertRaisesRegex(ValueError, "rank"):
                pilot.verify_and_select(self.csv_path, self.ledger_path)

    def test_private_paths_required(self):
        outside = self.root / "copy.csv"
        outside.write_bytes(self.csv_path.read_bytes())
        with self.assertRaisesRegex(ValueError, "private"):
            pilot.verify_and_select(outside, self.ledger_path)

    def test_queries_are_exact_and_never_use_price(self):
        url = pilot.legals_bbl_url(2, 123, 5)
        query = parse_qs(urlsplit(url).query)
        self.assertEqual(query["$where"], ["borough=2 AND block=123 AND lot=5"])
        self.assertEqual(query["$limit"], ["251"])
        self.assertNotIn("123456", url)
        self.assertIn("document_id", pilot.master_url("2026010100001"))
        self.assertIn("%24limit=101", pilot.legals_document_url("2026010100001"))
        with self.assertRaises(ValueError):
            pilot.master_url("x' OR true")

    def test_client_limits_requests_bytes_rate_and_timeout(self):
        calls = []
        clock = [0.0]

        def opener(url, timeout):
            calls.append((url, timeout, clock[0]))
            return b"[]"

        def sleep(seconds):
            clock[0] += seconds

        client = pilot.BoundedClient(opener, lambda: clock[0], sleep, max_requests=2)
        client.get("https://data.cityofnewyork.us/resource/8h5j-fqxa.json")
        client.get("https://data.cityofnewyork.us/resource/8h5j-fqxa.json")
        self.assertEqual(calls[1][2] - calls[0][2], 1.0)
        self.assertEqual(calls[0][1], 30)
        with self.assertRaisesRegex(ValueError, "request cap"):
            client.get("https://data.cityofnewyork.us/resource/8h5j-fqxa.json")
        with self.assertRaisesRegex(ValueError, "response byte"):
            pilot.BoundedClient(lambda *_: b"x" * (1024 * 1024 + 1)).get(
                "https://data.cityofnewyork.us/resource/8h5j-fqxa.json"
            )
        with self.assertRaises(ValueError):
            pilot.BoundedClient(lambda *_: b"[]").get("https://evil.example/x")

    def test_saturated_and_malformed_responses_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "saturated"):
            pilot.parse_rows(json.dumps([{}] * 251).encode(), 250)
        with self.assertRaisesRegex(ValueError, "malformed"):
            pilot.parse_rows(b"{}", 250)
        with self.assertRaisesRegex(ValueError, "malformed"):
            pilot.parse_rows(b"[2]", 250)
        with self.assertRaisesRegex(ValueError, "malformed"):
            pilot.parse_rows(b"not-json", 250)

    def test_pilot_preserves_all_candidates_and_private_responses(self):
        requests = []

        def opener(url, timeout):
            requests.append(url)
            where = parse_qs(urlsplit(url).query)["$where"][0]
            if where.startswith("borough="):
                parts = where.replace(" AND ", "=").split("=")
                borough, block, lot = parts[1], parts[3], parts[5]
                return json.dumps(
                    [
                        {
                            "document_id": f"D{borough}",
                            "borough": borough,
                            "block": block,
                            "lot": lot,
                        }
                    ]
                ).encode()
            identifier = where.split("'")[1]
            if "bnx9-e6tj" in url:
                return json.dumps(
                    [
                        {
                            "document_id": identifier,
                            "doc_type": "DEED",
                            "document_date": "2026-01-02",
                            "recorded_datetime": "2026-01-20",
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
                    },
                    {
                        "document_id": identifier,
                        "borough": "1",
                        "block": "12",
                        "lot": "1",
                    },
                ]
            ).encode()

        result = pilot.run_pilot(
            self.csv_path,
            self.ledger_path,
            self.run,
            opener=opener,
            sleep=lambda _: None,
        )
        self.assertEqual(result["status"], "completed_provisional_pilot")
        self.assertEqual(result["counts_by_borough"]["1"]["ambiguous"], 1)
        self.assertEqual(result["ambiguity_reasons"]["multiple_lots"], 4)
        self.assertEqual(result["candidate_document_types"]["DEED"], 4)
        self.assertTrue(list(self.run.glob("response-*.json")))
        self.assertNotIn("D1", json.dumps(result))
        self.assertNotIn("Private fixture", json.dumps(result))
        before = len(requests)
        self.assertEqual(
            result,
            pilot.run_pilot(self.csv_path, self.ledger_path, self.run, opener=opener),
        )
        self.assertEqual(len(requests), before)
        state_path = self.run / "state.json"
        original = json.loads(state_path.read_text())
        changes = (
            ("ambiguity_reasons", "multiple_lots", 99, "aggregate"),
            ("candidate_document_types", "DEED", 99, "aggregate"),
        )
        for field, key, value, message in changes:
            with self.subTest(field=field):
                tampered = json.loads(json.dumps(original))
                tampered["aggregate"][field][key] = value
                state_path.write_text(json.dumps(tampered))
                with self.assertRaisesRegex(ValueError, message):
                    pilot.run_pilot(
                        self.csv_path,
                        self.ledger_path,
                        self.run,
                        opener=lambda *_: self.fail("network"),
                    )
        tampered = json.loads(json.dumps(original))
        key = next(iter(tampered["inspection_order"]))
        tampered["inspection_order"][key] = ["FORGED"]
        state_path.write_text(json.dumps(tampered))
        with self.assertRaisesRegex(ValueError, "inspection order"):
            pilot.run_pilot(
                self.csv_path,
                self.ledger_path,
                self.run,
                opener=lambda *_: self.fail("network"),
            )

    def test_failure_is_incomplete_and_replay_makes_no_new_request(self):
        def bad_opener(url, timeout):
            raise TimeoutError("private URL context")

        result = pilot.run_pilot(
            self.csv_path,
            self.ledger_path,
            self.run,
            opener=bad_opener,
            sleep=lambda _: None,
        )
        self.assertEqual(result["status"], "incomplete")
        self.assertNotIn("private URL", json.dumps(result))
        self.assertEqual(
            result,
            pilot.run_pilot(
                self.csv_path,
                self.ledger_path,
                self.run,
                opener=lambda *_: self.fail("network"),
            ),
        )

    def test_replay_rejects_traversal_and_tampered_response(self):
        pilot.run_pilot(
            self.csv_path, self.ledger_path, self.run, opener=lambda *_: b"[]"
        )
        state_path = self.run / "state.json"
        state = json.loads(state_path.read_text())
        state["responses"][0]["filename"] = "../rolling.csv"
        state_path.write_text(json.dumps(state))
        with self.assertRaisesRegex(ValueError, "saved response"):
            pilot.run_pilot(
                self.csv_path,
                self.ledger_path,
                self.run,
                opener=lambda *_: self.fail("network"),
            )
        state["responses"][0]["filename"] = "response-001.json"
        state_path.write_text(json.dumps(state))
        (self.run / "response-001.json").write_bytes(b"{}")
        with self.assertRaisesRegex(ValueError, "response hash"):
            pilot.run_pilot(
                self.csv_path,
                self.ledger_path,
                self.run,
                opener=lambda *_: self.fail("network"),
            )

    def test_unrequested_fields_are_not_persisted(self):
        body = json.dumps(
            [
                {
                    "document_id": "D1",
                    "borough": "1",
                    "block": "10",
                    "lot": "1",
                    "party_name": "PRIVATE_PERSON",
                }
            ]
        ).encode()
        result = pilot.run_pilot(
            self.csv_path, self.ledger_path, self.run, opener=lambda *_: body
        )
        self.assertEqual(result["status"], "incomplete")
        self.assertNotIn("PRIVATE_PERSON", (self.run / "state.json").read_text())
        self.assertFalse(list(self.run.glob("response-*.json")))

    def test_conflicting_exact_bbl_response_is_incomplete(self):
        body = json.dumps(
            [
                {
                    "document_id": "D1",
                    "borough": "4",
                    "block": "10",
                    "lot": "1",
                }
            ]
        ).encode()
        result = pilot.run_pilot(
            self.csv_path, self.ledger_path, self.run, opener=lambda *_: body
        )
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(result["sale_labels_certified"], 0)

    def test_missing_identity_makes_no_replacement_query(self):
        self.rows[0]["LOT"] = ""
        self.rows[5]["LOT"] = ""
        self.prepare()
        requested = []

        def opener(url, timeout):
            requested.append(url)
            return b"[]"

        result = pilot.run_pilot(
            self.csv_path,
            self.ledger_path,
            self.run,
            opener=opener,
            sleep=lambda _: None,
        )
        self.assertEqual(result["counts_by_borough"]["1"], {"missing_identity": 1})
        self.assertEqual(len(requested), 3)

    def test_saturated_live_response_stops_without_a_valid_match(self):
        result = pilot.run_pilot(
            self.csv_path,
            self.ledger_path,
            self.run,
            opener=lambda *_: json.dumps([{}] * 251).encode(),
            sleep=lambda _: None,
        )
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(result["sale_labels_certified"], 0)

    def test_inspection_order_retains_outside_window_and_unknown_date(self):
        order = pilot.inspection_order(
            "01/01/2026",
            [
                ("OUTSIDE", [{"document_date": "2024-01-01T00:00:00.000"}]),
                ("NEAR", [{"document_date": "2026-01-02T00:00:00.000"}]),
                ("UNKNOWN", [{"document_date": ""}]),
            ],
        )
        self.assertEqual(order, ["NEAR", "OUTSIDE", "UNKNOWN"])
        with self.assertRaisesRegex(ValueError, "sale date"):
            pilot.inspection_order("not-a-date", [])

    def test_replay_rejects_wrong_query_and_state_status(self):
        pilot.run_pilot(
            self.csv_path,
            self.ledger_path,
            self.run,
            opener=lambda *_: b"[]",
            sleep=lambda _: None,
        )
        state_path = self.run / "state.json"
        state = json.loads(state_path.read_text())
        state["responses"][0]["url"] = pilot.legals_bbl_url(4, 999, 1)
        state_path.write_text(json.dumps(state))
        with self.assertRaisesRegex(ValueError, "query sequence"):
            pilot.run_pilot(
                self.csv_path,
                self.ledger_path,
                self.run,
                opener=lambda *_: self.fail("network"),
            )
        first = pilot.verify_and_select(self.csv_path, self.ledger_path)[0]
        state["responses"][0]["url"] = pilot.legals_bbl_url(
            first["borough"], int(first["block"]), int(first["lot"])
        )
        state["status"] = "complete"
        state["aggregate"]["status"] = "incomplete"
        state_path.write_text(json.dumps(state))
        with self.assertRaisesRegex(ValueError, "state status"):
            pilot.run_pilot(
                self.csv_path,
                self.ledger_path,
                self.run,
                opener=lambda *_: self.fail("network"),
            )

    def test_incomplete_state_can_replay_after_all_responses_were_saved(self):
        pilot.run_pilot(
            self.csv_path,
            self.ledger_path,
            self.run,
            opener=lambda *_: b"[]",
            sleep=lambda _: None,
        )
        state_path = self.run / "state.json"
        state = json.loads(state_path.read_text())
        state["status"] = "incomplete"
        state["aggregate"] = {"status": "incomplete", "sale_labels_certified": 0}
        state_path.write_text(json.dumps(state))
        result = pilot.run_pilot(
            self.csv_path,
            self.ledger_path,
            self.run,
            opener=lambda *_: self.fail("network"),
        )
        self.assertEqual(result["status"], "incomplete")

    def test_http_redirect_is_rejected_before_second_request(self):
        destinations = []

        class FakeOpener:
            def __init__(self, handlers):
                self.handlers = handlers

            def open(self, url, timeout):
                destinations.append(url)
                request = Request(url)
                return self.handlers[0].redirect_request(
                    request, None, 302, "Found", {}, "https://other.example/private"
                )

        with patch.object(
            pilot, "build_opener", side_effect=lambda *handlers: FakeOpener(handlers)
        ):
            with self.assertRaisesRegex(ValueError, "redirect"):
                pilot._http_get(
                    "https://data.cityofnewyork.us/resource/8h5j-fqxa.json", 30
                )
        self.assertEqual(len(destinations), 1)

    def test_replay_recomputes_reported_counts(self):
        pilot.run_pilot(
            self.csv_path,
            self.ledger_path,
            self.run,
            opener=lambda *_: b"[]",
            sleep=lambda _: None,
        )
        state_path = self.run / "state.json"
        state = json.loads(state_path.read_text())
        state["aggregate"]["counts_by_borough"]["1"]["no_acris_candidate"] = 99
        state_path.write_text(json.dumps(state))
        with self.assertRaisesRegex(ValueError, "aggregate"):
            pilot.run_pilot(
                self.csv_path,
                self.ledger_path,
                self.run,
                opener=lambda *_: self.fail("network"),
            )

    def test_replay_rejects_forged_inspection_order(self):
        # This synthetic state has complete BBL evidence and no document order.
        pilot.run_pilot(
            self.csv_path,
            self.ledger_path,
            self.run,
            opener=lambda *_: b"[]",
            sleep=lambda _: None,
        )
        state_path = self.run / "state.json"
        state = json.loads(state_path.read_text())
        state["inspection_order"] = {"1": ["PRIVATE_FAKE_DOCUMENT"]}
        state_path.write_text(json.dumps(state))
        with self.assertRaisesRegex(ValueError, "inspection order"):
            pilot.run_pilot(
                self.csv_path,
                self.ledger_path,
                self.run,
                opener=lambda *_: self.fail("network"),
            )

    def test_blank_unit_is_ambiguous_and_type_output_is_fixed_category(self):
        status, reasons = pilot._summarize(
            [{"document_id": "D1", "doc_type": "DEED"}],
            [
                {
                    "document_id": "D1",
                    "borough": "1",
                    "block": "10",
                    "lot": "1",
                    "unit": "",
                }
            ],
        )
        self.assertEqual(status, "ambiguous")
        self.assertIn("blank_or_missing_unit", reasons)
        self.assertEqual(pilot.document_type_category("Person Like Name"), "OTHER")
        self.assertEqual(pilot.document_type_category("DEED"), "DEED")
        self.assertEqual(pilot.document_type_category("MTGE"), "MORTGAGE")
        self.assertEqual(pilot.document_type_category(""), "UNKNOWN")

    def test_missing_linked_record_is_unresolved_with_reason_preserved(self):
        status, reasons, categories = pilot._document_summary(
            ["D1"], [("D1", [], [{"document_id": "D1", "unit": "A"}])]
        )
        self.assertEqual(status, "unresolved")
        self.assertEqual(reasons, {"missing_linked_record"})
        self.assertFalse(categories)

    def test_name_like_api_document_type_never_reaches_aggregate(self):
        private_type = "PERSON PRIVATE TYPE"

        def opener(url, timeout):
            where = parse_qs(urlsplit(url).query)["$where"][0]
            if where.startswith("borough="):
                parts = where.replace(" AND ", "=").split("=")
                return json.dumps(
                    [
                        {
                            "document_id": f"D{parts[1]}",
                            "borough": parts[1],
                            "block": parts[3],
                            "lot": parts[5],
                        }
                    ]
                ).encode()
            identifier = where.split("'")[1]
            if "bnx9-e6tj" in url:
                return json.dumps(
                    [{"document_id": identifier, "doc_type": private_type}]
                ).encode()
            return json.dumps(
                [
                    {
                        "document_id": identifier,
                        "borough": "1",
                        "block": "10",
                        "lot": "1",
                        "unit": "2",
                    }
                ]
            ).encode()

        result = pilot.run_pilot(
            self.csv_path,
            self.ledger_path,
            self.run,
            opener=opener,
            sleep=lambda _: None,
        )
        self.assertEqual(result["status"], "completed_provisional_pilot")
        self.assertEqual(result["candidate_document_types"], {"OTHER": 4})
        self.assertNotIn(private_type, json.dumps(result))

    def test_failure_categories_are_sanitized_and_cli_exits_nonzero(self):
        self.assertEqual(pilot.failure_category(TimeoutError("private URL")), "timeout")
        self.assertEqual(
            pilot.failure_category(ValueError("API response is saturated")), "saturated"
        )
        self.assertEqual(
            pilot.failure_category(OSError("private file path")), "io_error"
        )
        with (
            patch.object(pilot, "run_pilot", return_value={"status": "incomplete"}),
            patch.object(
                sys,
                "argv",
                [
                    "audit_nyc_acris_matches.py",
                    "--snapshot",
                    "x",
                    "--ledger",
                    "y",
                    "--private-run-dir",
                    "z",
                ],
            ),
            patch("builtins.print"),
        ):
            with self.assertRaises(SystemExit) as stopped:
                pilot.main()
        self.assertEqual(stopped.exception.code, 1)


if __name__ == "__main__":
    unittest.main()
