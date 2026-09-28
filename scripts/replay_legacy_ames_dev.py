"""Retrospective Ames development replay of the private Day-8 experiment.

Run this with the isolated legacy dependency environment. Reserved ARFF data
lines are discarded by their original zero-based positions before CSV parsing.
The original holdout was potentially exposed and is never scored here.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path

SOURCE_SHA256 = "10db9fe72ed693212a222e39981133ec1b3ee5090d7f2caf2461190a4ad51279"
HOLDOUT_SHA256 = "cafd7740c28130d1e7db58166a00f77257b8eea6e0f33863c529bcb8c77e9306"
LEGACY_LOCK_SHA256 = "a165ac8d49bfa7d2b4d42f46db2d6e33883fe78662df0cee9846828ba2a2aa6f"
SOURCE_ROWS = 1460
HOLDOUT_ROWS = 292
SEED = 42
REQUIRED_OUTPUTS = frozenset(
    {
        "cv_scores.csv",
        "metrics.csv",
        "day8_mae_pivot.csv",
        "dev_fold_predictions.csv",
        "split_membership.json",
        "replay_config.json",
        "feature_policy.json",
        "environment_packages.json",
    }
)
_ATTRIBUTE = re.compile(r"@attribute\s+(?:'([^']+)'|\"([^\"]+)\"|(\S+))", re.IGNORECASE)


def canonical_sha256(value: object) -> str:
    """Hash a JSON record with stable key and separator conventions."""
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def installed_packages() -> dict[str, str]:
    """Capture installed package versions without exposing wheel URLs or tokens."""
    return dict(
        sorted(
            (distribution.metadata["Name"].lower(), distribution.version)
            for distribution in metadata.distributions()
            if distribution.metadata.get("Name")
        )
    )


def require_legacy_lock(path: Path) -> str:
    """Fail rather than describe an unverified package lock as the old one."""
    return hashlib.sha256(
        _verified_bytes(path, LEGACY_LOCK_SHA256, "legacy lock", 5_000_000)
    ).hexdigest()


def collect_git_identity(project_root: Path) -> dict[str, str | bool]:
    """Record the current code commit and whether its tree has local edits."""

    def run_git(*args: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(project_root), *args],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.stdout.strip()

    commit = run_git("rev-parse", "HEAD")
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("Current code commit is not a full Git SHA")
    return {
        "code_commit": commit,
        "dirty_tree": bool(
            run_git("status", "--porcelain", "--untracked-files=normal")
        ),
    }


def verify_replay_identity(
    script_path: Path,
    project_root: Path,
    expected_code: dict[str, str | bool],
    expected_script_sha256: str,
    expected_packages: dict[str, str],
) -> None:
    """Reject a run if its code or installed packages changed after fitting began."""
    if hashlib.sha256(script_path.read_bytes()).hexdigest() != expected_script_sha256:
        raise ValueError("Replay script changed during fitting")
    if collect_git_identity(project_root) != expected_code:
        raise ValueError("Replay code identity changed during fitting")
    if installed_packages() != expected_packages:
        raise ValueError("Replay packages changed during fitting")


def prepare_staging(output_dir: Path) -> Path:
    """Start a crash-visible run without creating an apparently valid output."""
    if output_dir.exists():
        raise ValueError("Replay output directory already exists")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=f"{output_dir.name}.incomplete-", dir=output_dir.parent)
    )
    (staging / "status.json").write_text('{"status":"incomplete"}\n', encoding="utf-8")
    return staging


def promote_staging(staging: Path, output_dir: Path) -> None:
    """Publish a completed immutable run with one directory rename."""
    if output_dir.exists() or not (staging / "manifest.json").is_file():
        raise ValueError("Replay target exists or staged manifest is missing")
    try:
        manifest = json.loads((staging / "manifest.json").read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ValueError("Staged manifest is invalid") from error
    if manifest.get("status") != "complete":
        raise ValueError("Staged manifest must declare complete status")
    outputs = manifest.get("outputs")
    if not isinstance(outputs, dict) or outputs.keys() != REQUIRED_OUTPUTS:
        raise ValueError("Staged manifest is missing required output hashes")
    for name in REQUIRED_OUTPUTS:
        artifact = staging / name
        if not artifact.is_file():
            raise ValueError(f"Staged artifact is missing: {name}")
        actual_hash = hashlib.sha256(artifact.read_bytes()).hexdigest()
        if actual_hash != outputs[name]:
            raise ValueError(f"Staged artifact checksum differs: {name}")
    metadata_files = {
        "split_membership.json": "split_membership_sha256",
        "replay_config.json": "configuration_sha256",
        "feature_policy.json": "feature_policy_sha256",
        "environment_packages.json": "environment_packages_sha256",
    }
    for filename, hash_field in metadata_files.items():
        try:
            content = json.loads((staging / filename).read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise ValueError(f"Staged metadata is invalid: {filename}") from error
        if canonical_sha256(content) != manifest.get(hash_field):
            raise ValueError(f"Staged metadata checksum differs: {filename}")
    (staging / "status.json").write_text('{"status":"complete"}\n', encoding="utf-8")
    os.replace(staging, output_dir)


@dataclass(frozen=True)
class ReplayRun:
    data: object
    scores: tuple[dict[str, object], ...]
    predictions: tuple[dict[str, object], ...]
    split: dict[str, object]
    policy: dict[str, object]
    config: dict[str, object]
    packages: dict[str, str]
    context: dict[str, object]
    started_clock: float


def build_replay_manifest(
    staging: Path, run_id: str, run: ReplayRun
) -> dict[str, object]:
    """Connect the recorded hashes to the exact staged evidence files."""
    missing = REQUIRED_OUTPUTS - {
        path.name for path in staging.iterdir() if path.is_file()
    }
    if missing:
        raise ValueError(f"Staged output files are missing: {sorted(missing)}")
    return {
        "status": "complete",
        "evidence_class": "retrospective_development_only",
        "run_id": run_id,
        **run.context,
        "split_membership_sha256": canonical_sha256(run.split),
        "configuration_sha256": canonical_sha256(run.config),
        "feature_policy_sha256": canonical_sha256(run.policy),
        "environment_packages_sha256": canonical_sha256(run.packages),
        "outputs": {
            name: hashlib.sha256((staging / name).read_bytes()).hexdigest()
            for name in sorted(REQUIRED_OUTPUTS)
        },
    }


@dataclass(frozen=True)
class FilteredArff:
    field_names: tuple[str, ...]
    row_indices: tuple[int, ...]
    csv_text: str


def _verified_bytes(path: Path, expected_sha256: str, name: str, limit: int) -> bytes:
    if not re.fullmatch(r"[0-9a-fA-F]{64}", expected_sha256):
        raise ValueError(f"{name} expected SHA-256 must have 64 hexadecimal digits")
    with path.open("rb") as source:
        content = source.read(limit + 1)
    if len(content) > limit:
        raise ValueError(f"{name} exceeds the size limit")
    if hashlib.sha256(content).hexdigest() != expected_sha256.lower():
        raise ValueError(f"{name} SHA-256 checksum does not match")
    return content


def load_frozen_holdout(
    path: Path,
    *,
    expected_sha256: str,
    expected_count: int,
    source_count: int,
) -> tuple[int, ...]:
    """Read original zero-based row positions, preserving their saved order."""
    content = _verified_bytes(path, expected_sha256, "holdout", 100_000)
    reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
    if reader.fieldnames != ["row_id"]:
        raise ValueError("holdout must contain only the row_id column")
    values = tuple(row["row_id"] for row in reader)
    if len(values) != expected_count or any(
        not re.fullmatch(r"0|[1-9][0-9]*", item) for item in values
    ):
        raise ValueError("holdout count or row_id syntax is invalid")
    indices = tuple(int(item) for item in values)
    if len(set(indices)) != len(indices):
        raise ValueError("holdout contains duplicate row indices")
    if any(index >= source_count for index in indices):
        raise ValueError("holdout row index is out of range")
    return indices


def assert_development_only(
    row_indices: tuple[int, ...] | list[int],
    reserved_indices: tuple[int, ...],
    *,
    source_count: int,
) -> None:
    """Guard every fit and score partition against the frozen reservation."""
    if len(set(row_indices)) != len(row_indices):
        raise ValueError("development partition contains duplicate rows")
    if any(index < 0 or index >= source_count for index in row_indices):
        raise ValueError("development row index is out of range")
    if set(row_indices) & set(reserved_indices):
        raise ValueError("development partition contains a reserved holdout row")


def filter_development_arff(
    path: Path,
    reserved_indices: tuple[int, ...],
    *,
    expected_sha256: str,
    expected_rows: int,
) -> FilteredArff:
    """Skip reserved *physical data rows* before parsing even their Id values."""
    source = _verified_bytes(path, expected_sha256, "ARFF", 10_000_000)
    if len(set(reserved_indices)) != len(reserved_indices) or any(
        index < 0 or index >= expected_rows for index in reserved_indices
    ):
        raise ValueError("reserved indices are duplicate or out of range")
    fields: list[str] = []
    data_started = False
    source_index = 0
    kept_indices: list[int] = []
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    reserved = set(reserved_indices)
    for line in source.decode("utf-8-sig").splitlines():
        stripped = line.strip()
        if not data_started:
            if stripped.lower() == "@data":
                data_started = True
                writer.writerow(fields)
            elif stripped.lower().startswith("@attribute"):
                match = _ATTRIBUTE.match(stripped)
                if match is None:
                    raise ValueError("Invalid ARFF attribute declaration")
                fields.append(next(part for part in match.groups() if part is not None))
            continue
        if not stripped or stripped.startswith("%"):
            continue
        current_index = source_index
        source_index += 1
        if current_index in reserved:
            continue
        # Only development records reach a CSV parser or the SalePrice column.
        # OpenML's dense CSV parser treats double quotes as quoting syntax;
        # single quotes in Ames STRING values are literal category content.
        values = next(csv.reader([line], strict=True))
        if len(values) != len(fields):
            raise ValueError(
                f"Development ARFF row {current_index} has wrong field count"
            )
        writer.writerow(values)
        kept_indices.append(current_index)
    if (
        not data_started
        or len(fields) != len(set(fields))
        or not {"Id", "SalePrice"}.issubset(fields)
    ):
        raise ValueError("ARFF header is incomplete or duplicated")
    if source_index != expected_rows:
        raise ValueError(f"ARFF contains {source_index} rows, expected {expected_rows}")
    if len(kept_indices) + len(reserved) != expected_rows:
        raise ValueError("ARFF reserved/development partition is incomplete")
    assert_development_only(kept_indices, reserved_indices, source_count=expected_rows)
    return FilteredArff(tuple(fields), tuple(kept_indices), output.getvalue())


def _legacy_metrics(actual, predicted) -> dict[str, float]:
    import numpy as np

    true = np.asarray(actual, float)
    pred = np.asarray(predicted, float)
    residual = true - pred
    return {
        "mae": float(np.mean(np.abs(residual))),
        "rmse": float(np.sqrt(np.mean(residual**2))),
        # Historical evaluate.py clips negative predictions; keep this only
        # to reproduce its retrospective numbers, never for certification.
        "rmsle": float(
            np.sqrt(np.mean((np.log1p(np.clip(pred, 0, None)) - np.log1p(true)) ** 2))
        ),
        "r2": float(1 - np.sum(residual**2) / np.sum((true - np.mean(true)) ** 2)),
    }


def validate_finite_replay_values(values, *, field: str) -> None:
    """Reject invalid model outputs before any score or prediction is saved."""
    count = 0
    for value in values:
        count += 1
        try:
            number = float(value)
        except (TypeError, ValueError) as error:
            raise ValueError(f"{field} must be finite numeric values") from error
        if isinstance(value, bool) or not math.isfinite(number):
            raise ValueError(f"{field} must be finite numeric values")
    if count == 0:
        raise ValueError(f"{field} output is empty")


def day8_mae_pivot_rows(scores: list[dict[str, object]]) -> list[dict[str, object]]:
    """Pivot Day-8 fold MAE; this is not an independent baseline.py replay."""
    paired: dict[int, dict[str, object]] = {}
    for row in scores:
        fold = int(row["pli"])
        model = str(row["modele"])
        if model not in {"Dummy", "XGBoost"} or model in paired.get(fold, {}):
            raise ValueError("Baseline scores have an invalid model or duplicate pair")
        paired.setdefault(fold, {})[model] = row["mae"]
    if not paired or any(
        set(models) != {"Dummy", "XGBoost"} for models in paired.values()
    ):
        raise ValueError("Baseline scores require one Dummy/XGBoost pair per fold")
    return [
        {
            "pli": fold,
            "MAE_dummy": paired[fold]["Dummy"],
            "MAE_xgboost": paired[fold]["XGBoost"],
        }
        for fold in sorted(paired)
    ]


@dataclass(frozen=True)
class DevelopmentInputs:
    frame: object
    features: object
    labels: object
    reserved: tuple[int, ...]
    development_order: tuple[int, ...]


def _load_development(source: Path, holdout: Path) -> DevelopmentInputs:
    import numpy as np
    import pandas as pd
    from sklearn.model_selection import train_test_split

    reserved = load_frozen_holdout(
        holdout,
        expected_sha256=HOLDOUT_SHA256,
        expected_count=HOLDOUT_ROWS,
        source_count=SOURCE_ROWS,
    )
    filtered = filter_development_arff(
        source, reserved, expected_sha256=SOURCE_SHA256, expected_rows=SOURCE_ROWS
    )
    dev_order, recomputed_holdout = train_test_split(
        np.arange(SOURCE_ROWS), test_size=0.20, random_state=SEED
    )
    if tuple(int(item) for item in recomputed_holdout) != reserved:
        raise ValueError("Frozen holdout order differs from legacy train_test_split")
    order = tuple(int(item) for item in dev_order)
    assert_development_only(order, reserved, source_count=SOURCE_ROWS)
    frame = pd.read_csv(io.StringIO(filtered.csv_text), na_values=["?"])
    frame.index = pd.Index(filtered.row_indices)
    if not frame["Id"].eq(frame.index + 1).all():
        raise ValueError(
            "ARFF Id no longer matches the frozen zero-based row positions"
        )
    dev = frame.loc[dev_order]
    if len(dev) != SOURCE_ROWS - HOLDOUT_ROWS:
        raise ValueError("Development row count differs from the original split")
    labels = dev["SalePrice"]
    if not np.isfinite(labels.to_numpy(dtype=float)).all() or (labels <= 0).any():
        raise ValueError("Development prices are invalid")
    return DevelopmentInputs(
        frame, dev.drop(columns=["SalePrice"]), labels, reserved, order
    )


def _build_model_components(features):
    from sklearn.compose import ColumnTransformer
    from sklearn.dummy import DummyRegressor
    from sklearn.impute import SimpleImputer
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OneHotEncoder
    from xgboost import XGBRegressor

    numeric = features.select_dtypes(include="number").columns.tolist()
    categorical = [name for name in features.columns if name not in numeric]
    prep = ColumnTransformer(
        [
            ("num", SimpleImputer(strategy="median"), numeric),
            (
                "cat",
                Pipeline(
                    [
                        ("imp", SimpleImputer(strategy="most_frequent")),
                        ("oh", OneHotEncoder(handle_unknown="ignore")),
                    ]
                ),
                categorical,
            ),
        ]
    )
    models = {
        "Dummy": DummyRegressor(strategy="mean"),
        "XGBoost": XGBRegressor(
            n_estimators=400,
            max_depth=4,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=SEED,
            n_jobs=-1,
        ),
    }
    return prep, models, numeric, categorical


def _resolved_config() -> dict[str, object]:
    return {
        "seed": SEED,
        "holdout_test_size": 0.20,
        "cv": {"n_splits": 5, "shuffle": True, "random_state": SEED},
        "input_reconstruction": "Checksum-pinned ARFF development lines only; Pandas CSV inference; ? as missing; exact historical ames.csv unavailable.",
        "preprocessing": {
            "numeric": "SimpleImputer(strategy=median)",
            "categorical": "SimpleImputer(strategy=most_frequent)+OneHotEncoder(handle_unknown=ignore)",
        },
        "models": {
            "Dummy": {"strategy": "mean"},
            "XGBoost": {
                "n_estimators": 400,
                "max_depth": 4,
                "learning_rate": 0.05,
                "subsample": 0.8,
                "colsample_bytree": 0.8,
                "random_state": SEED,
                "n_jobs": -1,
            },
        },
        "metric_semantics": "legacy evaluate.py, including nonpositive prediction clipping for RMSLE",
    }


def _protocol_records(data: DevelopmentInputs, folds, numeric, categorical):
    split = {
        "protocol": "legacy_day8_single_shuffled_5fold_seed42",
        "development_order": list(data.development_order),
        "reserved_order": list(data.reserved),
        "folds": [
            {
                "fold": number,
                "train": [int(data.features.index[position]) for position in train],
                "validation": [
                    int(data.features.index[position]) for position in validation
                ],
            }
            for number, (train, validation) in enumerate(folds, start=1)
        ],
    }
    policy = {
        "policy": "legacy_all_non_target_columns_unrestricted_not_certified",
        "feature_columns": data.features.columns.tolist(),
        "numeric_columns": numeric,
        "categorical_columns": categorical,
    }
    return split, policy


def _run_cv(data: DevelopmentInputs, folds, prep, models):
    from sklearn.pipeline import Pipeline

    scores: list[dict[str, object]] = []
    predictions: list[dict[str, object]] = []
    for model_name, model in models.items():
        for fold, (train, validation) in enumerate(folds, start=1):
            x_train = data.features.iloc[train]
            x_validation = data.features.iloc[validation]
            y_train = data.labels.iloc[train]
            y_validation = data.labels.iloc[validation]
            assert_development_only(
                tuple(x_train.index), data.reserved, source_count=SOURCE_ROWS
            )
            assert_development_only(
                tuple(x_validation.index), data.reserved, source_count=SOURCE_ROWS
            )
            if set(x_train.index) & set(x_validation.index):
                raise ValueError("Training and validation folds overlap")
            pipe = Pipeline([("prep", prep), ("model", model)])
            started = time.perf_counter()
            pipe.fit(x_train, y_train)
            predicted = pipe.predict(x_validation)
            validate_finite_replay_values(predicted, field="prediction")
            metrics = _legacy_metrics(y_validation, predicted)
            validate_finite_replay_values(metrics.values(), field="metric")
            scores.append(
                {
                    "modele": model_name,
                    "pli": fold,
                    **metrics,
                    "temps_s": round(time.perf_counter() - started, 2),
                }
            )
            predictions.extend(
                {
                    "source_row_index": int(index),
                    "source_id": int(data.frame.at[index, "Id"]),
                    "modele": model_name,
                    "pli": fold,
                    "actual": float(actual),
                    "predicted": float(estimate),
                }
                for index, actual, estimate in zip(
                    x_validation.index, y_validation, predicted, strict=True
                )
            )
    return scores, predictions


def _write_json(staging: Path, name: str, value: object) -> None:
    (staging / name).write_text(
        json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )


def _write_score_tables(staging: Path, run: ReplayRun) -> None:
    import pandas as pd

    score_frame = pd.DataFrame(run.scores)[
        ["modele", "pli", "mae", "rmse", "rmsle", "r2", "temps_s"]
    ]
    summary = (
        score_frame.groupby("modele")
        .mean(numeric_only=True)
        .drop(columns="pli")
        .reset_index()
    )
    outputs = {
        "cv_scores.csv": score_frame,
        "metrics.csv": summary,
        "day8_mae_pivot.csv": pd.DataFrame(day8_mae_pivot_rows(list(run.scores))),
        "dev_fold_predictions.csv": pd.DataFrame(run.predictions),
    }
    for name, frame in outputs.items():
        frame.to_csv(staging / name, index=False)


def _persist_run(staging: Path, output_dir: Path, run: ReplayRun) -> None:
    _write_score_tables(staging, run)
    for name, value in (
        ("split_membership.json", run.split),
        ("feature_policy.json", run.policy),
        ("replay_config.json", run.config),
        ("environment_packages.json", run.packages),
    ):
        _write_json(staging, name, value)
    complete_run = replace(
        run,
        context={
            **run.context,
            "development_rows": len(run.data.features),
            "duration_seconds": round(time.perf_counter() - run.started_clock, 3),
        },
    )
    manifest = build_replay_manifest(staging, output_dir.name, complete_run)
    _write_json(staging, "manifest.json", manifest)
    script_path = Path(__file__).resolve()
    verify_replay_identity(
        script_path,
        script_path.parents[1],
        {key: run.context[key] for key in ("code_commit", "dirty_tree")},
        str(run.context["script_sha256"]),
        run.packages,
    )
    promote_staging(staging, output_dir)


def _run_context(
    code_identity: dict[str, str | bool],
    script_sha256: str,
    lock_sha256: str,
    config: dict[str, object],
    started_at: datetime,
    command: list[str] | None,
) -> dict[str, object]:
    import numpy as np
    import pandas as pd
    import sklearn
    import xgboost

    return {
        **code_identity,
        "source_sha256": SOURCE_SHA256,
        "holdout_sha256": HOLDOUT_SHA256,
        "legacy_uv_lock_sha256": lock_sha256,
        "script_sha256": script_sha256,
        "legacy_protocol": "day8_single_shuffled_5fold_seed42",
        "source_rows": SOURCE_ROWS,
        "reserved_rows_unparsed": HOLDOUT_ROWS,
        "checkpoint_identity": None,
        "checkpoint_persisted": False,
        "command": command,
        "started_at_utc": started_at.isoformat(),
        "numpy_version": np.__version__,
        "pandas_version": pd.__version__,
        "scikit_learn_version": sklearn.__version__,
        "xgboost_version": xgboost.__version__,
        "python_version": sys.version.split()[0],
        "input_reconstruction": config["input_reconstruction"],
    }


def run_replay(
    source: Path,
    holdout: Path,
    legacy_lock: Path,
    output_dir: Path,
    *,
    command: list[str] | None = None,
) -> Path:
    """Replay only the frozen legacy development folds."""
    from sklearn.model_selection import KFold

    started_at = datetime.now(UTC)
    started_clock = time.perf_counter()
    script_path = Path(__file__).resolve()
    code_identity = collect_git_identity(script_path.parents[1])
    script_sha256 = hashlib.sha256(script_path.read_bytes()).hexdigest()
    packages = installed_packages()
    lock_sha256 = require_legacy_lock(legacy_lock)
    data = _load_development(source, holdout)
    prep, models, numeric, categorical = _build_model_components(data.features)
    folds = tuple(
        KFold(n_splits=5, shuffle=True, random_state=SEED).split(data.features)
    )
    split, policy = _protocol_records(data, folds, numeric, categorical)
    config = _resolved_config()
    context = _run_context(
        code_identity, script_sha256, lock_sha256, config, started_at, command
    )
    staging = prepare_staging(output_dir)
    scores, predictions = _run_cv(data, folds, prep, models)
    run = ReplayRun(
        data,
        tuple(scores),
        tuple(predictions),
        split,
        policy,
        config,
        packages,
        context,
        started_clock,
    )
    _persist_run(staging, output_dir, run)
    return output_dir


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--holdout", type=Path, required=True)
    parser.add_argument("--legacy-lock", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    run_replay(
        arguments.source,
        arguments.holdout,
        arguments.legacy_lock,
        arguments.output,
        command=[sys.executable, *sys.argv],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
