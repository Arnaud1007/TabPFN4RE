"""Small, bounded evaluator for the supported XGBoost JSON model subset."""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
import struct
from typing import Sequence

__all__ = ["XGBoostJSONPredictor", "load_xgboost_json"]

_MAX_MODEL_BYTES = 4_000_000
_MAX_FEATURES = 10_000
_MAX_TREES = 10_000
_MAX_NODES_PER_TREE = 100_000
_MAX_TOTAL_NODES = 1_000_000


def _float32(value: float) -> float:
    try:
        return struct.unpack("!f", struct.pack("!f", value))[0]
    except (OverflowError, struct.error) as error:
        raise ValueError("XGBoost model contains an invalid float32 value") from error


def _integer(value: object, label: str, *, minimum: int, maximum: int) -> int:
    if isinstance(value, bool):
        raise ValueError(f"XGBoost {label} is invalid")
    try:
        result = int(value)  # XGBoost serializes several integral fields as strings.
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError(f"XGBoost {label} is invalid") from error
    if str(result) != str(value) or not minimum <= result <= maximum:
        raise ValueError(f"XGBoost {label} is invalid")
    return result


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"XGBoost {label} is invalid")
    try:
        result = float(value)
    except OverflowError as error:
        raise ValueError(f"XGBoost {label} is invalid") from error
    if not math.isfinite(result):
        raise ValueError(f"XGBoost {label} is invalid")
    return _float32(result)


def _array(tree: dict[str, object], name: str, count: int) -> list[object]:
    value = tree.get(name)
    if not isinstance(value, list) or len(value) != count:
        raise ValueError(f"XGBoost tree {name} is invalid")
    return value


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("XGBoost model contains a duplicate JSON key")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"XGBoost model contains invalid JSON constant {value}")


@dataclass(frozen=True)
class _Tree:
    left: tuple[int, ...]
    right: tuple[int, ...]
    default_left: tuple[bool, ...]
    features: tuple[int, ...]
    values: tuple[float, ...]

    def evaluate(self, row: tuple[float, ...]) -> float:
        node = 0
        for _ in range(len(self.left)):
            left = self.left[node]
            if left == -1:
                return self.values[node]
            value = row[self.features[node]]
            node = (
                left
                if math.isnan(value) and self.default_left[node]
                else self.right[node]
                if math.isnan(value)
                else left
                if value < self.values[node]
                else self.right[node]
            )
        raise ValueError("XGBoost tree traversal exceeded its node bound")


@dataclass(frozen=True)
class XGBoostJSONPredictor:
    """Immutable PredictorModel-compatible regression tree ensemble."""

    feature_count: int
    base_score: float
    _trees: tuple[_Tree, ...]

    def predict(self, matrix: Sequence[Sequence[float]]) -> tuple[float, ...]:
        if isinstance(matrix, (str, bytes, bytearray)) or not isinstance(
            matrix, Sequence
        ):
            raise ValueError("Prediction matrix must be a sequence of rows")
        predictions: list[float] = []
        for raw_row in matrix:
            if isinstance(raw_row, (str, bytes, bytearray)) or not isinstance(
                raw_row, Sequence
            ):
                raise ValueError("Prediction row must be a sequence")
            if len(raw_row) != self.feature_count:
                raise ValueError("Prediction row has the wrong feature count")
            row_values: list[float] = []
            for raw_value in raw_row:
                if isinstance(raw_value, bool) or not isinstance(
                    raw_value, (int, float)
                ):
                    raise ValueError("Prediction features must be numeric")
                try:
                    value = float(raw_value)
                except OverflowError as error:
                    raise ValueError("Prediction features must fit float32") from error
                if math.isinf(value):
                    raise ValueError("Prediction features must be finite or missing")
                row_values.append(_float32(value))
            row = tuple(row_values)
            prediction = self.base_score
            for tree in self._trees:
                prediction = _float32(prediction + tree.evaluate(row))
            predictions.append(prediction)
        return tuple(predictions)


