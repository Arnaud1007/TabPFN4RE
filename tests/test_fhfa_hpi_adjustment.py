"""Contract tests for an explicitly experimental FHFA HPI adjustment."""

from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError
from datetime import date

from tabpfn4realestate.features.fhfa_hpi import (
    HpiObservation,
    HpiSeries,
    adjust_price,
)

from scripts.king_research_predict import with_hpi_research_adjustment

SOURCE_SHA256 = (
    "d664a8e2e92f64aa17201b3bdd84d0ab4d1a4d00e9c6c15d5b34fb400c10d842"
)
SNAPSHOT_AVAILABLE_AT = date(2026, 10, 5)


def research_series(
    observations: tuple[HpiObservation, ...] | None = None,
) -> HpiSeries:
    return HpiSeries(
        series_id="FHFA_PO_NSA_SEATTLE_BELLEVUE_KENT",
        cbsa_code="42644",
        geography="Seattle-Bellevue-Kent, WA (MSAD)",
        index_type="purchase-only",
        seasonality="not-seasonally-adjusted",
        source_sha256=SOURCE_SHA256,
        source_release_date=date(2026, 8, 25),
        retrieved_at=date(2026, 10, 5),
        observations=(
            observations
            if observations is not None
            else (
                HpiObservation("2014Q3", 282.69, SNAPSHOT_AVAILABLE_AT),
                HpiObservation("2015Q1", 293.68, SNAPSHOT_AVAILABLE_AT),
                HpiObservation("2015Q2", 311.57, SNAPSHOT_AVAILABLE_AT),
                HpiObservation("2026Q2", 638.47, SNAPSHOT_AVAILABLE_AT),
            )
        ),
    )


