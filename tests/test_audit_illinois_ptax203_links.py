"""Offline, synthetic checks for Cook–PTAX linkage without label promotion."""

from __future__ import annotations

from contextlib import ExitStack
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import audit_illinois_ptax203_links as audit
from scripts import probe_illinois_ptax203 as probe


def cook_row(identifier: str, document: str, **updates: object) -> dict:
    return {
        "row_id": identifier,
        "doc_no": document,
        "year": "2025",
        "pin": "01234567890123",
        "sale_price": "100.00",
        "sale_date": "2025-02-05T00:00:00.000",
        "is_multisale": False,
        "num_parcels_sale": "1",
        **updates,
    }


def ptax_row(identifier: str, document: str, **updates: object) -> dict:
    return {
        "declaration_id": identifier,
        "document_number": document,
        "line_1_county": "Cook",
        "line_1_primary_pin": "01234567890123",
        "line_2_total_parcels": "1",
        "line_3_additional_pins": False,
        "line_11_full_consideration": "100.0",
        "line_12a_total_personal": "0",
        "line_13_net_consideration": "99",
        "date_recorded": "2025-02-05T00:00:00.000",
        "line_4_instrument_date": "2025-01-01T00:00:00.000",
        "line_10b_sale_between_related": False,
        "status": "A",
        "line_8_current_use": "Residential",
        "line_5_instrument_type": "Deed",
        **updates,
    }