def _base_score(value: object) -> float:
    if not isinstance(value, str) or len(value) > 100:
        raise ValueError("XGBoost base score is invalid")
    encoded = value.strip()
    if encoded.startswith("[") and encoded.endswith("]"):
        encoded = encoded[1:-1]
        if "," in encoded:
            raise ValueError("XGBoost base score is invalid")
    try:
        result = float(encoded)
    except (ValueError, OverflowError) as error:
        raise ValueError("XGBoost base score is invalid") from error
    if not math.isfinite(result):
        raise ValueError("XGBoost base score is invalid")
    return _float32(result)


def _tree(value: object, feature_count: int) -> _Tree:
    if not isinstance(value, dict):
        raise ValueError("XGBoost tree is invalid")
    left_raw = value.get("left_children")
    if not isinstance(left_raw, list):
        raise ValueError("XGBoost tree children are invalid")
    count = len(left_raw)
    if not 1 <= count <= _MAX_NODES_PER_TREE:
        raise ValueError("XGBoost tree node count is invalid")
    right_raw = _array(value, "right_children", count)
    default_raw = _array(value, "default_left", count)
    feature_raw = _array(value, "split_indices", count)
    split_raw = _array(value, "split_conditions", count)
    type_raw = _array(value, "split_type", count)
    parents_raw = _array(value, "parents", count)
    tree_parameters = value.get("tree_param")
    if not isinstance(tree_parameters, dict):
        raise ValueError("XGBoost tree parameters are invalid")
    expected_parameters = (
        ("num_deleted", 0, 0),
        ("num_feature", feature_count, feature_count),
        ("num_nodes", count, count),
        ("size_leaf_vector", 1, 1),
    )
    for name, minimum, maximum in expected_parameters:
        _integer(tree_parameters.get(name), name, minimum=minimum, maximum=maximum)
    category_fields = (
        "categories",
        "categories_nodes",
        "categories_segments",
        "categories_sizes",
    )
    if any(value.get(name) != [] for name in category_fields) or any(
        item != 0 or isinstance(item, bool) for item in type_raw
    ):
        raise ValueError("Categorical XGBoost trees are unsupported")
    weights_raw = _array(value, "base_weights", count)
    for weight in weights_raw:
        _number(weight, "base weight")

    left: list[int] = []
    right: list[int] = []
    defaults: list[bool] = []
    features: list[int] = []
    values: list[float] = []
    for node in range(count):
        left_child = _integer(
            left_raw[node], "left child", minimum=-1, maximum=count - 1
        )
        right_child = _integer(
            right_raw[node], "right child", minimum=-1, maximum=count - 1
        )
        if (left_child == -1) != (right_child == -1):
            raise ValueError("XGBoost tree has a partial child pair")
        default = default_raw[node]
        if default not in (0, 1) or isinstance(default, bool):
            raise ValueError("XGBoost default direction is invalid")
        feature = _integer(
            feature_raw[node], "split feature", minimum=0, maximum=feature_count - 1
        )
        left.append(left_child)
        right.append(right_child)
        defaults.append(bool(default))
        features.append(feature)
        values.append(_number(split_raw[node], "split condition"))

    visited: set[int] = set()
    pending = [0]
    while pending:
        node = pending.pop()
        if node in visited:
            raise ValueError("XGBoost tree contains a cycle or shared child")
        visited.add(node)
        if left[node] != -1:
            pending.extend((left[node], right[node]))
    if len(visited) != count:
        raise ValueError("XGBoost tree contains unreachable nodes")
    for node in range(1, count):
        parent = _integer(parents_raw[node], "parent", minimum=0, maximum=count - 1)
        if left[parent] != node and right[parent] != node:
            raise ValueError("XGBoost tree parent metadata is invalid")
    _integer(parents_raw[0], "root parent", minimum=2147483647, maximum=2147483647)
    return _Tree(
        tuple(left), tuple(right), tuple(defaults), tuple(features), tuple(values)
    )


