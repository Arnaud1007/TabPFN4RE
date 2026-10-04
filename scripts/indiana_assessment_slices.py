"""Post-hoc error slices for the fixed Indiana development predictions."""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import tempfile
from bisect import bisect_left
from collections import defaultdict
from collections.abc import Sequence
from decimal import Decimal
from pathlib import Path

from scripts.indiana_assessment_diagnostic import (
    OLD_SPLIT_MEMBERSHIP,
    PRIVATE_ROOT,
    PREDICTION_COLUMNS,
    replay_prediction_table,
)
from scripts.indiana_historical_benchmark import Sale, read_archive, split_sales
from scripts.private_review_io import (
    private_path,
    real_directory,
    same_path,
    verify_acl,
)
from scripts.run_indiana_historical_benchmark import (
    ROOT,
    SOURCE_SHA256,
    _clean_commit,
    _digest,
    _membership_hash,
)
from tabpfn4realestate.evaluation.metrics import PredictionRow, score_predictions

PROTOCOL = "indiana_sdf_snapshot_assessment_posthoc_slices_v1"
RUN_DIR = ROOT / "runs/indiana-assessment-diagnostic-v1"
PREDICTION_NAMES = {
    "base_xgboost": "base_xgboost_usd",
    "assessment_xgboost": "assessment_xgboost_usd",
    "zip_county_median": "zip_county_median_usd",
}
METRIC_KEYS = (
    "eligible_count",
    "mdape",
    "within_10",
    "p90_ape",
    "median_signed_percentage_error",
)


def training_quintile_cuts(training: Sequence[Sale]) -> tuple[Decimal, ...]:
    """Use nearest-rank 20/40/60/80 percentiles of 2024 prices only."""
    if (
        not training
        or len({sale.row_id for sale in training}) != len(training)
        or any(sale.sale_date.year != 2024 or sale.price <= 0 for sale in training)
    ):
        raise ValueError("Quintile cutoffs require unique positive 2024 training sales")
    prices = sorted(sale.price for sale in training)
    return tuple(prices[math.ceil(len(prices) * part / 5) - 1] for part in range(1, 5))


def _slice_score(
    rows: Sequence[tuple[Sale, dict[str, str]]], *, minimum_count: int = 1
) -> dict[str, object]:
    if len(rows) < minimum_count:
        return {
            "count": len(rows),
            "scorecards": None,
            "paired_assessment_better_count": None,
        }
    scorecards: dict[str, dict[str, float | int]] = {}
    for name, column in PREDICTION_NAMES.items():
        predictions = [
            PredictionRow(
                row_id=sale.row_id,
                actual=sale.price,
                predicted=Decimal(raw[column]),
                actual_currency="USD",
                predicted_currency="USD",
                status="estimated",
            )
            for sale, raw in rows
        ]
        scored = score_predictions(predictions)
        scorecards[name] = {
            key: float(value) if isinstance(value, Decimal) else value
            for key in METRIC_KEYS
            if (value := getattr(scored, key)) is not None
        }
    better = sum(
        abs(Decimal(raw["assessment_xgboost_usd"]) - sale.price)
        < abs(Decimal(raw["base_xgboost_usd"]) - sale.price)
        for sale, raw in rows
    )
    return {
        "count": len(rows),
        "scorecards": scorecards,
        "paired_assessment_better_count": better,
    }


