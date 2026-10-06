"""Run one bounded LightGBM candidate on the frozen King development protocol."""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.metadata
import io
import json
import math
import os
import platform
import shutil
import tempfile
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from scripts.king_historical_benchmark import (
    FEATURES,
    SOURCE_SHA256,
    Sale,
    encode_features,
    select_eligible_sales,
)
from scripts.private_review_io import real_directory, secure_directory, verify_acl
from scripts.run_king_absolute_error_development import (
    MAX_MANIFEST_BYTES,
    MAX_PREDICTION_BYTES,
    membership_sha256,
    read_development_source,
    read_regular_snapshot,
)
from scripts.run_king_comparable_development import (
    membership_for,
)
from scripts.run_king_historical_benchmark import (
    PRIVATE_ROOT,
    ROOT,
    _committed_code,
    _score,
    _score_summary,
)
from scripts.run_king_rolling_development import WINDOWS, monthly_windows

PROTOCOL = "king_lightgbm_development_screen_v1"
FROZEN_MANIFEST = (
    ROOT / "runs/king-log-absolute-error-development-20261006-v1/manifest.json"
)
FROZEN_MANIFEST_SHA256 = (
    "6b28a8bd0e22f9c0856c2faf15568992d2c139f24d51b63928d550f13bf108c5"
)
FROZEN_SPLIT_SHA256 = "47571792f8aa400a914169c4cd71f536942a0c9b1feb55d2b3ec1805608014ab"
FROZEN_PREDICTION_SHA256 = (
    "c895e704ce57526c76e015f377c6435f56ca9b8d6611c3026eabdc70d6d32ffe"
)
DECLARED_LOCK = ROOT / "locks/king-lightgbm-development.json"
DECLARED_LOCK_SHA256 = (
    "4987558441fbbb3b91a365d86f80c044fedeebd0c1301f325310d362bc2f0cca"
)
MAX_LOCK_BYTES = 10_000
FIT_TIME_CAP_SECONDS = 120.0
OVERALL_TIME_CAP_SECONDS = 300.0
REPLAY_RELATIVE_TOLERANCE = 1e-12
REPLAY_ABSOLUTE_TOLERANCE_USD = 1e-6
INCUMBENT_COLUMNS = (
    "row_id",
    "sale_date",
    "window",
    "actual_usd",
    "xgboost_usd",
    "xgboost_log_absolute_error_usd",
)
MODEL_PARAMETERS: dict[str, object] = {
    "objective": "regression_l1",
    "n_estimators": 250,
    "learning_rate": 0.05,
    "num_leaves": 31,
    "max_depth": 6,
    "min_child_samples": 20,
    "subsample": 0.8,
    "subsample_freq": 1,
    "colsample_bytree": 0.8,
    "reg_alpha": 0.0,
    "reg_lambda": 0.0,
    "random_state": 42,
    "n_jobs": 4,
    "deterministic": True,
    "force_col_wise": True,
    "verbosity": -1,
}


@dataclass(frozen=True)
class FittedWindow:
    """A fitted booster and the exact validation representation it produced."""

    model: object
    feature_names: tuple[str, ...]
    validation: tuple[Sale, ...]
    predictions: tuple[float, ...]


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_frozen_manifest() -> dict[str, object]:
    content = read_regular_snapshot(
        FROZEN_MANIFEST, MAX_MANIFEST_BYTES, "Frozen absolute-error manifest"
    )
    if hashlib.sha256(content).hexdigest() != FROZEN_MANIFEST_SHA256:
        raise ValueError("Frozen absolute-error manifest hash is incompatible")
    try:
        value = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Frozen absolute-error manifest is invalid") from error
    if not isinstance(value, dict):
        raise TypeError("Frozen absolute-error manifest must be an object")
    return value


def runtime_versions() -> dict[str, str]:
    names = ("numpy", "scipy", "lightgbm", "narwhals", "scikit-learn")
    try:
        versions = {name: importlib.metadata.version(name) for name in names}
    except importlib.metadata.PackageNotFoundError as error:
        raise ValueError("Frozen LightGBM runtime dependency is unavailable") from error
    return {
        "python": platform.python_version(),
        **versions,
        "platform": platform.platform(),
        "machine": platform.machine(),
    }


