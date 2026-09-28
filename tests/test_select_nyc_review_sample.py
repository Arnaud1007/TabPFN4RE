"""Synthetic tests for the frozen, private NYC source-review sample."""

from __future__ import annotations

import csv
from collections import Counter
from hashlib import sha256
from io import BytesIO, StringIO
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import profile_nyc_rolling_snapshot as profiler  # noqa: E402
import select_nyc_review_sample as selector  # noqa: E402


def row(**changes: str) -> tuple[str, ...]:
    values = {
        "BOROUGH": "1",
        "BLOCK": "1",
        "LOT": "1",
        "BUILDING CLASS CATEGORY": "01 ONE FAMILY DWELLINGS",
        "BUILDING CLASS AT TIME OF SALE": "A1",
        "APARTMENT NUMBER": "1",
        "GROSS SQUARE FEET": "1200",
        "SALE PRICE": "100000",
        "SALE DATE": "2026-01-01",
        "ADDRESS": "123 Private Address",
    } | changes
    return tuple(values.get(field, "") for field in profiler.HEADER)


def csv_bytes(rows: list[tuple[str, ...]], *, header=profiler.HEADER) -> bytes:
    buffer = StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow(header)
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def sufficient_rows() -> list[tuple[str, ...]]:
    rows = []
    for borough in "12345":
        for group in ("candidate", "other_or_ambiguous"):
            for index in range(30):
                values = {
                    "BOROUGH": borough,
                    "BLOCK": f"{borough}{index + 1}",
                    "LOT": f"{index + 1}",
                    "SALE DATE": "2026-01-01",
                    "SALE PRICE": "100000",
                }
                if group == "other_or_ambiguous":
                    values["BUILDING CLASS CATEGORY"] = "02 TWO FAMILY"
                    values["BUILDING CLASS AT TIME OF SALE"] = "B1"
                    values["LOT"] = f"{index + 101}"
                rows.append(row(**values))
    for index in range(40):
        rows.append(
            row(
                **{
                    "BLOCK": f"900{index}",
                    "LOT": "1",
                    "SALE PRICE": "0",
                    "GROSS SQUARE FEET": "",
                    "SALE DATE": "2025-09-01",
                }
            )
        )
    for index in range(20):
        rows.append(
            row(
                **{
                    "BLOCK": f"800{index}",
                    "LOT": "1",
                    "BUILDING CLASS CATEGORY": "13 CONDOS",
                    "BUILDING CLASS AT TIME OF SALE": "R4",
                    "APARTMENT NUMBER": "",
                    "SALE DATE": "2026-08-01",
                }
            )
        )
    for index in range(20):
        repeated = row(**{"BLOCK": f"700{index}", "LOT": "1"})
        rows.extend((repeated, repeated))
    return rows


def independent_expected_selection(rows, source_hash):
    """A fixture-only oracle, separate from the selector's parsers and ranking."""
    fields = [dict(zip(profiler.HEADER, values, strict=True)) for values in rows]
    keys = [
        tuple(
            record[name].strip()
            for name in ("BOROUGH", "BLOCK", "LOT", "SALE DATE", "SALE PRICE")
        )
        for record in fields
    ]
    counts = Counter(key for key in keys if all(key))
    ranks = {
        ordinal: sha256(
            f"nyc-review-v1|{source_hash}|42|{ordinal}".encode("utf-8")
        ).hexdigest()
        for ordinal in range(1, len(rows) + 1)
    }
    facts = {}
    for ordinal, record in enumerate(fields, 1):
        price = record["SALE PRICE"].strip()
        gross = record["GROSS SQUARE FEET"].strip()
        sale_class = record["BUILDING CLASS AT TIME OF SALE"].strip().upper()
        candidate = sale_class.startswith("A") and record[
            "BUILDING CLASS CATEGORY"
        ].strip().upper().startswith("01 ONE FAMILY")
        flags = {
            "price": not price or float(price.replace(",", "")) <= 1000,
            "identity": not record["BLOCK"].strip()
            or not record["LOT"].strip()
            or (sale_class.startswith("R") and not record["APARTMENT NUMBER"].strip()),
            "repeated_source_key": all(keys[ordinal - 1])
            and counts[keys[ordinal - 1]] > 1,
            "gross_area": not gross or float(gross) <= 0,
            "oldest_month": record["SALE DATE"].strip().startswith("2025-09"),
            "newest_month": record["SALE DATE"].strip().startswith("2026-08"),
        }
        cell = f"{record['BOROUGH'].strip()}:{'candidate' if candidate else 'other_or_ambiguous'}"
        facts[ordinal] = (flags, cell)
    selected = {}
    for bucket, quota in (
        ("price", 10),
        ("identity", 10),
        ("repeated_source_key", 10),
        ("gross_area", 10),
        ("oldest_month", 5),
        ("newest_month", 5),
    ):
        available = [
            ordinal
            for ordinal in ranks
            if facts[ordinal][0][bucket] and ordinal not in selected
        ]
        for ordinal in sorted(available, key=lambda value: (ranks[value], value))[
            :quota
        ]:
            selected[ordinal] = bucket
    for borough in "12345":
        for group in ("candidate", "other_or_ambiguous"):
            cell = f"{borough}:{group}"
            available = [
                ordinal
                for ordinal in ranks
                if facts[ordinal][1] == cell and ordinal not in selected
            ]
            for ordinal in sorted(available, key=lambda value: (ranks[value], value))[
                :15
            ]:
                selected[ordinal] = "structural"
    return {
        ordinal: {
            "ordinal": ordinal,
            "rank": ranks[ordinal],
            "primary_bucket": bucket,
            "structural_cell": facts[ordinal][1],
            "edge_flags": facts[ordinal][0],
        }
        for ordinal, bucket in selected.items()
    }


class SelectNycReviewSampleTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.private = self.root / "data" / "raw" / "nyc_dof"
        self.private.mkdir(parents=True)
        self.manifest = self.root / "snapshot.json"
        self.aggregate = self.root / "aggregate.json"
        self.output = self.private / "sample.jsonl"
        private_patch = patch.object(profiler, "PRIVATE_ROOT", self.private)
        private_patch.start()
        self.addCleanup(private_patch.stop)

    def prepare(self, rows=None, *, header=profiler.HEADER):
        rows = sufficient_rows() if rows is None else rows
        body = csv_bytes(rows, header=header)
        raw_sha = sha256(body).hexdigest()
        source_patch = patch.object(profiler, "APPROVED_SNAPSHOT_SHA256", raw_sha)
        source_patch.start()
        self.addCleanup(source_patch.stop)
        selector_patch = patch.object(selector, "SNAPSHOT_SHA256", raw_sha)
        selector_patch.start()
        self.addCleanup(selector_patch.stop)
        byte_patch = patch.object(selector, "SNAPSHOT_BYTES", len(body))
        byte_patch.start()
        self.addCleanup(byte_patch.stop)
        row_patch = patch.object(selector, "SNAPSHOT_ROWS", len(rows))
        row_patch.start()
        self.addCleanup(row_patch.stop)
        (self.private / "snapshot.csv").write_bytes(body)
        self.manifest.write_text(
            json.dumps(
                {
                    "source_id": "nyc_dof_rolling_usep_8jbt",
                    "capture_status": "inventory_only_not_asof_eligible",
                    "header_kind": "name",
                    "raw_filename": "snapshot.csv",
                    "sha256": raw_sha,
                    "bytes": len(body),
                    "rows": len(rows),
                }
            ),
            encoding="utf-8",
        )
        aggregate = {
            "source_id": "nyc_dof_rolling_usep_8jbt",
            "snapshot_sha256": raw_sha,
            "status": "source_inventory_only_not_sale_eligibility",
            **profiler._profile_csv(BytesIO(body), len(rows)),
        }
        aggregate_bytes = (json.dumps(aggregate, sort_keys=True) + "\n").encode()
        self.aggregate.write_bytes(aggregate_bytes)
        aggregate_patch = patch.object(
            selector, "PROFILE_SHA256", sha256(aggregate_bytes).hexdigest()
        )
        aggregate_patch.start()
        self.addCleanup(aggregate_patch.stop)
        return rows

    def select(self):
        return selector.select_sample(self.manifest, self.aggregate, self.output)

    def ledger(self):
        return [json.loads(line) for line in self.output.read_text().splitlines()]

    def test_quota_disjointness_flags_and_deterministic_replay(self):
        rows = self.prepare()
        summary = self.select()
        ledger = self.ledger()
        oracle = independent_expected_selection(rows, selector.SNAPSHOT_SHA256)
        self.assertEqual({entry["ordinal"]: entry for entry in ledger}, oracle)
        self.assertEqual(len(ledger), 200)
        self.assertEqual(len({entry["ordinal"] for entry in ledger}), 200)
        self.assertEqual(
            [entry["ordinal"] for entry in ledger],
            sorted(entry["ordinal"] for entry in ledger),
        )
        self.assertEqual(
            {
                bucket: sum(item["primary_bucket"] == bucket for item in ledger)
                for bucket in selector.EDGE_QUOTAS
            },
            selector.EDGE_QUOTAS,
        )
        self.assertEqual(
            sum(item["primary_bucket"] == "structural" for item in ledger), 150
        )
        for borough in "12345":
            for group in ("candidate", "other_or_ambiguous"):
                self.assertEqual(
                    sum(
                        item["primary_bucket"] == "structural"
                        and item["structural_cell"] == f"{borough}:{group}"
                        for item in ledger
                    ),
                    15,
                )
        for item in ledger:
            self.assertEqual(
                item["rank"],
                sha256(
                    f"nyc-review-v1|{selector.SNAPSHOT_SHA256}|42|{item['ordinal']}".encode()
                ).hexdigest(),
            )
            if item["primary_bucket"] != "structural":
                self.assertTrue(item["edge_flags"][item["primary_bucket"]])
        self.assertEqual(summary["selected_rows"], 200)
        self.assertEqual(
            summary["ledger_sha256"], sha256(self.output.read_bytes()).hexdigest()
        )
        self.assertNotIn("Private Address", self.output.read_text())
        self.assertNotIn("100000", self.output.read_text())
        with self.assertRaises(FileExistsError):
            self.select()
        replay = self.private / "replay.jsonl"
        second = selector.select_sample(self.manifest, self.aggregate, replay)
        self.assertEqual(self.output.read_bytes(), replay.read_bytes())
        self.assertEqual(summary["ledger_sha256"], second["ledger_sha256"])

    def test_trim_only_duplicate_key_and_incomplete_key(self):
        rows = sufficient_rows()
        rows.extend(
            [
                row(
                    **{
                        "BOROUGH": " 1 ",
                        "BLOCK": "Z",
                        "LOT": "1",
                        "SALE PRICE": " 1000 ",
                        "SALE DATE": " 2026-08-01 ",
                    }
                ),
                row(
                    **{
                        "BOROUGH": "1",
                        "BLOCK": "Z ",
                        "LOT": "1",
                        "SALE PRICE": "1000",
                        "SALE DATE": "2026-08-01",
                    }
                ),
                row(
                    **{
                        "BLOCK": "Y",
                        "LOT": "1",
                        "SALE PRICE": "1,000",
                        "SALE DATE": "08/01/2026",
                    }
                ),
                row(
                    **{
                        "BLOCK": "Y",
                        "LOT": "1",
                        "SALE PRICE": "1000",
                        "SALE DATE": "2026-08-01",
                    }
                ),
                row(
                    **{
                        "BLOCK": "",
                        "LOT": "1",
                        "SALE PRICE": "1000",
                        "SALE DATE": "2026-08-01",
                    }
                ),
                row(
                    **{
                        "BLOCK": "",
                        "LOT": "1",
                        "SALE PRICE": "1000",
                        "SALE DATE": "2026-08-01",
                    }
                ),
            ]
        )
        self.prepare(rows)
        summary = self.select()
        self.assertEqual(summary["source_profile_reconciled"], True)
        self.assertEqual(summary["duplicate_candidate_rows"], 42)

    def test_hash_header_row_count_and_profile_mismatch_fail_closed(self):
        self.prepare()
        original = (self.private / "snapshot.csv").read_bytes()
        (self.private / "snapshot.csv").write_bytes(
            original.replace(b"Private", b"Changed")
        )
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            self.select()
        (self.private / "snapshot.csv").write_bytes(original)
        data = json.loads(self.aggregate.read_text())
        self.aggregate.write_text(
            json.dumps(data | {"rows": data["rows"] + 1}), encoding="utf-8"
        )
        with self.assertRaisesRegex(ValueError, "profile|aggregate"):
            self.select()
        changed = self.aggregate.read_bytes()
        with patch.object(selector, "PROFILE_SHA256", sha256(changed).hexdigest()):
            with self.assertRaisesRegex(ValueError, "reconcile"):
                self.select()
        self.assertFalse(self.output.exists())

    def test_header_and_manifest_row_count_failure(self):
        rows = self.prepare()
        bad_body = csv_bytes(rows, header=profiler.HEADER[:-1] + ("DATE",))
        bad_hash = sha256(bad_body).hexdigest()
        (self.private / "snapshot.csv").write_bytes(bad_body)
        source = json.loads(self.manifest.read_text())
        self.manifest.write_text(
            json.dumps(source | {"sha256": bad_hash, "bytes": len(bad_body)})
        )
        with (
            patch.object(profiler, "APPROVED_SNAPSHOT_SHA256", bad_hash),
            patch.object(selector, "SNAPSHOT_SHA256", bad_hash),
            patch.object(selector, "SNAPSHOT_BYTES", len(bad_body)),
        ):
            with self.assertRaisesRegex(ValueError, "Aggregate profile"):
                self.select()
            with self.assertRaisesRegex(ValueError, "header"):
                list(selector._rows(bad_body, len(rows)))
        (self.private / "snapshot.csv").write_bytes(csv_bytes(rows))
        self.manifest.write_text(json.dumps(source | {"rows": len(rows) + 1}))
        with self.assertRaisesRegex(ValueError, "row count"):
            self.select()
        self.assertFalse(self.output.exists())

    def test_private_output_and_no_overwrite(self):
        self.prepare()
        with self.assertRaisesRegex(ValueError, "private"):
            selector.select_sample(
                self.manifest, self.aggregate, self.root / "public.jsonl"
            )
        self.output.write_text("keep me", encoding="utf-8")
        with self.assertRaises(FileExistsError):
            self.select()
        self.assertEqual(self.output.read_text(), "keep me")

    def test_private_source_path_and_output_symlink_guards(self):
        self.prepare()
        source = json.loads(self.manifest.read_text())
        self.manifest.write_text(
            json.dumps(source | {"raw_filename": "../snapshot.csv"})
        )
        with self.assertRaisesRegex(ValueError, "filename"):
            self.select()
        self.manifest.write_text(json.dumps(source))
        actual_is_symlink = Path.is_symlink

        def source_link(path):
            return path == self.private / "snapshot.csv" or actual_is_symlink(path)

        with patch.object(Path, "is_symlink", source_link):
            with self.assertRaisesRegex(ValueError, "regular file"):
                self.select()

        def output_link(path):
            return path == self.output or actual_is_symlink(path)

        with patch.object(Path, "is_symlink", output_link):
            with self.assertRaises(FileExistsError):
                self.select()

    def test_manifest_symlink_and_nonregular_file_rejected_before_read(self):
        self.prepare()
        actual_is_symlink = Path.is_symlink

        def manifest_link(path):
            return path == self.manifest or actual_is_symlink(path)

        with patch.object(Path, "is_symlink", manifest_link):
            with self.assertRaisesRegex(ValueError, "manifest.*regular"):
                self.select()
        self.manifest.unlink()
        self.manifest.mkdir()
        with self.assertRaisesRegex(ValueError, "manifest.*regular"):
            self.select()
        self.assertFalse(self.output.exists())

    def test_pinned_byte_buffer_remains_immutable_after_source_mutation(self):
        self.prepare()
        manifest, raw, body = selector._verify_source(self.manifest, self.private)
        self.assertEqual(len(body), manifest["bytes"])
        raw.write_bytes(b"changed")
        parsed = list(selector._rows(body, manifest["rows"]))
        self.assertEqual(len(parsed), manifest["rows"])
        with self.assertRaisesRegex(ValueError, "byte count|SHA-256"):
            selector._verify_source(self.manifest, self.private)

    def test_malformed_csv_row_and_source_change_during_selection(self):
        self.prepare()
        original = (self.private / "snapshot.csv").read_bytes()
        malformed = original.replace(
            b"123 Private Address", b"123 Private Address,evil", 1
        )
        bad_hash = sha256(malformed).hexdigest()
        (self.private / "snapshot.csv").write_bytes(malformed)
        source = json.loads(self.manifest.read_text())
        self.manifest.write_text(
            json.dumps(source | {"sha256": bad_hash, "bytes": len(malformed)})
        )
        with (
            patch.object(profiler, "APPROVED_SNAPSHOT_SHA256", bad_hash),
            patch.object(selector, "SNAPSHOT_SHA256", bad_hash),
            patch.object(selector, "SNAPSHOT_BYTES", len(malformed)),
        ):
            with self.assertRaisesRegex(ValueError, "Aggregate profile"):
                self.select()
            with self.assertRaisesRegex(ValueError, "field count"):
                list(selector._rows(malformed, source["rows"]))
        (self.private / "snapshot.csv").write_bytes(original)
        self.manifest.write_text(json.dumps(source))
        original_choose = selector._choose

        def change_after_selection(candidates):
            chosen = original_choose(candidates)
            (self.private / "snapshot.csv").write_bytes(original + b"x")
            return chosen

        with patch.object(selector, "_choose", side_effect=change_after_selection):
            with self.assertRaisesRegex(ValueError, "byte count|byte limit"):
                self.select()
        self.assertFalse(self.output.exists())

    def test_insufficient_disjoint_bucket_produces_no_ledger(self):
        rows = sufficient_rows()
        rows = [
            tuple(
                "2026-01-01" if field == "SALE DATE" else value
                for field, value in zip(profiler.HEADER, record, strict=True)
            )
            for record in rows
        ]
        self.prepare(rows)
        with self.assertRaisesRegex(ValueError, "oldest month|quota"):
            self.select()
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
