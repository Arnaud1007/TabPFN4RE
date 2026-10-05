"""Replay the frozen King predictions with an FHFA metro-level adjustment."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import asdict
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from scripts.king_research_predict import (
    FHFA_CBSA,
    FHFA_GEOGRAPHY,
    FHFA_RELEASE_DATE,
    FHFA_SNAPSHOT_DATE,
)
from tabpfn4realestate.evaluation.metrics import PredictionRow, score_predictions
from tabpfn4realestate.features.fhfa_hpi import load_verified_metro_series

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = "king_fhfa_adjustment_replay_v1"
PREDICTION_SHA256 = "25e64ecca3c83e017124428bc3b37baf0c44d17094b37fa43f0ae667f4151923"
FHFA_SHA256 = "d664a8e2e92f64aa17201b3bdd84d0ab4d1a4d00e9c6c15d5b34fb400c10d842"
PREDICTION_HEADER = (
    "row_id",
    "sale_date",
    "actual_usd",
    "xgboost_usd",
    "zipcode_median_usd",
)
_SHA256 = re.compile(r"[0-9a-f]{64}")


def _verified_bytes(path: Path, expected_sha256: str, limit: int) -> bytes:
    if _SHA256.fullmatch(expected_sha256) is None:
        raise ValueError("Expected checksum is invalid")
    if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
        raise ValueError("Replay input is missing, redirected, or too large")
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != expected_sha256:
        raise ValueError("Replay input checksum mismatch")
    return content


def _decimal(value: str, field: str) -> Decimal:
    try:
        number = Decimal(value)
    except InvalidOperation as error:
        raise ValueError(f"{field} is not numeric") from error
    if not number.is_finite() or number <= 0:
        raise ValueError(f"{field} must be finite and positive")
    return number


def _quarter(value: str) -> str:
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise ValueError("Replay sale date is invalid") from error
    if date(2015, 1, 1) <= parsed <= date(2015, 3, 31):
        return "2015Q1"
    if date(2015, 4, 1) <= parsed <= date(2015, 6, 30):
        return "2015Q2"
    raise ValueError("Replay sale date is outside the supported quarter range")


def _score(rows: tuple[dict[str, str], ...], field: str) -> dict[str, object]:
    score = score_predictions(
        tuple(
            PredictionRow(
                row_id=row["row_id"],
                actual=Decimal(row["actual_usd"]),
                predicted=Decimal(row[field]),
                actual_currency="USD",
                predicted_currency="USD",
                status="estimated",
            )
            for row in rows
        )
    )
    return {
        key: float(value) if isinstance(value, Decimal) else value
        for key, value in asdict(score).items()
    }


def describe_retrospective_change(
    raw: Mapping[str, Decimal], adjusted: Mapping[str, Decimal]
) -> dict[str, object]:
    """Report descriptive deltas without making a selection decision."""
    return {
        "mdape_delta": str(adjusted["mdape"] - raw["mdape"]),
        "within_10_delta": str(adjusted["within_10"] - raw["within_10"]),
        "p90_ape_delta": str(adjusted["p90_ape"] - raw["p90_ape"]),
        "promotion_eligible": False,
        "historical_asof_eligible": False,
        "uses_revised_hindsight": True,
        "applicability_verified": False,
        "cohort_status": "consumed_post_hoc",
        "reason": "Exploratory sensitivity only; requires a new untouched cohort.",
    }


def replay_adjustment(
    *,
    prediction_path: Path,
    expected_prediction_sha256: str,
    hpi_path: Path,
    expected_hpi_sha256: str,
) -> dict[str, object]:
    """Verify both inputs, preserve raw estimates, and score exact-quarter ratios."""
    prediction_content = _verified_bytes(
        prediction_path, expected_prediction_sha256, 2_000_000
    )
    _verified_bytes(hpi_path, expected_hpi_sha256, 2_000_000)
    series = load_verified_metro_series(
        hpi_path,
        expected_sha256=expected_hpi_sha256,
        cbsa_code=FHFA_CBSA,
        geography=FHFA_GEOGRAPHY,
        quarters=("2015Q1", "2015Q2"),
        source_release_date=FHFA_RELEASE_DATE,
        retrieved_at=FHFA_SNAPSHOT_DATE,
    )
    reader = csv.DictReader(prediction_content.decode("utf-8").splitlines())
    if tuple(reader.fieldnames or ()) != PREDICTION_HEADER:
        raise ValueError("King replay prediction schema is incompatible")
    index = {
        item.quarter: Decimal(str(item.index_value)) for item in series.observations
    }
    base = index["2015Q1"]
    seen: set[str] = set()
    rows: list[dict[str, str]] = []
    for source in reader:
        row_id = source["row_id"]
        if not row_id or row_id in seen:
            raise ValueError("Duplicate or empty prediction row ID")
        seen.add(row_id)
        sale_quarter = _quarter(source["sale_date"])
        actual = _decimal(source["actual_usd"], "actual_usd")
        raw = _decimal(source["xgboost_usd"], "xgboost_usd")
        _decimal(source["zipcode_median_usd"], "zipcode_median_usd")
        factor = index[sale_quarter] / base
        adjusted = raw if factor == 1 else (raw * factor).quantize(Decimal("0.01"))
        rows.append(
            {
                **source,
                "actual_usd": str(actual),
                "xgboost_usd": str(raw),
                "sale_quarter": sale_quarter,
                "hpi_factor": str(factor.normalize()),
                "hpi_adjusted_xgboost_usd": str(adjusted),
            }
        )
    if not rows:
        raise ValueError("King replay cohort is empty")
    immutable_rows = tuple(rows)
    scorecards: dict[str, object] = {}
    for cohort in ("overall", "2015Q1", "2015Q2"):
        selected = (
            immutable_rows
            if cohort == "overall"
            else tuple(row for row in immutable_rows if row["sale_quarter"] == cohort)
        )
        if not selected:
            raise ValueError(f"King replay cohort {cohort} is empty")
        scorecards[cohort] = {
            "xgboost": _score(selected, "xgboost_usd"),
            "hpi_adjusted_xgboost": _score(selected, "hpi_adjusted_xgboost_usd"),
        }
    overall = scorecards["overall"]
    raw_metrics = {
        key: Decimal(str(overall["xgboost"][key]))
        for key in ("mdape", "within_10", "p90_ape")
    }
    adjusted_metrics = {
        key: Decimal(str(overall["hpi_adjusted_xgboost"][key]))
        for key in ("mdape", "within_10", "p90_ape")
    }
    return {
        "protocol": PROTOCOL,
        "evidence_class": "retrospective_research_only",
        "input_hashes": {
            "predictions": expected_prediction_sha256,
            "fhfa_hpi": expected_hpi_sha256,
        },
        "rows": list(immutable_rows),
        "scorecards": scorecards,
        "retrospective_change": describe_retrospective_change(
            raw_metrics, adjusted_metrics
        ),
        "historical_asof_eligible": False,
        "uses_revised_hindsight": True,
        "applicability_verified": False,
        "certified_90_day_origin": False,
        "g_us_gate": "PENDING",
    }


def main() -> int:
    result = replay_adjustment(
        prediction_path=ROOT
        / "data/raw/king-benchmark/king-later-2015-v1/later_predictions.csv",
        expected_prediction_sha256=PREDICTION_SHA256,
        hpi_path=ROOT / "data/raw/fhfa/hpi_po_metro_2026-10-05.txt",
        expected_hpi_sha256=FHFA_SHA256,
    )
    print(
        json.dumps(
            {key: value for key, value in result.items() if key != "rows"},
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
