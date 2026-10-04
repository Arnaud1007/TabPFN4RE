"""Fixed research comparison of Indiana disclosure-snapshot assessments.

Assessment fields occur in the retrieved sale-disclosure snapshot. Their
historical vintage and availability at a 90-day pre-sale origin are unknown.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import tempfile
from collections.abc import Sequence
from dataclasses import asdict
from datetime import date
from decimal import Decimal
from pathlib import Path
from time import perf_counter

from scripts.indiana_historical_benchmark import (
    ASSESSMENT_FEATURES,
    MODEL_FEATURES,
    Sale,
    encode_assessment_features,
    encode_features,
    read_archive,
    split_sales,
)
from scripts.private_review_io import (
    real_directory,
    same_path,
    secure_directory,
    verify_acl,
)
from scripts.run_indiana_historical_benchmark import (
    MODEL_PARAMETERS,
    PRIVATE_ROOT,
    ROOT,
    SOURCE_SHA256,
    _clean_commit,
    _digest,
    _json_hash,
    _membership_hash,
    baseline_predictions,
)
from tabpfn4realestate.evaluation.metrics import PredictionRow, score_predictions

PROTOCOL = "indiana_sdf_snapshot_assessment_retrospective_diagnostic_v1"
OLD_SPLIT_MEMBERSHIP = {
    "train": "1c6ab9e720a5b6ef0e1e7032ad326e45a8bf5ee77eb5c57d072a1a5483665dae",
    "validation": "2f2b37e186eb5eb97d1609041b17fc8ec7f6a56813667b7e59f2974a505d97b9",
}
PREDICTION_COLUMNS = (
    "row_id",
    "sale_date",
    "actual_usd",
    "base_xgboost_usd",
    "assessment_xgboost_usd",
    "zip_county_median_usd",
)


def write_prediction_table(
    path: Path,
    sales: Sequence[Sale],
    *,
    base: Sequence[float],
    assessment: Sequence[float],
    median: Sequence[float],
) -> None:
    """Save row-aligned predictions, rejecting partial or invalid outputs."""
    if any(
        len(predictions) != len(sales) for predictions in (base, assessment, median)
    ):
        raise ValueError("Prediction count differs from validation count")
    if len({sale.row_id for sale in sales}) != len(sales):
        raise ValueError("Prediction rows contain duplicate economic sales")
    if any(
        not math.isfinite(value) or value <= 0
        for predictions in (base, assessment, median)
        for value in predictions
    ):
        raise ValueError("Prediction amount must be positive and finite")
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(PREDICTION_COLUMNS)
        for sale, base_value, assessment_value, median_value in zip(
            sales, base, assessment, median, strict=True
        ):
            writer.writerow(
                (
                    sale.row_id,
                    sale.sale_date.isoformat(),
                    sale.price,
                    base_value,
                    assessment_value,
                    median_value,
                )
            )


def replay_prediction_table(path: Path) -> dict[str, dict[str, object]]:
    """Compute scorecards only from the saved paired prediction rows."""
    with path.open("r", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or ()) != PREDICTION_COLUMNS:
            raise ValueError("Saved prediction schema is incompatible")
        rows = list(reader)
    if not rows or len({row["row_id"] for row in rows}) != len(rows):
        raise ValueError("Saved prediction rows are empty or duplicate")
    for row in rows:
        if None in row or any(value is None or value == "" for value in row.values()):
            raise ValueError("Saved prediction row is malformed")
        try:
            sale_date = date.fromisoformat(row["sale_date"])
        except ValueError as error:
            raise ValueError("Saved prediction sale date is invalid") from error
        if sale_date.year != 2025 or sale_date.isoformat() != row["sale_date"]:
            raise ValueError("Saved prediction sale date is outside the protocol")
    summaries: dict[str, dict[str, object]] = {}
    for name, column in (
        ("base_xgboost", "base_xgboost_usd"),
        ("assessment_xgboost", "assessment_xgboost_usd"),
        ("zip_county_median", "zip_county_median_usd"),
    ):
        predictions = [
            PredictionRow(
                row_id=row["row_id"],
                actual=Decimal(row["actual_usd"]),
                predicted=Decimal(row[column]),
                actual_currency="USD",
                predicted_currency="USD",
                status="estimated",
            )
            for row in rows
        ]
        score = asdict(score_predictions(predictions))
        summaries[name] = {
            key: float(value) if isinstance(value, Decimal) else value
            for key, value in score.items()
        }
    return summaries


def _assessment_quality(rows: Sequence[Sale]) -> dict[str, int]:
    return {
        "land_av_missing": sum(sale.assessed_land is None for sale in rows),
        "improvement_av_missing": sum(
            sale.assessed_improvement is None for sale in rows
        ),
        "neighborhood_missing": sum(sale.neighborhood_code is None for sale in rows),
        "land_av_zero": sum(sale.assessed_land == 0 for sale in rows),
        "improvement_av_zero": sum(sale.assessed_improvement == 0 for sale in rows),
    }


def _validated_output_path(output: Path) -> Path:
    """Require a new direct child of the private benchmark directory."""
    if ".." in output.parts:
        raise ValueError("Output must be a new private Indiana benchmark directory")
    path = output.absolute()
    if (
        not same_path(path.parent, PRIVATE_ROOT)
        or path.exists()
        or path.is_symlink()
        or not same_path(path, path.resolve(strict=False))
    ):
        raise ValueError("Output must be a new private Indiana benchmark directory")
    return path


def run_diagnostic(source_2024: Path, source_2025: Path, output: Path) -> dict:
    """Fit paired models once on the already-consumed development cohort."""
    import numpy as np
    from xgboost import XGBRegressor

    commit = _clean_commit()
    PRIVATE_ROOT.mkdir(parents=True, exist_ok=True)
    real_directory(PRIVATE_ROOT, PRIVATE_ROOT.parent)
    secure_directory(PRIVATE_ROOT)
    verify_acl(PRIVATE_ROOT)
    output = _validated_output_path(output)

    started = perf_counter()
    training, training_funnel = read_archive(
        source_2024, SOURCE_SHA256[2024], year=2024
    )
    validation, validation_funnel = read_archive(
        source_2025, SOURCE_SHA256[2025], year=2025
    )
    split_sales(training, validation)
    memberships = {
        "train": _membership_hash(training),
        "validation": _membership_hash(validation),
    }
    if memberships != OLD_SPLIT_MEMBERSHIP:
        raise ValueError("Assessment diagnostic cohort differs from the fixed baseline")

    base_names, base_train, base_validation = encode_features(training, validation)
    assessment_names, assessment_train, assessment_validation = (
        encode_assessment_features(training, validation)
    )
    historical_median = baseline_predictions(training, validation)
    log_prices = np.log([float(sale.price) for sale in training])
    base_model = XGBRegressor(**MODEL_PARAMETERS)
    assessment_model = XGBRegressor(**MODEL_PARAMETERS)
    fit_started = perf_counter()
    base_model.fit(base_train, log_prices)
    base_fit_seconds = perf_counter() - fit_started
    fit_started = perf_counter()
    assessment_model.fit(assessment_train, log_prices)
    assessment_fit_seconds = perf_counter() - fit_started
    base_predictions = tuple(
        float(p) for p in np.exp(base_model.predict(base_validation))
    )
    assessment_predictions = tuple(
        float(p) for p in np.exp(assessment_model.predict(assessment_validation))
    )

    scratch = Path(
        tempfile.mkdtemp(prefix="indiana-assessment-incomplete-", dir=PRIVATE_ROOT)
    )
    secure_directory(scratch)
    predictions_path = scratch / "predictions.csv"
    write_prediction_table(
        predictions_path,
        validation,
        base=base_predictions,
        assessment=assessment_predictions,
        median=historical_median,
    )
    scorecards = replay_prediction_table(predictions_path)
    if any(card["eligible_count"] != len(validation) for card in scorecards.values()):
        raise ValueError("Paired scorecard denominator differs from validation cohort")
    base_model.save_model(scratch / "base_model.json")
    assessment_model.save_model(scratch / "assessment_model.json")
    (scratch / "base_feature_names.json").write_text(
        json.dumps(base_names, indent=2) + "\n", encoding="utf-8"
    )
    (scratch / "assessment_feature_names.json").write_text(
        json.dumps(assessment_names, indent=2) + "\n", encoding="utf-8"
    )
    feature_policy = {
        "base_raw_features": MODEL_FEATURES,
        "assessment_raw_features": ASSESSMENT_FEATURES,
        "assessment_values": "whole-dollar 12.0, log1p, separate missing indicators",
        "neighborhood": "county-scoped, train-only DictVectorizer",
        "available_at_90_day_origin": "unknown; retrospective diagnostic only",
    }
    summary = {
        "run_id": output.name,
        "protocol": PROTOCOL,
        "status": "retrospective_sale_disclosure_snapshot_diagnostic",
        "certified_90_day_origin": False,
        "g_us_gate": "PENDING",
        "code_commit": commit,
        "environment_lock_sha256": _digest(
            ROOT / "locks/ames-prototype-requirements.txt"
        ),
        "source_sha256": SOURCE_SHA256,
        "data_snapshot_sha256": _json_hash(SOURCE_SHA256),
        "split_membership_sha256": memberships,
        "split_sha256": _json_hash(memberships),
        "training_count": len(training),
        "validation_count": len(validation),
        "training_funnel": training_funnel,
        "validation_funnel": validation_funnel,
        "training_assessment_quality": _assessment_quality(training),
        "validation_assessment_quality": _assessment_quality(validation),
        "feature_policy_sha256": _json_hash(feature_policy),
        "base_encoded_feature_count": len(base_names),
        "assessment_encoded_feature_count": len(assessment_names),
        "model_parameters": MODEL_PARAMETERS,
        "configuration_sha256": _json_hash(MODEL_PARAMETERS),
        "base_checkpoint_sha256": _digest(scratch / "base_model.json"),
        "assessment_checkpoint_sha256": _digest(scratch / "assessment_model.json"),
        "scorecards": scorecards,
        "base_fit_seconds": base_fit_seconds,
        "assessment_fit_seconds": assessment_fit_seconds,
        "elapsed_seconds": perf_counter() - started,
    }
    (scratch / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    manifest = {
        "protocol": PROTOCOL,
        "code_commit": commit,
        "files": {
            path.name: _digest(path) for path in scratch.iterdir() if path.is_file()
        },
    }
    (scratch / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    _validated_output_path(output)
    scratch.rename(output)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-2024", type=Path, required=True)
    parser.add_argument("--source-2025", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    summary = run_diagnostic(args.source_2024, args.source_2025, args.output)
    print(
        json.dumps(
            {
                "status": summary["status"],
                "training_count": summary["training_count"],
                "validation_count": summary["validation_count"],
                "scorecards": summary["scorecards"],
                "elapsed_seconds": summary["elapsed_seconds"],
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
