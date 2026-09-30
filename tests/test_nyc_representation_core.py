"""Synthetic RED tests for the frozen NYC representation diagnostic v2."""

from __future__ import annotations

import json
import sys
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import nyc_representation_core as core  # noqa: E402


def sale(
    *,
    borough: str = "2",
    block: str = "00012",
    lot: str = "003",
    apartment: str = "",
    date_text: str = "09/15/2025",
    price: str = "750000",
    address: str = "PRIVATE ADDRESS",
    building_class: str = "A1",
    neighborhood: str = "PRIVATE NEIGHBORHOOD",
) -> tuple[str, ...]:
    fields = [""] * 21
    fields[0], fields[1], fields[4], fields[5] = borough, neighborhood, block, lot
    fields[8], fields[9], fields[18] = address, apartment, building_class
    fields[19], fields[20] = price, date_text
    return tuple(fields)


def analyze(
    csv: list[tuple[int, tuple[str, ...]]],
    xlsx: list[tuple[int, tuple[str, ...]]],
    *,
    borough: str = "Bronx",
    borough_code: str = "2",
    date_system: str = "1900_default",
) -> dict:
    return core.analyze_borough(
        csv,
        xlsx,
        borough=borough,
        borough_code=borough_code,
        date_system=date_system,
    )


class RepresentationParsingTest(unittest.TestCase):
    def test_parse_api_rejects_unknown_source_and_nonstring_input(self):
        with self.assertRaises((TypeError, ValueError)):
            core.parse_date(None, source="csv", date_system="1900_default")
        with self.assertRaises((TypeError, ValueError)):
            core.parse_price(None, source="xlsx")
        with self.assertRaises(ValueError):
            core.parse_date("2025-09-15", source="other", date_system="1900_default")
        with self.assertRaises(ValueError):
            core.parse_price("750000", source="other")

    def test_csv_dates_accept_only_declared_calendar_and_midnight_forms(self):
        valid = (
            "2025-09-15",
            "09/15/2025",
            "2025-09-15T00:00:00",
            "2025-09-15 00:00:00",
            "2025-09-15T00:00:00.0",
            "2025-09-15 00:00:00.000000",
        )
        for value in valid:
            with self.subTest(value=value):
                self.assertEqual(
                    core.parse_date(value, source="csv", date_system="1900_default"),
                    date(2025, 9, 15),
                )

    def test_csv_dates_reject_serial_timezone_nonmidnight_and_bad_calendar(self):
        invalid = (
            "45915",
            "2025-09-15T12:00:00",
            "2025-09-15T00:00:01",
            "2025-09-15T00:00:00.0000000",
            "2025-09-15T00:00:00Z",
            "2025-09-15T00:00:00+00:00",
            "9/15/2025",
            "09/15/25",
            "2025-02-29",
            "09/31/2025",
            "2026-09-01",
            "2024-01-01",
            "",
        )
        for value in invalid:
            with self.subTest(value=value):
                self.assertIsNone(
                    core.parse_date(value, source="csv", date_system="1900_default")
                )

    def test_xlsx_date_serial_is_pinned_to_1900_and_valid_period(self):
        serial = (date(2025, 9, 15) - date(1899, 12, 30)).days
        self.assertEqual(
            core.parse_date(str(serial), source="xlsx", date_system="1900_default"),
            date(2025, 9, 15),
        )
        for value in ("-1", "60", "60.5", "Infinity", "1e999999999"):
            with self.subTest(value=value):
                self.assertIsNone(
                    core.parse_date(value, source="xlsx", date_system="1900_default")
                )
        self.assertIsNone(
            core.parse_date(str(serial), source="csv", date_system="1900_default")
        )

    def test_xlsx_date_accepts_text_forms_and_rejects_unsupported_system(self):
        self.assertEqual(
            core.parse_date("2025-09-15", source="xlsx", date_system="1900_default"),
            date(2025, 9, 15),
        )
        with self.assertRaises(ValueError):
            analyze([], [], date_system="1904_explicit")

    def test_price_grammars_preserve_exact_decimal_and_signed_zero(self):
        for value, expected in (
            ("750000", Decimal("750000")),
            ("750,000.00", Decimal("750000.00")),
            ("-1,234.50", Decimal("-1234.50")),
            ("0", Decimal("0")),
        ):
            with self.subTest(value=value, source="csv"):
                self.assertEqual(core.parse_price(value, source="csv"), expected)
        for value, expected in (
            ("750000", Decimal("750000")),
            ("-1234.50", Decimal("-1234.50")),
            ("0", Decimal("0")),
        ):
            with self.subTest(value=value, source="xlsx"):
                self.assertEqual(core.parse_price(value, source="xlsx"), expected)
        self.assertEqual(core.parse_price("7.5E+5", source="xlsx"), Decimal("750000"))
        self.assertIsNone(core.parse_price("7.5E+5", source="csv"))
        self.assertIsNone(core.parse_price("750,000.00", source="xlsx"))

    def test_price_rejects_bad_grouping_exponents_and_nonfinite(self):
        for value in (
            "$750,000",
            "75,00",
            "1,0000",
            "750,000.00",
            "1.2.3",
            "NaN",
            "Infinity",
            "1e13",
            "1e-13",
            "1234567890123456789e0",
            "",
        ):
            with self.subTest(value=value):
                self.assertIsNone(core.parse_price(value, source="xlsx"))
        self.assertEqual(
            core.parse_price("123456789012345678e0", source="xlsx"),
            Decimal("123456789012345678"),
        )
        self.assertEqual(core.parse_price("1e12", source="xlsx"), Decimal("1e12"))