def verify_runtime_versions(frozen: Mapping[str, object]) -> dict[str, str]:
    del frozen  # The new experiment lock is independent of the incumbent lock.
    content = read_regular_snapshot(DECLARED_LOCK, MAX_LOCK_BYTES, "Declared lock")
    if hashlib.sha256(content).hexdigest() != DECLARED_LOCK_SHA256:
        raise ValueError("Declared dependency lock hash is incompatible")
    try:
        lock = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Declared dependency lock is invalid") from error
    if not isinstance(lock, dict) or not isinstance(lock.get("dependencies"), dict):
        raise ValueError("Declared dependency lock is invalid")
    expected = {"python": lock.get("python"), **lock["dependencies"]}
    observed = runtime_versions()
    if any(observed.get(name) != version for name, version in expected.items()):
        raise ValueError("Runtime versions do not match the frozen lock")
    return observed


def verify_frozen_design(frozen: Mapping[str, object]) -> None:
    expected_feature_hash = hashlib.sha256(
        json.dumps(FEATURES, separators=(",", ":")).encode()
    ).hexdigest()
    if (
        frozen.get("protocol") != "king_log_absolute_error_development_screen_v1"
        or frozen.get("status") != "complete"
        or frozen.get("source_sha256") != SOURCE_SHA256
        or frozen.get("frozen_rolling_split_sha256") != FROZEN_SPLIT_SHA256
        or frozen.get("feature_policy_sha256") != expected_feature_hash
        or frozen.get("prediction_artifact_sha256") != FROZEN_PREDICTION_SHA256
    ):
        raise ValueError("Frozen incumbent design is incompatible")


def verify_frozen_membership(
    actual: Mapping[str, object], frozen: Mapping[str, object]
) -> None:
    if actual != frozen.get("window_membership"):
        raise ValueError("Current rows do not match frozen incumbent membership")
    observed_split = frozen.get(
        "frozen_rolling_split_sha256", frozen.get("split_sha256")
    )
    if membership_sha256(actual) != observed_split:
        raise ValueError("Frozen incumbent split hash is incompatible")


def _expected_rows(
    windows: Sequence[tuple[str, Sequence[Sale], Sequence[Sale]]],
) -> tuple[tuple[str, Sale], ...]:
    return tuple((name, row) for name, _, validation in windows for row in validation)


def read_frozen_incumbent(
    path: Path,
    frozen: Mapping[str, object],
    windows: Sequence[tuple[str, Sequence[Sale], Sequence[Sale]]],
) -> dict[str, tuple[float, ...]]:
    content = read_frozen_prediction_snapshot(path, frozen)
    return parse_frozen_incumbent(content, windows)


def read_frozen_prediction_snapshot(path: Path, frozen: Mapping[str, object]) -> bytes:
    """Hash-bind the incumbent artifact before any source label is opened."""
    content = read_regular_snapshot(
        path, MAX_PREDICTION_BYTES, "Frozen absolute-error predictions"
    )
    outputs = frozen.get("outputs")
    if (
        frozen.get("prediction_artifact_sha256") != FROZEN_PREDICTION_SHA256
        or not isinstance(outputs, dict)
        or outputs.get("predictions.csv") != FROZEN_PREDICTION_SHA256
        or hashlib.sha256(content).hexdigest() != FROZEN_PREDICTION_SHA256
    ):
        raise ValueError("Frozen incumbent prediction hash is incompatible")
    return content


def parse_frozen_incumbent(
    content: bytes,
    windows: Sequence[tuple[str, Sequence[Sale], Sequence[Sale]]],
) -> dict[str, tuple[float, ...]]:
    """Validate a previously hash-bound snapshot against frozen row membership."""
    try:
        reader = csv.DictReader(io.StringIO(content.decode("utf-8"), newline=""))
    except UnicodeDecodeError as error:
        raise ValueError("Frozen incumbent predictions are not UTF-8") from error
    if tuple(reader.fieldnames or ()) != INCUMBENT_COLUMNS:
        raise ValueError("Frozen incumbent prediction schema is incompatible")
    rows = list(reader)
    expected = _expected_rows(windows)
    if len(rows) != len(expected):
        raise ValueError("Frozen incumbent prediction membership is incompatible")
    loaded: dict[str, list[float]] = {name: [] for name, _, _ in windows}
    for row, (expected_window, expected_sale) in zip(rows, expected, strict=True):
        if (
            row["row_id"] != expected_sale.row_id
            or row["window"] != expected_window
            or row["sale_date"] != expected_sale.sale_date.isoformat()
            or Decimal(row["actual_usd"]) != expected_sale.price
        ):
            raise ValueError("Frozen incumbent prediction membership is incompatible")
        prediction = float(row["xgboost_log_absolute_error_usd"])
        if not math.isfinite(prediction) or prediction <= 0:
            raise ValueError("Frozen incumbent prediction is invalid")
        loaded[expected_window].append(prediction)
    return {name: tuple(values) for name, values in loaded.items()}


