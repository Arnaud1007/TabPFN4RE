"""Fast historical Ames model comparison and local prototype prediction.

This engineering protocol uses only the frozen legacy development partition.
It cannot certify future US sale-price accuracy.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal
import hashlib
from importlib import metadata
import json
import math
from pathlib import Path
import re
import sys
import tempfile
import time
from typing import Mapping, Sequence

from scripts import replay_legacy_ames_dev as legacy

PROTOCOL = "ames_dev_prototype_v1"
EXCLUDED = frozenset(
    {"Id", "SalePrice", "MoSold", "YrSold", "SaleType", "SaleCondition"}
)
REQUIRED_REQUEST = frozenset({"GrLivArea", "OverallQual", "Neighborhood"})
_TARGET_PATTERN = re.compile(
    r"sale.?price|target|rendement_locatif|note_attractivite_marche|"
    r"note_potentiel_d_investissement",
    re.IGNORECASE,
)
_MAX_REQUEST_BYTES = 100_000
_MAX_BUNDLE_BYTES = 100_000
_MAX_PREPROCESS_BYTES = 1_000_000
_MAX_MODEL_BYTES = 10_000_000
_LOCK_LINE = re.compile(r"([A-Za-z0-9-]+)==([A-Za-z0-9.]+)")


def allowed_feature_names(columns: Sequence[str]) -> tuple[str, ...]:
    """Exclude declared sale outcomes and fail on new target-derived columns."""
    if len(set(columns)) != len(columns) or not all(
        isinstance(name, str) and name for name in columns
    ):
        raise ValueError("Feature names must be unique nonempty strings")
    unexpected = [
        name
        for name in columns
        if name not in EXCLUDED and _TARGET_PATTERN.search(name)
    ]
    if unexpected:
        raise ValueError(f"New target-derived feature is forbidden: {unexpected}")
    selected = tuple(name for name in columns if name not in EXCLUDED)
    if not selected or not REQUIRED_REQUEST.issubset(selected):
        raise ValueError("Ames prototype is missing required property features")
    return selected


def validate_request(
    request: Mapping[str, object],
    feature_names: Sequence[str],
    numeric_names: frozenset[str],
) -> dict[str, object]:
    """Normalize a local request against the exact trained feature schema."""
    if not isinstance(request, dict):
        raise ValueError("Request must be a JSON object")
    if set(request) != set(feature_names):
        raise ValueError("Request must contain exactly the trained feature names")
    if not REQUIRED_REQUEST.issubset(request):
        raise ValueError("Request requires GrLivArea, OverallQual and Neighborhood")
    if any(request[name] is None for name in REQUIRED_REQUEST):
        raise ValueError("Required property features cannot be missing")
    if not numeric_names.issubset(feature_names):
        raise ValueError("Numeric schema is incompatible with model features")
    normalized: dict[str, object] = {}
    for name in feature_names:
        value = request.get(name)
        if value is None:
            normalized[name] = None
        elif name in numeric_names:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{name} must be a finite number")
            number = float(value)
            if not math.isfinite(number):
                raise ValueError(f"{name} must be a finite number")
            normalized[name] = number
        elif isinstance(value, str) and 0 < len(value) <= 100 and value.strip():
            normalized[name] = value.strip()
        else:
            raise ValueError(f"{name} must be a nonempty category")
    if float(normalized["GrLivArea"]) <= 0:
        raise ValueError("GrLivArea must be positive")
    if not 1 <= float(normalized["OverallQual"]) <= 10:
        raise ValueError("OverallQual must be between 1 and 10")
    return normalized


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, sort_keys=True, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def _read_json_bounded(path: Path, limit: int) -> dict[str, object]:
    with path.open("rb") as stream:
        content = stream.read(limit + 1)
    if len(content) > limit:
        raise ValueError(f"Artifact {path.name} exceeds its size limit")
    value = json.loads(content.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Artifact {path.name} must be a JSON object")
    return value


def _validate_dependency_lock(project_root: Path) -> str:
    """Require this interpreter to match the prototype's pinned dependencies."""
    if sys.version_info[:2] != (3, 11):
        raise ValueError("Ames prototype requires Python 3.11")
    lock_path = project_root / "locks/ames-prototype-requirements.txt"
    with lock_path.open("rb") as stream:
        content = stream.read(10_001)
    if len(content) > 10_000:
        raise ValueError("Prototype dependency lock exceeds size limit")
    pins = [
        line.strip()
        for line in content.decode("utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    if len(pins) != 8:
        raise ValueError("Prototype dependency lock has an unexpected pin count")
    for line in pins:
        match = _LOCK_LINE.fullmatch(line)
        if match is None or metadata.version(match[1]) != match[2]:
            raise ValueError(f"Prototype dependency mismatch: {line}")
    return hashlib.sha256(content).hexdigest()


def _components(features, model_name: str):
    from sklearn.compose import ColumnTransformer
    from sklearn.dummy import DummyRegressor
    from sklearn.impute import SimpleImputer
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OneHotEncoder
    from xgboost import XGBRegressor

    numeric = tuple(features.select_dtypes(include="number").columns)
    categorical = tuple(name for name in features.columns if name not in numeric)
    prep = ColumnTransformer(
        [
            ("num", SimpleImputer(strategy="median"), list(numeric)),
            (
                "cat",
                Pipeline(
                    [
                        ("impute", SimpleImputer(strategy="most_frequent")),
                        ("encode", OneHotEncoder(handle_unknown="ignore")),
                    ]
                ),
                list(categorical),
            ),
        ]
    )
    if model_name == "median":
        model = DummyRegressor(strategy="median")
    elif model_name == "xgboost":
        model = XGBRegressor(
            n_estimators=400,
            max_depth=4,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42,
            n_jobs=4,
        )
    else:
        raise ValueError("Unknown prototype model")
    return Pipeline([("preprocess", prep), ("model", model)]), numeric, categorical


def _preprocessing_snapshot(pipeline, numeric, categorical) -> dict[str, object]:
    transform = pipeline.named_steps["preprocess"]
    numeric_imputer = transform.named_transformers_["num"]
    category_pipeline = transform.named_transformers_["cat"]
    category_imputer = category_pipeline.named_steps["impute"]
    encoder = category_pipeline.named_steps["encode"]
    if (
        len(numeric_imputer.statistics_) != len(numeric)
        or len(category_imputer.statistics_) != len(categorical)
        or len(encoder.categories_) != len(categorical)
    ):
        raise ValueError("Fitted preprocessing schema changed")
    numeric_fill = [float(value) for value in numeric_imputer.statistics_]
    if any(not math.isfinite(value) for value in numeric_fill):
        raise ValueError("Numeric imputation value is invalid")
    category_fill = [str(value) for value in category_imputer.statistics_]
    categories = [[str(value) for value in group] for group in encoder.categories_]
    if any(
        not group or fill not in group
        for fill, group in zip(category_fill, categories, strict=True)
    ):
        raise ValueError("Categorical imputation schema is invalid")
    return {
        "protocol": PROTOCOL,
        "numeric": list(numeric),
        "categorical": list(categorical),
        "numeric_fill": numeric_fill,
        "categorical_fill": category_fill,
        "categories": categories,
        "sparse_output": bool(transform.sparse_output_),
    }


def _encode_request(values: Mapping[str, object], snapshot: Mapping[str, object]):
    import numpy as np
    from scipy.sparse import csr_matrix

    numeric = snapshot["numeric"]
    categorical = snapshot["categorical"]
    numeric_fill = snapshot["numeric_fill"]
    category_fill = snapshot["categorical_fill"]
    categories = snapshot["categories"]
    if not (
        isinstance(numeric, list)
        and isinstance(categorical, list)
        and isinstance(numeric_fill, list)
        and isinstance(category_fill, list)
        and isinstance(categories, list)
        and len(numeric) == len(numeric_fill)
        and len(categorical) == len(category_fill) == len(categories)
        and isinstance(snapshot.get("sparse_output"), bool)
    ):
        raise ValueError("Preprocessing snapshot schema is invalid")
    encoded = []
    unseen_categories: list[str] = []
    for name, fallback in zip(numeric, numeric_fill, strict=True):
        number = float(fallback if values[name] is None else values[name])
        if not math.isfinite(number):
            raise ValueError("Numeric preprocessing value is invalid")
        encoded.append(number)
    for name, fallback, group in zip(
        categorical, category_fill, categories, strict=True
    ):
        category = fallback if values[name] is None else values[name]
        if not isinstance(group, list) or not group:
            raise ValueError("Preprocessing category vocabulary is invalid")
        if category not in group:
            unseen_categories.append(name)
        encoded.extend(float(category == member) for member in group)
    matrix = np.asarray([encoded], dtype=np.float32)
    transformed = csr_matrix(matrix) if snapshot["sparse_output"] else matrix
    return transformed, tuple(unseen_categories)


def _score(records: Sequence[dict[str, object]], model_name: str) -> dict[str, object]:
    from tabpfn4realestate.evaluation.metrics import PredictionRow, score_predictions

    rows = [
        PredictionRow(
            row_id=str(record["source_row_index"]),
            actual=Decimal(str(record["actual"])),
            predicted=Decimal(str(record["predicted"])),
            actual_currency="USD",
            predicted_currency="USD",
            status="estimated",
        )
        for record in records
        if record["model"] == model_name
    ]
    result = score_predictions(rows)
    return asdict(result)


def _fold_predictions(data, features):
    from sklearn.model_selection import KFold

    folds = tuple(KFold(n_splits=5, shuffle=True, random_state=42).split(features))
    records: list[dict[str, object]] = []
    split: list[dict[str, object]] = []
    durations: dict[str, float] = {}
    for fold_number, (train_positions, validation_positions) in enumerate(folds, 1):
        x_train = features.iloc[train_positions]
        x_validation = features.iloc[validation_positions]
        y_train = data.labels.iloc[train_positions]
        y_validation = data.labels.iloc[validation_positions]
        legacy.assert_development_only(
            tuple(x_train.index), data.reserved, source_count=legacy.SOURCE_ROWS
        )
        legacy.assert_development_only(
            tuple(x_validation.index), data.reserved, source_count=legacy.SOURCE_ROWS
        )
        if set(x_train.index) & set(x_validation.index):
            raise ValueError("Development fold partitions overlap")
        split.append(
            {
                "fold": fold_number,
                "train": [int(index) for index in x_train.index],
                "validation": [int(index) for index in x_validation.index],
            }
        )
        for model_name in ("median", "xgboost"):
            pipeline, _, _ = _components(features, model_name)
            started = time.perf_counter()
            pipeline.fit(x_train, y_train)
            predicted = pipeline.predict(x_validation)
            elapsed = time.perf_counter() - started
            durations[model_name] = durations.get(model_name, 0.0) + elapsed
            if any(
                not math.isfinite(float(value)) or float(value) <= 0
                for value in predicted
            ):
                raise ValueError(
                    f"{model_name} made a nonpositive or nonfinite prediction"
                )
            records.extend(
                {
                    "source_row_index": int(index),
                    "fold": fold_number,
                    "model": model_name,
                    "actual": float(actual),
                    "predicted": float(estimate),
                }
                for index, actual, estimate in zip(
                    x_validation.index, y_validation, predicted, strict=True
                )
            )
    expected = set(data.development_order)
    for model_name in ("median", "xgboost"):
        indices = [
            int(row["source_row_index"])
            for row in records
            if row["model"] == model_name
        ]
        if len(indices) != len(expected) or set(indices) != expected:
            raise ValueError("OOF predictions do not cover development exactly once")
    return records, split, durations


def run_experiment(source: Path, holdout: Path, output: Path) -> Path:
    """Fit two fixed candidates, save paired OOF predictions and a local bundle."""
    private_root = (
        Path(__file__).resolve().parents[1] / "data" / "raw" / "ames-prototype"
    )
    if not output.resolve().is_relative_to(private_root.resolve()):
        raise ValueError(
            "Prototype output must stay under ignored data/raw/ames-prototype"
        )
    started = time.perf_counter()
    project_root = Path(__file__).resolve().parents[1]
    script_path = Path(__file__).resolve()
    script_sha256 = _sha256(script_path)
    code_identity = legacy.collect_git_identity(project_root)
    dependency_lock_sha256 = _validate_dependency_lock(project_root)
    packages = legacy.installed_packages()
    data = legacy._load_development(source, holdout)
    names = allowed_feature_names(tuple(data.features.columns))
    features = data.features.loc[:, list(names)]
    if output.exists():
        raise ValueError("Experiment output already exists")
    records, folds, durations = _fold_predictions(data, features)
    scorecards = {name: _score(records, name) for name in ("median", "xgboost")}
    champion = min(scorecards, key=lambda name: scorecards[name]["mdape"])
    pipeline, numeric, categorical = _components(features, champion)
    legacy.assert_development_only(
        tuple(features.index), data.reserved, source_count=legacy.SOURCE_ROWS
    )
    pipeline.fit(features, data.labels)
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=f"{output.name}.incomplete-", dir=output.parent)
    )
    try:
        with (staging / "predictions.csv").open(
            "w", encoding="utf-8", newline=""
        ) as stream:
            writer = csv.DictWriter(
                stream,
                fieldnames=["source_row_index", "fold", "model", "actual", "predicted"],
            )
            writer.writeheader()
            writer.writerows(records)
        _write_json(staging / "scorecards.json", scorecards)
        _write_json(
            staging / "split.json",
            {"development_order": data.development_order, "folds": folds},
        )
        _write_json(
            staging / "feature_policy.json",
            {
                "protocol": PROTOCOL,
                "included": names,
                "excluded": sorted(EXCLUDED),
                "numeric": numeric,
                "categorical": categorical,
            },
        )
        config = {
            "protocol": PROTOCOL,
            "seed": 42,
            "folds": 5,
            "models": {
                "median": "training-fold median",
                "xgboost": {
                    "n_estimators": 400,
                    "max_depth": 4,
                    "learning_rate": 0.05,
                    "subsample": 0.8,
                    "colsample_bytree": 0.8,
                    "random_state": 42,
                    "n_jobs": 4,
                },
            },
            "champion_rule": "lowest development OOF MdAPE; prototype only",
        }
        _write_json(staging / "config.json", config)
        _write_json(staging / "environment_packages.json", packages)
        snapshot = _preprocessing_snapshot(pipeline, numeric, categorical)
        _write_json(staging / "preprocessing.json", snapshot)
        if champion == "xgboost":
            pipeline.named_steps["model"].save_model(staging / "model.json")
        else:
            constant = float(pipeline.named_steps["model"].constant_[0][0])
            _write_json(staging / "model.json", {"median_price": constant})
        bundle = {
            "protocol": PROTOCOL,
            "model": champion,
            "features": names,
            "numeric": numeric,
            "categorical": categorical,
            "model_sha256": _sha256(staging / "model.json"),
            "preprocessing_sha256": _sha256(staging / "preprocessing.json"),
            "feature_policy_sha256": _sha256(staging / "feature_policy.json"),
            "environment_packages_sha256": _sha256(
                staging / "environment_packages.json"
            ),
            "dependency_lock_sha256": dependency_lock_sha256,
            "source_sha256": legacy.SOURCE_SHA256,
            "holdout_sha256": legacy.HOLDOUT_SHA256,
        }
        _write_json(staging / "bundle.json", bundle)
        outputs = {
            path.name: _sha256(path) for path in staging.iterdir() if path.is_file()
        }
        _write_json(
            staging / "manifest.json",
            {
                "run_id": output.name,
                "status": "complete",
                "evidence_class": "historical_ames_development_only",
                "created_at_utc": datetime.now(UTC).isoformat(),
                **code_identity,
                "script_sha256": script_sha256,
                "dependency_lock_sha256": dependency_lock_sha256,
                "source_sha256": legacy.SOURCE_SHA256,
                "holdout_sha256": legacy.HOLDOUT_SHA256,
                "split_sha256": outputs["split.json"],
                "feature_policy_sha256": outputs["feature_policy.json"],
                "configuration_sha256": outputs["config.json"],
                "environment_packages_sha256": outputs["environment_packages.json"],
                "checkpoint_identity": outputs["model.json"],
                "development_rows": len(features),
                "reserved_rows_unparsed": len(data.reserved),
                "champion": champion,
                "fit_and_validation_predict_seconds": durations,
                "total_seconds": time.perf_counter() - started,
                "outputs": outputs,
            },
        )
        if any(_sha256(staging / name) != digest for name, digest in outputs.items()):
            raise ValueError("Staged artifact changed before promotion")
        if (
            _sha256(script_path) != script_sha256
            or legacy.collect_git_identity(project_root) != code_identity
            or _validate_dependency_lock(project_root) != dependency_lock_sha256
            or legacy.installed_packages() != packages
        ):
            raise ValueError("Code, dependency lock or environment changed during fit")
        staging.rename(output)
    except Exception as error:
        _write_json(
            staging / "status.json", {"status": "incomplete", "error": str(error)}
        )
        raise
    return output


