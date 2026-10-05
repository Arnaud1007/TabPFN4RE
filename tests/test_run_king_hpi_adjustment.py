"""Contract tests for the bounded King/FHFA retrospective replay."""

from __future__ import annotations

from decimal import Decimal
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tabpfn4realestate.evaluation.metrics import score_predictions

from scripts import run_king_hpi_adjustment as replay


PREDICTION_HEADER = (
    "row_id,sale_date,actual_usd,xgboost_usd,zipcode_median_usd\n"
)
HPI_HEADER = "cbsa\tmetro_name\tyr\tqtr\tindex_nsa\tindex_sa\n"


def prediction_bytes(rows: tuple[str, ...] | None = None) -> bytes:
    values = rows or (
        "q1,2015-03-31,100.00,100.00,90.00\n",
        "q2,2015-04-01,106.00,100.00,90.00\n",
    )
    return (PREDICTION_HEADER + "".join(values)).encode("utf-8")


def hpi_bytes() -> bytes:
    return (
        HPI_HEADER
        + '42644\t"Seattle-Bellevue-Kent, WA (MSAD)"\t2015\t1\t100.00\t99.00\n'
        + '42644\t"Seattle-Bellevue-Kent, WA (MSAD)"\t2015\t2\t106.00\t105.00\n'
    ).encode("utf-8")


class KingHpiReplayTests(unittest.TestCase):
    def run_fixture(
        self,
        *,
        predictions: bytes | None = None,
        hpi: bytes | None = None,
    ) -> dict[str, object]:
        prediction_content = predictions or prediction_bytes()
        hpi_content = hpi or hpi_bytes()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prediction_path = root / "later_predictions.csv"
            hpi_path = root / "hpi.tsv"
            prediction_path.write_bytes(prediction_content)
            hpi_path.write_bytes(hpi_content)
            result = replay.replay_adjustment(
                prediction_path=prediction_path,
                expected_prediction_sha256=hashlib.sha256(
                    prediction_content
                ).hexdigest(),
                hpi_path=hpi_path,
                expected_hpi_sha256=hashlib.sha256(hpi_content).hexdigest(),
            )
            self.assertEqual(prediction_path.read_bytes(), prediction_content)
            self.assertEqual(hpi_path.read_bytes(), hpi_content)
            return result

    def test_replay_preserves_raw_predictions_and_uses_each_exact_sale_quarter(
        self,
    ) -> None:
        with patch.object(
            replay,
            "score_predictions",
            wraps=score_predictions,
        ) as common_metric_engine:
            result = self.run_fixture()

        self.assertEqual(result["protocol"], "king_fhfa_adjustment_replay_v1")
        self.assertEqual(result["evidence_class"], "retrospective_research_only")
        self.assertFalse(result["certified_90_day_origin"])
        self.assertEqual(result["g_us_gate"], "PENDING")
        rows = result["rows"]
        self.assertEqual(
            [(row["row_id"], row["sale_quarter"]) for row in rows],
            [("q1", "2015Q1"), ("q2", "2015Q2")],
        )
        self.assertEqual(
            [row["xgboost_usd"] for row in rows],
            ["100.00", "100.00"],
        )
        self.assertEqual(
            [row["hpi_adjusted_xgboost_usd"] for row in rows],
            ["100.00", "106.00"],
        )
        self.assertEqual(
            [row["hpi_factor"] for row in rows],
            ["1", "1.06"],
        )

        scorecards = result["scorecards"]
        self.assertEqual(set(scorecards), {"overall", "2015Q1", "2015Q2"})
        for cohort in scorecards.values():
            self.assertEqual(
                set(cohort), {"xgboost", "hpi_adjusted_xgboost"}
            )
        self.assertEqual(
            scorecards["overall"]["hpi_adjusted_xgboost"]["mdape"], 0.0
        )
        self.assertGreater(scorecards["overall"]["xgboost"]["mdape"], 0.0)
        self.assertEqual(common_metric_engine.call_count, 6)

    def test_replay_verifies_both_input_hashes_before_parsing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prediction_path = root / "later_predictions.csv"
            hpi_path = root / "hpi.tsv"
            prediction_path.write_bytes(prediction_bytes())
            hpi_path.write_bytes(hpi_bytes())
            valid_prediction_hash = hashlib.sha256(prediction_bytes()).hexdigest()
            valid_hpi_hash = hashlib.sha256(hpi_bytes()).hexdigest()

            for changed_argument in (
                "expected_prediction_sha256",
                "expected_hpi_sha256",
            ):
                arguments = {
                    "prediction_path": prediction_path,
                    "expected_prediction_sha256": valid_prediction_hash,
                    "hpi_path": hpi_path,
                    "expected_hpi_sha256": valid_hpi_hash,
                }
                arguments[changed_argument] = "0" * 64
                with self.subTest(changed_argument=changed_argument):
                    with self.assertRaisesRegex(ValueError, "checksum"):
                        replay.replay_adjustment(**arguments)

    def test_schema_duplicate_ids_and_dates_outside_q1_q2_fail_closed(self) -> None:
        changed_header = prediction_bytes().replace(
            b"xgboost_usd", b"model_prediction_usd", 1
        )
        with self.assertRaisesRegex(ValueError, "schema"):
            self.run_fixture(predictions=changed_header)

        duplicated = prediction_bytes(
            (
                "same,2015-03-31,100,100,90\n",
                "same,2015-04-01,106,100,90\n",
            )
        )
        with self.assertRaisesRegex(ValueError, "[Dd]uplicate.*row"):
            self.run_fixture(predictions=duplicated)
        for invalid_date in ("2014-12-31", "2015-07-01", "not-a-date", ""):
            rows = (f"bad,{invalid_date},100,100,90\n",)
            with self.subTest(invalid_date=invalid_date):
                with self.assertRaisesRegex(ValueError, "sale date|quarter"):
                    self.run_fixture(predictions=prediction_bytes(rows))

    def test_candidate_criteria_are_explicit_and_require_every_guardrail(self) -> None:
        raw = {
            "mdape": Decimal("0.10"),
            "within_10": Decimal("0.80"),
            "p90_ape": Decimal("0.20"),
        }
        passing = {
            "mdape": Decimal("0.098"),
            "within_10": Decimal("0.795"),
            "p90_ape": Decimal("0.205"),
        }
        result = replay.assess_candidate(raw, passing)

        self.assertEqual(
            result["thresholds"],
            {
                "minimum_relative_mdape_reduction": "0.02",
                "maximum_within_10_degradation": "0.005",
                "maximum_p90_ape_degradation": "0.005",
            },
        )
        self.assertEqual(
            result["passes"],
            {
                "mdape_useful_gain": True,
                "within_10_noninferiority": True,
                "p90_ape_noninferiority": True,
            },
        )
        self.assertEqual(result["outcome"], "candidate_for_further_research")

        for key, value in (
            ("mdape", Decimal("0.099")),
            ("within_10", Decimal("0.7949")),
            ("p90_ape", Decimal("0.2051")),
        ):
            failing = dict(passing)
            failing[key] = value
            with self.subTest(key=key):
                self.assertEqual(
                    replay.assess_candidate(raw, failing)["outcome"],
                    "do_not_promote",
                )


if __name__ == "__main__":
    unittest.main()