def _lgbm_regressor():
    from lightgbm import LGBMRegressor

    return LGBMRegressor


def fit_lightgbm(training: Sequence[Sale], validation: Sequence[Sale]) -> FittedWindow:
    import numpy as np

    feature_names, training_rows, validation_rows = encode_features(
        training, validation
    )
    model = _lgbm_regressor()(**MODEL_PARAMETERS)
    labels = np.log(np.asarray([float(row.price) for row in training], dtype=float))
    model.fit(np.asarray(training_rows, dtype=float), labels)
    predictions = tuple(
        float(value)
        for value in np.exp(model.predict(np.asarray(validation_rows, dtype=float)))
    )
    if len(predictions) != len(validation) or not all(
        math.isfinite(value) and value > 0 for value in predictions
    ):
        raise ValueError("LightGBM produced invalid predictions")
    return FittedWindow(model, feature_names, tuple(validation), predictions)


def encode_with_feature_names(
    sales: Sequence[Sale], feature_names: Sequence[str]
) -> tuple[tuple[float, ...], ...]:
    """Rebuild rows from a persisted, ordered training-only feature manifest."""
    names = tuple(feature_names)
    numeric_count = len(FEATURES) - 1
    if names[:numeric_count] != tuple(FEATURES[:numeric_count]):
        raise ValueError("Persisted feature order is incompatible")
    zipcode_names = names[numeric_count:]
    if (
        not zipcode_names
        or len(set(names)) != len(names)
        or any(
            not isinstance(name, str) or not name.startswith("zipcode=")
            for name in zipcode_names
        )
    ):
        raise ValueError("Persisted ZIP encoder manifest is incompatible")
    zipcodes = tuple(name.removeprefix("zipcode=") for name in zipcode_names)
    if any(not value for value in zipcodes):
        raise ValueError("Persisted ZIP encoder manifest is incompatible")
    return tuple(
        (
            *(float(sale.attributes[name]) for name in FEATURES[:numeric_count]),
            *(
                float(str(sale.attributes["zipcode"]) == zipcode)
                for zipcode in zipcodes
            ),
        )
        for sale in sales
    )


