"""One fixed, research-only Indiana 2024-to-2025 price comparison."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import subprocess
import tempfile
from collections.abc import Sequence
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
from time import perf_counter

from scripts.indiana_historical_benchmark import (
    ADDITIONAL_SPECIAL_FLAGS,
    MODEL_FEATURES,
    ONE_FAMILY_CODES,
    SPECIAL_FLAGS,
    Sale,
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
from tabpfn4realestate.evaluation.metrics import PredictionRow, score_predictions

ROOT = Path(__file__).resolve().parents[1]
PRIVATE_ROOT = ROOT / "data/raw/indiana_sdf/benchmarks"
PROTOCOL = "indiana_sdf_2024_2025_retrospective_research_v1"
SOURCE_SHA256 = {
    2024: "a208f5b7230c0e5a0a5b74217a8b37e7d175e12cce59f122ffe2369a548bf6bd",
    2025: "f574f75604c953a1c0e498550ea05a20ebf705e8dfaca9aa1090d7a358ee4e12",
}
MODEL_PARAMETERS = {
    "n_estimators": 180,
    "max_depth": 5,
    "learning_rate": 0.08,
    "min_child_weight": 20,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "tree_method": "hist",
    "n_jobs": 4,
    "random_state": 42,
    "objective": "reg:squarederror",
}


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _membership_hash(rows: Sequence[Sale]) -> str:
    return hashlib.sha256(
        ("\n".join(sale.row_id for sale in rows) + "\n").encode("utf-8")
    ).hexdigest()


def _json_hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _quality_flags(rows: Sequence[Sale]) -> dict[str, int | str]:
    """Describe source extremes without removing them from the score."""
    return {
        "price_below_10000_usd": sum(sale.price < 10_000 for sale in rows),
        "price_above_10000000_usd": sum(sale.price > 10_000_000 for sale in rows),
        "acreage_above_100": sum(
            sale.acreage is not None and sale.acreage > 100 for sale in rows
        ),
        "acreage_missing": sum(sale.acreage is None for sale in rows),
        "minimum_price_usd": str(min(sale.price for sale in rows)),
        "maximum_price_usd": str(max(sale.price for sale in rows)),
    }


def _clean_commit() -> str:
    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=normal"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    if status.stdout.strip():
        raise ValueError("Indiana benchmark requires a clean committed worktree")
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def baseline_predictions(
    training: Sequence[Sale], validation: Sequence[Sale], *, min_zip_sales: int = 20
) -> tuple[float, ...]:
    """Use past ZIP/county medians with county and statewide fallbacks."""
    from statistics import median

    if not training or min_zip_sales < 1:
        raise ValueError("Baseline needs training rows and a positive support floor")
    by_zip: dict[tuple[str, str], list[Decimal]] = {}
    by_county: dict[str, list[Decimal]] = {}
    for sale in training:
        by_zip.setdefault((sale.county_id, sale.zipcode), []).append(sale.price)
        by_county.setdefault(sale.county_id, []).append(sale.price)
    zip_medians = {
        key: float(median(prices))
        for key, prices in by_zip.items()
        if len(prices) >= min_zip_sales
    }
    county_medians = {key: float(median(prices)) for key, prices in by_county.items()}
    statewide = float(median(sale.price for sale in training))
    return tuple(
        zip_medians.get(
            (sale.county_id, sale.zipcode),
            county_medians.get(sale.county_id, statewide),
        )
        for sale in validation
    )


def write_predictions(
    path: Path, sales: Sequence[Sale], model: Sequence[float], baseline: Sequence[float]
) -> None:
    if len(sales) != len(model) or len(sales) != len(baseline):
        raise ValueError("Prediction count differs from validation count")
    if len({sale.row_id for sale in sales}) != len(sales):
        raise ValueError("Prediction rows contain duplicate economic sales")
    if any(not math.isfinite(value) or value <= 0 for value in (*model, *baseline)):
        raise ValueError("Prediction amount must be positive and finite")
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            (
                "row_id",
                "sale_date",
                "actual_usd",
                "xgboost_usd",
                "zip_county_median_usd",
            )
        )
        for sale, model_value, baseline_value in zip(
            sales, model, baseline, strict=True
        ):
            writer.writerow(
                (
                    sale.row_id,
                    sale.sale_date.isoformat(),
                    sale.price,
                    model_value,
                    baseline_value,
                )
            )


def replay_predictions(path: Path) -> dict[str, dict[str, float | int | str | None]]:
    """Generate every reported metric from the saved private row predictions."""
    with path.open("r", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        expected = (
            "row_id",
            "sale_date",
            "actual_usd",
            "xgboost_usd",
            "zip_county_median_usd",
        )
        if tuple(reader.fieldnames or ()) != expected:
            raise ValueError("Saved prediction schema is incompatible")
        rows = list(reader)
    summaries: dict[str, dict[str, float | int | str | None]] = {}
    for name, column in (
        ("xgboost", "xgboost_usd"),
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


def run_benchmark(source_2024: Path, source_2025: Path, output: Path) -> dict:
    """Fit once; score all eligible 2025 sales as retrospective research."""
    import numpy as np
    from xgboost import XGBRegressor

    commit = _clean_commit()
    PRIVATE_ROOT.mkdir(parents=True, exist_ok=True)
    real_directory(PRIVATE_ROOT, PRIVATE_ROOT.parent)
    secure_directory(PRIVATE_ROOT)
    verify_acl(PRIVATE_ROOT)
    if (
        not same_path(output.parent, PRIVATE_ROOT)
        or output.exists()
        or output.is_symlink()
    ):
        raise ValueError("Output must be a new private Indiana benchmark directory")
    started = perf_counter()
    training, training_funnel = read_archive(
        source_2024, SOURCE_SHA256[2024], year=2024
    )
    validation, validation_funnel = read_archive(
        source_2025, SOURCE_SHA256[2025], year=2025
    )
    split_sales(training, validation)
    names, train_matrix, validation_matrix = encode_features(training, validation)
    baseline = baseline_predictions(training, validation)
    model = XGBRegressor(**MODEL_PARAMETERS)
    model.fit(train_matrix, np.log([float(sale.price) for sale in training]))
    predictions = tuple(
        float(value) for value in np.exp(model.predict(validation_matrix))
    )
    if len(predictions) != len(validation):
        raise ValueError("Model prediction count changed")

    scratch = Path(tempfile.mkdtemp(prefix="indiana-incomplete-", dir=PRIVATE_ROOT))
    secure_directory(scratch)
    prediction_path = scratch / "predictions.csv"
    write_predictions(prediction_path, validation, predictions, baseline)
    scorecards = replay_predictions(prediction_path)
    if any(card["eligible_count"] != len(validation) for card in scorecards.values()):
        raise ValueError("Saved scorecard denominator differs from validation cohort")
    model.save_model(scratch / "model.json")
    (scratch / "feature_names.json").write_text(
        json.dumps(names, indent=2) + "\n", encoding="utf-8"
    )
    split_memberships = {
        "train": _membership_hash(training),
        "validation": _membership_hash(validation),
    }
    feature_policy = {
        "raw_features": MODEL_FEATURES,
        "one_family_codes": sorted(ONE_FAMILY_CODES),
        "required_no_special_flags": SPECIAL_FLAGS,
        "additional_special_flags": ADDITIONAL_SPECIAL_FLAGS,
        "acreage_transform": "log1p_with_missing_indicator",
        "categorical_encoding": "train_only_DictVectorizer",
    }
    summary = {
        "run_id": output.name,
        "protocol": PROTOCOL,
        "status": "retrospective_research_only",
        "certified_90_day_origin": False,
        "code_commit": commit,
        "environment_lock_sha256": _digest(
            ROOT / "locks/ames-prototype-requirements.txt"
        ),
        "source_sha256": SOURCE_SHA256,
        "data_snapshot_sha256": _json_hash(SOURCE_SHA256),
        "training_count": len(training),
        "validation_count": len(validation),
        "split_membership_sha256": split_memberships,
        "split_sha256": _json_hash(split_memberships),
        "raw_feature_allowlist": MODEL_FEATURES,
        "feature_policy_sha256": _json_hash(feature_policy),
        "encoded_feature_count": len(names),
        "model_parameters": MODEL_PARAMETERS,
        "configuration_sha256": _json_hash(MODEL_PARAMETERS),
        "checkpoint_sha256": _digest(scratch / "model.json"),
        "training_funnel": training_funnel,
        "validation_funnel": validation_funnel,
        "training_quality_flags": _quality_flags(training),
        "validation_quality_flags": _quality_flags(validation),
        "scorecards": scorecards,
        "elapsed_seconds": perf_counter() - started,
    }
    (scratch / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    manifest = {
        "protocol": PROTOCOL,
        "code_commit": commit,
        "files": {
            name: _digest(scratch / name)
            for name in (
                "predictions.csv",
                "model.json",
                "feature_names.json",
                "summary.json",
            )
        },
    }
    (scratch / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    scratch.replace(output)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-2024", type=Path, required=True)
    parser.add_argument("--source-2025", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    summary = run_benchmark(args.source_2024, args.source_2025, args.output)
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
