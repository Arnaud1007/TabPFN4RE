"""Run the bounded King three-field source-row feature ablation."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
import shutil
import stat
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from scripts.king_historical_benchmark import (
    COLUMNS,
    FEATURES,
    MAX_SOURCE_BYTES,
    SOURCE_SHA256,
    Sale,
    _locate_data,
    _parse_sale,
    encode_features,
    select_eligible_sales,
)
from scripts.private_review_io import real_directory, secure_directory, verify_acl
from scripts.run_king_absolute_error_development import (
    DEVELOPMENT_END,
    MAX_MANIFEST_BYTES,
    MAX_PREDICTION_BYTES,
    membership_sha256,
    read_regular_snapshot,
    verify_runtime_versions,
)
from scripts.run_king_comparable_development import membership_for
from scripts.run_king_historical_benchmark import (
    MODEL_PARAMETERS,
    PRIVATE_ROOT,
    ROOT,
    _committed_code,
    _score,
    _score_summary,
)
from scripts.run_king_rolling_development import WINDOWS, monthly_windows
from tabpfn4realestate.evaluation.metrics import Scorecard

PROTOCOL = "king_three_field_feature_family_development_v1"
ADDED_FEATURES = ("yr_renovated", "sqft_living15", "sqft_lot15")
INCUMBENT_MANIFEST = (
    ROOT / "runs/king-log-absolute-error-development-20261006-v1/manifest.json"
)
INCUMBENT_MANIFEST_SHA256 = (
    "6b28a8bd0e22f9c0856c2faf15568992d2c139f24d51b63928d550f13bf108c5"
)
INCUMBENT_PREDICTION_SHA256 = (
    "c895e704ce57526c76e015f377c6435f56ca9b8d6611c3026eabdc70d6d32ffe"
)
FROZEN_SPLIT_SHA256 = "47571792f8aa400a914169c4cd71f536942a0c9b1feb55d2b3ec1805608014ab"
INCUMBENT_COLUMNS = (
    "row_id",
    "sale_date",
    "window",
    "actual_usd",
    "xgboost_usd",
    "xgboost_log_absolute_error_usd",
)


@dataclass(frozen=True)
class SourceFeatureRow:
    sale: Sale
    added_values: tuple[float, float, float]
    future_renovation_replaced: bool


def read_source_snapshot(path: Path) -> list[str]:
    """Read, hash, and decode one bounded regular non-reparse source snapshot."""
    try:
        metadata = path.lstat()
    except OSError as error:
        raise ValueError("King source could not be inspected") from error
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    if getattr(metadata, "st_file_attributes", 0) & reparse_flag:
        raise ValueError("King source must not be a reparse point")
    content = read_regular_snapshot(path, MAX_SOURCE_BYTES, "King source")
    if hashlib.sha256(content).hexdigest() != SOURCE_SHA256:
        raise ValueError("King source checksum mismatch")
    try:
        return content.decode("utf-8").splitlines()
    except UnicodeDecodeError as error:
        raise ValueError("King source is not UTF-8") from error


def read_development_source(path: Path) -> tuple[SourceFeatureRow, ...]:
    """Read only pre-March rows and retain the three predeclared raw fields."""
    lines = read_source_snapshot(path)
    marker = _locate_data(lines)
    result: list[SourceFeatureRow] = []
    observed = 0
    for raw_line in lines[marker + 1 :]:
        if not raw_line.strip() or raw_line.lstrip().startswith("%"):
            continue
        observed += 1
        prefix = raw_line.split(",", 2)
        if len(prefix) != 3 or not prefix[0] or not prefix[1]:
            raise ValueError("Source row lacks an id/date prefix")
        if prefix[1] >= DEVELOPMENT_END:
            continue
        values = next(csv.reader(io.StringIO(raw_line)))
        sale = _parse_sale(values, raw_line)
        fields = dict(zip(COLUMNS, values, strict=True))
        try:
            renovation = float(fields["yr_renovated"])
            living15 = float(fields["sqft_living15"])
            lot15 = float(fields["sqft_lot15"])
        except ValueError as error:
            raise ValueError("Added source feature is invalid") from error
        if not all(math.isfinite(value) for value in (renovation, living15, lot15)):
            raise ValueError("Added source feature is not finite")
        future = renovation > sale.sale_date.year
        result.append(
            SourceFeatureRow(
                sale=sale,
                added_values=(math.nan if future else renovation, living15, lot15),
                future_renovation_replaced=future,
            )
        )
    if observed != 21_613:
        raise ValueError("Source row count does not match expected row count")
    return tuple(result)


def load_incumbent_manifest() -> dict[str, object]:
    content = read_regular_snapshot(
        INCUMBENT_MANIFEST, MAX_MANIFEST_BYTES, "Incumbent manifest"
    )
    if hashlib.sha256(content).hexdigest() != INCUMBENT_MANIFEST_SHA256:
        raise ValueError("Incumbent manifest hash is incompatible")
    value = json.loads(content.decode("utf-8"))
    if not isinstance(value, dict):
        raise TypeError("Incumbent manifest must be an object")
    if (
        value.get("protocol") != "king_log_absolute_error_development_screen_v1"
        or value.get("status") != "complete"
        or value.get("source_sha256") != SOURCE_SHA256
        or value.get("frozen_rolling_split_sha256") != FROZEN_SPLIT_SHA256
        or value.get("prediction_artifact_sha256") != INCUMBENT_PREDICTION_SHA256
        or not isinstance(value.get("declared_lock_sha256"), str)
        or not isinstance(value.get("window_membership"), dict)
    ):
        raise ValueError("Incumbent manifest metadata is incompatible")
    return value


def verify_incumbent_runtime(manifest: Mapping[str, object]) -> dict[str, str]:
    """Apply the shared lock verifier to the incumbent's named lock field."""
    declared = manifest.get("declared_lock_sha256")
    if not isinstance(declared, str):
        raise ValueError("Incumbent dependency lock identity is missing")
    return verify_runtime_versions({"dependency_lock_sha256": declared})


