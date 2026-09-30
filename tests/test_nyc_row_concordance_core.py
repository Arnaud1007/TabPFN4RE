"""Synthetic RED tests for exact same-publisher row concordance."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import nyc_row_concordance_core as core  # noqa: E402
from nyc_row_concordance_core import compare_borough, public_projection  # noqa: E402


def sale(
    *,
    borough: str = "2",
    block: str = "00012",
    lot: str = "003",
    apartment: str = "",
    date: str = "09/15/2025",
    price: str = "750000",
    address: str = "PRIVATE ADDRESS",
    building_class: str = "A1",
    neighborhood: str = "PRIVATE NEIGHBORHOOD",
) -> tuple[str, ...]:
    row = [""] * 21
    row[0], row[1], row[4], row[5] = borough, neighborhood, block, lot
    row[8], row[9], row[18] = address, apartment, building_class
    row[19], row[20] = price, date
    return tuple(row)


def compare(
    csv: list[tuple[int, tuple[str, ...]]],
    xlsx: list[tuple[int, tuple[str, ...]]],
) -> dict:
    return compare_borough(csv, xlsx, borough="Bronx", borough_code="2")


class RowConcordanceCoreTest(unittest.TestCase):
    def test_exact_multiset_and_unique_pair_with_blank_apartment(self):
        a = sale()
        b = sale(block="00013", lot="001", apartment="4B")
        result = compare([(1, a), (2, b)], [(6, b), (7, a)])
        c = result["counts"]
        self.assertEqual(result["csv_rows"], 2)
        self.assertEqual(result["xlsx_rows"], 2)
        self.assertEqual(c["exact_full_row_multiset_matches"], 2)
        self.assertEqual(c["unique_key_pairs"], 2)
        self.assertEqual(c["unique_full_row_matches"], 2)
        self.assertEqual(c["unique_address_matches"], 2)
        self.assertEqual(c["unique_building_class_matches"], 2)
        self.assertEqual(c["csv_incomplete_key_rows"], 0)
        self.assertEqual(c["xlsx_incomplete_key_rows"], 0)
        self.assertEqual(
            [x["status"] for x in result["ledger"]], ["unique_pair_exact"] * 4
        )
        self.assertEqual(result["label_status"], "unqualified")
        self.assertEqual(result["sale_labels_certified"], 0)
        self.assertNotIn("PRIVATE", json.dumps(result))

    def test_trim_only_preserves_leading_zeros_and_date_price_format(self):
        csv = sale(block=" 00012 ", lot=" 003 ", price=" 750000 ")
        xlsx = sale()
        result = compare([(1, csv)], [(6, xlsx)])
        self.assertEqual(result["counts"]["unique_key_pairs"], 1)
        self.assertEqual(result["counts"]["exact_full_row_multiset_matches"], 1)

        result = compare(
            [(1, sale(block="00012", date="09/15/2025", price="750000"))],
            [(6, sale(block="12", date="2025-09-15", price="750,000"))],
        )
        self.assertEqual(result["counts"]["unique_key_pairs"], 0)
        self.assertEqual(result["counts"]["exact_full_row_multiset_matches"], 0)
        self.assertEqual(result["counts"]["csv_only_key_groups"], 1)
        self.assertEqual(result["counts"]["xlsx_only_key_groups"], 1)

    def test_pair_reports_address_and_class_independently(self):
        result = compare(
            [(1, sale(address="A", building_class="A1"))],
            [(6, sale(address="B", building_class="B2"))],
        )
        c = result["counts"]
        self.assertEqual(c["unique_key_pairs"], 1)
        self.assertEqual(c["unique_full_row_matches"], 0)
        self.assertEqual(c["unique_full_row_mismatches"], 1)
        self.assertEqual(c["unique_address_matches"], 0)
        self.assertEqual(c["unique_address_mismatches"], 1)
        self.assertEqual(c["unique_building_class_matches"], 0)
        self.assertEqual(c["unique_building_class_mismatches"], 1)
        self.assertEqual(result["ledger"][0]["status"], "unique_pair_mismatch")

    def test_noncritical_field_changes_full_row_only(self):
        result = compare(
            [(1, sale(neighborhood="FIRST"))],
            [(6, sale(neighborhood="SECOND"))],
        )
        c = result["counts"]
        self.assertEqual(c["unique_key_pairs"], 1)
        self.assertEqual(c["unique_full_row_mismatches"], 1)
        self.assertEqual(c["unique_address_matches"], 1)
        self.assertEqual(c["unique_building_class_matches"], 1)

    def test_blank_and_nonblank_apartment_are_distinct_keys(self):
        result = compare(
            [(1, sale(apartment=""))],
            [(6, sale(apartment="4B"))],
        )
        c = result["counts"]
        self.assertEqual(c["unique_key_pairs"], 0)
        self.assertEqual(c["csv_only_key_groups"], 1)
        self.assertEqual(c["xlsx_only_key_groups"], 1)

    def test_duplicate_key_not_arbitrarily_paired(self):
        a = sale(address="A")
        b = sale(address="B")
        result = compare([(1, a), (2, b)], [(6, a), (7, b)])
        c = result["counts"]
        self.assertEqual(c["exact_full_row_multiset_matches"], 2)
        self.assertEqual(c["unique_key_pairs"], 0)
        self.assertEqual(c["duplicate_key_groups"], 1)
        self.assertEqual(c["csv_duplicate_key_rows"], 2)
        self.assertEqual(c["xlsx_duplicate_key_rows"], 2)
        self.assertEqual(c["multiplicity_disagreement_groups"], 0)
        self.assertTrue(all(x["status"] == "duplicate_key" for x in result["ledger"]))

    def test_unequal_multiplicity_and_source_only_group_counts(self):
        a = sale()
        csv_only = sale(block="100")
        xlsx_only = sale(block="200")
        result = compare(
            [(1, a), (2, a), (3, csv_only)],
            [(6, a), (7, xlsx_only), (8, xlsx_only)],
        )
        c = result["counts"]
        self.assertEqual(c["multiplicity_disagreement_groups"], 1)
        self.assertEqual(c["csv_only_key_groups"], 1)
        self.assertEqual(c["csv_only_rows"], 1)
        self.assertEqual(c["xlsx_only_key_groups"], 1)
        self.assertEqual(c["xlsx_only_rows"], 2)
        self.assertEqual(c["duplicate_key_groups"], 2)
        self.assertEqual(c["exact_full_row_multiset_matches"], 1)

    def test_incomplete_key_is_not_paired_and_blank_apartment_is_complete(self):
        incomplete = sale(block=" ")
        complete = sale()
        result = compare(
            [(1, incomplete), (2, complete)], [(6, incomplete), (7, complete)]
        )
        c = result["counts"]
        self.assertEqual(c["csv_incomplete_key_rows"], 1)
        self.assertEqual(c["xlsx_incomplete_key_rows"], 1)
        self.assertEqual(c["unique_key_pairs"], 1)
        self.assertEqual(c["exact_full_row_multiset_matches"], 2)
        self.assertEqual(c["csv_only_key_groups"], 0)
        self.assertEqual(c["xlsx_only_key_groups"], 0)
        self.assertEqual(result["ledger"][0]["status"], "incomplete_key")

    def test_rejects_wrong_borough_and_malformed_rows_without_raw_values(self):
        malformed = [
            ([(1, sale(borough="3"))], []),
            ([(1, sale())], [(6, sale(borough="3"))]),
            ([(1, sale()[:-1])], []),
            ([(1, (*sale()[:-1], 5))], []),
            ([(0, sale())], []),
            ([(True, sale())], []),
            ([(1, sale()), (1, sale())], []),
        ]
        for csv, xlsx in malformed:
            with (
                self.subTest(csv=csv, xlsx=xlsx),
                self.assertRaises(ValueError) as raised,
            ):
                compare(csv, xlsx)
            self.assertNotIn("PRIVATE", str(raised.exception))
        with self.assertRaises(ValueError):
            compare_borough([], [], borough="Bronx", borough_code="3")
        with self.assertRaises(ValueError):
            compare_borough([], [], borough="Manhattan", borough_code="1")
        with self.assertRaises(ValueError):
            compare_borough([], [], borough=["Bronx"], borough_code="2")

    def test_ledger_has_only_trace_fields_and_no_raw_values(self):
        result = compare([(1, sale())], [(6, sale())])
        for entry in result["ledger"]:
            self.assertEqual(
                set(entry),
                {"source", "ordinal", "status", "row_sha256", "key_sha256"},
            )
            self.assertEqual(len(entry["row_sha256"]), 64)
            self.assertEqual(len(entry["key_sha256"]), 64)
        self.assertNotIn("PRIVATE", json.dumps(result))
        self.assertNotIn("750000", json.dumps(result))

    def test_public_projection_suppresses_whole_breakdown_for_small_cell(self):
        result = compare([(1, sale())], [(6, sale())])
        public = public_projection(result)
        self.assertIsNone(public["counts"])
        self.assertEqual(public["suppression_reason"], "small_positive_cell_1_to_4")
        self.assertEqual(public["csv_rows"], 1)
        self.assertEqual(public["xlsx_rows"], 1)
        self.assertEqual(public["label_status"], "unqualified")
        self.assertEqual(public["sale_labels_certified"], 0)
        self.assertNotIn("ledger", public)
        self.assertNotIn("sha256", json.dumps(public))
        self.assertNotIn("ordinal", json.dumps(public))

    def test_public_projection_shows_fixed_counts_when_no_small_cell(self):
        rows = [(i, sale(block=str(i))) for i in range(1, 6)]
        other = [(i + 5, values) for i, values in rows]
        public = public_projection(compare(rows, other))
        self.assertIsNone(public["suppression_reason"])
        self.assertEqual(public["counts"]["unique_key_pairs"], 5)
        self.assertEqual(public["counts"]["unique_full_row_mismatches"], 0)
        self.assertNotIn("ledger", public)

    def test_public_projection_rejects_missing_metric_or_bad_count(self):
        result = compare([], [])
        del result["counts"]["unique_key_pairs"]
        with self.assertRaises(ValueError):
            public_projection(result)
        result = compare([], [])
        result["counts"]["unique_key_pairs"] = -1
        with self.assertRaises(ValueError):
            public_projection(result)

    def test_public_projection_checks_group_and_pair_reconciliation(self):
        result = compare([(1, sale())], [(6, sale())])
        result["counts"]["csv_complete_key_groups"] += 1
        with self.assertRaises(ValueError):
            public_projection(result)
        result = compare([(1, sale())], [(6, sale())])
        result["counts"]["csv_ambiguous_shared_key_rows"] += 1
        with self.assertRaises(ValueError):
            public_projection(result)
        result = compare([(1, sale())], [(6, sale())])
        result["counts"]["unique_address_matches"] = 0
        with self.assertRaises(ValueError):
            public_projection(result)

    def test_public_projection_suppresses_one_mismatch_among_five_pairs(self):
        rows = [(i, sale(block=str(i))) for i in range(1, 6)]
        other = [
            (i + 5, sale(block=str(i), address="DIFFERENT") if i == 1 else values)
            for i, values in rows
        ]
        public = public_projection(compare(rows, other))
        self.assertIsNone(public["counts"])
        self.assertEqual(public["suppression_reason"], "small_positive_cell_1_to_4")

    def test_combined_cell_character_cap_rejects_oversized_borough(self):
        row = sale()
        one_source_characters = sum(map(len, row))
        with patch.object(
            core, "MAX_RESIDENT_CELL_CHARS", one_source_characters * 2 - 1, create=True
        ):
            with self.assertRaisesRegex(ValueError, "character cap"):
                compare([(1, row)], [(6, row)])


if __name__ == "__main__":
    unittest.main()