def save_and_verify_window(
    staging: Path, name: str, fitted: FittedWindow
) -> dict[str, str]:
    """Persist a native booster and encoder, then replay its exact predictions."""
    import numpy as np
    from lightgbm import Booster

    checkpoint = staging / f"{name}-lightgbm.txt"
    encoder = staging / f"{name}-feature-order.json"
    fitted.model.booster_.save_model(checkpoint)  # type: ignore[attr-defined]
    encoder.write_text(
        json.dumps(
            {"feature_names": list(fitted.feature_names)},
            sort_keys=True,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )
    persisted = json.loads(encoder.read_text(encoding="utf-8"))
    if not isinstance(persisted, dict) or not isinstance(
        persisted.get("feature_names"), list
    ):
        raise ValueError("Persisted feature-order artifact is invalid")
    replay_rows = encode_with_feature_names(
        fitted.validation, tuple(persisted["feature_names"])
    )
    reloaded = Booster(model_file=str(checkpoint))
    replay = np.exp(reloaded.predict(np.asarray(replay_rows, dtype=float)))
    expected = np.asarray(fitted.predictions, dtype=float)
    if replay.shape != expected.shape or not np.allclose(
        replay,
        expected,
        rtol=REPLAY_RELATIVE_TOLERANCE,
        atol=REPLAY_ABSOLUTE_TOLERANCE_USD,
    ):
        raise ValueError("Persisted LightGBM replay prediction mismatch")
    return {checkpoint.name: _digest(checkpoint), encoder.name: _digest(encoder)}


def screening_candidate(
    *,
    incumbent_mdape: Decimal,
    challenger_mdape: Decimal,
    incumbent_within_10: Decimal,
    challenger_within_10: Decimal,
    incumbent_p90: Decimal,
    challenger_p90: Decimal,
    challenger_bias: Decimal,
    improved_windows: int,
) -> str:
    if not 0 <= improved_windows <= 4:
        raise ValueError("Improved-window count must be between zero and four")
    if (
        improved_windows >= 3
        and challenger_mdape <= incumbent_mdape * Decimal("0.98")
        and challenger_within_10 >= incumbent_within_10 - Decimal("0.005")
        and challenger_p90 <= incumbent_p90 + Decimal("0.005")
        and abs(challenger_bias) <= Decimal("0.01")
    ):
        return "lightgbm"
    return "xgboost_log_absolute_error"


def enforce_time_caps(fit_seconds: float, overall_seconds: float) -> None:
    if fit_seconds > FIT_TIME_CAP_SECONDS:
        raise TimeoutError("LightGBM fit time cap exceeded")
    if overall_seconds > OVERALL_TIME_CAP_SECONDS:
        raise TimeoutError("LightGBM overall time cap exceeded")


def configuration() -> dict[str, object]:
    return {
        "model_family": "lightgbm",
        "model": dict(MODEL_PARAMETERS),
        "target": "log_price",
        "prediction_transform": "exp",
        "fit_count": 4,
        "fit_time_cap_seconds": FIT_TIME_CAP_SECONDS,
        "overall_time_cap_seconds": OVERALL_TIME_CAP_SECONDS,
        "windows": [
            (name, start.isoformat(), end.isoformat()) for name, start, end in WINDOWS
        ],
    }


def run(source: Path, frozen_predictions: Path, output: Path) -> dict[str, object]:
    started = time.monotonic()
    commit = _committed_code()
    created_root = not PRIVATE_ROOT.exists()
    PRIVATE_ROOT.mkdir(parents=True, exist_ok=True)
    real_directory(PRIVATE_ROOT, PRIVATE_ROOT.parent)
    if created_root:
        secure_directory(PRIVATE_ROOT)
    verify_acl(PRIVATE_ROOT)
    if (
        output.parent.resolve() != PRIVATE_ROOT.resolve()
        or output.exists()
        or output.is_symlink()
    ):
        raise ValueError("Output must be a new private King benchmark directory")

    frozen = load_frozen_manifest()
    verify_frozen_design(frozen)
    runtime = verify_runtime_versions(frozen)
    incumbent_snapshot = read_frozen_prediction_snapshot(frozen_predictions, frozen)
    source_rows = read_development_source(source)
    eligible, quarantine = select_eligible_sales(source_rows)
    windows = monthly_windows(eligible)
    membership = membership_for(windows)
    verify_frozen_membership(membership, frozen)
    if membership_sha256(membership) != FROZEN_SPLIT_SHA256:
        raise ValueError("Frozen split hash is incompatible")
    incumbents = parse_frozen_incumbent(incumbent_snapshot, windows)

    rows: list[tuple[Sale, str, float, float]] = []
    models: dict[str, FittedWindow] = {}
    window_scores: dict[str, object] = {}
    fit_timings: dict[str, float] = {}
    improved_windows = 0
    for name, training, validation in windows:
        fit_started = time.monotonic()
        fitted = fit_lightgbm(training, validation)
        challenger = fitted.predictions
        fit_seconds = time.monotonic() - fit_started
        enforce_time_caps(fit_seconds, time.monotonic() - started)
        incumbent = incumbents[name]
        scores = {
            "xgboost_log_absolute_error": _score(validation, incumbent),
            "lightgbm": _score(validation, challenger),
        }
        improved_windows += int(
            scores["lightgbm"].mdape < scores["xgboost_log_absolute_error"].mdape
        )
        window_scores[name] = {
            key: _score_summary(value) for key, value in scores.items()
        }
        fit_timings[name] = fit_seconds
        models[name] = fitted
        rows.extend(
            (row, name, incumbent_value, challenger_value)
            for row, incumbent_value, challenger_value in zip(
                validation, incumbent, challenger, strict=True
            )
        )

    validations = tuple(row[0] for row in rows)
    pooled = {
        "xgboost_log_absolute_error": _score(
            validations, tuple(row[2] for row in rows)
        ),
        "lightgbm": _score(validations, tuple(row[3] for row in rows)),
    }
    selected = screening_candidate(
        incumbent_mdape=pooled["xgboost_log_absolute_error"].mdape,
        challenger_mdape=pooled["lightgbm"].mdape,
        incumbent_within_10=pooled["xgboost_log_absolute_error"].within_10,
        challenger_within_10=pooled["lightgbm"].within_10,
        incumbent_p90=pooled["xgboost_log_absolute_error"].p90_ape,
        challenger_p90=pooled["lightgbm"].p90_ape,
        challenger_bias=pooled["lightgbm"].median_signed_percentage_error,
        improved_windows=improved_windows,
    )
    pre_output_seconds = time.monotonic() - started
    enforce_time_caps(max(fit_timings.values()), pre_output_seconds)
    summary = {
        "protocol": PROTOCOL,
        "evidence_class": "development_screening_only",
        "source_rows_parsed": len(source_rows),
        "eligible_rows": len(eligible),
        "quarantine_counts": quarantine,
        "windows": window_scores,
        "pooled": {key: _score_summary(value) for key, value in pooled.items()},
        "improved_windows": improved_windows,
        "development_screening_candidate": selected,
        "fit_count": len(models),
        "fit_seconds": fit_timings,
        "pre_output_seconds": pre_output_seconds,
        "march_may_labels_parsed": 0,
        "march_may_rows_scored": 0,
        "promotion_eligible": False,
        "promotion_ineligibility_reason": (
            "historical publication timing, feature vintages, arm's-length status, "
            "and commercial-use rights remain unresolved"
        ),
        "certified_90_day_origin": False,
        "g_us_gate": "PENDING",
    }
    return _write_outputs(
        output,
        summary,
        rows,
        models,
        membership,
        runtime,
        commit,
        started,
    )


def _write_outputs(
    output: Path,
    summary: dict[str, object],
    rows: Sequence[tuple[Sale, str, float, float]],
    models: Mapping[str, FittedWindow],
    membership: Mapping[str, object],
    runtime: Mapping[str, str],
    commit: str,
    started: float,
) -> dict[str, object]:
    with tempfile.TemporaryDirectory(dir=PRIVATE_ROOT, prefix="lightgbm-") as directory:
        staging = Path(directory)
        secure_directory(staging)
        with (staging / "predictions.csv").open(
            "w", newline="", encoding="utf-8"
        ) as stream:
            writer = csv.writer(stream)
            writer.writerow(
                (*INCUMBENT_COLUMNS[:4], INCUMBENT_COLUMNS[-1], "lightgbm_usd")
            )
            for row, window, incumbent, challenger in rows:
                writer.writerow(
                    (
                        row.row_id,
                        row.sale_date,
                        window,
                        row.price,
                        incumbent,
                        challenger,
                    )
                )
        replay_outputs: dict[str, str] = {}
        for name, fitted in models.items():
            replay_outputs.update(save_and_verify_window(staging, name, fitted))
        artifact_summary = {
            **summary,
            "artifact_ready_seconds": time.monotonic() - started,
        }
        enforce_time_caps(0.0, float(artifact_summary["artifact_ready_seconds"]))
        (staging / "scorecards.json").write_text(
            json.dumps(artifact_summary, indent=2, sort_keys=True), encoding="utf-8"
        )
        outputs = {
            path.name: _digest(path) for path in staging.iterdir() if path.is_file()
        }
        if any(outputs.get(name) != digest for name, digest in replay_outputs.items()):
            raise ValueError("Persisted replay artifact hash changed")
        configured = configuration()
        manifest = {
            "run_id": output.name,
            "status": "complete",
            "code_commit": commit,
            "protocol": PROTOCOL,
            "source_sha256": SOURCE_SHA256,
            "declared_lock_sha256": DECLARED_LOCK_SHA256,
            "runtime_versions": dict(runtime),
            "feature_policy_sha256": hashlib.sha256(
                json.dumps(FEATURES, separators=(",", ":")).encode()
            ).hexdigest(),
            "window_membership": membership,
            "frozen_incumbent_split_sha256": FROZEN_SPLIT_SHA256,
            "frozen_incumbent_manifest_sha256": FROZEN_MANIFEST_SHA256,
            "frozen_incumbent_prediction_sha256": FROZEN_PREDICTION_SHA256,
            "configuration": configured,
            "configuration_sha256": hashlib.sha256(
                json.dumps(configured, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest(),
            "fit_count": len(models),
            "outputs": outputs,
            "challenger_checkpoint_identities": {
                name: outputs[f"{name}-lightgbm.txt"] for name in sorted(models)
            },
            "feature_order_identities": {
                name: outputs[f"{name}-feature-order.json"] for name in sorted(models)
            },
            "native_replay": {
                "verified": True,
                "relative_tolerance": REPLAY_RELATIVE_TOLERANCE,
                "absolute_tolerance_usd": REPLAY_ABSOLUTE_TOLERANCE_USD,
            },
            "prediction_artifact_sha256": outputs["predictions.csv"],
        }
        (staging / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
        )
        real_directory(staging, PRIVATE_ROOT)
        verify_acl(staging)
        enforce_time_caps(0.0, time.monotonic() - started)
        os.replace(staging, output)
        try:
            real_directory(output, PRIVATE_ROOT)
            verify_acl(output)
            enforce_time_caps(0.0, time.monotonic() - started)
        except Exception:
            shutil.rmtree(output)
            raise
    return artifact_summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--frozen-predictions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            run(args.source, args.frozen_predictions, args.output), sort_keys=True
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