def read_incumbent_predictions(
    path: Path,
    manifest: Mapping[str, object],
    windows: Sequence[tuple[str, Sequence[Sale], Sequence[Sale]]],
) -> dict[str, tuple[float, ...]]:
    content = read_regular_snapshot(path, MAX_PREDICTION_BYTES, "Incumbent predictions")
    outputs = manifest.get("outputs")
    if (
        hashlib.sha256(content).hexdigest() != INCUMBENT_PREDICTION_SHA256
        or not isinstance(outputs, dict)
        or outputs.get("predictions.csv") != INCUMBENT_PREDICTION_SHA256
    ):
        raise ValueError("Incumbent prediction hash is incompatible")
    expected = tuple((name, sale) for name, _, valid in windows for sale in valid)
    reader = csv.DictReader(io.StringIO(content.decode("utf-8"), newline=""))
    if tuple(reader.fieldnames or ()) != INCUMBENT_COLUMNS:
        raise ValueError("Incumbent prediction schema is incompatible")
    rows = list(reader)
    if len(rows) != len(expected):
        raise ValueError("Incumbent prediction membership is incompatible")
    loaded: dict[str, list[float]] = {name: [] for name, _, _ in windows}
    for row, (name, sale) in zip(rows, expected, strict=True):
        if (
            row["row_id"] != sale.row_id
            or row["sale_date"] != sale.sale_date.isoformat()
            or row["window"] != name
            or Decimal(row["actual_usd"]) != sale.price
        ):
            raise ValueError("Incumbent prediction membership is incompatible")
        prediction = float(row["xgboost_log_absolute_error_usd"])
        if not math.isfinite(prediction) or prediction <= 0:
            raise ValueError("Incumbent prediction is invalid")
        loaded[name].append(prediction)
    return {name: tuple(values) for name, values in loaded.items()}


def encode_feature_family(
    training: Sequence[Sale],
    validation: Sequence[Sale],
    values: Mapping[str, tuple[float, float, float]],
) -> tuple[
    tuple[str, ...], tuple[tuple[float, ...], ...], tuple[tuple[float, ...], ...]
]:
    names, train_base, valid_base = encode_features(training, validation)

    def append(
        rows: Sequence[Sale], base: Sequence[tuple[float, ...]]
    ) -> tuple[tuple[float, ...], ...]:
        try:
            return tuple(
                (*encoded, *values[sale.row_id])
                for sale, encoded in zip(rows, base, strict=True)
            )
        except KeyError as error:
            raise ValueError("Added feature row identity is missing") from error

    return (
        (*names, *ADDED_FEATURES),
        append(training, train_base),
        append(validation, valid_base),
    )