class FhfaHpiAdjustmentTests(unittest.TestCase):
    def test_exact_quarter_values_produce_a_frozen_research_adjustment(self) -> None:
        adjustment = adjust_price(
            amount=200_000.0,
            series=research_series(),
            base_quarter="2014Q3",
            target_quarter="2026Q2",
            as_of=date(2026, 10, 5),
        )

        self.assertAlmostEqual(adjustment.amount, 451_710.3540981287)
        self.assertAlmostEqual(adjustment.factor, 638.47 / 282.69)
        self.assertEqual(adjustment.base_index, 282.69)
        self.assertEqual(adjustment.target_index, 638.47)
        self.assertEqual(adjustment.base_quarter, "2014Q3")
        self.assertEqual(adjustment.target_quarter, "2026Q2")
        self.assertEqual(adjustment.as_of, date(2026, 10, 5))
        with self.assertRaises(FrozenInstanceError):
            adjustment.amount = 1.0  # type: ignore[misc]

    def test_series_and_observations_are_immutable_value_objects(self) -> None:
        observation = HpiObservation("2026Q2", 638.47, SNAPSHOT_AVAILABLE_AT)
        series = research_series((observation,))

        with self.assertRaises(FrozenInstanceError):
            observation.index_value = 1.0  # type: ignore[misc]
        with self.assertRaises(FrozenInstanceError):
            series.geography = "changed"  # type: ignore[misc]
        self.assertIsInstance(series.observations, tuple)

    def test_pinned_2015_quarters_remain_available_for_retrospective_backtest(
        self,
    ) -> None:
        for target_quarter, expected in (
            ("2015Q1", 293_680.0),
            ("2015Q2", 311_570.0),
        ):
            with self.subTest(target_quarter=target_quarter):
                adjustment = adjust_price(
                    amount=282_690.0,
                    series=research_series(),
                    base_quarter="2014Q3",
                    target_quarter=target_quarter,
                    as_of=SNAPSHOT_AVAILABLE_AT,
                )
                self.assertAlmostEqual(adjustment.amount, expected)

    def test_missing_quarter_is_rejected_instead_of_using_nearest_value(self) -> None:
        with self.assertRaisesRegex(ValueError, "exact.*2026Q1"):
            adjust_price(
                amount=200_000.0,
                series=research_series(),
                base_quarter="2014Q3",
                target_quarter="2026Q1",
                as_of=date(2026, 10, 5),
            )

    def test_future_target_quarter_is_rejected_even_if_a_row_is_present(self) -> None:
        series = research_series(
            (
                HpiObservation("2014Q3", 282.69, SNAPSHOT_AVAILABLE_AT),
                HpiObservation("2026Q4", 650.0, SNAPSHOT_AVAILABLE_AT),
            )
        )

        with self.assertRaisesRegex(ValueError, "future quarter"):
            adjust_price(
                amount=200_000.0,
                series=series,
                base_quarter="2014Q3",
                target_quarter="2026Q4",
                as_of=date(2026, 10, 5),
            )

    def test_unpublished_observation_is_rejected_at_the_requested_as_of_date(self) -> None:
        with self.assertRaisesRegex(ValueError, "not available"):
            adjust_price(
                amount=200_000.0,
                series=research_series(),
                base_quarter="2014Q3",
                target_quarter="2026Q2",
                as_of=date(2026, 7, 31),
            )

    def test_invalid_series_and_adjustment_inputs_fail_closed(self) -> None:
        invalid_observations = (
            (),
            (HpiObservation("2026-Q2", 638.47, SNAPSHOT_AVAILABLE_AT),),
            (HpiObservation("2026Q2", 0.0, SNAPSHOT_AVAILABLE_AT),),
            (
                HpiObservation("2026Q2", 638.47, SNAPSHOT_AVAILABLE_AT),
                HpiObservation("2026Q2", 638.48, SNAPSHOT_AVAILABLE_AT),
            ),
        )
        for observations in invalid_observations:
            with self.subTest(observations=observations), self.assertRaises(ValueError):
                research_series(observations)

        for amount in (0, -1, float("nan"), float("inf"), True, "200000"):
            with self.subTest(amount=amount), self.assertRaises(ValueError):
                adjust_price(
                    amount=amount,  # type: ignore[arg-type]
                    series=research_series(),
                    base_quarter="2014Q3",
                    target_quarter="2026Q2",
                    as_of=date(2026, 10, 5),
                )

    def test_king_response_retains_historical_estimate_and_adds_clear_metadata(
        self,
    ) -> None:
        response = {
            "amount": 200_000.0,
            "currency": "USD",
            "model": "xgboost",
            "status": "historical_research_only",
            "reference_period": "King County sales, January-February 2015",
            "certified_90_day_origin": False,
            "g_us_gate": "PENDING",
            "manifest_sha256": "b" * 64,
            "model_sha256": "c" * 64,
        }
        original = dict(response)

        result = with_hpi_research_adjustment(
            response,
            series=research_series(),
            base_quarter="2014Q3",
            target_quarter="2026Q2",
            as_of=date(2026, 10, 5),
        )

        self.assertIsNot(result, response)
        self.assertEqual(response, original)
        self.assertEqual(result["amount"], 200_000.0)
        self.assertEqual(result["status"], "historical_research_only")
        self.assertFalse(result["certified_90_day_origin"])
        self.assertEqual(result["g_us_gate"], "PENDING")
        metadata = result["experimental_hpi_adjustment"]
        self.assertAlmostEqual(metadata["amount"], 451_710.3540981287)
        self.assertEqual(metadata["currency"], "USD")
        self.assertEqual(metadata["status"], "research_only")
        self.assertEqual(metadata["series_id"], research_series().series_id)
        self.assertEqual(metadata["cbsa_code"], "42644")
        self.assertEqual(metadata["geography"], research_series().geography)
        self.assertEqual(metadata["index_type"], "purchase-only")
        self.assertEqual(metadata["seasonality"], "not-seasonally-adjusted")
        self.assertEqual(metadata["base_quarter"], "2014Q3")
        self.assertEqual(metadata["target_quarter"], "2026Q2")
        self.assertEqual(metadata["as_of"], "2026-10-05")
        self.assertEqual(metadata["source_release_date"], "2026-08-25")
        self.assertEqual(metadata["snapshot_available_at"], "2026-10-05")
        self.assertEqual(metadata["source_sha256"], SOURCE_SHA256)
        warning = metadata["warning"].lower()
        self.assertIn("research only", warning)
        self.assertIn("average market appreciation", warning)
        self.assertIn("not a current valuation", warning)
        self.assertIn("not a 90-day estimate", warning)


if __name__ == "__main__":
    unittest.main()