def analyze_slices(
    training: Sequence[Sale],
    validation: Sequence[Sale],
    predictions_path: Path,
    *,
    min_county: int = 200,
) -> dict[str, object]:
    """Score disjoint diagnostics while retaining the complete 2025 denominator."""
    if min_county < 200:
        raise ValueError("County support floor must be at least 200")
    cuts = training_quintile_cuts(training)
    if (
        not validation
        or len({sale.row_id for sale in validation}) != len(validation)
        or any(sale.sale_date.year != 2025 for sale in validation)
    ):
        raise ValueError("Slices require unique 2025 validation sales")
    saved_scorecards = replay_prediction_table(predictions_path)
    with predictions_path.open("r", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or ()) != PREDICTION_COLUMNS:
            raise ValueError("Saved prediction schema is incompatible")
        raw_rows = list(reader)
    by_id = {sale.row_id: sale for sale in validation}
    if len(raw_rows) != len(validation) or set(by_id) != {
        raw["row_id"] for raw in raw_rows
    }:
        raise ValueError("Saved prediction membership differs from validation")
    rows: list[tuple[Sale, dict[str, str]]] = []
    for raw in raw_rows:
        sale = by_id[raw["row_id"]]
        if (
            Decimal(raw["actual_usd"]) != sale.price
            or raw["sale_date"] != sale.sale_date.isoformat()
        ):
            raise ValueError("Saved prediction actual or date differs from source")
        rows.append((sale, raw))

    overall = _slice_score(rows)
    for name, summary in saved_scorecards.items():
        for key in METRIC_KEYS:
            if summary[key] != overall["scorecards"][name][key]:
                raise ValueError("Saved prediction scorecard replay differs")

    quintile_rows: list[list[tuple[Sale, dict[str, str]]]] = [[] for _ in range(5)]
    county_rows: defaultdict[str, list[tuple[Sale, dict[str, str]]]] = defaultdict(list)
    assessment_rows: dict[str, list[tuple[Sale, dict[str, str]]]] = {
        "both_positive": [],
        "any_zero": [],
        "missing": [],
    }
    for sale, raw in rows:
        quintile_rows[bisect_left(cuts, sale.price)].append((sale, raw))
        county_rows[sale.county_id].append((sale, raw))
        if sale.assessed_land is None or sale.assessed_improvement is None:
            state = "missing"
        elif sale.assessed_land == 0 or sale.assessed_improvement == 0:
            state = "any_zero"
        else:
            state = "both_positive"
        assessment_rows[state].append((sale, raw))

    supported_counties = {
        county: _slice_score(group)
        for county, group in sorted(county_rows.items())
        if len(group) >= min_county
    }
    omitted_counties = [
        group for group in county_rows.values() if len(group) < min_county
    ]
    return {
        "status": "posthoc_development_diagnostic_only",
        "training_price_quintile_cuts_usd": [float(cut) for cut in cuts],
        "quintile_boundary_rule": "nearest_rank_training_prices; ties in lower band",
        "county_minimum_count": min_county,
        "overall": overall,
        "price_quintiles": [
            _slice_score(group, minimum_count=200) for group in quintile_rows
        ],
        "assessment_states": {
            name: _slice_score(group, minimum_count=200)
            for name, group in assessment_rows.items()
        },
        "counties": supported_counties,
        "counties_below_floor": {
            "count": len(omitted_counties),
            "sales": sum(len(group) for group in omitted_counties),
        },
    }


def run_slices(source_2024: Path, source_2025: Path, output: Path) -> dict[str, object]:
    """Hash-check the fixed sources and private predictions before publication."""
    commit = _clean_commit()
    real_directory(RUN_DIR, ROOT / "runs")
    real_directory(output.parent, ROOT / "runs")
    if (
        not same_path(output, RUN_DIR / "slices.json")
        or output.exists()
        or output.is_symlink()
    ):
        raise ValueError("Output must be the new fixed public slice file")
    private_run = PRIVATE_ROOT / "indiana-assessment-diagnostic-v1"
    real_directory(private_run, PRIVATE_ROOT)
    verify_acl(private_run)
    prediction_path = private_path(
        private_run / "predictions.csv", private_run, must_exist=True
    )
    manifest = json.loads(
        (RUN_DIR / "private_artifact_manifest.json").read_text(encoding="utf-8")
    )
    expected = manifest["files"]["predictions.csv"]
    if _digest(prediction_path) != expected:
        raise ValueError("Private prediction checksum differs from the frozen run")
    training, _ = read_archive(source_2024, SOURCE_SHA256[2024], year=2024)
    validation, _ = read_archive(source_2025, SOURCE_SHA256[2025], year=2025)
    split_sales(training, validation)
    memberships = {
        "train": _membership_hash(training),
        "validation": _membership_hash(validation),
    }
    if memberships != OLD_SPLIT_MEMBERSHIP:
        raise ValueError("Slice source membership differs from the fixed benchmark")
    result = {
        **analyze_slices(training, validation, prediction_path),
        "protocol": PROTOCOL,
        "code_commit": commit,
        "source_sha256": SOURCE_SHA256,
        "prediction_sha256": expected,
        "split_membership_sha256": memberships,
        "certified_90_day_origin": False,
        "g_us_gate": "PENDING",
    }
    content = json.dumps(result, indent=2, sort_keys=True) + "\n"
    descriptor, temporary = tempfile.mkstemp(
        prefix=".slices-", suffix=".tmp", dir=RUN_DIR
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        if output.exists() or output.is_symlink():
            raise ValueError("Slice output appeared during publication")
        os.link(temporary, output)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-2024", type=Path, required=True)
    parser.add_argument("--source-2025", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run_slices(args.source_2024, args.source_2025, args.output)
    print(
        json.dumps(
            {
                "overall": result["overall"],
                "counties_scored": len(result["counties"]),
                "counties_below_floor": result["counties_below_floor"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