def fit_feature_family(
    training: Sequence[Sale],
    validation: Sequence[Sale],
    values: Mapping[str, tuple[float, float, float]],
) -> tuple[tuple[float, ...], object]:
    import numpy as np
    from xgboost import XGBRegressor

    _, train_rows, valid_rows = encode_feature_family(training, validation, values)
    model = XGBRegressor(**{**MODEL_PARAMETERS, "objective": "reg:absoluteerror"})
    labels = np.log(np.asarray([float(row.price) for row in training], dtype=float))
    model.fit(np.asarray(train_rows, dtype=float), labels)
    predictions = tuple(
        float(value)
        for value in np.exp(model.predict(np.asarray(valid_rows, dtype=float)))
    )
    if len(predictions) != len(validation) or not all(
        math.isfinite(value) and value > 0 for value in predictions
    ):
        raise ValueError("Feature-family model produced invalid predictions")
    return predictions, model


def select_candidate(
    incumbent: Scorecard, challenger: Scorecard, improved_windows: int
) -> str:
    if not 0 <= improved_windows <= 4:
        raise ValueError("Improved-window count must be between zero and four")
    if (
        improved_windows >= 3
        and challenger.mdape <= incumbent.mdape * Decimal("0.98")
        and challenger.within_10 >= incumbent.within_10 - Decimal("0.005")
        and challenger.p90_ape <= incumbent.p90_ape + Decimal("0.005")
    ):
        return "xgboost_log_absolute_error_plus_source_family"
    return "xgboost_log_absolute_error"


def configuration() -> dict[str, object]:
    return {
        "model": {**MODEL_PARAMETERS, "objective": "reg:absoluteerror"},
        "changed_factor": "feature_family",
        "added_features_jointly": list(ADDED_FEATURES),
        "individual_variants": [],
        "future_renovation_policy": "replace_with_xgboost_missing_nan",
        "zero_renovation_policy": "retain_source_zero",
        "fit_count": 4,
        "windows": [
            (name, start.isoformat(), end.isoformat()) for name, start, end in WINDOWS
        ],
    }


def run(source: Path, incumbent_predictions: Path, output: Path) -> dict[str, object]:
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
    manifest = load_incumbent_manifest()
    runtime = verify_incumbent_runtime(manifest)
    source_rows = read_development_source(source)
    eligible, quarantine = select_eligible_sales(tuple(row.sale for row in source_rows))
    windows = monthly_windows(eligible)
    membership = membership_for(windows)
    if membership_sha256(
        membership
    ) != FROZEN_SPLIT_SHA256 or membership != manifest.get("window_membership"):
        raise ValueError("Frozen development membership is incompatible")
    incumbents = read_incumbent_predictions(incumbent_predictions, manifest, windows)
    feature_values = {row.sale.row_id: row.added_values for row in source_rows}
    if len(feature_values) != len(source_rows):
        raise ValueError("Source contains duplicate exact rows")

    predictions_rows: list[tuple[Sale, str, float, float]] = []
    models: dict[str, object] = {}
    window_scores: dict[str, object] = {}
    improved = 0
    for name, training, validation in windows:
        challenger, model = fit_feature_family(training, validation, feature_values)
        incumbent = incumbents[name]
        scores = {
            "xgboost_log_absolute_error": _score(validation, incumbent),
            "xgboost_log_absolute_error_plus_source_family": _score(
                validation, challenger
            ),
        }
        improved += int(
            scores["xgboost_log_absolute_error_plus_source_family"].mdape
            < scores["xgboost_log_absolute_error"].mdape
        )
        window_scores[name] = {
            key: _score_summary(value) for key, value in scores.items()
        }
        models[name] = model
        predictions_rows.extend(
            (sale, name, base, candidate)
            for sale, base, candidate in zip(
                validation, incumbent, challenger, strict=True
            )
        )
    validations = tuple(row[0] for row in predictions_rows)
    pooled = {
        "xgboost_log_absolute_error": _score(
            validations, tuple(row[2] for row in predictions_rows)
        ),
        "xgboost_log_absolute_error_plus_source_family": _score(
            validations, tuple(row[3] for row in predictions_rows)
        ),
    }
    selected = select_candidate(
        pooled["xgboost_log_absolute_error"],
        pooled["xgboost_log_absolute_error_plus_source_family"],
        improved,
    )
    summary = {
        "protocol": PROTOCOL,
        "evidence_class": "retrospective_source_row_development_only",
        "source_rows_parsed": len(source_rows),
        "eligible_rows": len(eligible),
        "quarantine_counts": quarantine,
        "future_renovation_values_replaced": sum(
            row.future_renovation_replaced for row in source_rows
        ),
        "windows": window_scores,
        "pooled": {key: _score_summary(value) for key, value in pooled.items()},
        "improved_windows": improved,
        "development_screening_candidate": selected,
        "fit_count": len(models),
        "march_may_labels_parsed": 0,
        "march_may_rows_scored": 0,
        "promotion_eligible": False,
        "promotion_ineligibility_reason": "feature vintages, publication timing, rights, and transaction eligibility remain unresolved",
        "g_us_gate": "PENDING",
    }
    _write_outputs(
        output, summary, predictions_rows, models, membership, manifest, runtime, commit
    )
    return summary


