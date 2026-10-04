"""Run one frozen, research-only King County sale-date model comparison."""

from __future__ import annotations

import argparse
import csv
from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Mapping, Sequence

from scripts.king_historical_benchmark import (
    SOURCE_SHA256,
    Sale,
    encode_features,
    read_pinned_source,
    select_eligible_sales,
    split_sales,
)
from scripts.private_review_io import real_directory, secure_directory, verify_acl
from tabpfn4realestate.evaluation.metrics import (
    PredictionRow,
    Scorecard,
    score_predictions,
)

ROOT = Path(__file__).resolve().parents[1]
PRIVATE_ROOT = ROOT / "data/raw/king-benchmark"
PROTOCOL = "king_historical_sale_date_v1"
MODEL_PARAMETERS = {
    "n_estimators": 250,
    "max_depth": 6,
    "learning_rate": 0.05,
    "min_child_weight": 10,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "tree_method": "hist",
    "n_jobs": 4,
    "random_state": 42,
    "objective": "reg:squarederror",
}


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _membership_hash(rows: Sequence[Sale]) -> str:
    return hashlib.sha256(
        ("\n".join(row.row_id for row in rows) + "\n").encode("utf-8")
    ).hexdigest()


def verify_split_manifest(
    splits: Mapping[str, Sequence[Sale]],
    manifest: Mapping[str, object],
    *,
    expected_source_sha256: str,
    quarantine_counts: Mapping[str, int],
) -> None:
    """Reject changed source, eligibility, boundaries or split membership."""
    if (
        manifest.get("protocol") != PROTOCOL
        or manifest.get("source_sha256") != expected_source_sha256
        or manifest.get("boundaries")
        != {
            "train_before": "2015-01-01",
            "validation_before": "2015-03-01",
            "test_from": "2015-03-01",
        }
    ):
        raise ValueError("Frozen split manifest protocol or source changed")
    cohort = manifest.get("cohort_notes")
    if not isinstance(cohort, dict) or cohort.get("eligible_rows") != sum(
        map(len, splits.values())
    ):
        raise ValueError("Frozen split manifest eligible count changed")
    if cohort.get("quarantine_counts") != dict(quarantine_counts):
        raise ValueError("Frozen split manifest quarantine counts changed")
    saved = manifest.get("splits")
    if not isinstance(saved, dict) or set(saved) != {"train", "validation", "test"}:
        raise ValueError("Frozen split manifest roles changed")
    for name in ("train", "validation", "test"):
        expected = saved[name]
        if (
            not isinstance(expected, dict)
            or expected.get("count") != len(splits[name])
            or expected.get("membership_sha256") != _membership_hash(splits[name])
            or not splits[name]
        ):
            raise ValueError(f"Frozen split manifest {name} membership changed")


def baseline_predictions(
    training: Sequence[Sale], queries: Sequence[Sale]
) -> tuple[float, ...]:
    """Zipcode medians with a countywide fallback, fitted on training only."""
    if not training:
        raise ValueError("Baseline requires training sales")
    overall, medians = _baseline_parameters(training)
    return tuple(
        medians.get(str(sale.attributes["zipcode"]), overall) for sale in queries
    )


def _baseline_parameters(training: Sequence[Sale]) -> tuple[float, dict[str, float]]:
    from statistics import median

    overall = float(median(sale.price for sale in training))
    by_zip: dict[str, list[Decimal]] = {}
    for sale in training:
        by_zip.setdefault(str(sale.attributes["zipcode"]), []).append(sale.price)
    return overall, {
        zipcode: float(median(prices)) for zipcode, prices in by_zip.items()
    }


def _committed_code() -> str:
    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=normal"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    if status.stdout.strip():
        raise ValueError("Benchmark requires a clean committed worktree")
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def choose_champion(
    *,
    baseline_mdape: Decimal,
    model_mdape: Decimal,
    baseline_p90: Decimal,
    model_p90: Decimal,
    baseline_within_10: Decimal,
    model_within_10: Decimal,
) -> str:
    """Apply development-only minimum-gain and non-inferiority rules."""
    if (
        model_mdape <= baseline_mdape * Decimal("0.98")
        and model_p90 <= baseline_p90 + Decimal("0.005")
        and model_within_10 >= baseline_within_10 - Decimal("0.005")
    ):
        return "xgboost"
    return "zipcode_median"


def _score(sales: Sequence[Sale], predictions: Sequence[float]) -> Scorecard:
    if len(sales) != len(predictions):
        raise ValueError("Prediction count differs from sale count")
    rows = [
        PredictionRow(
            row_id=sale.row_id,
            actual=sale.price,
            predicted=Decimal(str(prediction)),
            actual_currency="USD",
            predicted_currency="USD",
            status="estimated",
        )
        for sale, prediction in zip(sales, predictions, strict=True)
    ]
    return score_predictions(rows)


def _score_summary(score: Scorecard) -> dict[str, object]:
    values = asdict(score)
    return {
        key: (float(value) if isinstance(value, Decimal) else value)
        for key, value in values.items()
    }


def _fit_predict(
    training: Sequence[Sale], queries: Sequence[Sale]
) -> tuple[tuple[float, ...], object, tuple[str, ...]]:
    import numpy as np
    from xgboost import XGBRegressor

    names, train_rows, query_rows = encode_features(training, queries)
    model = XGBRegressor(**MODEL_PARAMETERS)
    model.fit(
        np.asarray(train_rows, dtype=float),
        np.log(np.asarray([float(sale.price) for sale in training], dtype=float)),
    )
    predictions = tuple(
        float(value)
        for value in np.exp(model.predict(np.asarray(query_rows, dtype=float)))
    )
    if not all(math.isfinite(value) and value > 0 for value in predictions):
        raise ValueError("Model produced an invalid prediction")
    return predictions, model, names


