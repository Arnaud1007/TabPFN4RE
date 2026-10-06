"""Differentially verify the stdlib evaluator against pinned XGBoost."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import platform
import random
import struct

from scripts.king_xgboost_json import load_xgboost_json

MAX_MODEL_BYTES = 4_000_000
CHECKPOINT_SHA256 = "de9a7e8b1b6261a689070af200e4c4d1eb51a4fb5d77d8977341875bbf7d7357"
FEATURE_COUNT = 84
EXPECTED_RUNTIME = {
    "machine": "AMD64",
    "numpy": "2.4.6",
    "platform": "Windows-10-10.0.26200-SP0",
    "python": "3.11.6",
    "xgboost": "3.2.0",
}


def _read_model(path: Path, expected_sha256: str) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise ValueError("Model must be a regular file")
    content = path.read_bytes()
    if len(content) > MAX_MODEL_BYTES:
        raise ValueError("Model exceeds the verification size limit")
    if hashlib.sha256(content).hexdigest() != expected_sha256:
        raise ValueError("Model SHA-256 does not match the pinned checkpoint")
    return content


def _f32_hex(value: float) -> str:
    return struct.pack("<f", float(value)).hex()


def _float32_boundaries(value: float) -> tuple[float, float, float]:
    exact = struct.unpack("<f", struct.pack("<f", value))[0]
    bits = struct.unpack("<I", struct.pack("<f", exact))[0]
    if exact == 0.0:
        adjacent = (0x80000001, bits, 0x00000001)
    elif exact > 0.0:
        adjacent = (bits - 1, bits, bits + 1)
    else:
        adjacent = (bits + 1, bits, bits - 1)
    values = tuple(struct.unpack("<f", struct.pack("<I", item))[0] for item in adjacent)
    if len({_f32_hex(item) for item in values}) != 3:
        raise ValueError("Threshold has no distinct finite float32 boundaries")
    return values


def _verification_rows(
    model: dict[str, object], feature_count: int
) -> list[list[float]]:
    rng = random.Random(42)
    rows = [
        [rng.uniform(-1_000_000.0, 1_000_000.0) for _ in range(feature_count)]
        for _ in range(1_000)
    ]
    trees = model["learner"]["gradient_booster"]["model"]["trees"]  # type: ignore[index]
    for tree in trees:
        for node, left in enumerate(tree["left_children"]):
            if left == -1:
                continue
            for row in _node_boundary_rows(tree, node, feature_count):
                if not _reaches_node(tree, row, node):
                    raise ValueError(
                        "Constructed boundary row bypasses its target node"
                    )
                rows.append(row)
    return rows


def _node_boundary_rows(
    tree: dict[str, object], target: int, feature_count: int
) -> tuple[list[float], list[float], list[float]]:
    left = tree["left_children"]
    right = tree["right_children"]
    features = tree["split_indices"]
    thresholds = tree["split_conditions"]
    parents: dict[int, tuple[int, bool]] = {}
    for node, (left_child, right_child) in enumerate(zip(left, right)):
        if left_child != -1:
            parents[int(left_child)] = (node, True)
            parents[int(right_child)] = (node, False)
    constraints: dict[int, tuple[float, float]] = {}
    current = target
    while current in parents:
        parent, took_left = parents[current]
        feature = int(features[parent])
        threshold = _float32_boundaries(float(thresholds[parent]))[1]
        lower, upper = constraints.get(feature, (-math.inf, math.inf))
        constraints[feature] = (
            (lower, min(upper, threshold))
            if took_left
            else (max(lower, threshold), upper)
        )
        current = parent

    base = [0.0] * feature_count
    for feature, (lower, upper) in constraints.items():
        if lower >= upper:
            raise ValueError("Tree contains an unsatisfiable root-to-node path")
        base[feature] = lower if math.isfinite(lower) else _float32_boundaries(upper)[0]
    target_feature = int(features[target])
    result: list[list[float]] = []
    for boundary in _float32_boundaries(float(thresholds[target])):
        lower, upper = constraints.get(target_feature, (-math.inf, math.inf))
        if not lower <= boundary < upper:
            raise ValueError("Target boundary conflicts with an ancestor split")
        row = list(base)
        row[target_feature] = boundary
        result.append(row)
    return result[0], result[1], result[2]


def _reaches_node(tree: dict[str, object], row: list[float], target: int) -> bool:
    node = 0
    while node != target and tree["left_children"][node] != -1:
        feature = int(tree["split_indices"][node])
        threshold = _float32_boundaries(float(tree["split_conditions"][node]))[1]
        node = int(
            tree["left_children"][node]
            if row[feature] < threshold
            else tree["right_children"][node]
        )
    return node == target


def verify(model_path: Path) -> dict[str, object]:
    content = _read_model(model_path, CHECKPOINT_SHA256)
    document = json.loads(content)
    rows = _verification_rows(document, FEATURE_COUNT)
    pure = load_xgboost_json(
        content, FEATURE_COUNT, expected_objective="reg:absoluteerror"
    ).predict(rows)

    import numpy
    import xgboost
    from xgboost import XGBRegressor

    observed_runtime = {
        "machine": platform.machine(),
        "numpy": numpy.__version__,
        "platform": platform.platform(),
        "python": platform.python_version(),
        "xgboost": xgboost.__version__,
    }
    if observed_runtime != EXPECTED_RUNTIME:
        raise ValueError("Native reference runtime does not match the pinned release")
    native = XGBRegressor()
    native.load_model(model_path)
    reference = native.predict(numpy.asarray(rows, dtype=numpy.float32))
    mismatches = sum(
        _f32_hex(actual) != _f32_hex(expected)
        for actual, expected in zip(pure, reference, strict=True)
    )
    if mismatches:
        raise ValueError(f"Evaluator differs from XGBoost on {mismatches} rows")
    return {
        "checkpoint_sha256": CHECKPOINT_SHA256,
        "feature_count": FEATURE_COUNT,
        "random_rows": 1_000,
        "rows_compared": len(rows),
        "bitwise_mismatches": mismatches,
        "status": "passed",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.model), sort_keys=True))


if __name__ == "__main__":
    main()