class OfflineLinkTests(unittest.TestCase):
    def test_zero_one_many_and_repeated_deed_grains(self):
        cook = [
            cook_row("a", "A"),
            cook_row("b", "A"),
            cook_row("c", "B"),
            cook_row("d", "C"),
        ]
        ptax = [ptax_row("p1", "A"), ptax_row("p2", "C"), ptax_row("p3", "C")]
        result = audit.build_worklist(cook, ptax, max_pairs=500)
        self.assertEqual(result["candidate_links"], 4)
        self.assertEqual(result["unique_document_strings"], 3)
        self.assertEqual(result["returned_declarations"], 3)
        self.assertEqual(
            [len(item["candidates"]) for item in result["items"]], [1, 1, 0, 2]
        )
        self.assertEqual(result["items"][0]["document_group_cook_rows"], 2)
        self.assertEqual(result["items"][1]["document_group_distinct_pins"], 1)
        self.assertEqual(result["items"][2]["priority_flags"][0], "missing_link")
        self.assertEqual(result["items"][3]["priority_flags"][0], "multiple_links")
        self.assertEqual(result["certified_sale_labels"], 0)

    def test_exact_string_no_normalization_and_duplicate_ids_rejected(self):
        rows = [
            cook_row("a", "001-23"),
            cook_row("b", "00123"),
            cook_row("c", " 001-23"),
        ]
        result = audit.build_worklist(rows, [ptax_row("p", "001-23")], max_pairs=10)
        self.assertEqual(
            [len(item["candidates"]) for item in result["items"]], [1, 0, 0]
        )
        with self.assertRaisesRegex(ValueError, "duplicate PTAX"):
            audit.build_worklist(
                rows, [ptax_row("p", "001-23"), ptax_row("p", "00123")], max_pairs=10
            )
        with self.assertRaisesRegex(ValueError, "candidate cap"):
            audit.build_worklist(rows, [ptax_row("p", "001-23")], max_pairs=0)

    def test_candidate_states_keep_conflicts_unknown_and_secondary_pin_ambiguity(self):
        cook = cook_row("a", "A", is_multisale=True, num_parcels_sale="2")
        declaration = ptax_row(
            "p",
            "A",
            line_1_county="DuPage",
            line_1_primary_pin="99999999999999",
            line_2_total_parcels="2",
            line_3_additional_pins=True,
            line_11_full_consideration="100.00",
            line_13_net_consideration="98.75",
            date_recorded="2025-02-06",
            line_10b_sale_between_related=True,
        )
        candidate = audit.build_worklist([cook], [declaration], max_pairs=1)["items"][
            0
        ]["candidates"][0]
        self.assertEqual(candidate["county_state"], "conflict")
        self.assertEqual(candidate["pin_state"], "possible_nonprimary")
        self.assertEqual(candidate["parcel_scope_state"], "multi_parcel_indicator")
        self.assertEqual(candidate["line_11_vs_cook_state"], "same")
        self.assertEqual(candidate["line_13_vs_cook_state"], "different")
        self.assertEqual(candidate["recorded_date_state"], "different")
        self.assertEqual(candidate["instrument_month_state"], "present_coarse")
        self.assertEqual(candidate["instrument_month_vs_cook_state"], "different_month")
        self.assertEqual(candidate["related_party_state"], "reported_true")

    def test_missing_malformed_and_false_remain_distinct(self):
        cook = cook_row(
            "a",
            "A",
            pin="",
            sale_price="NaN",
            sale_date="invalid",
            num_parcels_sale="?",
            is_multisale=None,
        )
        declaration = ptax_row(
            "p",
            "A",
            line_1_county="??",
            line_1_primary_pin="",
            line_2_total_parcels=None,
            line_3_additional_pins=None,
            line_11_full_consideration="Infinity",
            line_13_net_consideration=None,
            date_recorded="",
            line_4_instrument_date="bad",
            line_10b_sale_between_related=None,
            status=None,
        )
        candidate = audit.build_worklist([cook], [declaration], max_pairs=1)["items"][
            0
        ]["candidates"][0]
        self.assertEqual(candidate["county_state"], "unknown")
        self.assertEqual(candidate["pin_state"], "missing")
        self.assertEqual(candidate["parcel_scope_state"], "malformed")
        self.assertEqual(candidate["line_11_vs_cook_state"], "malformed")
        self.assertEqual(candidate["line_13_vs_cook_state"], "missing")
        self.assertEqual(candidate["recorded_date_state"], "missing")
        self.assertEqual(candidate["instrument_month_state"], "malformed")
        self.assertEqual(candidate["instrument_month_vs_cook_state"], "malformed")
        self.assertEqual(candidate["related_party_state"], "missing")
        self.assertEqual(candidate["status_code_state"], "missing")
        self.assertIn(
            "unresolved_evidence",
            audit.build_worklist([cook], [declaration], max_pairs=1)["items"][0][
                "priority_flags"
            ],
        )
        unknown_secondary = audit.build_worklist(
            [cook_row("u", "U")],
            [
                ptax_row(
                    "q3",
                    "U",
                    line_1_county="Mystery",
                    line_1_primary_pin="99999999999999",
                    line_3_additional_pins=None,
                )
            ],
            max_pairs=1,
        )["items"][0]["candidates"][0]
        self.assertEqual(unknown_secondary["county_state"], "unknown")
        self.assertEqual(
            unknown_secondary["pin_state"], "unequal_primary_unknown_secondary"
        )

    def test_unresolved_states_prioritized_without_explicit_disagreement(self):
        row = cook_row("r", "D")
        declaration = ptax_row(
            "p",
            "D",
            line_1_county="??",
            line_1_primary_pin="",
            line_2_total_parcels="bad",
            line_11_full_consideration="",
            date_recorded="not-a-date",
            status=None,
            line_8_current_use=None,
            line_5_instrument_type=None,
        )
        item = audit.build_worklist([row], [declaration], max_pairs=1)["items"][0]
        self.assertEqual(item["priority_flags"], ["unresolved_evidence"])

    def test_nonpositive_gross_or_net_amount_is_unresolved_not_a_match(self):
        row = cook_row("r", "D", sale_price="0")
        declaration = ptax_row(
            "p",
            "D",
            line_11_full_consideration="0.00",
            line_12a_total_personal="0",
            line_13_net_consideration="0",
            status=None,
            line_8_current_use=None,
            line_5_instrument_type=None,
        )
        item = audit.build_worklist([row], [declaration], max_pairs=1)["items"][0]
        candidate = item["candidates"][0]
        self.assertEqual(candidate["line_11_vs_cook_state"], "nonpositive")
        self.assertEqual(candidate["line_13_vs_cook_state"], "nonpositive")
        self.assertEqual(candidate["line_12_state"], "present")
        self.assertIn("unresolved_evidence", item["priority_flags"])
        negative = audit.build_worklist(
            [cook_row("n", "N", sale_price="-1")],
            [
                ptax_row(
                    "q",
                    "N",
                    line_11_full_consideration="-1",
                    line_12a_total_personal="-1",
                )
            ],
            max_pairs=1,
        )["items"][0]["candidates"][0]
        self.assertEqual(negative["line_11_vs_cook_state"], "nonpositive")
        self.assertEqual(negative["line_12_state"], "nonpositive")

    def test_each_missing_critical_field_triggers_unresolved_review(self):
        alterations = (
            {"line_1_primary_pin": ""},
            {"line_2_total_parcels": ""},
            {"line_11_full_consideration": ""},
            {"date_recorded": ""},
        )
        for change in alterations:
            with self.subTest(change=change):
                item = audit.build_worklist(
                    [cook_row("r", "D")],
                    [ptax_row("p", "D", **change)],
                    max_pairs=1,
                )["items"][0]
                self.assertIn("unresolved_evidence", item["priority_flags"])
        self.assertEqual(
            audit.build_worklist(
                [cook_row("b", "B")], [ptax_row("q", "B")], max_pairs=1
            )["items"][0]["candidates"][0]["related_party_state"],
            "reported_false",
        )
        malformed_day = audit.build_worklist(
            [cook_row("b", "B", sale_date="bad")],
            [ptax_row("q", "B", date_recorded="2025-02-05")],
            max_pairs=1,
        )["items"][0]["candidates"][0]
        self.assertEqual(malformed_day["recorded_date_state"], "malformed")
        self.assertEqual(
            audit.build_worklist(
                [cook_row("c", "C")],
                [ptax_row("q2", "C", line_4_instrument_date="2025-02-01")],
                max_pairs=1,
            )["items"][0]["candidates"][0]["instrument_month_vs_cook_state"],
            "same_month",
        )

    def test_public_projection_contains_only_prepublished_denominators_and_hashes(self):
        summary = audit.public_summary("a" * 64, "b" * 64, "c" * 64, 100)
        self.assertEqual(summary["certified_sale_labels"], 0)
        self.assertEqual(summary["review_queue_size"], 100)
        self.assertIs(summary["historical_asof_eligible"], False)
        self.assertEqual(summary["g_us_gate"], "PENDING")
        for forbidden in (
            "document_number",
            "pin",
            "price",
            "date",
            "candidate_links",
            "matched_count",
        ):
            self.assertNotIn(forbidden, json.dumps(summary).lower())
        with self.assertRaises(ValueError):
            audit.public_summary("bad", "b" * 64, "c" * 64, 100)

    def test_private_run_replays_exact_bytes_and_rejects_tamper(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            source.mkdir()
            private = root / audit.RUN_NAME
            output = root / "summary.json"
            rows = [cook_row(f"r{i}", f"D{i % 83}") for i in range(100)]
            declarations = [ptax_row(f"p{i}", f"D{i}") for i in range(80)]
            source_info = {
                "cook_capture_sha256": "a" * 64,
                "response_set_sha256": "b" * 64,
            }
            with ExitStack() as stack:
                stack.enter_context(
                    patch.object(
                        audit,
                        "_load_sources",
                        return_value=(rows, declarations, source_info),
                    )
                )

                def new_run():
                    private.mkdir(exist_ok=False)
                    return private

                stack.enter_context(
                    patch.object(audit, "_new_run", side_effect=new_run)
                )
                stack.enter_context(
                    patch.object(audit, "_private_root", return_value=root)
                )
                stack.enter_context(
                    patch.object(audit.private_io, "verify_acl", return_value=None)
                )
                stack.enter_context(
                    patch.object(
                        audit.private_io, "secure_directory", return_value=None
                    )
                )
                summary = audit.run(source, output)
                self.assertEqual(summary, audit.verify(private, source))
                self.assertEqual(json.loads(output.read_text()), summary)
                self.assertEqual(summary["review_queue_size"], 100)
                self.assertNotIn("D0", output.read_text())
                self.assertLess((private / "worklist.jsonl").stat().st_size, 512 * 1024)
                manifest = private / "complete.json"
                original_manifest = manifest.read_bytes()
                manifest.write_bytes(b"{}\n")
                with self.assertRaisesRegex(ValueError, "manifest"):
                    audit.verify(private, source)
                manifest.write_bytes(original_manifest)
                extra = root / "nested"
                extra.mkdir()
                with self.assertRaisesRegex(ValueError, "identity"):
                    audit.verify(extra, source)
                with self.assertRaises(FileExistsError):
                    audit.run(source, root / "again.json")
                (private / "worklist.jsonl").write_bytes(b"changed\n")
                with self.assertRaisesRegex(ValueError, "worklist"):
                    audit.verify(private, source)

    def test_failed_source_verification_produces_no_output(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "summary.json"
            with patch.object(
                audit, "_load_sources", side_effect=ValueError("source hash differs")
            ):
                self.assertEqual(
                    audit.main(
                        ["run", "--source-run-dir", str(root), "--output", str(output)]
                    ),
                    1,
                )
            self.assertFalse(output.exists())

    def test_unexpected_ptax_field_is_rejected_before_worklist(self):
        with self.assertRaisesRegex(ValueError, "Unexpected PTAX"):
            audit.build_worklist(
                [cook_row("r", "D")],
                [ptax_row("p", "D", buyer_name="private")],
                max_pairs=1,
            )

    def test_public_output_cannot_be_placed_inside_private_source_root(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary) / "private-root"
            root.mkdir()
            source = root / audit.SOURCE_RUN_NAME
            source.mkdir()
            output = root / "new-summary.json"
            with (
                patch.object(probe, "PRIVATE_ROOT", root),
                patch.object(audit, "_load_sources") as loader,
            ):
                self.assertEqual(
                    audit.main(
                        [
                            "run",
                            "--source-run-dir",
                            str(source),
                            "--output",
                            str(output),
                        ]
                    ),
                    1,
                )
                loader.assert_not_called()
            self.assertFalse(output.exists())

    def test_public_output_cannot_be_placed_elsewhere_in_data_raw(self):
        with TemporaryDirectory() as temporary:
            raw = Path(temporary) / "data" / "raw"
            source = raw / "illinois_ptax203" / audit.SOURCE_RUN_NAME
            source.mkdir(parents=True)
            other = raw / "other-source"
            other.mkdir()
            output = other / "summary.json"
            with (
                patch.object(audit, "RAW_ROOT", raw),
                patch.object(audit, "_load_sources") as loader,
            ):
                self.assertEqual(
                    audit.main(
                        [
                            "run",
                            "--source-run-dir",
                            str(source),
                            "--output",
                            str(output),
                        ]
                    ),
                    1,
                )
                loader.assert_not_called()
            self.assertFalse(output.exists())
            self.assertFalse((source.parent / audit.RUN_NAME).exists())

    def test_malformed_unicode_is_a_generic_cli_failure(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "summary.json"
            with patch.object(
                audit, "_load_sources", side_effect=UnicodeError("secret surrogate")
            ):
                self.assertEqual(
                    audit.main(
                        ["run", "--source-run-dir", str(root), "--output", str(output)]
                    ),
                    1,
                )
            self.assertFalse(output.exists())

    def test_loader_replays_all_frozen_response_bytes_and_detects_tamper(self):
        with TemporaryDirectory() as temporary:
            source = Path(temporary) / audit.SOURCE_RUN_NAME
            source.mkdir()
            selected_rows = [cook_row(f"r{i}", f"D{i % 83:03d}") for i in range(100)]
            cook_rows = [
                row
                for i, selected_row in enumerate(selected_rows)
                for row in (
                    cook_row(f"old{i}", selected_row["doc_no"], year="2023"),
                    selected_row,
                )
            ]
            self.assertEqual(len(cook_rows), 200)
            selected = probe.select_documents(cook_rows)
            batches = probe._batches(selected)
            self.assertEqual(len(batches), 9)
            bodies = [b"{}"]
            for batch in batches:
                declarations = [
                    ptax_row(f"p{int(document[1:])}", document)
                    for document in batch
                    if int(document[1:]) < 80
                ]
                bodies.extend(
                    (
                        probe._encoded([{"matched_count": str(len(declarations))}]),
                        probe._encoded(declarations),
                    )
                )
            bodies.append(b"{}")
            self.assertEqual(len(bodies), 20)
            response_sha = probe._hash(
                probe._encoded([probe._hash(body) for body in bodies])
            )
            for index, body in enumerate(bodies):
                (source / f"response-{index:02d}.json").write_bytes(body)
            info = {
                "response_set_sha256": response_sha,
                "cook_capture_sha256": audit.cook.CAPTURE_SHA256,
                "selected_cook_rows": 100,
                "unique_document_strings": 83,
                "returned_declarations": 80,
                "request_count": 20,
            }
            with ExitStack() as stack:
                stack.enter_context(
                    patch.object(audit, "PINNED_RESPONSE_SET_SHA256", response_sha)
                )
                stack.enter_context(patch.object(probe, "verify", return_value=info))
                stack.enter_context(
                    patch.object(audit.cook, "_capture_rows", return_value=cook_rows)
                )
                loaded_cook, loaded_ptax, loaded_info = audit._load_sources(source)
                self.assertEqual(loaded_cook, selected_rows)
                self.assertEqual(len(loaded_ptax), 80)
                self.assertEqual(loaded_info, info)
                (source / "response-02.json").write_bytes(b"[]")
                with self.assertRaisesRegex(ValueError, "response bytes"):
                    audit._load_sources(source)
                with self.assertRaisesRegex(ValueError, "identity"):
                    audit._load_sources(source.parent)


if __name__ == "__main__":
    unittest.main()