def _write_outputs(
    output: Path,
    summary: Mapping[str, object],
    rows: Sequence[tuple[Sale, str, float, float]],
    models: Mapping[str, object],
    membership: Mapping[str, object],
    incumbent: Mapping[str, object],
    runtime: Mapping[str, str],
    commit: str,
) -> None:
    with tempfile.TemporaryDirectory(
        dir=PRIVATE_ROOT, prefix="feature-family-"
    ) as directory:
        staging = Path(directory)
        secure_directory(staging)
        with (staging / "predictions.csv").open(
            "w", newline="", encoding="utf-8"
        ) as stream:
            writer = csv.writer(stream)
            writer.writerow(
                (
                    *INCUMBENT_COLUMNS[:4],
                    "xgboost_log_absolute_error_usd",
                    "xgboost_log_absolute_error_plus_source_family_usd",
                )
            )
            for sale, window, base, candidate in rows:
                writer.writerow(
                    (sale.row_id, sale.sale_date, window, sale.price, base, candidate)
                )
        (staging / "scorecards.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
        )
        for name, model in models.items():
            model.save_model(
                staging / f"{name}-xgboost-log-absolute-error-plus-source-family.json"
            )
        outputs = {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in staging.iterdir()
            if path.is_file()
        }
        configured = configuration()
        saved = {
            "run_id": output.name,
            "status": "complete",
            "code_commit": commit,
            "protocol": PROTOCOL,
            "source_sha256": SOURCE_SHA256,
            "dependency_lock_sha256": incumbent["declared_lock_sha256"],
            "runtime_versions": dict(runtime),
            "base_feature_policy_sha256": hashlib.sha256(
                json.dumps(FEATURES, separators=(",", ":")).encode()
            ).hexdigest(),
            "added_features": list(ADDED_FEATURES),
            "window_membership": membership,
            "split_sha256": membership_sha256(membership),
            "incumbent_manifest_sha256": INCUMBENT_MANIFEST_SHA256,
            "incumbent_prediction_sha256": INCUMBENT_PREDICTION_SHA256,
            "configuration": configured,
            "configuration_sha256": hashlib.sha256(
                json.dumps(configured, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest(),
            "fit_count": len(models),
            "outputs": outputs,
            "challenger_checkpoint_identities": {
                name: outputs[
                    f"{name}-xgboost-log-absolute-error-plus-source-family.json"
                ]
                for name in sorted(models)
            },
            "prediction_artifact_sha256": outputs["predictions.csv"],
        }
        (staging / "manifest.json").write_text(
            json.dumps(saved, indent=2, sort_keys=True), encoding="utf-8"
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
    parser.add_argument("--incumbent-predictions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            run(args.source, args.incumbent_predictions, args.output), sort_keys=True
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
