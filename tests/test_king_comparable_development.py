from __future__ import annotations

import json
import math
import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType, SimpleNamespace
from unittest.mock import patch

from scripts import run_king_comparable_development as comparable
from scripts.king_historical_benchmark import Sale


def sale(
    row_id: str,
    property_id: str,
    when: date,
    *,
    price: str = "100000",
    latitude: float = 47.6,
    longitude: float = -122.3,
    area: float = 1000,
) -> Sale:
    return Sale(
        row_id=row_id,
        property_id=property_id,
        sale_date=when,
        price=Decimal(price),
        attributes=MappingProxyType(
            {
                "lat": latitude,
                "long": longitude,
                "sqft_living": area,
                "zipcode": "98001",
            }
        ),
    )


class KingComparableDevelopmentTests(unittest.TestCase):
    def test_post_rename_acl_failure_removes_complete_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            private = Path(temporary) / "private"
            private.mkdir()
            output = private / "failed-run"
            lock = Path(temporary) / "lock.txt"
            lock.write_text("declared", encoding="utf-8")
            frozen_manifest = Path(temporary) / "frozen.json"
            frozen_manifest.write_text("{}", encoding="utf-8")
            with (
                patch.object(comparable, "PRIVATE_ROOT", private),
                patch.object(comparable, "DECLARED_LOCK", lock),
                patch.object(comparable, "FROZEN_MANIFEST", frozen_manifest),
                patch.object(comparable, "secure_directory"),
                patch.object(comparable, "real_directory"),
                patch.object(
                    comparable,
                    "verify_acl",
                    side_effect=(None, PermissionError("post-rename ACL failure")),
                ),
                patch.object(comparable, "_runtime_versions", return_value={}),
            ):
                with self.assertRaisesRegex(PermissionError, "post-rename"):
                    comparable._write_outputs(
                        output,
                        {},
                        (),
                        {},
                        {},
                        {},
                        {},
                        {},
                        {"split_sha256": "split"},
                        "a" * 40,
                    )
            self.assertFalse(output.exists())

    def test_chronological_residual_target_is_absent_from_its_training_model(
        self,
    ) -> None:
        rows = (
            sale("may", "may", date(2014, 5, 2)),
            sale("june-a", "june-a", date(2014, 6, 2), price="110000"),
            sale("june-b", "june-b", date(2014, 6, 3), price="120000"),
            sale("july", "july", date(2014, 7, 2), price="130000"),
        )
        calls: list[tuple[set[str], set[str]]] = []

        def fit(training, validation, weights):
            del weights
            calls.append(
                (
                    {item.row_id for item in training},
                    {item.row_id for item in validation},
                )
            )
            return tuple(100000.0 for _ in validation), object()

        with patch.object(comparable, "_fit_predict", side_effect=fit):
            residuals, folds = comparable.chronological_residuals(rows)

        self.assertNotIn("may", residuals)
        self.assertEqual(set(residuals), {"june-a", "june-b", "july"})
        self.assertEqual(set(folds), {"2014-06", "2014-07"})
        self.assertTrue(calls)
        self.assertTrue(all(not training & targets for training, targets in calls))

    def test_source_reader_never_parses_march_may_prices(self) -> None:
        prior = ["1", "20150228T000000", "100000", *("1" for _ in range(18))]
        future = ["2", "20150301T000000", "SECRET", *("1" for _ in range(18))]
        lines = [",".join(prior), *(",".join(future) for _ in range(21_612))]
        parsed = sale("prior", "1", date(2015, 2, 28))
        with (
            patch.object(comparable, "_decode_source", return_value=lines),
            patch.object(comparable, "_locate_data", return_value=-1),
            patch.object(comparable, "_parse_sale", return_value=parsed) as parse,
        ):
            result = comparable.read_development_source(Path("ignored"))

        self.assertEqual(result, (parsed,))
        parse.assert_called_once_with(prior, lines[0])

    def test_candidates_are_prior_deduplicated_and_deterministic(self) -> None:
        cutoff = date(2015, 1, 1)
        subject = sale("subject", "subject-home", cutoff)
        candidates = (
            sale("old-repeat", "repeat", date(2014, 8, 1), longitude=-122.301),
            sale("latest-repeat", "repeat", date(2014, 12, 1), longitude=-122.302),
            sale("neighbor-b", "b", date(2014, 11, 1), longitude=-122.303),
            sale("neighbor-c", "c", date(2014, 10, 1), longitude=-122.304),
            sale("same-home", "subject-home", date(2014, 12, 1)),
            sale("at-cutoff", "future", cutoff),
            sale("too-old", "ancient", date(2013, 12, 31)),
        )
        residuals = {item.row_id: math.log(1.1) for item in candidates}

        first = comparable.build_index(candidates, residuals, cutoff=cutoff)
        second = comparable.build_index(
            tuple(reversed(candidates)), residuals, cutoff=cutoff
        )
        first_match = comparable.retrieve(first, subject)
        second_match = comparable.retrieve(second, subject)

        self.assertEqual(first_match.row_ids, second_match.row_ids)
        self.assertEqual(
            set(first_match.row_ids), {"latest-repeat", "neighbor-b", "neighbor-c"}
        )
        self.assertNotIn("old-repeat", first_match.row_ids)
        self.assertNotIn("same-home", first_match.row_ids)

    def test_retrieval_does_not_rank_by_price_and_expands_radius(self) -> None:
        cutoff = date(2015, 1, 1)
        subject = sale("subject", "subject", cutoff)
        candidates = (
            sale("near", "near", date(2014, 12, 1), price="1", longitude=-122.301),
            sale("middle", "middle", date(2014, 12, 1), price="2", longitude=-122.34),
            sale("far", "far", date(2014, 12, 1), price="3", longitude=-122.42),
        )
        residuals = {item.row_id: float(index) for index, item in enumerate(candidates)}
        original = comparable.retrieve(
            comparable.build_index(candidates, residuals, cutoff=cutoff), subject
        )
        swapped = tuple(
            sale(
                item.row_id,
                item.property_id,
                item.sale_date,
                price=str(1000 - index),
                longitude=float(item.attributes["long"]),
            )
            for index, item in enumerate(candidates)
        )
        changed = comparable.retrieve(
            comparable.build_index(swapped, residuals, cutoff=cutoff), subject
        )

        self.assertEqual(original.row_ids, changed.row_ids)
        self.assertGreater(original.radius_km, 2)
        self.assertEqual(original.support, "supported")

    def test_low_support_falls_back_and_residual_correction_is_hand_computed(
        self,
    ) -> None:
        cutoff = date(2015, 1, 1)
        subject = sale("subject", "subject", cutoff)
        one = sale("one", "one", date(2014, 12, 1), longitude=-122.301)
        low = comparable.correct_prediction(
            subject,
            100000.0,
            comparable.build_index((one,), {"one": math.log(2)}, cutoff=cutoff),
        )
        self.assertEqual(low.prediction, 100000.0)
        self.assertEqual(low.support, "low_support")

        rows = tuple(
            sale(
                str(index),
                str(index),
                date(2014, 12, 1),
                longitude=-122.3 - index / 10000,
            )
            for index in range(1, 4)
        )
        supported_index = comparable.build_index(
            rows,
            {item.row_id: math.log(1.1) for item in rows},
            cutoff=cutoff,
        )
        supported = comparable.correct_prediction(subject, 100000.0, supported_index)
        self.assertAlmostEqual(supported.prediction, 110000.0, places=6)
        self.assertEqual(supported.support, "supported")

        invalid_subject = sale(
            "invalid", "invalid", cutoff, latitude=91, longitude=-122.3
        )
        invalid = comparable.correct_prediction(
            invalid_subject, 100000.0, supported_index
        )
        self.assertEqual(invalid.support, "low_support")
        self.assertEqual(invalid.prediction, 100000.0)

    def test_future_march_rows_cannot_change_january_result(self) -> None:
        cutoff = date(2015, 1, 1)
        subject = sale("subject", "subject", cutoff)
        prior = tuple(
            sale(str(index), str(index), date(2014, 12, 1), longitude=-122.301)
            for index in range(3)
        )
        future = sale("march", "march", date(2015, 3, 1), longitude=-122.3)
        residuals = {item.row_id: math.log(1.05) for item in (*prior, future)}

        without = comparable.correct_prediction(
            subject,
            100000,
            comparable.build_index(prior, residuals, cutoff=cutoff),
        )
        with_future = comparable.correct_prediction(
            subject,
            100000,
            comparable.build_index((*prior, future), residuals, cutoff=cutoff),
        )
        self.assertEqual(without, with_future)

    def test_membership_must_match_frozen_rolling_manifest(self) -> None:
        membership = {
            "2014-11": {
                "training_count": 1,
                "training_sha256": "a",
                "validation_count": 1,
                "validation_sha256": "b",
            }
        }
        frozen = {
            "run_id": "king-rolling-development-20261005-v1",
            "protocol": "king_rolling_development_v1",
            "status": "complete",
            "source_sha256": comparable.SOURCE_SHA256,
            "window_membership": membership,
            "split_sha256": comparable._membership_sha256(membership),
        }
        comparable.verify_frozen_membership(membership, frozen)
        changed = json.loads(json.dumps(membership))
        changed["2014-11"]["validation_count"] = 2
        with self.assertRaisesRegex(ValueError, "frozen rolling membership"):
            comparable.verify_frozen_membership(changed, frozen)
        with self.assertRaisesRegex(ValueError, "manifest identity"):
            comparable.verify_frozen_membership(
                membership, {**frozen, "protocol": "tampered"}
            )
        with self.assertRaisesRegex(ValueError, "split hash"):
            comparable.verify_frozen_membership(
                membership, {**frozen, "split_sha256": "0" * 64}
            )

    def test_screening_rule_requires_every_predeclared_condition(self) -> None:
        accepted = comparable.screen_candidate(
            incumbent_mdape=Decimal("0.100"),
            challenger_mdape=Decimal("0.097"),
            incumbent_within_10=Decimal("0.50"),
            challenger_within_10=Decimal("0.495"),
            incumbent_p90=Decimal("0.30"),
            challenger_p90=Decimal("0.305"),
            improved_windows=3,
            valid_predictions=True,
        )
        self.assertEqual(accepted, "xgboost_comparable_residual")
        boundary_four = comparable.screen_candidate(
            incumbent_mdape=Decimal("0.100"),
            challenger_mdape=Decimal("0.097"),
            incumbent_within_10=Decimal("0.50"),
            challenger_within_10=Decimal("0.495"),
            incumbent_p90=Decimal("0.30"),
            challenger_p90=Decimal("0.305"),
            improved_windows=4,
            valid_predictions=True,
        )
        self.assertEqual(boundary_four, "xgboost_comparable_residual")
        self.assertEqual(
            comparable.screen_candidate(
                incumbent_mdape=Decimal("0.100"),
                challenger_mdape=Decimal("0.097"),
                incumbent_within_10=Decimal("0.50"),
                challenger_within_10=Decimal("0.495"),
                incumbent_p90=Decimal("0.30"),
                challenger_p90=Decimal("0.305"),
                improved_windows=2,
                valid_predictions=True,
            ),
            "xgboost",
        )
        boundary_zero = comparable.screen_candidate(
            incumbent_mdape=Decimal("0.100"),
            challenger_mdape=Decimal("0.097"),
            incumbent_within_10=Decimal("0.50"),
            challenger_within_10=Decimal("0.495"),
            incumbent_p90=Decimal("0.30"),
            challenger_p90=Decimal("0.305"),
            improved_windows=0,
            valid_predictions=True,
        )
        self.assertEqual(boundary_zero, "xgboost")
        for invalid_count in (-1, 5):
            with self.subTest(improved_windows=invalid_count):
                with self.assertRaisesRegex(ValueError, "between zero and four"):
                    comparable.screen_candidate(
                        incumbent_mdape=Decimal("0.100"),
                        challenger_mdape=Decimal("0.097"),
                        incumbent_within_10=Decimal("0.50"),
                        challenger_within_10=Decimal("0.50"),
                        incumbent_p90=Decimal("0.30"),
                        challenger_p90=Decimal("0.30"),
                        improved_windows=invalid_count,
                        valid_predictions=True,
                    )

    def test_runner_writes_private_outputs_and_runtime_versions(self) -> None:
        rows = tuple(
            sale(str(index), str(index), when, longitude=-122.3 - index / 10000)
            for index, when in enumerate(
                (
                    date(2014, 10, 1),
                    date(2014, 10, 2),
                    date(2014, 10, 3),
                    date(2014, 11, 15),
                    date(2014, 12, 15),
                    date(2015, 1, 15),
                    date(2015, 2, 15),
                    date(2015, 3, 15),
                )
            )
        )
        membership = comparable.membership_for(comparable.monthly_windows(rows))
        frozen = {
            "run_id": "king-rolling-development-20261005-v1",
            "protocol": "king_rolling_development_v1",
            "status": "complete",
            "source_sha256": comparable.SOURCE_SHA256,
            "window_membership": membership,
            "split_sha256": comparable._membership_sha256(membership),
        }

        def fake_fit(training, other, weights):
            del training, weights
            return tuple(100000.0 for _ in other), SimpleNamespace(
                save_model=lambda path: Path(path).write_text("model", encoding="utf-8")
            )

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            private = root / "king-benchmark"
            private.mkdir()
            output = private / "comparable-v1"
            frozen_path = root / "rolling-manifest.json"
            frozen_path.write_text(json.dumps(frozen), encoding="utf-8")
            lock = root / "lock.txt"
            lock.write_text("numpy==test\n", encoding="utf-8")
            with (
                patch.object(comparable, "PRIVATE_ROOT", private),
                patch.object(comparable, "FROZEN_MANIFEST", frozen_path),
                patch.object(comparable, "DECLARED_LOCK", lock),
                patch.object(comparable, "_committed_code", return_value="a" * 40),
                patch.object(comparable, "secure_directory"),
                patch.object(comparable, "real_directory"),
                patch.object(comparable, "verify_acl"),
                patch.object(comparable, "read_development_source", return_value=rows),
                patch.object(
                    comparable, "select_eligible_sales", return_value=(rows, {})
                ),
                patch.object(comparable, "_fit_predict", side_effect=fake_fit),
            ):
                result = comparable.run(Path("source.arff"), output)

            self.assertEqual(result["march_may_labels_parsed"], 0)
            self.assertEqual(result["march_may_rows_scored"], 0)
            self.assertFalse(result["promotion_eligible"])
            self.assertEqual(result["duplicate_transfer_control"], "unavailable")
            self.assertNotIn("selected_candidate", result)
            self.assertIn("development_screening_candidate", result)
            manifest = json.loads((output / "manifest.json").read_text())
            self.assertEqual(
                manifest["frozen_rolling_split_sha256"],
                comparable._membership_sha256(membership),
            )
            self.assertIn("declared_lock_sha256", manifest)
            self.assertNotIn("dependency_lock_sha256", manifest)
            self.assertIn("python", manifest["runtime_versions"])
            self.assertIn("numpy", manifest["runtime_versions"])
            self.assertIn("scipy", manifest["runtime_versions"])
            self.assertIn("xgboost", manifest["runtime_versions"])
            self.assertEqual(len(manifest["challenger_run_artifact_identities"]), 4)
            self.assertIn("residual_fold_sha256", manifest)
            self.assertIn("model", manifest["configuration"])
            self.assertTrue((output / "2014-11-comparable-index.json").is_file())
            self.assertTrue((output / "chronological-residuals.json").is_file())
            self.assertTrue((output / "predictions.csv").is_file())


if __name__ == "__main__":
    unittest.main()
