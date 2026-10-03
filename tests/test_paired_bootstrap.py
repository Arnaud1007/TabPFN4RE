"""Synthetic US13 paired, dependence-aware bootstrap contracts."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal, localcontext
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tabpfn4realestate.evaluation.metrics import (  # noqa: E402
    PredictionRow,
    score_predictions,
)
from tabpfn4realestate.evaluation.paired_bootstrap import (  # noqa: E402
    ComparisonMeta,
    compare_paired_blocks,
)


BASE = datetime(2024, 1, 1, tzinfo=timezone.utc)
D = Decimal


def metadata(
    row_id, index=0, *, property_id=None, market="metro-a", geo=None, time=None
):
    return ComparisonMeta(
        row_id=row_id,
        property_id=property_id or f"property-{row_id}",
        market_id=market,
        geographic_block_id=geo or f"geo-{index}",
        temporal_block_id=time or "quarter-1",
        origin=BASE + timedelta(days=index),
    )


def prediction(row_id, estimate, *, actual="100", status="estimated", currency="USD"):
    return PredictionRow(
        row_id=row_id,
        actual=D(actual),
        predicted=D(estimate) if estimate is not None else None,
        actual_currency=currency,
        predicted_currency=currency if estimate is not None else None,
        status=status,
        reason=None if status == "estimated" else "unsupported",
    )


def compare(meta, baseline, challenger, **changes):
    options = {"split_hash": "a" * 64, "block_plan_hash": "b" * 64, "draws": 100}
    return compare_paired_blocks(meta, baseline, challenger, **(options | changes))


def twenty_rows():
    meta = tuple(
        metadata(
            f"row-{index:02d}", index, market="metro-a" if index < 10 else "metro-b"
        )
        for index in range(20)
    )
    base = tuple(
        prediction(row.row_id, str(112 + index % 5)) for index, row in enumerate(meta)
    )
    challenger = tuple(
        prediction(row.row_id, str(102 + index % 7)) for index, row in enumerate(meta)
    )
    return meta, base, challenger


def type7(values, numerator, denominator):
    ordered = sorted(values)
    with localcontext() as context:
        context.prec = 40
        position = D(len(ordered) - 1) * D(numerator) / D(denominator)
        lower = int(position)
        weight = position - lower
        return (
            ordered[lower] * (1 - weight)
            + ordered[min(lower + 1, len(ordered) - 1)] * weight
        )


class PairedBootstrapTests(unittest.TestCase):
    def test_hand_calculated_signed_deltas_and_exact_ten_percent_boundary(self):
        meta = (metadata("a", 0), metadata("b", 1))
        baseline = (prediction("a", "120"), prediction("b", "90"))
        challenger = (prediction("a", "100"), prediction("b", "100"))
        result = compare(meta, baseline, challenger)
        self.assertEqual(result.status, "INCONCLUSIVE")
        self.assertIsNone(result.pooled.ci95)
        self.assertEqual(result.pooled.point.mdape, D("-0.15"))
        self.assertEqual(result.pooled.point.within_10, D("0.5"))
        self.assertEqual(result.pooled.point.signed_bias, D("-0.05"))
        self.assertEqual(result.pooled.point.absolute_bias, D("-0.05"))
        self.assertEqual(result.pooled.point.p90_ape, D("-0.19"))
        self.assertEqual(result.row_count, 2)

    def test_order_and_decimal_context_do_not_change_hash_or_seeded_replicates(self):
        meta, baseline, challenger = twenty_rows()
        baseline = (
            prediction(meta[0].row_id, "112.999", actual="100.001"),
        ) + baseline[1:]
        challenger = (
            prediction(meta[0].row_id, "102.001", actual="100.001"),
        ) + challenger[1:]
        first = compare(meta, baseline, challenger)
        with localcontext() as context:
            context.prec = 3
            reordered = compare(
                tuple(reversed(meta)),
                tuple(reversed(baseline)),
                tuple(reversed(challenger)),
            )
        self.assertEqual(first.status, "ESTIMABLE")
        self.assertEqual(first.comparison_hash, reordered.comparison_hash)
        self.assertEqual(first.pooled.replicates, reordered.pooled.replicates)
        self.assertEqual(
            first.equal_market.replicates, reordered.equal_market.replicates
        )
        self.assertEqual(first.component_count, 20)

    def test_transitive_property_links_keep_component_and_draw_order(self):
        linked = (
            metadata("a", 0, property_id="p1", geo="a"),
            metadata("z1", 1, property_id="p1", geo="z"),
            metadata("c", 2, property_id="p2", geo="c"),
            metadata("z2", 3, property_id="p2", geo="z"),
            metadata("b", 4, geo="b"),
        )
        filler = tuple(
            metadata(f"f-{i:02d}", i + 5, geo=f"f-{i:02d}") for i in range(18)
        )
        rows = linked + filler
        base = tuple(
            prediction(row.row_id, str(111 + i % 7)) for i, row in enumerate(rows)
        )
        challenger = tuple(
            prediction(row.row_id, str(102 + i % 5)) for i, row in enumerate(rows)
        )
        first = compare(rows, base, challenger)
        reverse = compare(
            tuple(reversed(rows)), tuple(reversed(base)), tuple(reversed(challenger))
        )
        self.assertEqual(first.component_count, 20)
        self.assertTrue(
            any(unit.row_ids == ("a", "c", "z1", "z2") for unit in first.components)
        )
        self.assertEqual(first.components, reverse.components)
        self.assertEqual(first.comparison_hash, reverse.comparison_hash)
        self.assertEqual(first.pooled.replicates, reverse.pooled.replicates)

    def test_point_metrics_match_shared_scorecard(self):
        meta = (metadata("a", 0), metadata("b", 1), metadata("c", 2), metadata("d", 3))
        baseline = (
            prediction("a", "4", actual="3"),
            prediction("b", "9", actual="10"),
            prediction("c", "110", actual="100"),
            prediction("d", "90", actual="100"),
        )
        challenger = tuple(
            prediction(row.row_id, str(row.actual), actual=str(row.actual))
            for row in baseline
        )
        result = compare(meta, baseline, challenger)
        left = score_predictions(baseline)
        right = score_predictions(challenger)
        for name, score_name in (
            ("mdape", "mdape"),
            ("within_10", "within_10"),
            ("signed_bias", "median_signed_percentage_error"),
            ("p90_ape", "p90_ape"),
        ):
            expected = getattr(right, score_name) - getattr(left, score_name)
            self.assertAlmostEqual(
                getattr(result.pooled.point, name), expected, places=25
            )
        self.assertAlmostEqual(
            result.pooled.point.absolute_bias,
            abs(right.median_signed_percentage_error)
            - abs(left.median_signed_percentage_error),
            places=25,
        )

    def test_missing_extra_duplicate_and_changed_actual_fail_before_sampling(self):
        meta, baseline, challenger = twenty_rows()
        with self.assertRaisesRegex(ValueError, "row IDs"):
            compare(meta, baseline[:-1], challenger)
        with self.assertRaisesRegex(ValueError, "row IDs"):
            compare(meta, baseline + (baseline[0],), challenger)
        with self.assertRaisesRegex(ValueError, "actual"):
            compare(
                meta,
                baseline,
                (replace(challenger[0], actual=D("101")),) + challenger[1:],
            )
        with self.assertRaisesRegex(ValueError, "USD"):
            prediction("wrong-currency", "100", currency="EUR")
        with self.assertRaisesRegex(ValueError, "metadata"):
            compare(meta[:-1], baseline, challenger)

    def test_failed_or_abstained_rows_cannot_shrink_pair_cohort(self):
        meta, baseline, challenger = twenty_rows()
        for status in ("failed", "abstained"):
            invalid = replace(
                challenger[0],
                predicted=None,
                predicted_currency=None,
                status=status,
                reason="unsupported",
            )
            with (
                self.subTest(status=status),
                self.assertRaisesRegex(ValueError, "estimated"),
            ):
                compare(meta, baseline, (invalid,) + challenger[1:])
        with self.assertRaises(ValueError):
            prediction("bad", "0")
        with self.assertRaises(ValueError):
            prediction("bad", "NaN")
        with self.assertRaisesRegex(ValueError, "representation budget"):
            prediction("oversized-money", "1E+65")

    def test_repeat_property_merges_space_time_cells(self):
        meta, baseline, challenger = twenty_rows()
        linked = replace(
            meta[1], property_id=meta[0].property_id, temporal_block_id="quarter-2"
        )
        result = compare((meta[0], linked) + meta[2:], baseline, challenger)
        self.assertEqual(result.component_count, 19)
        self.assertEqual(result.status, "INCONCLUSIVE")
        self.assertTrue(
            any(unit.row_ids == ("row-00", "row-01") for unit in result.components)
        )
        self.assertIsNone(result.pooled.ci95)
        crossing = replace(meta[10], property_id=meta[0].property_id)
        with self.assertRaisesRegex(ValueError, "markets"):
            compare(meta[:10] + (crossing,) + meta[11:], baseline, challenger)

    def test_giant_component_is_inconclusive_without_interval(self):
        meta, baseline, challenger = twenty_rows()
        merged = (
            tuple(replace(row, property_id="one-home") for row in meta[:10]) + meta[10:]
        )
        result = compare(merged, baseline, challenger)
        self.assertEqual(result.component_count, 11)
        self.assertEqual(result.status, "INCONCLUSIVE")
        self.assertEqual(result.pooled.replicates, ())

    def test_seed_draw_budget_and_hash_changes(self):
        meta, baseline, challenger = twenty_rows()
        first = compare(meta, baseline, challenger)
        self.assertEqual(first.draws_completed, 100)
        changed = compare(meta, baseline, challenger, seed=43)
        self.assertNotEqual(first.comparison_hash, changed.comparison_hash)
        self.assertNotEqual(first.pooled.replicates, changed.pooled.replicates)
        self.assertEqual(
            compare(meta, baseline, challenger, draws=5000).draws_completed, 5000
        )
        for changes in (
            {"draws": 1},
            {"draws": 5001},
            {"draws": True},
            {"seed": -1},
            {"seed": True},
            {"split_hash": "bad"},
            {"protocol_id": "us_real_v1"},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                compare(meta, baseline, challenger, **changes)

        class OversizedSequence:
            def __len__(self):
                return 100_001

            def __getitem__(self, index):
                raise AssertionError("Budget check must run before reading rows")

        with self.assertRaisesRegex(ValueError, "100,000-row budget"):
            compare(OversizedSequence(), baseline, challenger)

    def test_large_component_resampling_budget_fails_before_draws(self):
        large_cell = tuple(
            metadata(f"large-{i:04d}", i, geo="shared") for i in range(1001)
        )
        others = tuple(
            metadata(f"other-{i:02d}", i + 1001, geo=f"other-{i:02d}")
            for i in range(19)
        )
        rows = large_cell + others
        baseline = tuple(prediction(row.row_id, "110") for row in rows)
        challenger = tuple(prediction(row.row_id, "105") for row in rows)
        with self.assertRaisesRegex(ValueError, "resampling work budget"):
            compare(rows, baseline, challenger, draws=5000)

    def test_inconclusive_large_component_skips_resampling_budget(self):
        rows = tuple(
            metadata(f"one-{index:05d}", index, geo="one") for index in range(20_001)
        )
        baseline = tuple(prediction(row.row_id, "110") for row in rows)
        challenger = tuple(prediction(row.row_id, "105") for row in rows)
        result = compare(rows, baseline, challenger, draws=5000)
        self.assertEqual(result.status, "INCONCLUSIVE")
        self.assertEqual(result.component_count, 1)
        self.assertEqual(result.draws_completed, 0)
        self.assertIsNone(result.pooled.ci95)

    def test_percentile_interval_recomputes_from_saved_replicates(self):
        meta, baseline, challenger = twenty_rows()
        result = compare(meta, baseline, challenger)
        self.assertEqual(result.status, "ESTIMABLE")
        self.assertEqual(result.market_count, 2)
        for scope in (result.pooled, result.equal_market):
            self.assertEqual(len(scope.replicates), 100)
            observed = tuple(rep.mdape for rep in scope.replicates)
            self.assertEqual(scope.ci95.mdape.lower, type7(observed, 25, 1000))
            self.assertEqual(scope.ci95.mdape.upper, type7(observed, 975, 1000))
            self.assertLessEqual(scope.ci95.mdape.lower, scope.ci95.mdape.upper)
        self.assertNotEqual(result.pooled.point.mdape, result.equal_market.point.mdape)


if __name__ == "__main__":
    unittest.main()
