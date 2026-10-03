"""Synthetic checks for private Cook / Additional PIN triage."""

from __future__ import annotations

from contextlib import ExitStack
from contextlib import redirect_stderr
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts import audit_illinois_additional_pins as audit
from scripts import audit_illinois_ptax203_links as prior
from scripts import probe_illinois_additional_pins as source


def cook(identifier: str, document: str, pin: object = "00123456789012") -> dict:
    return {"row_id": identifier, "doc_no": document, "pin": pin}


def ptax(
    identifier: str, document: str, pin: object = "00123456789012", **updates: object
) -> dict:
    return {
        "declaration_id": identifier,
        "document_number": document,
        "line_1_primary_pin": pin,
        "line_2_total_parcels": "1",
        "line_3_additional_pins": False,
        **updates,
    }


def additional(identifier: str, pin: object, **updates: object) -> dict:
    return {"declaration_id": identifier, "pin": pin, **updates}


class OfflineAdditionalPinTests(unittest.TestCase):
    def test_pin_relations_preserve_exact_format_and_leading_zero(self):
        self.assertEqual(
            audit.pin_relation("00123456789012", "00123456789012"), "raw_exact"
        )
        self.assertEqual(
            audit.pin_relation("00-12-345-678-9012", "00123456789012"),
            "display_equivalent",
        )
        self.assertEqual(
            audit.pin_relation("00123456789012", "PT00123456789012"), "part_parcel_lead"
        )
        self.assertEqual(
            audit.pin_relation("00123456789012", "PT 00-12-345-678-9012"),
            "part_parcel_lead",
        )
        self.assertEqual(
            audit.pin_relation("00123456789012", "ROW only"), "right_of_way"
        )
        self.assertEqual(
            audit.pin_relation("00123456789012", "row ONLY"), "right_of_way"
        )
        self.assertEqual(
            audit.pin_relation("00123456789012", "10123456789012"), "valid_unequal"
        )
        self.assertEqual(
            audit.pin_relation("00123456789012", "PT10123456789012"), "unknown"
        )
        self.assertEqual(audit.pin_relation("00123456789012", None), "missing")
        self.assertEqual(audit.pin_relation("00123456789012", ""), "missing")
        for invalid in (
            123456789012,
            " 00123456789012",
            "00123456789012 ",
            "00-12-345-678-9012-",
            "0012345678901²",
            "００１２３４５６７８９０１２",
            "PT  00123456789012",
            "PT/00123456789012",
        ):
            with self.subTest(invalid=invalid):
                self.assertEqual(
                    audit.pin_relation("00123456789012", invalid), "unknown"
                )

    def test_zero_one_many_duplicate_rows_and_repeated_deed_are_kept(self):
        rows = [cook("a", "A"), cook("b", "A"), cook("c", "B")]
        declarations = [
            ptax("d1", "A", line_3_additional_pins=True),
            ptax("d2", "A", line_3_additional_pins=True),
            ptax("d3", "B"),
        ]
        first = additional("d1", "00-12-345-678-9012", split_parcel="unknown text")
        observations = [
            first,
            first.copy(),
            additional("d1", "00123456789012", lot_size_units="x"),
            additional("d3", "10123456789012"),
        ]
        prior_items = prior.build_worklist(rows, declarations)["items"]
        result = audit.build_worklist(prior_items, declarations, observations)
        self.assertEqual(len(result["items"]), 3)
        self.assertEqual(
            [len(item["candidates"]) for item in result["items"]], [2, 2, 1]
        )
        candidate = result["items"][0]["candidates"][0]
        self.assertEqual(candidate["primary_relation"], "raw_exact")
        self.assertEqual(candidate["additional_observation_count"], 3)
        self.assertEqual(
            [ref["ordinal"] for ref in candidate["additional_observations"]], [1, 2, 3]
        )
        self.assertEqual(
            [ref["relation"] for ref in candidate["additional_observations"]],
            ["display_equivalent", "display_equivalent", "raw_exact"],
        )
        self.assertEqual(
            candidate["additional_observations"][0]["row_sha256"],
            candidate["additional_observations"][1]["row_sha256"],
        )
        self.assertIn("duplicate_observation", candidate["review_flags"])
        self.assertIn("multiple_distinct_additional_pins", candidate["review_flags"])
        self.assertIn("primary_and_additional_equality", candidate["review_flags"])
        self.assertEqual(result["items"][0]["ordinal"], 1)
        self.assertEqual(result["items"][1]["cook_row_id"], "b")
        self.assertIn("repeated_cook_document", result["items"][0]["review_flags"])
        self.assertIn("multiple_declarations", result["items"][0]["review_flags"])
        self.assertIn(
            "line3_true_zero_rows", result["items"][0]["candidates"][1]["review_flags"]
        )
        self.assertIn(
            "line3_false_with_rows", result["items"][2]["candidates"][0]["review_flags"]
        )
        self.assertNotIn("split_parcel", json.dumps(result))
        self.assertNotIn("unknown text", json.dumps(result))
        self.assertEqual(result["certified_sale_labels"], 0)

    def test_unrelated_declaration_invalid_input_and_caps_fail_closed(self):
        rows = [cook("a", "A")]
        declarations = [ptax("d1", "A")]
        previous = prior.build_worklist(rows, declarations)["items"]
        with self.assertRaisesRegex(ValueError, "outside|unrelated"):
            audit.build_worklist(
                previous, declarations, [additional("other", "00123456789012")]
            )
        with self.assertRaisesRegex(ValueError, "cap"):
            audit.build_worklist(
                previous,
                declarations,
                [additional("d1", "00123456789012")],
                max_references=0,
            )
        with self.assertRaisesRegex(ValueError, "cap"):
            audit.build_worklist(previous, declarations, [], max_pairs=0)
        with self.assertRaises(ValueError):
            audit.build_worklist(
                previous,
                declarations,
                [additional("d1", "00123456789012", buyer_name="secret")],
            )
        with self.assertRaises(ValueError):
            audit.build_worklist(previous, declarations + declarations, [])
        with self.assertRaises(ValueError):
            audit.build_worklist(previous + previous, declarations, [])
        with self.assertRaises(ValueError):
            audit.build_worklist(previous, declarations, [{"declaration_id": []}])

    def test_same_pin_in_nonidentical_rows_stays_two_references(self):
        rows = [cook("a", "A")]
        declarations = [ptax("d", "A")]
        observations = [
            additional("d", "00123456789012", split_parcel="yes"),
            additional("d", "00123456789012", split_parcel="unknown"),
        ]
        candidate = audit.build_worklist(
            prior.build_worklist(rows, declarations)["items"],
            declarations,
            observations,
        )["items"][0]["candidates"][0]
        self.assertEqual(candidate["additional_observation_count"], 2)
        self.assertEqual(candidate["additional_distinct_raw_pin_count"], 1)
        self.assertEqual(candidate["additional_duplicate_observation_count"], 0)
        self.assertNotEqual(
            candidate["additional_observations"][0]["row_sha256"],
            candidate["additional_observations"][1]["row_sha256"],
        )
        self.assertIn("repeated_pin_distinct_rows", candidate["review_flags"])
        self.assertNotIn("split_parcel", json.dumps(candidate))

    def test_reference_cap_and_prior_document_integrity(self):
        self.assertEqual(audit.PROTOCOL, "illinois-additional-pin-offline-v3")
        self.assertIn("offline-v3-", audit.RUN_NAME)
        rows = [cook("a", "A"), cook("b", "A"), cook("c", "A")]
        declarations = [ptax("d", "A")]
        previous = prior.build_worklist(rows, declarations)["items"]
        observations = [additional("d", "00123456789012") for _ in range(167)]
        result = audit.build_worklist(previous, declarations, observations)
        self.assertEqual(result["candidate_pairs"], 3)
        self.assertEqual(result["observation_references"], 501)
        boundary_rows = [cook(f"boundary{i}", "A") for i in range(10)]
        boundary_previous = prior.build_worklist(boundary_rows, declarations)["items"]
        boundary_observations = [additional("d", "00123456789012") for _ in range(500)]
        boundary = audit.build_worklist(
            boundary_previous, declarations, boundary_observations
        )
        self.assertEqual(boundary["observation_references"], 5000)
        many_rows = [cook(f"r{i}", "A") for i in range(11)] + [cook("last", "B")]
        many_declarations = declarations + [ptax("e", "B")]
        many_previous = prior.build_worklist(many_rows, many_declarations)["items"]
        many_observations = [additional("d", "00123456789012") for _ in range(454)]
        many_observations += [additional("e", "00123456789012") for _ in range(7)]
        just_over = audit.build_worklist(
            many_previous,
            many_declarations,
            many_observations,
            max_references=5001,
        )
        self.assertEqual(just_over["observation_references"], 5001)
        with self.assertRaisesRegex(ValueError, "cap"):
            audit.build_worklist(many_previous, many_declarations, many_observations)
        previous[0]["candidates"][0]["declaration_id"] = "missing"
        with self.assertRaisesRegex(ValueError, "outside"):
            audit.build_worklist(previous, declarations, [])
        previous[0]["candidates"][0]["declaration_id"] = "d"
        declarations[0]["document_number"] = "B"
        with self.assertRaisesRegex(ValueError, "document"):
            audit.build_worklist(previous, declarations, [])

    def test_loader_pins_replayed_additional_bytes_and_prior_public_hash(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            old = root / prior.RUN_NAME
            old.mkdir()
            rows = [cook("a", "A")]
            declarations = [ptax("d", "A")]
            old_result = prior.build_worklist(rows, declarations)
            old_content = prior._worklist_bytes(old_result)
            (old / "worklist.jsonl").write_bytes(old_content)
            old_hash = audit._hash(old_content)
            aggregate = root / "aggregate.json"
            aggregate.write_text(json.dumps({"private_worklist_sha256": old_hash}))
            responses = [b"metadata", b"rows"]
            response_hash = audit._hash(
                audit._encoded([audit._hash(body) for body in responses])
            )
            info = {"response_set_sha256": source.PTAX_SHA256}
            source_info = {
                "additional_response_set_sha256": response_hash,
                "cook_capture_sha256": source.COOK_SHA256,
                "ptax_response_set_sha256": source.PTAX_SHA256,
            }
            replay = {
                "responses": responses,
                "rows": [additional("d", "00123456789012")],
            }
            with ExitStack() as stack:
                stack.enter_context(
                    patch.object(prior, "_private_root", return_value=root)
                )
                stack.enter_context(
                    patch.object(
                        prior,
                        "verify",
                        return_value={"private_worklist_sha256": old_hash},
                    )
                )
                stack.enter_context(
                    patch.object(
                        prior, "_load_sources", return_value=(rows, declarations, info)
                    )
                )
                stack.enter_context(
                    patch.object(source, "verify", return_value=source_info)
                )
                source_replay = stack.enter_context(
                    patch.object(source, "_replay", return_value=replay)
                )
                stack.enter_context(
                    patch.object(audit, "PRIOR_WORKLIST_SHA256", old_hash)
                )
                stack.enter_context(
                    patch.object(audit, "ADDITIONAL_RESPONSE_SET_SHA256", response_hash)
                )
                stack.enter_context(patch.object(audit, "PRIOR_AGGREGATE", aggregate))
                loaded = audit._load_sources(root / source.RUN_NAME)
                self.assertEqual(loaded[2], replay["rows"])
                source_replay.return_value = {
                    "responses": [responses[0], b"future corrected row"],
                    "rows": [additional("d", "10123456789012")],
                }
                with self.assertRaisesRegex(ValueError, "frozen hash"):
                    audit._load_sources(root / source.RUN_NAME)
                source_replay.return_value = replay
                aggregate.write_text(json.dumps({"private_worklist_sha256": "f" * 64}))
                with self.assertRaisesRegex(ValueError, "Prior private worklist"):
                    audit._load_sources(root / source.RUN_NAME)

    def test_public_summary_is_fixed_allowlist(self):
        summary = audit.public_summary("a" * 64, "b" * 64, "c" * 64, "d" * 64, "e" * 64)
        self.assertEqual(summary["certified_sale_labels"], 0)
        self.assertEqual(summary["selected_cook_rows"], 100)
        self.assertEqual(summary["unique_document_strings"], 83)
        self.assertEqual(summary["returned_declarations"], 80)
        self.assertEqual(summary["u0_gate"], "PENDING")
        self.assertIs(summary["historical_asof_eligible"], False)
        for forbidden in (
            "pin",
            "price",
            "date",
            "match",
            "additional_rows",
            "candidate",
            "query_url",
        ):
            self.assertNotIn(forbidden, summary)
        with self.assertRaises(ValueError):
            audit.public_summary("bad", "b" * 64, "c" * 64, "d" * 64, "e" * 64)

    def test_run_and_replay_detect_tamper_acl_and_create_only(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            private = root / audit.RUN_NAME
            output = root / "summary.json"
            source_dir = root / source.RUN_NAME
            source_dir.mkdir()
            rows = [cook(f"r{i}", f"D{i % 83}") for i in range(100)]
            declarations = [ptax(f"d{i}", f"D{i % 83}") for i in range(80)]
            previous = prior.build_worklist(rows, declarations)["items"]
            observations = [additional("d1", "00123456789012")]
            expected_info = ("a" * 64, "b" * 64, "c" * 64, "d" * 64)
            with ExitStack() as stack:
                stack.enter_context(
                    patch.object(
                        audit,
                        "_load_sources",
                        return_value=(
                            previous,
                            declarations,
                            observations,
                            expected_info,
                        ),
                    )
                )
                stack.enter_context(
                    patch.object(audit, "_private_root", return_value=root)
                )
                stack.enter_context(
                    patch.object(
                        audit, "_new_run", side_effect=lambda: self._new_run(private)
                    )
                )
                acl = stack.enter_context(patch.object(audit.private_io, "verify_acl"))
                summary = audit.run(source_dir, output)
                self.assertEqual(summary, audit.verify(private, source_dir))
                self.assertEqual(json.loads(output.read_text()), summary)
                self.assertNotIn("00123456789012", output.read_text())
                self.assertEqual(
                    len((private / "worklist.jsonl").read_text().splitlines()), 100
                )
                acl.side_effect = ValueError("ACL failure")
                with self.assertRaisesRegex(ValueError, "ACL"):
                    audit.verify(private, source_dir)
                acl.side_effect = None
                with self.assertRaises(FileExistsError):
                    audit.run(source_dir, root / "again.json")
                original = (private / "worklist.jsonl").read_bytes()
                (private / "worklist.jsonl").write_bytes(b"tamper\n")
                with self.assertRaisesRegex(ValueError, "worklist"):
                    audit.verify(private, source_dir)
                (private / "worklist.jsonl").write_bytes(original)
                (private / "complete.json").write_bytes(b"{}\n")
                with self.assertRaisesRegex(ValueError, "manifest"):
                    audit.verify(private, source_dir)

    def test_private_directory_is_create_only_and_acl_checked(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            with (
                patch.object(source, "_private_root", return_value=root),
                patch.object(audit.private_io, "secure_directory") as secure,
                patch.object(audit.private_io, "verify_acl") as acl,
            ):
                directory = audit._new_run()
                self.assertEqual(directory, root / audit.RUN_NAME)
                secure.assert_called_once_with(directory)
                acl.assert_called_once_with(directory)
                with self.assertRaises(FileExistsError):
                    audit._new_run()

    def test_public_output_boundary_and_cli_error_are_generic(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_dir = root / source.RUN_NAME
            source_dir.mkdir()
            private_output = root / "data" / "raw" / "aggregate.json"
            private_output.parent.mkdir(parents=True)
            with patch.object(prior, "RAW_ROOT", private_output.parent):
                with self.assertRaisesRegex(ValueError, "private"):
                    audit._public_destination(private_output, source_dir)
            output = root / "summary.json"
            error = StringIO()
            with (
                patch.object(
                    audit, "_load_sources", side_effect=ValueError("secret row 123")
                ),
                redirect_stderr(error),
            ):
                result = audit.main(
                    [
                        "run",
                        "--source-run-dir",
                        str(source_dir),
                        "--output",
                        str(output),
                    ]
                )
            self.assertEqual(result, 1)
            self.assertFalse(output.exists())
            self.assertNotIn("secret row 123", error.getvalue())

    def test_worklist_byte_cap_fails_before_public_write(self):
        result = audit.build_worklist(
            prior.build_worklist([cook("a", "A")], [ptax("d", "A")])["items"],
            [ptax("d", "A")],
            [additional("d", "00123456789012")],
        )
        with (
            patch.object(audit, "MAX_WORKLIST_BYTES", 1),
            self.assertRaisesRegex(ValueError, "worklist cap"),
        ):
            audit._worklist_bytes(result)

    @staticmethod
    def _new_run(directory: Path) -> Path:
        directory.mkdir(exist_ok=False)
        return directory


if __name__ == "__main__":
    unittest.main()