class RepresentationTierTest(unittest.TestCase):
    def assert_only_tier_and_later_match(
        self, csv: tuple[str, ...], xlsx: tuple[str, ...], first: int
    ):
        result = analyze([(1, csv)], [(6, xlsx)])
        tiers = result["counts"]["tiers"]
        expected_edges = (
            [0, 1, 0, 1, 1]
            if first == 1
            else [int(index >= first) for index in range(5)]
        )
        for index in range(5):
            self.assertEqual(
                tiers[f"K{index}"]["unique_candidate_edges"],
                expected_edges[index],
                f"K{index}",
            )
        self.assertEqual(result["counts"]["statuses"]["csv_isolated_candidate"], 1)
        self.assertEqual(result["counts"]["statuses"]["xlsx_isolated_candidate"], 1)
        self.assertEqual(result["sale_labels_certified"], 0)
        return result

    def test_k0_matches_exact_trimmed_strings_and_is_source_order_independent(self):
        a = sale()
        b = sale(block="00013", address="OTHER PRIVATE ADDRESS")
        result = analyze([(1, a), (2, b)], [(8, b), (7, a)])
        reordered = analyze([(2, b), (1, a)], [(7, a), (8, b)])
        self.assertEqual(result["counts"], reordered["counts"])
        self.assertEqual(result["counts"]["tiers"]["K0"]["unique_candidate_edges"], 2)
        self.assertEqual(result["counts"]["statuses"]["csv_isolated_candidate"], 2)
        self.assertEqual(result["counts"]["fields"]["full_row_matches"], 2)
        self.assertEqual(result["label_status"], "unqualified")

    def test_k1_canonical_date_only(self):
        result = self.assert_only_tier_and_later_match(
            sale(date_text="09/15/2025"), sale(date_text="2025-09-15"), 1
        )
        fields = result["counts"]["fields"]
        self.assertEqual(fields["raw_date_matches"], 0)
        self.assertEqual(fields["canonical_date_matches"], 1)
        self.assertEqual(fields["raw_price_matches"], 1)

    def test_k2_decimal_price_only(self):
        result = analyze(
            [(1, sale(price="750,000.00"))], [(6, sale(price="750000.00"))]
        )
        tiers = result["counts"]["tiers"]
        self.assertEqual(
            [tiers[f"K{i}"]["unique_candidate_edges"] for i in range(5)],
            [0, 0, 1, 1, 1],
        )
        self.assertEqual(result["counts"]["fields"]["raw_price_matches"], 0)
        self.assertEqual(result["counts"]["fields"]["decimal_price_matches"], 1)

    def test_k3_requires_both_date_and_price_conversion(self):
        self.assert_only_tier_and_later_match(
            sale(date_text="09/15/2025", price="750,000.00"),
            sale(date_text="2025-09-15", price="7.5e5"),
            3,
        )

    def test_k4_removes_leading_zero_only_from_positive_ascii_block_lot(self):
        self.assert_only_tier_and_later_match(
            sale(block="00012", lot="003", date_text="09/15/2025", price="750,000.00"),
            sale(block="12", lot="3", date_text="2025-09-15", price="7.5e5"),
            4,
        )
        for block in ("0", "-12", "+12", "１２", "12A"):
            with self.subTest(block=block):
                result = analyze([(1, sale(block=block))], [(6, sale(block="12"))])
                self.assertEqual(
                    result["counts"]["tiers"]["K4"]["unique_candidate_edges"], 0
                )

    def test_apartment_keeps_leading_zero_and_blank_is_not_wildcard(self):
        for apartment in ("", "04B"):
            with self.subTest(apartment=apartment):
                result = analyze(
                    [(1, sale(apartment=apartment))],
                    [(6, sale(block="12", lot="3", apartment="4B"))],
                )
                self.assertEqual(
                    result["counts"]["tiers"]["K4"]["unique_candidate_edges"], 0
                )

    def test_typed_tier_parse_failure_never_becomes_blank_key(self):
        bad = sale(date_text="2025-09-15T23:00:00", price="750000")
        good = sale(date_text="2025-09-15", price="750000")
        result = analyze([(1, bad)], [(6, good)])
        self.assertEqual(result["counts"]["tiers"]["K0"]["csv_valid_rows"], 1)
        self.assertEqual(result["counts"]["tiers"]["K1"]["csv_valid_rows"], 0)
        self.assertEqual(result["counts"]["parse_failures"]["csv_date"], 1)
        self.assertEqual(result["counts"]["statuses"]["csv_unmatched"], 1)

    def test_duplicate_key_and_cross_tier_edges_remain_ambiguous(self):
        csv = sale(date_text="09/15/2025", price="750000")
        x_date = sale(date_text="2025-09-15", price="750000")
        x_price = sale(date_text="09/15/2025", price="7.5e5")
        result = analyze([(1, csv)], [(6, x_date), (7, x_price)])
        tiers = result["counts"]["tiers"]
        self.assertEqual(tiers["K1"]["unique_candidate_edges"], 1)
        self.assertEqual(tiers["K2"]["unique_candidate_edges"], 1)
        self.assertEqual(tiers["K3"]["ambiguous_shared_groups"], 1)
        self.assertEqual(result["counts"]["statuses"]["csv_isolated_candidate"], 0)
        self.assertEqual(result["counts"]["statuses"]["csv_ambiguous"], 1)
        self.assertEqual(result["counts"]["statuses"]["xlsx_ambiguous"], 2)

    def test_k4_normalization_collision_overrides_unique_k0_edge(self):
        result = analyze(
            [(1, sale(block="00012")), (2, sale(block="12"))],
            [(6, sale(block="12"))],
        )
        tiers = result["counts"]["tiers"]
        self.assertEqual(tiers["K0"]["unique_candidate_edges"], 1)
        self.assertEqual(tiers["K4"]["ambiguous_shared_groups"], 1)
        self.assertEqual(result["counts"]["statuses"]["csv_isolated_candidate"], 0)
        self.assertEqual(result["counts"]["statuses"]["csv_ambiguous"], 2)
        self.assertEqual(result["counts"]["statuses"]["xlsx_ambiguous"], 1)

    def test_raw_key_incomplete_is_exclusive_status_and_other_side_unmatched(self):
        result = analyze([(1, sale(block=" "))], [(6, sale())])
        self.assertEqual(result["counts"]["statuses"]["csv_raw_key_incomplete"], 1)
        self.assertEqual(result["counts"]["statuses"]["xlsx_unmatched"], 1)
        for tier in result["counts"]["tiers"].values():
            self.assertEqual(tier["csv_valid_rows"], 0)

    def test_every_tier_has_source_row_and_group_reconciliation(self):
        result = analyze(
            [(1, sale()), (2, sale()), (3, sale(block=" "))],
            [(6, sale()), (7, sale(block="999"))],
        )
        required = {
            "csv_valid_rows",
            "xlsx_valid_rows",
            "csv_invalid_or_incomplete_rows",
            "xlsx_invalid_or_incomplete_rows",
            "unique_candidate_edges",
            "ambiguous_shared_groups",
            "csv_unique_edge_rows",
            "xlsx_unique_edge_rows",
            "csv_shared_ambiguous_rows",
            "xlsx_shared_ambiguous_rows",
            "csv_only_rows",
            "xlsx_only_rows",
            "csv_key_groups",
            "xlsx_key_groups",
            "csv_duplicate_key_groups",
            "xlsx_duplicate_key_groups",
            "csv_only_key_groups",
            "xlsx_only_key_groups",
        }
        for name, tier in result["counts"]["tiers"].items():
            with self.subTest(tier=name):
                self.assertTrue(required <= set(tier))
                for source, total in (("csv", 3), ("xlsx", 2)):
                    self.assertEqual(
                        tier[f"{source}_valid_rows"]
                        + tier[f"{source}_invalid_or_incomplete_rows"],
                        total,
                    )
                    self.assertEqual(
                        tier[f"{source}_valid_rows"],
                        tier[f"{source}_unique_edge_rows"]
                        + tier[f"{source}_shared_ambiguous_rows"]
                        + tier[f"{source}_only_rows"],
                    )
                    self.assertEqual(
                        tier[f"{source}_key_groups"],
                        tier["unique_candidate_edges"]
                        + tier["ambiguous_shared_groups"]
                        + tier[f"{source}_only_key_groups"],
                    )
        self.assertEqual(result["counts"]["tiers"]["K0"]["csv_duplicate_key_groups"], 1)

    def test_zero_and_negative_prices_are_diagnostic_candidates_only(self):
        for price in ("0", "-123.45"):
            with self.subTest(price=price):
                result = analyze([(1, sale(price=price))], [(6, sale(price=price))])
                self.assertEqual(
                    result["counts"]["tiers"]["K0"]["unique_candidate_edges"], 1
                )
                self.assertEqual(result["sale_labels_certified"], 0)
                self.assertEqual(result["label_status"], "unqualified")