def predict(
    bundle_dir: Path, request: Mapping[str, object], expected_bundle_sha256: str
) -> dict[str, object]:
    """Predict from a bounded, externally pinned, data-only local bundle."""
    from xgboost import XGBRegressor

    private_root = (
        Path(__file__).resolve().parents[1] / "data" / "raw" / "ames-prototype"
    )
    if not bundle_dir.resolve().is_relative_to(private_root.resolve()):
        raise ValueError("Prototype bundle must be in the private artifact directory")
    if not re.fullmatch(r"[0-9a-f]{64}", expected_bundle_sha256):
        raise ValueError("Expected bundle SHA-256 is invalid")
    bundle_path = bundle_dir / "bundle.json"
    with bundle_path.open("rb") as stream:
        bundle_bytes = stream.read(_MAX_BUNDLE_BYTES + 1)
    if (
        len(bundle_bytes) > _MAX_BUNDLE_BYTES
        or hashlib.sha256(bundle_bytes).hexdigest() != expected_bundle_sha256
    ):
        raise ValueError("Bundle changed or exceeds its size limit")
    bundle = json.loads(bundle_bytes.decode("utf-8"))
    if not isinstance(bundle, dict) or bundle.get("protocol") != PROTOCOL:
        raise ValueError("Model bundle is incompatible")
    policy = _read_json_bounded(
        bundle_dir / "feature_policy.json", _MAX_PREPROCESS_BYTES
    )
    snapshot = _read_json_bounded(
        bundle_dir / "preprocessing.json", _MAX_PREPROCESS_BYTES
    )
    if (
        bundle.get("feature_policy_sha256")
        != _sha256(bundle_dir / "feature_policy.json")
        or bundle.get("preprocessing_sha256")
        != _sha256(bundle_dir / "preprocessing.json")
        or bundle.get("environment_packages_sha256")
        != _sha256(bundle_dir / "environment_packages.json")
        or bundle.get("dependency_lock_sha256")
        != _validate_dependency_lock(Path(__file__).resolve().parents[1])
    ):
        raise ValueError("Bundle policy, preprocessing or environment changed")
    names = tuple(bundle["features"])
    numeric = tuple(bundle["numeric"])
    categorical = tuple(bundle["categorical"])
    if (
        allowed_feature_names(names) != names
        or set(numeric) & set(categorical)
        or set(numeric) | set(categorical) != set(names)
        or policy.get("included") != list(names)
        or policy.get("numeric") != list(numeric)
        or policy.get("categorical") != list(categorical)
        or snapshot.get("protocol") != PROTOCOL
        or snapshot.get("numeric") != list(numeric)
        or snapshot.get("categorical") != list(categorical)
    ):
        raise ValueError("Model feature schema is incompatible")
    values = validate_request(request, names, frozenset(numeric))
    model_path = bundle_dir / "model.json"
    with model_path.open("rb") as stream:
        model_bytes = stream.read(_MAX_MODEL_BYTES + 1)
    if len(model_bytes) > _MAX_MODEL_BYTES or hashlib.sha256(
        model_bytes
    ).hexdigest() != bundle.get("model_sha256"):
        raise ValueError("Model changed or exceeds its size limit")
    if bundle["model"] == "xgboost":
        model = XGBRegressor()
        model.load_model(bytearray(model_bytes))
        transformed, unseen_categories = _encode_request(values, snapshot)
        estimate = float(model.predict(transformed)[0])
    elif bundle["model"] == "median":
        constant = json.loads(model_bytes.decode("utf-8"))
        estimate = float(constant["median_price"])
        _, unseen_categories = _encode_request(values, snapshot)
    else:
        raise ValueError("Unknown model in bundle")
    if not math.isfinite(estimate) or estimate <= 0:
        raise ValueError("Model produced an invalid price")
    return {
        "amount": estimate,
        "currency": "USD",
        "model": bundle["model"],
        "protocol": PROTOCOL,
        "status": "historical_prototype",
        "support_status": "unseen_category"
        if unseen_categories
        else "schema_supported",
        "unseen_category_features": list(unseen_categories),
        "missing_feature_count": sum(value is None for value in values.values()),
        "model_sha256": bundle["model_sha256"],
        "bundle_sha256": expected_bundle_sha256,
    }


def _read_request(path: Path) -> dict[str, object]:
    with path.open("rb") as stream:
        content = stream.read(_MAX_REQUEST_BYTES + 1)
    if len(content) > _MAX_REQUEST_BYTES:
        raise ValueError("Request JSON exceeds size limit")
    value = json.loads(content.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Request must contain a JSON object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("train-evaluate")
    run.add_argument("--source", type=Path, required=True)
    run.add_argument("--holdout", type=Path, required=True)
    run.add_argument("--output", type=Path, required=True)
    serve = commands.add_parser("predict")
    serve.add_argument("--bundle", type=Path, required=True)
    serve.add_argument("--request", type=Path, required=True)
    serve.add_argument("--bundle-sha256", required=True)
    arguments = parser.parse_args()
    if arguments.command == "train-evaluate":
        output = run_experiment(arguments.source, arguments.holdout, arguments.output)
        print(output)
    else:
        print(
            json.dumps(
                predict(
                    arguments.bundle,
                    _read_request(arguments.request),
                    arguments.bundle_sha256,
                ),
                sort_keys=True,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