def load_xgboost_json(
    model_bytes: bytes,
    expected_feature_count: int,
    expected_objective: str | None = None,
) -> XGBoostJSONPredictor:
    """Validate and load a bounded gbtree regression model from JSON bytes."""
    if type(model_bytes) is not bytes or not 1 <= len(model_bytes) <= _MAX_MODEL_BYTES:
        raise ValueError("XGBoost model bytes are invalid or exceed the size limit")
    if (
        type(expected_feature_count) is not int
        or not 1 <= expected_feature_count <= _MAX_FEATURES
    ):
        raise ValueError("Expected feature count is invalid")
    try:
        document = json.loads(
            model_bytes,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_json_constant,
        )
    except (json.JSONDecodeError, UnicodeDecodeError, RecursionError) as error:
        raise ValueError("XGBoost model is not valid JSON") from error
    if not isinstance(document, dict):
        raise ValueError("XGBoost model root is invalid")
    try:
        learner = document["learner"]
        parameters = learner["learner_model_param"]
        objective = learner["objective"]
        booster = learner["gradient_booster"]
        model = booster["model"]
        booster_parameters = model["gbtree_model_param"]
    except (KeyError, TypeError) as error:
        raise ValueError("XGBoost model structure is invalid") from error
    if not all(
        isinstance(item, dict)
        for item in (learner, parameters, objective, booster, model, booster_parameters)
    ):
        raise ValueError("XGBoost model structure is invalid")
    if booster.get("name") != "gbtree":
        raise ValueError("Only XGBoost gbtree models are supported")
    objective_name = objective.get("name")
    if objective_name not in ("reg:squarederror", "reg:absoluteerror"):
        raise ValueError("XGBoost objective is unsupported")
    if expected_objective is not None and objective_name != expected_objective:
        raise ValueError("XGBoost objective does not match the bundle")
    feature_count = _integer(
        parameters.get("num_feature"), "feature count", minimum=1, maximum=_MAX_FEATURES
    )
    if feature_count != expected_feature_count:
        raise ValueError(
            "XGBoost model feature count does not match the expected feature count"
        )
    if (
        _integer(
            parameters.get("num_target", "1"), "target count", minimum=1, maximum=1
        )
        != 1
    ):
        raise ValueError("XGBoost target count is unsupported")
    if (
        _integer(parameters.get("num_class", "0"), "class count", minimum=0, maximum=0)
        != 0
    ):
        raise ValueError("XGBoost classifiers are unsupported")
    if (
        _integer(
            booster_parameters.get("num_parallel_tree"),
            "parallel tree count",
            minimum=1,
            maximum=1,
        )
        != 1
    ):
        raise ValueError("XGBoost parallel forests are unsupported")
    tree_values = model.get("trees")
    if not isinstance(tree_values, list) or len(tree_values) > _MAX_TREES:
        raise ValueError("XGBoost tree collection is invalid")
    declared = _integer(
        booster_parameters.get("num_trees"),
        "tree count",
        minimum=0,
        maximum=_MAX_TREES,
    )
    if declared != len(tree_values) or model.get("tree_info") != [0] * declared:
        raise ValueError("XGBoost tree metadata is inconsistent")
    indptr = model.get("iteration_indptr")
    if (
        not isinstance(indptr, list)
        or indptr[0:1] != [0]
        or indptr[-1:] != [declared]
        or any(
            type(item) is not int or item != index for index, item in enumerate(indptr)
        )
    ):
        raise ValueError("XGBoost iteration metadata is unsupported")
    trees = tuple(_tree(item, feature_count) for item in tree_values)
    if sum(len(tree.left) for tree in trees) > _MAX_TOTAL_NODES:
        raise ValueError("XGBoost model exceeds the total node limit")
    return XGBoostJSONPredictor(
        feature_count, _base_score(parameters.get("base_score")), trees
    )