class RepresentationAccountingPrivacyTest(unittest.TestCase):
    def assert_rejects_tampered_counts(self, mutator):
        result = analyze([(1, sale())], [(6, sale())])
        mutator(result["counts"])
        with self.assertRaises(ValueError):
            core.public_projection(result)

    def test_public_projection_rejects_malformed_nested_tiers(self):
        def remove_tier(counts):
            del counts["tiers"]["K3"]

        def add_unknown_tier(counts):
            counts["tiers"]["K5"] = dict(counts["tiers"]["K4"])

        def remove_tier_metric(counts):
            del counts["tiers"]["K0"]["csv_valid_rows"]

        def insert_boolean(counts):
            counts["tiers"]["K0"]["unique_candidate_edges"] = True

        def break_tier_reconciliation(counts):
            counts["tiers"]["K0"]["csv_valid_rows"] += 1

        for mutator in (
            remove_tier,
            add_unknown_tier,
            remove_tier_metric,
            insert_boolean,
            break_tier_reconciliation,
        ):
            with self.subTest(mutator=mutator.__name__):
                self.assert_rejects_tampered_counts(mutator)

    def test_public_projection_rejects_malformed_nested_statuses(self):
        def remove_status(counts):
            del counts["statuses"]["xlsx_unmatched"]

        def add_unknown_status(counts):
            counts["statuses"]["csv_private"] = 0

        def insert_negative(counts):
            counts["statuses"]["csv_isolated_candidate"] = -1

        def insert_boolean(counts):
            counts["statuses"]["xlsx_isolated_candidate"] = True

        def break_status_reconciliation(counts):
            counts["statuses"]["xlsx_isolated_candidate"] = 0

        for mutator in (
            remove_status,
            add_unknown_status,
            insert_negative,
            insert_boolean,
            break_status_reconciliation,
        ):
            with self.subTest(mutator=mutator.__name__):
                self.assert_rejects_tampered_counts(mutator)

    def test_public_projection_rejects_tampered_private_ledger(self):
        def remove_entry(result):
            result["ledger"].pop()

        def duplicate_csv_ordinal(result):
            result["ledger"][1]["ordinal"] = result["ledger"][0]["ordinal"]

        def inject_raw_key(result):
            result["ledger"][0]["raw_key"] = "PRIVATE UNIT"

        def invalidate_fingerprint(result):
            result["ledger"][0]["row_sha256"] = "G" * 64

        def mismatch_status(result):
            result["ledger"][0]["status"] = "unmatched"

        for mutator in (
            remove_entry,
            duplicate_csv_ordinal,
            inject_raw_key,
            invalidate_fingerprint,
            mismatch_status,
        ):
            with self.subTest(mutator=mutator.__name__):
                first = sale(block="1")
                second = sale(block="2")
                result = analyze(
                    [(1, first), (2, second)],
                    [(6, first), (7, second)],
                )
                mutator(result)
                with self.assertRaises(ValueError) as raised:
                    core.public_projection(result)
                self.assertNotIn("PRIVATE UNIT", str(raised.exception))

    def test_public_projection_rejects_invalid_format_only_count(self):
        for value in (-1, 2, True, 1.5):
            with self.subTest(value=value):
                self.assert_rejects_tampered_counts(
                    lambda counts: counts["fields"].update(format_only_candidates=value)
                )

    def test_public_projection_rejects_malformed_lexical_histograms(self):
        def remove_date_category(counts):
            del counts["lexical_forms"]["csv"]["date"]["us_date"]

        def add_unregistered_price_category(counts):
            counts["lexical_forms"]["csv"]["price"]["raw_secret"] = 0

        def invalidate_histogram_total(counts):
            counts["lexical_forms"]["csv"]["date"]["us_date"] += 1

        def insert_boolean(counts):
            counts["lexical_forms"]["csv"]["date"]["us_date"] = True

        for mutator in (
            remove_date_category,
            add_unregistered_price_category,
            invalidate_histogram_total,
            insert_boolean,
        ):
            with self.subTest(mutator=mutator.__name__):
                self.assert_rejects_tampered_counts(mutator)

    def test_public_projection_rejects_malformed_overlap_counts(self):
        def remove_column(counts):
            counts["overlap"]["raw_columns"].pop()

        def exceed_source_denominator(counts):
            counts["overlap"]["raw_columns"][0] = 2

        def insert_negative(counts):
            counts["overlap"]["decimal_price"] = -1

        def add_unknown_key(counts):
            counts["overlap"]["private_value"] = 0

        for mutator in (
            remove_column,
            exceed_source_denominator,
            insert_negative,
            add_unknown_key,
        ):
            with self.subTest(mutator=mutator.__name__):
                self.assert_rejects_tampered_counts(mutator)

    def test_public_projection_rejects_malformed_parse_failure_counts(self):
        def remove_count(counts):
            del counts["parse_failures"]["csv_date"]

        def exceed_source_denominator(counts):
            counts["parse_failures"]["xlsx_price"] = 2

        def insert_boolean(counts):
            counts["parse_failures"]["csv_price"] = True

        def add_unknown_key(counts):
            counts["parse_failures"]["invented"] = 0

        for mutator in (
            remove_count,
            exceed_source_denominator,
            insert_boolean,
            add_unknown_key,
        ):
            with self.subTest(mutator=mutator.__name__):
                self.assert_rejects_tampered_counts(mutator)

    def test_public_projection_rejects_malformed_collision_counts(self):
        def remove_count(counts):
            del counts["normalization_collisions"]["csv"]["groups"]

        def exceed_source_denominator(counts):
            counts["normalization_collisions"]["csv"]["rows"] = 2

        def insert_negative(counts):
            counts["normalization_collisions"]["xlsx"]["groups"] = -1

        def add_unknown_key(counts):
            counts["normalization_collisions"]["xlsx"]["private_value"] = 0

        for mutator in (
            remove_count,
            exceed_source_denominator,
            insert_negative,
            add_unknown_key,
        ):
            with self.subTest(mutator=mutator.__name__):
                self.assert_rejects_tampered_counts(mutator)

    def test_lexical_form_histograms_are_fixed_categories_and_reconcile(self):
        serial = str((date(2025, 9, 15) - date(1899, 12, 30)).days)
        result = analyze(
            [
                (1, sale()),
                (2, sale(block="13", date_text="2025-09-15", price="750,000")),
            ],
            [(6, sale(date_text=serial, price="7.5e5"))],
        )
        lexical = result["counts"]["lexical_forms"]
        for source, total in (("csv", 2), ("xlsx", 1)):
            for family in ("date", "price"):
                histogram = lexical[source][family]
                self.assertTrue(histogram)
                self.assertTrue(
                    all(
                        type(value) is int and value >= 0
                        for value in histogram.values()
                    )
                )
                self.assertEqual(sum(histogram.values()), total)
        self.assertNotIn("PRIVATE", json.dumps(lexical))

    def test_field_comparison_separates_raw_typed_and_other_columns(self):
        result = analyze(
            [(1, sale(date_text="09/15/2025", price="750,000.00"))],
            [(6, sale(date_text="2025-09-15", price="7.5e5"))],
        )
        fields = result["counts"]["fields"]
        self.assertEqual(fields["raw_date_matches"], 0)
        self.assertEqual(fields["canonical_date_matches"], 1)
        self.assertEqual(fields["canonical_date_mismatches"], 0)
        self.assertEqual(fields["canonical_date_unparseable"], 0)
        self.assertEqual(fields["raw_price_matches"], 0)
        self.assertEqual(fields["decimal_price_matches"], 1)
        self.assertEqual(fields["decimal_price_mismatches"], 0)
        self.assertEqual(fields["decimal_price_unparseable"], 0)
        self.assertEqual(fields["other_19_exact"], 1)
        self.assertEqual(fields["full_row_matches"], 0)
        disagreements = fields["column_disagreements"]
        self.assertEqual(len(disagreements), 21)
        self.assertEqual(
            [i for i, value in enumerate(disagreements) if value], [19, 20]
        )

    def test_address_and_building_class_disagreements_are_independent(self):
        result = analyze(
            [(1, sale(address="PRIVATE A", building_class="A1"))],
            [(6, sale(address="PRIVATE B", building_class="B2"))],
        )
        fields = result["counts"]["fields"]
        self.assertEqual(fields["address_matches"], 0)
        self.assertEqual(fields["building_class_matches"], 0)
        self.assertEqual(fields["other_19_exact"], 0)
        self.assertEqual(fields["column_disagreements"][8], 1)
        self.assertEqual(fields["column_disagreements"][18], 1)

    def test_unparseable_typed_values_on_k0_pair_are_tristate(self):
        row = sale(date_text="bad date", price="bad price")
        result = analyze([(1, row)], [(6, row)])
        fields = result["counts"]["fields"]
        self.assertEqual(fields["raw_date_matches"], 1)
        self.assertEqual(fields["raw_price_matches"], 1)
        self.assertEqual(fields["canonical_date_matches"], 0)
        self.assertEqual(fields["canonical_date_unparseable"], 1)
        self.assertEqual(fields["decimal_price_matches"], 0)
        self.assertEqual(fields["decimal_price_unparseable"], 1)

    def test_overlap_counts_same_column_values_independent_of_pairing(self):
        result = analyze(
            [(1, sale(date_text="09/15/2025", price="750,000.00"))],
            [(6, sale(date_text="2025-09-15", price="7.5e5"))],
        )
        overlap = result["counts"]["overlap"]
        self.assertEqual(len(overlap["raw_columns"]), 21)
        self.assertEqual(overlap["raw_columns"][8], 1)
        self.assertEqual(overlap["raw_columns"][19], 0)
        self.assertEqual(overlap["raw_columns"][20], 0)
        self.assertEqual(overlap["canonical_date"], 1)
        self.assertEqual(overlap["decimal_price"], 1)
        self.assertEqual(overlap["canonical_block"], 1)
        self.assertEqual(overlap["canonical_lot"], 1)

    def test_exclusive_statuses_reconcile_each_source_and_ledger_is_private(self):
        csv = [
            (1, sale()),
            (2, sale(block="888")),
            (3, sale(block=" ")),
        ]
        xlsx = [(6, sale()), (7, sale(block="999"))]
        result = analyze(csv, xlsx)
        statuses = result["counts"]["statuses"]
        for source, expected in (("csv", 3), ("xlsx", 2)):
            self.assertEqual(
                sum(
                    statuses[f"{source}_{status}"]
                    for status in (
                        "isolated_candidate",
                        "ambiguous",
                        "unmatched",
                        "raw_key_incomplete",
                    )
                ),
                expected,
            )
        self.assertEqual(len(result["ledger"]), 5)
        for entry in result["ledger"]:
            self.assertIn(
                entry["status"],
                {"isolated_candidate", "ambiguous", "unmatched", "raw_key_incomplete"},
            )
            self.assertEqual(len(entry["row_sha256"]), 64)
            self.assertNotIn("PRIVATE", json.dumps(entry))
        self.assertNotIn("PRIVATE", json.dumps(result))
        self.assertNotIn("750000", json.dumps(result))

    def test_rejects_malformed_source_rows_and_borough_without_exposing_values(self):
        bad_inputs = (
            ([(1, sale(borough="3"))], []),
            ([(1, sale()[:-1])], []),
            ([(1, (*sale()[:-1], 5))], []),
            ([(0, sale())], []),
            ([(True, sale())], []),
            ([(1, sale()), (1, sale())], []),
        )
        for csv, xlsx in bad_inputs:
            with self.subTest(csv=csv, xlsx=xlsx):
                with self.assertRaises(ValueError) as raised:
                    analyze(csv, xlsx)
                self.assertNotIn("PRIVATE", str(raised.exception))
        with self.assertRaises(ValueError):
            analyze([], [], borough="Manhattan", borough_code="1")

    def test_combined_source_character_limit_applies_before_comparison(self):
        row = sale()
        with patch.object(core, "MAX_RESIDENT_CELL_CHARS", sum(map(len, row)) * 2 - 1):
            with self.assertRaisesRegex(ValueError, "character cap"):
                analyze([(1, row)], [(6, row)])

    def test_public_projection_suppresses_small_cell_and_staten_even_when_large(self):
        small = core.public_projection(analyze([(1, sale())], [(6, sale())]))
        self.assertIsNone(small["counts"])
        self.assertEqual(small["suppression_reason"], "small_positive_cell_1_to_4")
        staten_rows = [(i, sale(borough="5", block=str(i))) for i in range(1, 6)]
        staten = analyze(
            staten_rows,
            [(i + 5, row) for i, (_, row) in enumerate(staten_rows, 1)],
            borough="Staten Island",
            borough_code="5",
        )
        public = core.public_projection(staten)
        self.assertIsNone(public["counts"])
        self.assertEqual(
            public["suppression_reason"], "staten_cross_version_protection"
        )
        self.assertNotIn("ledger", public)
        self.assertNotIn("overlap", json.dumps(public))

    def test_public_projection_suppresses_small_pairwise_tier_difference(self):
        shared = [(index, sale(block=str(index))) for index in range(1, 6)]
        csv = [
            *shared,
            (6, sale(block="50", date_text="09/15/2025", address="PRIVATE A")),
            *((index, sale(block=str(100 + index))) for index in range(7, 12)),
        ]
        xlsx = [
            *((index + 20, row) for index, row in shared),
            (26, sale(block="50", date_text="2025-09-15", address="PRIVATE B")),
            *((index + 20, sale(block=str(200 + index))) for index in range(7, 12)),
        ]
        result = analyze(csv, xlsx)
        counts = result["counts"]
        values = [
            *(
                counts["tiers"][f"K{index}"]["unique_candidate_edges"]
                for index in range(5)
            ),
            counts["statuses"]["csv_isolated_candidate"],
            counts["fields"]["format_only_candidates"],
        ]
        self.assertEqual(values, [5, 6, 5, 6, 6, 6, 0])
        self.assertTrue(all(value == 0 or value >= 5 for value in values))
        self.assertTrue(
            all(
                denominator - value >= 5 for denominator in (11, 11) for value in values
            )
        )
        self.assertIsNone(core.public_projection(result)["counts"])
        self.assertEqual(
            core.public_projection(result)["suppression_reason"],
            "small_positive_cell_1_to_4",
        )

    def test_public_projection_suppresses_small_denominator_complement(self):
        shared = [(index, sale(block=str(index))) for index in range(1, 6)]
        result = analyze(
            [*shared, (6, sale(block="100"))],
            [*((index + 10, row) for index, row in shared), (16, sale(block="200"))],
        )
        counts = result["counts"]
        values = [
            *(
                counts["tiers"][f"K{index}"]["unique_candidate_edges"]
                for index in range(5)
            ),
            counts["statuses"]["csv_isolated_candidate"],
            counts["fields"]["format_only_candidates"],
        ]
        self.assertEqual(values, [5, 5, 5, 5, 5, 5, 0])
        self.assertTrue(all(value == 0 or value >= 5 for value in values))
        self.assertTrue(
            all(abs(a - b) not in range(1, 5) for a in values for b in values)
        )
        self.assertEqual(result["csv_rows"] - values[0], 1)
        self.assertIsNone(core.public_projection(result)["counts"])
        self.assertEqual(
            core.public_projection(result)["suppression_reason"],
            "small_positive_cell_1_to_4",
        )

    def test_public_projection_allowlists_safe_aggregate_and_rejects_tampering(self):
        rows = [(i, sale(block=str(i))) for i in range(1, 6)]
        result = analyze(rows, [(i + 5, row) for i, row in rows])
        public = core.public_projection(result)
        self.assertEqual(public["counts"]["tiers"]["K0"]["unique_candidate_edges"], 5)
        self.assertNotIn("overlap", json.dumps(public))
        self.assertNotIn("column_disagreements", json.dumps(public))
        self.assertNotIn("ledger", json.dumps(public))
        self.assertEqual(public["label_status"], "unqualified")
        result["counts"]["statuses"]["csv_isolated_candidate"] += 1
        with self.assertRaises(ValueError):
            core.public_projection(result)


if __name__ == "__main__":
    unittest.main()
