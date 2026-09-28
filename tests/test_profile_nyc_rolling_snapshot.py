"""Synthetic aggregate-only checks for the frozen NYC rolling CSV profiler."""

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

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import profile_nyc_rolling_snapshot as profiler  # noqa: E402


HEADER = (
    "BOROUGH",
    "NEIGHBORHOOD",
    "BUILDING CLASS CATEGORY",
    "TAX CLASS AT PRESENT",
    "BLOCK",
    "LOT",
    "EASE-MENT",
    "BUILDING CLASS AT PRESENT",
    "ADDRESS",
    "APARTMENT NUMBER",
    "ZIP CODE",
    "RESIDENTIAL UNITS",
    "COMMERCIAL UNITS",
    "TOTAL UNITS",
    "LAND SQUARE FEET",
    "GROSS SQUARE FEET",
    "YEAR BUILT",
    "TAX CLASS AT TIME OF SALE",
    "BUILDING CLASS AT TIME OF SALE",
    "SALE PRICE",
    "SALE DATE",
)


def row(**values: str) -> tuple[str, ...]:
    fields = {
        "BOROUGH": "1",
        "BLOCK": "123",
        "LOT": "4",
        "BUILDING CLASS CATEGORY": "01 ONE FAMILY DWELLINGS",
        "BUILDING CLASS AT TIME OF SALE": "A1",
        "ADDRESS": "10 Private St",
        "SALE PRICE": "100000",
        "SALE DATE": "2026-08-01",
        "GROSS SQUARE FEET": "1200",
        "LAND SQUARE FEET": "2000",
    }
    return tuple((fields | values).get(name, "") for name in HEADER)


def csv_bytes(rows: tuple[tuple[str, ...], ...], *, header=HEADER) -> bytes:
    buffer = StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow(header)
    writer.writerows(rows)
    return buffer.getvalue().encode()


class ProfileSnapshotTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.private = self.root / "data" / "raw" / "nyc_dof"
        self.private.mkdir(parents=True)
        self.manifest = self.root / "runs" / "snapshot.json"
        self.manifest.parent.mkdir()
        self.output = self.private / "profile.json"
        root_patch = patch.object(profiler, "PRIVATE_ROOT", self.private)
        root_patch.start()
        self.addCleanup(root_patch.stop)

    def prepare(self, rows: tuple[tuple[str, ...], ...], *, header=HEADER):
        body = csv_bytes(rows, header=header)
        hash_patch = patch.object(
            profiler, "APPROVED_SNAPSHOT_SHA256", sha256(body).hexdigest()
        )
        hash_patch.start()
        self.addCleanup(hash_patch.stop)
        (self.private / "snapshot.csv").write_bytes(body)
        self.manifest.write_text(
            json.dumps(
                {
                    "source_id": "nyc_dof_rolling_usep_8jbt",
                    "raw_filename": "snapshot.csv",
                    "sha256": sha256(body).hexdigest(),
                    "bytes": len(body),
                    "rows": len(rows),
                    "header_kind": "name",
                    "capture_status": "inventory_only_not_asof_eligible",
                }
            ),
            encoding="utf-8",
        )

    def test_aggregate_profile_and_candidate_duplicates(self):
        self.prepare(
            (
                row(),
                row(**{"ADDRESS": "OTHER PRIVATE ADDRESS"}),
                row(
                    **{
                        "BOROUGH": "2",
                        "BLOCK": "6",
                        "LOT": "8",
                        "BUILDING CLASS CATEGORY": "13 CONDOS - ELEVATOR APARTMENTS",
                        "BUILDING CLASS AT TIME OF SALE": "R4",
                        "SALE PRICE": "0",
                        "GROSS SQUARE FEET": "",
                        "LAND SQUARE FEET": "",
                        "APARTMENT NUMBER": "5A",
                    }
                ),
                row(
                    **{
                        "BOROUGH": "6",
                        "BLOCK": "",
                        "SALE PRICE": "-2",
                        "BUILDING CLASS CATEGORY": "",
                        "BUILDING CLASS AT TIME OF SALE": "",
                        "APARTMENT NUMBER": "",
                    }
                ),
                row(
                    **{
                        "BOROUGH": "3",
                        "BLOCK": "2",
                        "SALE PRICE": "bogus",
                        "BUILDING CLASS CATEGORY": "02 TWO FAMILY DWELLINGS",
                        "BUILDING CLASS AT TIME OF SALE": "B2",
                    }
                ),
                row(
                    **{
                        "BOROUGH": "4",
                        "BLOCK": "3",
                        "SALE PRICE": "",
                        "BUILDING CLASS CATEGORY": "02 TWO FAMILY DWELLINGS",
                    }
                ),
            )
        )
        result = profiler.profile_snapshot(self.manifest, self.output)
        self.assertEqual(json.loads(self.output.read_text(encoding="utf-8")), result)
        self.assertEqual(result["rows"], 6)
        self.assertEqual(
            result["borough_counts"],
            {"1": 2, "2": 1, "3": 1, "4": 1, "5": 0, "unknown": 1},
        )
        self.assertEqual(
            result["sale_price_parse_state"],
            {"positive": 2, "zero": 1, "negative": 1, "invalid": 1, "missing": 1},
        )
        self.assertEqual(
            result["building_class_prefix_counts"],
            {"A": 3, "R": 1, "other": 1, "missing": 1},
        )
        self.assertEqual(result["missing_area_counts"], {"gross": 1, "land": 1})
        self.assertEqual(
            result["apartment_missing_by_class"]["A"], {"rows": 3, "missing": 3}
        )
        self.assertEqual(
            result["apartment_missing_by_class"]["R"], {"rows": 1, "missing": 0}
        )
        self.assertEqual(
            result["exact_source_string_duplicate_candidates"],
            {
                "complete_key_rows": 4,
                "incomplete_key_rows": 2,
                "repeated_groups": 1,
                "rows_in_repeated_groups": 2,
                "excess_rows": 1,
            },
        )
        self.assertEqual(
            result["screening_by_borough_and_class"]["1"]["A"],
            {"rows": 2, "positive_price": 2, "positive_price_with_gross_area": 2},
        )
        self.assertEqual(
            result["one_family_by_borough"]["1"],
            {"candidate": 2, "other_or_ambiguous": 0},
        )
        self.assertEqual(
            result["one_family_by_borough"]["4"],
            {"candidate": 0, "other_or_ambiguous": 1},
        )
        self.assertEqual(result["one_family_class_disagreements"], 1)
        self.assertEqual(
            result["price_review_buckets"],
            {
                "zero": 1,
                "positive_at_most_1000": 0,
                "negative": 1,
                "invalid": 1,
                "missing": 1,
            },
        )
        self.assertEqual(
            result["identity_review_buckets"],
            {"missing_block": 1, "missing_lot": 0, "r_class_missing_apartment": 0},
        )
        self.assertEqual(
            result["gross_area_review_buckets"],
            {"missing": 1, "nonpositive": 0, "invalid": 0},
        )
        self.assertEqual(
            result["sale_month_bounds"],
            {
                "oldest": "2026-08",
                "oldest_rows": 6,
                "newest": "2026-08",
                "newest_rows": 6,
                "invalid_or_missing": 0,
            },
        )
        rendered = json.dumps(result)
        self.assertNotIn("Private St", rendered)
        self.assertNotIn("123", rendered)
        self.assertNotIn("100000", rendered)
        self.assertNotIn("2026-08-01", rendered)
        self.assertNotIn("snapshot.csv", rendered)
        self.assertIn("trim-only", result["duplicate_key_policy"])
        self.assertIn("no semantic normalization", result["duplicate_key_policy"])

    def test_hash_mismatch_rejected_before_csv_read(self):
        self.prepare((row(),))
        body = (self.private / "snapshot.csv").read_bytes()
        (self.private / "snapshot.csv").write_bytes(
            body.replace(b"Private", b"Changed")
        )
        with self.assertRaisesRegex(ValueError, "SHA-256|byte count"):
            profiler.profile_snapshot(self.manifest, self.output)
        self.assertFalse(self.output.exists())

    def test_manifest_byte_and_row_count_mismatch_rejected(self):
        self.prepare((row(),))
        source = json.loads(self.manifest.read_text(encoding="utf-8"))
        self.manifest.write_text(
            json.dumps(source | {"bytes": source["bytes"] + 1}), encoding="utf-8"
        )
        with self.assertRaisesRegex(ValueError, "byte count"):
            profiler.profile_snapshot(self.manifest, self.output)
        self.manifest.write_text(json.dumps(source | {"rows": 2}), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "row count"):
            profiler.profile_snapshot(self.manifest, self.output)
        self.assertFalse(self.output.exists())

    def test_declared_and_actual_csv_byte_caps(self):
        self.prepare((row(),))
        source = json.loads(self.manifest.read_text(encoding="utf-8"))
        limit = source["bytes"] - 1
        with patch.object(profiler, "MAX_CSV_BYTES", limit):
            with self.assertRaisesRegex(ValueError, "CSV byte limit"):
                profiler.profile_snapshot(self.manifest, self.output)
            self.manifest.write_text(
                json.dumps(source | {"bytes": limit}), encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "exceeds byte limit"):
                profiler.profile_snapshot(self.manifest, self.output)
        self.assertFalse(self.output.exists())

    def test_header_or_row_shape_change_rejected(self):
        self.prepare((row(),), header=HEADER[:-1] + ("DATE",))
        with self.assertRaisesRegex(ValueError, "header"):
            profiler.profile_snapshot(self.manifest, self.output)
        self.prepare((row()[:-1],))
        with self.assertRaisesRegex(ValueError, "field count"):
            profiler.profile_snapshot(self.manifest, self.output)
        self.assertFalse(self.output.exists())

    def test_private_path_and_output_guard(self):
        self.prepare((row(),))
        with self.assertRaisesRegex(ValueError, "private"):
            profiler.profile_snapshot(self.manifest, self.root / "public.json")
        source = json.loads(self.manifest.read_text(encoding="utf-8"))
        self.manifest.write_text(
            json.dumps(source | {"raw_filename": "../snapshot.csv"}), encoding="utf-8"
        )
        with self.assertRaisesRegex(ValueError, "filename"):
            profiler.profile_snapshot(self.manifest, self.output)
        self.assertFalse(self.output.exists())

    def test_junction_like_private_ancestor_is_rejected(self):
        self.prepare((row(),))
        actual_resolve = Path.resolve
        redirected_parent = self.private.parent

        def resolve_with_junction(path, strict=False):
            if path == redirected_parent:
                return self.root / "outside"
            return actual_resolve(path, strict=strict)

        with patch.object(Path, "resolve", resolve_with_junction):
            with self.assertRaisesRegex(ValueError, "redirects"):
                profiler.profile_snapshot(self.manifest, self.output)
        self.assertFalse(self.output.exists())

    def test_existing_output_is_not_overwritten(self):
        self.prepare((row(),))
        self.output.write_text("original", encoding="utf-8")
        with self.assertRaises(FileExistsError):
            profiler.profile_snapshot(self.manifest, self.output)
        self.assertEqual(self.output.read_text(encoding="utf-8"), "original")

    def test_different_registered_revision_is_rejected(self):
        self.prepare((row(),))
        with patch.object(profiler, "APPROVED_SNAPSHOT_SHA256", "0" * 64):
            with self.assertRaisesRegex(ValueError, "pre-registered"):
                profiler.profile_snapshot(self.manifest, self.output)
        self.assertFalse(self.output.exists())

    def test_price_parser_is_strict_and_aggregate_only(self):
        self.prepare(
            (
                row(**{"SALE PRICE": " 1,234.50 "}),
                row(**{"LOT": "5", "SALE PRICE": "1,23"}),
                row(**{"LOT": "6", "SALE PRICE": "$123"}),
                row(**{"LOT": "7", "SALE PRICE": "NaN"}),
                row(**{"LOT": "8", "SALE PRICE": "١٢٣"}),
            )
        )
        result = profiler.profile_snapshot(self.manifest, self.output)
        self.assertEqual(result["sale_price_parse_state"]["positive"], 1)
        self.assertEqual(result["sale_price_parse_state"]["invalid"], 4)
        self.assertEqual(result["screening_by_borough_and_class"]["1"]["A"]["rows"], 5)

    def test_duplicate_groups_do_not_normalize_equivalent_source_strings(self):
        self.prepare(
            (
                row(**{"SALE PRICE": "100000", "SALE DATE": "2026-08-01"}),
                row(**{"SALE PRICE": "100,000", "SALE DATE": "08/01/2026"}),
            )
        )
        result = profiler.profile_snapshot(self.manifest, self.output)
        self.assertEqual(
            result["exact_source_string_duplicate_candidates"]["repeated_groups"], 0
        )

    def test_review_buckets_and_month_extremes(self):
        self.prepare(
            (
                row(
                    **{
                        "SALE PRICE": "1",
                        "GROSS SQUARE FEET": "0",
                        "SALE DATE": "01/31/2026",
                    }
                ),
                row(
                    **{
                        "LOT": "5",
                        "SALE PRICE": "1000",
                        "GROSS SQUARE FEET": "-5",
                        "SALE DATE": "2026-01-01",
                    }
                ),
                row(
                    **{
                        "LOT": "6",
                        "SALE PRICE": "1001",
                        "GROSS SQUARE FEET": "bad",
                        "SALE DATE": "2026-08-02",
                    }
                ),
                row(
                    **{
                        "LOT": "7",
                        "BUILDING CLASS AT TIME OF SALE": "R4",
                        "SALE DATE": "not-a-date",
                    }
                ),
            )
        )
        result = profiler.profile_snapshot(self.manifest, self.output)
        self.assertEqual(result["price_review_buckets"]["positive_at_most_1000"], 2)
        self.assertEqual(
            result["gross_area_review_buckets"],
            {"missing": 0, "nonpositive": 2, "invalid": 1},
        )
        self.assertEqual(
            result["identity_review_buckets"]["r_class_missing_apartment"], 1
        )
        self.assertEqual(
            result["sale_month_bounds"],
            {
                "oldest": "2026-01",
                "oldest_rows": 2,
                "newest": "2026-08",
                "newest_rows": 1,
                "invalid_or_missing": 1,
            },
        )


if __name__ == "__main__":
    unittest.main()
