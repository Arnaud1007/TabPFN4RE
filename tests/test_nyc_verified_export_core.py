"""Synthetic tests for the private NYC verified-export comparison core."""

from __future__ import annotations

import hashlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import nyc_verified_export_core as core  # noqa: E402


def row(code="2", block="10", lot="1", unit="", day="09/15/2025", price="750000"):
    values = [""] * 21
    values[0], values[4], values[5], values[9] = code, block, lot, unit
    values[8], values[19], values[20] = "SYNTHETIC STREET", price, day
    return tuple(values)


class SelectionTest(unittest.TestCase):
    def setUp(self):
        self.sample = set(range(1, 201))
        self.codes = {i: str(2 + (i - 1) // 50) for i in self.sample}
        self.sha = "a" * 64

    def test_deterministic_two_each_plus_two_global(self):
        chosen = core.select_pilot(self.sample, self.codes, self.sha)
        self.assertEqual(len(chosen), 10)
        self.assertEqual(len(set(chosen)), 10)
        self.assertEqual(chosen, core.select_pilot(self.sample, self.codes, self.sha))
        expected = []
        for code in "2345":
            group = [i for i in self.sample if self.codes[i] == code]
            expected.extend(sorted(group, key=self.rank)[:2])
        remaining = self.sample - set(expected)
        expected.extend(sorted(remaining, key=self.rank)[:2])
        self.assertEqual(chosen, tuple(expected))

    def rank(self, ordinal):
        body = f"nyc-verified-export-pilot-v1|{self.sha}|{ordinal}".encode()
        return hashlib.sha256(body).hexdigest(), ordinal

    def test_missing_sample_row_fails(self):
        self.codes.pop(1)
        with self.assertRaises(ValueError):
            core.select_pilot(self.sample, self.codes, self.sha)

    def test_missing_borough_quota_fails(self):
        self.codes = {
            i: ("5" if code == "2" else code) for i, code in self.codes.items()
        }
        with self.assertRaises(ValueError):
            core.select_pilot(self.sample, self.codes, self.sha)

    def test_bad_sample_or_hash_fails(self):
        for sample, sha in (({1}, self.sha), (self.sample, "bad")):
            with self.assertRaises(ValueError):
                core.select_pilot(sample, self.codes, sha)

    def test_manhattan_excluded_and_bad_borough_type_rejected(self):
        mapping = {i: "1" if i <= 20 else str(2 + (i - 21) // 45) for i in self.sample}
        chosen = core.select_pilot(self.sample, mapping, self.sha)
        self.assertEqual(len(chosen), 10)
        self.assertTrue(all(mapping[item] != "1" for item in chosen))
        mapping[1] = None
        with self.assertRaises(ValueError):
            core.select_pilot(self.sample, mapping, self.sha)


class ComparisonTest(unittest.TestCase):
    def compare(self, csv, xlsx, selected=(1,)):
        return core.compare_borough(
            csv, xlsx, selected=set(selected), borough="Bronx", borough_code="2"
        )

    def test_raw_and_canonical_and_field_disagreement(self):
        csv = [(1, row()), (2, row(block="20")), (3, row(block="30"))]
        changed = list(row(block="30", day="2025-09-15", price="750000.0"))
        changed[8] = "DIFFERENT SYNTHETIC STREET"
        xlsx = [
            (101, row(day="09/15/2025")),
            (102, row(block="20", day="2025-09-15", price="7.5E5")),
            (103, tuple(changed)),
        ]
        result = self.compare(csv, xlsx, selected=(1, 2, 3))
        self.assertEqual(
            [item["status"] for item in result],
            [
                "raw_full_21_concordance",
                "canonical_full_21_concordance",
                "unique_candidate_with_field_disagreement",
            ],
        )
        self.assertEqual(result[2]["difference_positions"], [9])
        self.assertEqual(result[1]["workbook_row_number"], 102)
        self.assertEqual(
            set(result[0]),
            {
                "ordinal",
                "borough",
                "status",
                "workbook_row_number",
                "difference_positions",
            },
        )
        self.assertNotIn("SYNTHETIC STREET", str(result))

    def test_invalid_key_and_unmatched(self):
        csv = [(1, row(day="invalid")), (2, row(block="20")), (3, row(price="NaN"))]
        self.assertEqual(
            [item["status"] for item in self.compare(csv, [], selected=(1, 2, 3))],
            [
                "invalid_key",
                "unmatched",
                "invalid_key",
            ],
        )

    def test_duplicate_keys_on_either_side_are_ambiguous(self):
        for csv, xlsx in (
            ([(1, row()), (2, row())], [(101, row())]),
            ([(1, row())], [(101, row()), (102, row())]),
        ):
            self.assertEqual(self.compare(csv, xlsx)[0]["status"], "ambiguous")

    def test_distinct_units_do_not_match(self):
        result = self.compare([(1, row(unit="1A"))], [(101, row(unit="1B"))])
        self.assertEqual(result[0]["status"], "unmatched")

    def test_weaker_tier_crosslink_rejects_canonical_pair(self):
        csv = [(1, row(day="09/15/2025", price="750000"))]
        xlsx = [
            (101, row(day="2025-09-15", price="750000.0")),
            (102, row(block="010", day="2025-09-15", price="750000.0")),
        ]
        self.assertEqual(self.compare(csv, xlsx)[0]["status"], "ambiguous")

    def test_normalized_block_collision_rejects_only_affected_pair(self):
        csv = [(1, row(block="10")), (2, row(block="010")), (3, row(block="30"))]
        xlsx = [(101, row(block="10")), (103, row(block="30"))]
        result = self.compare(csv, xlsx, selected=(1, 3))
        self.assertEqual(result[0]["status"], "ambiguous")
        self.assertEqual(result[1]["status"], "raw_full_21_concordance")

    def test_reverse_crosslink_via_k4_rejects_pair(self):
        csv = [(1, row(block="10")), (2, row(block="010"))]
        xlsx = [(101, row(block="10"))]
        self.assertEqual(self.compare(csv, xlsx)[0]["status"], "ambiguous")

    def test_every_non_key_field_position_and_outer_whitespace(self):
        base = row()
        for index in range(21):
            if index in core.KEY_COLUMNS:
                continue
            changed = list(base)
            changed[index] = " DIFFERENT "
            result = self.compare([(1, base)], [(101, tuple(changed))])
            self.assertEqual(
                result[0]["status"], "unique_candidate_with_field_disagreement"
            )
            self.assertEqual(result[0]["difference_positions"], [index + 1])
        spaced = tuple(f" {value} " for value in base)
        self.assertEqual(
            self.compare([(1, base)], [(101, spaced)])[0]["status"],
            "raw_full_21_concordance",
        )

    def test_missing_or_invalid_key_and_blank_apartment(self):
        for bad in (
            row(block=""),
            row(lot=""),
            row(day="09/31/2025"),
            row(price="Infinity"),
        ):
            self.assertEqual(
                self.compare([(1, bad)], [(101, bad)])[0]["status"], "invalid_key"
            )
        self.assertEqual(
            self.compare([(1, row(unit=""))], [(101, row(unit=""))])[0]["status"],
            "raw_full_21_concordance",
        )

    def test_input_order_and_nonselected_rows_do_not_change_selected_result(self):
        csv = [(2, row(block="20")), (1, row())]
        xlsx = [(102, row(block="20")), (101, row())]
        first = self.compare(csv, xlsx)
        second = self.compare(list(reversed(csv)), list(reversed(xlsx)))
        self.assertEqual(first, second)
        self.assertEqual(len(first), 1)

    def test_malformed_rows_and_wrong_borough_fail(self):
        for csv in ([(1, row(code="3"))], [(1, ("short",))], [(1, row()), (1, row())]):
            with self.assertRaises(ValueError):
                self.compare(csv, [])


if __name__ == "__main__":
    unittest.main()
