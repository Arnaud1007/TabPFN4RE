"""Focused tests for the dependency-free XGBoost JSON predictor."""

from __future__ import annotations

import json
import math
from pathlib import Path
import struct
import unittest

from scripts.king_xgboost_json import load_xgboost_json


FIXTURES = Path(__file__).parent / "fixtures"


def model_bytes(
    *, num_feature: str = "2", objective: str = "reg:squarederror"
) -> bytes:
    tree = {
        "base_weights": [0.0, 1.25, -0.75],
        "categories": [],
        "categories_nodes": [],
        "categories_segments": [],
        "categories_sizes": [],
        "default_left": [1, 0, 0],
        "id": 0,
        "left_children": [1, -1, -1],
        "parents": [2147483647, 0, 0],
        "right_children": [2, -1, -1],
        "split_conditions": [2.5, 1.25, -0.75],
        "split_indices": [0, 0, 0],
        "split_type": [0, 0, 0],
        "tree_param": {
            "num_deleted": "0",
            "num_feature": num_feature,
            "num_nodes": "3",
            "size_leaf_vector": "1",
        },
    }
    document = {
        "version": [3, 2, 0],
        "learner": {
            "learner_model_param": {
                "base_score": "[5E-1]",
                "num_class": "0",
                "num_feature": num_feature,
                "num_target": "1",
            },
            "objective": {"name": objective},
            "gradient_booster": {
                "name": "gbtree",
                "model": {
                    "gbtree_model_param": {
                        "num_parallel_tree": "1",
                        "num_trees": "1",
                    },
                    "iteration_indptr": [0, 1],
                    "tree_info": [0],
                    "trees": [tree],
                },
            },
        },
    }
    return json.dumps(document).encode()


class XGBoostJSONPredictorTests(unittest.TestCase):
    def test_matches_pinned_xgboost_3_2_multitree_oracle_bit_for_bit(self) -> None:
        model = (FIXTURES / "xgboost_3_2_numeric_gbtree.json").read_bytes()
        oracle = json.loads(
            (FIXTURES / "xgboost_3_2_numeric_gbtree_oracle.json").read_text(
                encoding="utf-8"
            )
        )
        rows = [
            [math.nan if value is None else value for value in row]
            for row in oracle["rows"]
        ]

        predictions = load_xgboost_json(
            model, 2, expected_objective="reg:absoluteerror"
        ).predict(rows)

        self.assertEqual(
            [struct.pack("!f", value).hex() for value in predictions],
            oracle["prediction_float32_hex"],
        )

    def test_predicts_numeric_and_missing_branches_with_float32_math(self) -> None:
        predictor = load_xgboost_json(model_bytes(), expected_feature_count=2)
        self.assertEqual(predictor.predict([[2.0, 99.0]]), (1.75,))
        self.assertEqual(predictor.predict([[3.0, 99.0]]), (-0.25,))
        self.assertEqual(predictor.predict([[math.nan, 99.0]]), (1.75,))

    def test_rejects_feature_count_drift_and_bad_prediction_rows(self) -> None:
        with self.assertRaisesRegex(ValueError, "feature count"):
            load_xgboost_json(model_bytes(num_feature="3"), 2)
        predictor = load_xgboost_json(model_bytes(), 2)
        for matrix in (
            [[1.0]],
            [[1.0, math.inf]],
            [[True, 1.0]],
            [[10**400, 1.0]],
            "bad",
        ):
            with self.subTest(matrix=matrix), self.assertRaises(ValueError):
                predictor.predict(matrix)  # type: ignore[arg-type]

    def test_rejects_unsupported_or_malformed_models(self) -> None:
        cases = []
        wrong_objective = json.loads(model_bytes())
        wrong_objective["learner"]["objective"]["name"] = "binary:logistic"
        cases.append(wrong_objective)
        categorical = json.loads(model_bytes())
        categorical["learner"]["gradient_booster"]["model"]["trees"][0]["split_type"][
            0
        ] = 1
        cases.append(categorical)
        cycle = json.loads(model_bytes())
        cycle["learner"]["gradient_booster"]["model"]["trees"][0]["left_children"][
            0
        ] = 0
        cases.append(cycle)
        bad_tree_param = json.loads(model_bytes())
        bad_tree_param["learner"]["gradient_booster"]["model"]["trees"][0][
            "tree_param"
        ]["num_nodes"] = "99"
        cases.append(bad_tree_param)
        overflowing_number = json.loads(model_bytes())
        overflowing_number["learner"]["gradient_booster"]["model"]["trees"][0][
            "split_conditions"
        ][0] = 10**400
        cases.append(overflowing_number)
        for document in cases:
            with self.subTest(), self.assertRaises(ValueError):
                load_xgboost_json(json.dumps(document).encode(), 2)

    def test_rejects_non_json_and_oversized_input(self) -> None:
        for content in (
            b"not json",
            b"[1]",
            b'{"learner": {}, "learner": {}}',
            b" " * 4_000_001,
        ):
            with self.subTest(size=len(content)), self.assertRaises(ValueError):
                load_xgboost_json(content, 2)

    def test_requires_bundle_objective_when_supplied(self) -> None:
        with self.assertRaisesRegex(ValueError, "does not match"):
            load_xgboost_json(
                model_bytes(objective="reg:squarederror"),
                2,
                expected_objective="reg:absoluteerror",
            )

    def test_zero_round_model_returns_only_the_base_score(self) -> None:
        document = json.loads(model_bytes())
        model = document["learner"]["gradient_booster"]["model"]
        model["trees"] = []
        model["tree_info"] = []
        model["iteration_indptr"] = [0]
        model["gbtree_model_param"]["num_trees"] = "0"
        predictor = load_xgboost_json(json.dumps(document).encode(), 2)
        self.assertEqual(predictor.predict([[1.0, 2.0]]), (0.5,))


if __name__ == "__main__":
    unittest.main()