def _write_predictions(
    path: Path,
    sales: Sequence[Sale],
    model_predictions: Sequence[float],
    baseline: Sequence[float],
) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            ("row_id", "sale_date", "actual_usd", "xgboost_usd", "zipcode_median_usd")
        )
        for sale, model_value, baseline_value in zip(
            sales, model_predictions, baseline, strict=True
        ):
            writer.writerow(
                (
                    sale.row_id,
                    sale.sale_date.isoformat(),
                    str(sale.price),
                    model_value,
                    baseline_value,
                )
            )


def run_benchmark(
    source: Path, split_manifest: Path, output: Path
) -> dict[str, object]:
    """Compare fixed candidates on validation; keep the dated test unscored."""
    commit = _committed_code()
    if not PRIVATE_ROOT.exists():
        PRIVATE_ROOT.mkdir(parents=True)
        secure_directory(PRIVATE_ROOT)
    real_directory(PRIVATE_ROOT, PRIVATE_ROOT.parent)
    verify_acl(PRIVATE_ROOT)
    if (
        output.parent.resolve() != PRIVATE_ROOT.resolve()
        or output.exists()
        or output.is_symlink()
    ):
        raise ValueError("Output must be a new private King benchmark directory")
    with split_manifest.open("rb") as stream:
        manifest_bytes = stream.read(100_001)
    if len(manifest_bytes) > 100_000:
        raise ValueError("Frozen split manifest exceeds size limit")
    frozen = json.loads(manifest_bytes.decode("utf-8"))
    split_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    sales = read_pinned_source(source)
    eligible, quarantine = select_eligible_sales(sales)
    splits = split_sales(eligible)
    verify_split_manifest(
        splits,
        frozen,
        expected_source_sha256=SOURCE_SHA256,
        quarantine_counts=quarantine,
    )
    train, validation = splits["train"], splits["validation"]

    val_baseline = baseline_predictions(train, validation)
    val_model, model, feature_names = _fit_predict(train, validation)
    baseline_score = _score(validation, val_baseline)
    model_score = _score(validation, val_model)
    champion = choose_champion(
        baseline_mdape=baseline_score.mdape,
        model_mdape=model_score.mdape,
        baseline_p90=baseline_score.p90_ape,
        model_p90=model_score.p90_ape,
        baseline_within_10=baseline_score.within_10,
        model_within_10=model_score.within_10,
    )

    summary = {
        "protocol": PROTOCOL,
        "evidence_class": "historical_sale_date_research_only",
        "candidate_selected_on_validation": champion,
        "source_rows": len(sales),
        "eligible_rows": len(eligible),
        "quarantine_counts": quarantine,
        "train_rows": len(train),
        "validation_rows": len(validation),
        "test_rows_frozen_not_scored": len(splits["test"]),
        "validation": {
            "zipcode_median": _score_summary(baseline_score),
            "xgboost": _score_summary(model_score),
        },
        "test_status": "not_scored",
        "certified_90_day_origin": False,
        "g_us_gate": "PENDING",
    }
    with tempfile.TemporaryDirectory(dir=PRIVATE_ROOT, prefix="staging-") as directory:
        staging = Path(directory)
        secure_directory(staging)
        real_directory(staging, PRIVATE_ROOT)
        _write_predictions(
            staging / "validation_predictions.csv", validation, val_model, val_baseline
        )
        model.save_model(staging / "xgboost_model.json")
        overall, medians = _baseline_parameters(train)
        (staging / "zipcode_median.json").write_text(
            json.dumps({"overall": overall, "zipcodes": medians}, sort_keys=True),
            encoding="utf-8",
        )
        selected_artifact = (
            "xgboost_model.json" if champion == "xgboost" else "zipcode_median.json"
        )
        (staging / "candidate.json").write_text(
            json.dumps(
                {"selected_on_validation": champion, "artifact": selected_artifact},
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        (staging / "feature_names.json").write_text(
            json.dumps(feature_names), encoding="utf-8"
        )
        (staging / "scorecards.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
        )
        manifest = {
            "run_id": output.name,
            "code_commit": commit,
            "source_sha256": SOURCE_SHA256,
            "split_manifest_sha256": split_sha256,
            "dependency_lock_sha256": _digest(
                ROOT / "locks/ames-prototype-requirements.txt"
            ),
            "configuration_sha256": hashlib.sha256(
                json.dumps(MODEL_PARAMETERS, sort_keys=True).encode()
            ).hexdigest(),
            "checkpoint_identity": _digest(staging / selected_artifact),
            "selected_candidate": champion,
            "feature_policy_sha256": hashlib.sha256(
                json.dumps(feature_names).encode()
            ).hexdigest(),
            "outputs": {
                path.name: _digest(path) for path in staging.iterdir() if path.is_file()
            },
            "status": "validation_complete_test_unscored",
            "scope": "historical_research_only",
            "created_at_utc": datetime.now(UTC).isoformat(),
        }
        (staging / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
        )
        os.replace(staging, output)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--split-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run_benchmark(args.source, args.split_manifest, args.output)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
