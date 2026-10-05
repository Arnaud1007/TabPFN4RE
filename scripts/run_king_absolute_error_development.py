"""Run the bounded King log absolute-error development screen."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
import platform
import shutil
import stat
import tempfile
from collections.abc import Mapping, Sequence
from decimal import Decimal
from pathlib import Path

from scripts.king_historical_benchmark import (
    FEATURES,
    SOURCE_SHA256,
    Sale,
    _decode_source,
    _locate_data,
    _parse_sale,
    encode_features,
    select_eligible_sales,
)
from scripts.private_review_io import real_directory, secure_directory, verify_acl
from scripts.run_king_comparable_development import (
    membership_for,
    verify_frozen_membership,
)
from scripts.run_king_historical_benchmark import (
    MODEL_PARAMETERS,
    PRIVATE_ROOT,
    ROOT,
    _committed_code,
    _score,
    _score_summary,
)
from scripts.run_king_rolling_development import WINDOWS, monthly_windows

PROTOCOL = "king_log_absolute_error_development_screen_v1"
FROZEN_MANIFEST = ROOT / "runs/king-rolling-development-20261005-v1/manifest.json"
FROZEN_MANIFEST_SHA256 = (
    "a32cdbb1a4708b5f097a2d2949e228497636c5c7c358e2cb4128b269e91bbd12"
)
DECLARED_LOCK = ROOT / "locks/ames-prototype-requirements.txt"
DEVELOPMENT_END = "20150301T000000"
MAX_MANIFEST_BYTES = 1_000_000
MAX_PREDICTION_BYTES = 10_000_000
MAX_LOCK_BYTES = 100_000
FROZEN_COLUMNS = (
    "row_id",
    "sale_date",
    "window",
    "actual_usd",
    "zipcode_median_usd",
    "xgboost_usd",
    "xgboost_recency_180d_usd",
)


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_regular_snapshot(path: Path, limit: int, label: str) -> bytes:
    """Read one bounded regular-file snapshot and reject symbolic links."""
    if limit <= 0:
        raise ValueError("Snapshot size limit must be positive")
    try:
        path_metadata = path.lstat()
        if stat.S_ISLNK(path_metadata.st_mode):
            raise ValueError(f"{label} must not be a symbolic link")
        if not stat.S_ISREG(path_metadata.st_mode):
            raise ValueError(f"{label} must be a regular file")
        if path_metadata.st_size > limit:
            raise ValueError(f"{label} exceeds size limit")
        with path.open("rb") as stream:
            metadata = os.fstat(stream.fileno())
            if not stat.S_ISREG(metadata.st_mode):
                raise ValueError(f"{label} must be a regular file")
            if metadata.st_size > limit:
                raise ValueError(f"{label} exceeds size limit")
            content = stream.read(limit + 1)
    except OSError as error:
        raise ValueError(f"{label} could not be read") from error
    if len(content) > limit:
        raise ValueError(f"{label} exceeds size limit")
    return content


def membership_sha256(membership: Mapping[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(membership, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def load_frozen_manifest() -> dict[str, object]:
    """Load only the exact committed rolling manifest."""
    content = read_regular_snapshot(
        FROZEN_MANIFEST, MAX_MANIFEST_BYTES, "Frozen rolling manifest"
    )
    if hashlib.sha256(content).hexdigest() != FROZEN_MANIFEST_SHA256:
        raise ValueError("Frozen rolling manifest hash is incompatible")
    try:
        value = json.loads(content.decode("utf-8"))
    except UnicodeDecodeError as error:
        raise ValueError("Frozen rolling manifest is not UTF-8") from error
    if not isinstance(value, dict):
        raise TypeError("Frozen rolling manifest must be an object")
    return value


def read_development_source(path: Path) -> tuple[Sale, ...]:
    """Parse full sale rows only when their date prefix is before March 2015."""
    lines = _decode_source(path, SOURCE_SHA256)
    marker = _locate_data(lines)
    parsed: list[Sale] = []
    observed_rows = 0
    for raw_line in lines[marker + 1 :]:
        if not raw_line.strip() or raw_line.lstrip().startswith("%"):
            continue
        observed_rows += 1
        prefix = raw_line.split(",", 2)
        if len(prefix) != 3 or not prefix[0] or not prefix[1]:
            raise ValueError("Source row lacks an id/date prefix")
        if prefix[1] < DEVELOPMENT_END:
            values = next(csv.reader(io.StringIO(raw_line)))
            parsed.append(_parse_sale(values, raw_line))
    if observed_rows != 21_613:
        raise ValueError("Source row count does not match expected row count")
    return tuple(parsed)


def _expected_rows(
    windows: Sequence[tuple[str, Sequence[Sale], Sequence[Sale]]],
) -> tuple[tuple[str, Sale], ...]:
    return tuple((name, item) for name, _, validation in windows for item in validation)


def read_frozen_incumbent(
    path: Path,
    frozen: Mapping[str, object],
    windows: Sequence[tuple[str, Sequence[Sale], Sequence[Sale]]],
) -> dict[str, tuple[float, ...]]:
    """Read incumbent predictions only after exact artifact and row checks."""
    expected_digest = frozen.get("prediction_artifact_sha256")
    outputs = frozen.get("outputs")
    content = read_regular_snapshot(
        path, MAX_PREDICTION_BYTES, "Frozen rolling predictions"
    )
    if (
        not isinstance(expected_digest, str)
        or not isinstance(outputs, dict)
        or outputs.get("predictions.csv") != expected_digest
        or hashlib.sha256(content).hexdigest() != expected_digest
    ):
        raise ValueError("Frozen rolling prediction artifact hash is incompatible")

    expected = _expected_rows(windows)
    loaded: dict[str, list[float]] = {name: [] for name, _, _ in windows}
    try:
        decoded = content.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("Frozen rolling predictions are not UTF-8") from error
    reader = csv.DictReader(io.StringIO(decoded, newline=""))
    if tuple(reader.fieldnames or ()) != FROZEN_COLUMNS:
        raise ValueError("Frozen rolling prediction schema is incompatible")
    rows = list(reader)
    if len(rows) != len(expected):
        raise ValueError("Frozen rolling prediction membership is incompatible")
    for row, (expected_window, expected_sale) in zip(rows, expected, strict=True):
        if (
            row["row_id"] != expected_sale.row_id
            or row["window"] != expected_window
            or row["sale_date"] != expected_sale.sale_date.isoformat()
            or Decimal(row["actual_usd"]) != expected_sale.price
        ):
            raise ValueError("Frozen rolling prediction membership is incompatible")
        prediction = float(row["xgboost_usd"])
        if not math.isfinite(prediction) or prediction <= 0:
            raise ValueError("Frozen incumbent prediction is invalid")
        loaded[expected_window].append(prediction)
    return {name: tuple(values) for name, values in loaded.items()}


def fit_absolute_error(
    training: Sequence[Sale], validation: Sequence[Sale]
) -> tuple[tuple[float, ...], object]:
    """Fit the registered model with only its objective changed."""
    import numpy as np
    from xgboost import XGBRegressor

    _, training_rows, validation_rows = encode_features(training, validation)
    parameters = {**MODEL_PARAMETERS, "objective": "reg:absoluteerror"}
    model = XGBRegressor(**parameters)
    labels = np.log(np.asarray([float(item.price) for item in training], dtype=float))
    model.fit(np.asarray(training_rows, dtype=float), labels)
    predicted = tuple(
        float(value)
        for value in np.exp(model.predict(np.asarray(validation_rows, dtype=float)))
    )
    if len(predicted) != len(validation) or not all(
        math.isfinite(value) and value > 0 for value in predicted
    ):
        raise ValueError("Absolute-error model produced invalid predictions")
    return predicted, model


def screening_candidate(
    *,
    incumbent_mdape: Decimal,
    challenger_mdape: Decimal,
    incumbent_within_10: Decimal,
    challenger_within_10: Decimal,
    incumbent_p90: Decimal,
    challenger_p90: Decimal,
    improved_windows: int,
) -> str:
    """Apply the existing development useful-gain rule."""
    if not 0 <= improved_windows <= 4:
        raise ValueError("Improved-window count must be between zero and four")
    if (
        improved_windows >= 3
        and challenger_mdape <= incumbent_mdape * Decimal("0.98")
        and challenger_within_10 >= incumbent_within_10 - Decimal("0.005")
        and challenger_p90 <= incumbent_p90 + Decimal("0.005")
    ):
        return "xgboost_log_absolute_error"
    return "xgboost"


def runtime_versions() -> dict[str, str]:
    import numpy
    import xgboost

    return {
        "python": platform.python_version(),
        "numpy": numpy.__version__,
        "xgboost": xgboost.__version__,
        "platform": platform.platform(),
        "machine": platform.machine(),
    }


def verify_frozen_design(frozen: Mapping[str, object]) -> None:
    """Bind model, windows and feature policy before source labels are read."""
    rolling_configuration = {
        "model": MODEL_PARAMETERS,
        "half_life_days": 180,
        "windows": [
            (name, start.isoformat(), end.isoformat()) for name, start, end in WINDOWS
        ],
    }
    configuration_digest = hashlib.sha256(
        json.dumps(rolling_configuration, sort_keys=True).encode()
    ).hexdigest()
    feature_digest = hashlib.sha256(
        json.dumps(FEATURES, separators=(",", ":")).encode()
    ).hexdigest()
    if frozen.get("configuration_sha256") != configuration_digest:
        raise ValueError("Frozen rolling configuration hash is incompatible")
    if frozen.get("feature_policy_sha256") != feature_digest:
        raise ValueError("Frozen rolling feature policy hash is incompatible")


def verify_runtime_versions(frozen: Mapping[str, object]) -> dict[str, str]:
    """Reject dependency drift before any source label is parsed or model fitted."""
    lock_content = read_regular_snapshot(
        DECLARED_LOCK, MAX_LOCK_BYTES, "Declared dependency lock"
    )
    lock_digest = hashlib.sha256(lock_content).hexdigest()
    if frozen.get("dependency_lock_sha256") != lock_digest:
        raise ValueError("Frozen rolling dependency lock hash is incompatible")
    pinned = {
        name: version
        for line in lock_content.decode("utf-8").splitlines()
        if "==" in line
        for name, version in (line.strip().split("==", maxsplit=1),)
    }
    observed = runtime_versions()
    expected = {
        "numpy": pinned.get("numpy"),
        "xgboost": pinned.get("xgboost"),
    }
    if any(observed.get(name) != version for name, version in expected.items()):
        raise ValueError("Runtime dependency versions do not match the frozen lock")
    if not observed.get("python", "").startswith("3.11."):
        raise ValueError("Runtime Python version does not match the frozen environment")
    return observed


def configuration() -> dict[str, object]:
    return {
        "model": {**MODEL_PARAMETERS, "objective": "reg:absoluteerror"},
        "changed_factor": "objective",
        "incumbent_objective": MODEL_PARAMETERS["objective"],
        "challenger_objective": "reg:absoluteerror",
        "fit_count": 4,
        "windows": [
            (name, start.isoformat(), end.isoformat()) for name, start, end in WINDOWS
        ],
    }


def run(source: Path, frozen_predictions: Path, output: Path) -> dict[str, object]:
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
    source_rows = read_development_source(source)
    eligible, quarantine = select_eligible_sales(source_rows)
    windows = monthly_windows(eligible)
    membership = membership_for(windows)
    verify_frozen_membership(membership, frozen)
    incumbents = read_frozen_incumbent(frozen_predictions, frozen, windows)

    rows: list[tuple[Sale, str, float, float]] = []
    models: dict[str, object] = {}
    window_scores: dict[str, object] = {}
    improved_windows = 0
    for name, training, validation in windows:
        challenger, model = fit_absolute_error(training, validation)
        incumbent = incumbents[name]
        scores = {
            "xgboost": _score(validation, incumbent),
            "xgboost_log_absolute_error": _score(validation, challenger),
        }
        improved_windows += int(
            scores["xgboost_log_absolute_error"].mdape < scores["xgboost"].mdape
        )
        window_scores[name] = {
            key: _score_summary(value) for key, value in scores.items()
        }
        models[name] = model
        rows.extend(
            (item, name, base, candidate)
            for item, base, candidate in zip(
                validation, incumbent, challenger, strict=True
            )
        )

    validations = tuple(item[0] for item in rows)
    pooled = {
        "xgboost": _score(validations, tuple(item[2] for item in rows)),
        "xgboost_log_absolute_error": _score(
            validations, tuple(item[3] for item in rows)
        ),
    }
    candidate = screening_candidate(
        incumbent_mdape=pooled["xgboost"].mdape,
        challenger_mdape=pooled["xgboost_log_absolute_error"].mdape,
        incumbent_within_10=pooled["xgboost"].within_10,
        challenger_within_10=pooled["xgboost_log_absolute_error"].within_10,
        incumbent_p90=pooled["xgboost"].p90_ape,
        challenger_p90=pooled["xgboost_log_absolute_error"].p90_ape,
        improved_windows=improved_windows,
    )
    summary = {
        "protocol": PROTOCOL,
        "evidence_class": "development_screening_only",
        "source_rows_parsed": len(source_rows),
        "eligible_rows": len(eligible),
        "quarantine_counts": quarantine,
        "windows": window_scores,
        "pooled": {key: _score_summary(value) for key, value in pooled.items()},
        "improved_windows": improved_windows,
        "development_screening_candidate": candidate,
        "fit_count": len(models),
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
    _write_outputs(output, summary, rows, models, membership, frozen, runtime, commit)
    return summary


def _write_outputs(
    output: Path,
    summary: Mapping[str, object],
    rows: Sequence[tuple[Sale, str, float, float]],
    models: Mapping[str, object],
    membership: Mapping[str, object],
    frozen: Mapping[str, object],
    runtime: Mapping[str, str],
    commit: str,
) -> None:
    with tempfile.TemporaryDirectory(dir=PRIVATE_ROOT, prefix="absolute-") as directory:
        staging = Path(directory)
        secure_directory(staging)
        with (staging / "predictions.csv").open(
            "w", newline="", encoding="utf-8"
        ) as stream:
            writer = csv.writer(stream)
            writer.writerow(
                (
                    "row_id",
                    "sale_date",
                    "window",
                    "actual_usd",
                    "xgboost_usd",
                    "xgboost_log_absolute_error_usd",
                )
            )
            for item, window, incumbent, challenger in rows:
                writer.writerow(
                    (
                        item.row_id,
                        item.sale_date,
                        window,
                        item.price,
                        incumbent,
                        challenger,
                    )
                )
        (staging / "scorecards.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
        )
        for name, model in models.items():
            model.save_model(staging / f"{name}-xgboost-log-absolute-error.json")
        outputs = {
            path.name: _digest(path) for path in staging.iterdir() if path.is_file()
        }
        configured = configuration()
        manifest = {
            "run_id": output.name,
            "status": "complete",
            "code_commit": commit,
            "protocol": PROTOCOL,
            "source_sha256": SOURCE_SHA256,
            "declared_lock_sha256": frozen["dependency_lock_sha256"],
            "runtime_versions": dict(runtime),
            "feature_policy_sha256": hashlib.sha256(
                json.dumps(FEATURES, separators=(",", ":")).encode()
            ).hexdigest(),
            "window_membership": membership,
            "frozen_rolling_split_sha256": frozen.get("split_sha256"),
            "frozen_rolling_manifest_sha256": FROZEN_MANIFEST_SHA256,
            "frozen_rolling_prediction_sha256": frozen["prediction_artifact_sha256"],
            "configuration": configured,
            "configuration_sha256": hashlib.sha256(
                json.dumps(configured, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest(),
            "fit_count": len(models),
            "outputs": outputs,
            "challenger_checkpoint_identities": {
                name: outputs[f"{name}-xgboost-log-absolute-error.json"]
                for name in sorted(models)
            },
            "prediction_artifact_sha256": outputs["predictions.csv"],
        }
        (staging / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
        )
        real_directory(staging, PRIVATE_ROOT)
        verify_acl(staging)
        os.replace(staging, output)
        try:
            real_directory(output, PRIVATE_ROOT)
            verify_acl(output)
        except Exception:
            shutil.rmtree(output)
            raise


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
