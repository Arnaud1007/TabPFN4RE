"""Run the frozen King comparable-residual development experiment."""

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
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

from scripts.king_historical_benchmark import (
    COLUMNS,
    FEATURES,
    SOURCE_SHA256,
    Sale,
    _decode_source,
    _locate_data,
    _parse_sale,
    select_eligible_sales,
)
from scripts.private_review_io import real_directory, secure_directory, verify_acl
from scripts.run_king_historical_benchmark import (
    MODEL_PARAMETERS,
    PRIVATE_ROOT,
    ROOT,
    _committed_code,
    _score,
    _score_summary,
)
from scripts.run_king_rolling_development import (
    WINDOW_STARTS,
    _fit_predict,
    monthly_windows,
)

PROTOCOL = "king_exploratory_partial_comparable_residual_screen_v1"
FROZEN_MANIFEST = ROOT / "runs/king-rolling-development-20261005-v1/manifest.json"
DECLARED_LOCK = ROOT / "locks/ames-prototype-requirements.txt"
DEVELOPMENT_END = date(2015, 3, 1)
RADII_KM = (2.0, 10.0, 30.0)
NEIGHBORS = 10
MIN_SUPPORT = 3
EARTH_RADIUS_KM = 6371.0088


@dataclass(frozen=True)
class ComparableIndex:
    cutoff: date
    sales: tuple[Sale, ...]
    residuals: tuple[float, ...]
    unit_coordinates: object
    tree: object


@dataclass(frozen=True)
class Retrieval:
    row_ids: tuple[str, ...]
    residuals: tuple[float, ...]
    weights: tuple[float, ...]
    radius_km: float
    support: str


@dataclass(frozen=True)
class CorrectedPrediction:
    prediction: float
    support: str
    comparable_count: int
    radius_km: float
    row_ids: tuple[str, ...]


def read_development_source(path: Path) -> tuple[Sale, ...]:
    """Parse only pre-March rows while still verifying the complete pinned file."""
    lines = _decode_source(path, SOURCE_SHA256)
    marker = _locate_data(lines)
    parsed: list[Sale] = []
    observed_rows = 0
    for raw_line in lines[marker + 1 :]:
        if not raw_line.strip() or raw_line.lstrip().startswith("%"):
            continue
        observed_rows += 1
        values = next(csv.reader(io.StringIO(raw_line)))
        if len(values) != len(COLUMNS):
            raise ValueError("Source row has an incompatible column count")
        raw_date = values[1]
        if raw_date < "20150301T000000":
            parsed.append(_parse_sale(values, raw_line))
    if observed_rows != 21_613:
        raise ValueError("Source row count does not match expected row count")
    return tuple(parsed)


def _unit_coordinate(latitude: float, longitude: float) -> tuple[float, float, float]:
    latitude_radians = math.radians(latitude)
    longitude_radians = math.radians(longitude)
    cosine = math.cos(latitude_radians)
    return (
        cosine * math.cos(longitude_radians),
        cosine * math.sin(longitude_radians),
        math.sin(latitude_radians),
    )


def _candidate_is_valid(item: Sale, cutoff: date) -> bool:
    attributes = item.attributes
    area = float(attributes.get("sqft_living", 0))
    latitude = float(attributes.get("lat", math.nan))
    longitude = float(attributes.get("long", math.nan))
    return (
        cutoff.replace(year=cutoff.year - 1) <= item.sale_date < cutoff
        and math.isfinite(area)
        and area > 0
        and math.isfinite(latitude)
        and math.isfinite(longitude)
        and -90 <= latitude <= 90
        and -180 <= longitude <= 180
    )


def build_index(
    candidates: Sequence[Sale], residual_by_row: Mapping[str, float], *, cutoff: date
) -> ComparableIndex:
    """Build a deterministic index using the latest eligible sale per property."""
    import numpy as np
    from scipy.spatial import cKDTree

    latest: dict[str, Sale] = {}
    for item in candidates:
        if item.row_id not in residual_by_row or not _candidate_is_valid(item, cutoff):
            continue
        previous = latest.get(item.property_id)
        if previous is None or (item.sale_date, item.row_id) > (
            previous.sale_date,
            previous.row_id,
        ):
            latest[item.property_id] = item
    sales = tuple(sorted(latest.values(), key=lambda item: item.row_id))
    try:
        residuals = tuple(float(residual_by_row[item.row_id]) for item in sales)
    except KeyError as error:
        raise ValueError(
            "Every comparable candidate needs a base-model residual"
        ) from error
    if not all(math.isfinite(value) for value in residuals):
        raise ValueError("Comparable residuals must be finite")
    coordinates = np.asarray(
        [
            _unit_coordinate(
                float(item.attributes["lat"]), float(item.attributes["long"])
            )
            for item in sales
        ],
        dtype=float,
    ).reshape((-1, 3))
    tree = cKDTree(coordinates) if sales else None
    return ComparableIndex(cutoff, sales, residuals, coordinates, tree)


def _distance_km(first: object, second: object) -> float:
    import numpy as np

    chord = float(np.linalg.norm(first - second))
    return 2 * EARTH_RADIUS_KM * math.asin(min(1.0, chord / 2))


def retrieve(index: ComparableIndex, subject: Sale) -> Retrieval:
    """Retrieve target-blind comparable rows under the frozen configuration."""
    import numpy as np

    if index.tree is None:
        return Retrieval((), (), (), RADII_KM[-1], "low_support")
    subject_area = float(subject.attributes.get("sqft_living", 0))
    latitude = float(subject.attributes.get("lat", math.nan))
    longitude = float(subject.attributes.get("long", math.nan))
    if (
        subject_area <= 0
        or not math.isfinite(subject_area)
        or not math.isfinite(latitude)
        or not math.isfinite(longitude)
        or not -90 <= latitude <= 90
        or not -180 <= longitude <= 180
    ):
        return Retrieval((), (), (), RADII_KM[-1], "low_support")
    coordinate = np.asarray(_unit_coordinate(latitude, longitude), dtype=float)
    selected: list[tuple[float, str, int, float]] = []
    radius_used = RADII_KM[-1]
    for radius in RADII_KM:
        chord_radius = 2 * math.sin(radius / (2 * EARTH_RADIUS_KM))
        positions = index.tree.query_ball_point(coordinate, chord_radius)
        ranked = []
        for position in positions:
            candidate = index.sales[position]
            if candidate.property_id == subject.property_id:
                continue
            distance = _distance_km(index.unit_coordinates[position], coordinate)
            age_days = (index.cutoff - candidate.sale_date).days
            area_ratio = abs(
                math.log(float(candidate.attributes["sqft_living"]) / subject_area)
            )
            score = distance + age_days / 365 + area_ratio / 0.25
            ranked.append((score, candidate.row_id, position, 1 / (1 + score)))
        selected = sorted(ranked)[:NEIGHBORS]
        radius_used = radius
        if len(selected) >= MIN_SUPPORT:
            break
    support = "supported" if len(selected) >= MIN_SUPPORT else "low_support"
    return Retrieval(
        tuple(item[1] for item in selected),
        tuple(index.residuals[item[2]] for item in selected),
        tuple(item[3] for item in selected),
        radius_used,
        support,
    )


def _weighted_median(values: Sequence[float], weights: Sequence[float]) -> float:
    ordered = sorted(zip(values, weights, strict=True), key=lambda item: item[0])
    threshold = sum(weights) / 2
    cumulative = 0.0
    for value, weight in ordered:
        cumulative += weight
        if cumulative >= threshold:
            return value
    raise ValueError("Weighted median requires positive observations")


def correct_prediction(
    subject: Sale, incumbent: float, index: ComparableIndex
) -> CorrectedPrediction:
    match = retrieve(index, subject)
    if match.support == "low_support":
        return CorrectedPrediction(
            float(incumbent),
            match.support,
            len(match.row_ids),
            match.radius_km,
            match.row_ids,
        )
    residual = _weighted_median(match.residuals, match.weights)
    prediction = math.exp(math.log(float(incumbent)) + residual)
    if not math.isfinite(prediction) or prediction <= 0:
        raise ValueError("Comparable correction produced an invalid prediction")
    return CorrectedPrediction(
        prediction, match.support, len(match.row_ids), match.radius_km, match.row_ids
    )


def membership_for(
    windows: Sequence[tuple[str, Sequence[Sale], Sequence[Sale]]],
) -> dict[str, dict[str, int | str]]:
    return {
        name: {
            "training_count": len(training),
            "training_sha256": hashlib.sha256(
                ("\n".join(item.row_id for item in training) + "\n").encode()
            ).hexdigest(),
            "validation_count": len(validation),
            "validation_sha256": hashlib.sha256(
                ("\n".join(item.row_id for item in validation) + "\n").encode()
            ).hexdigest(),
        }
        for name, training, validation in windows
    }


def _membership_sha256(membership: Mapping[str, object]) -> str:
    return hashlib.sha256(
        json.dumps(membership, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def verify_frozen_membership(
    actual: Mapping[str, object], frozen: Mapping[str, object]
) -> None:
    if frozen.get("source_sha256") != SOURCE_SHA256:
        raise ValueError("Frozen rolling source does not match the pinned source")
    if (
        frozen.get("run_id") != "king-rolling-development-20261005-v1"
        or frozen.get("protocol") != "king_rolling_development_v1"
        or frozen.get("status") != "complete"
    ):
        raise ValueError("Frozen rolling manifest identity is incompatible")
    if actual != frozen.get("window_membership"):
        raise ValueError("Current rows do not match frozen rolling membership")
    if frozen.get("split_sha256") != _membership_sha256(actual):
        raise ValueError("Frozen rolling split hash is incompatible")


def screen_candidate(
    *,
    incumbent_mdape: Decimal,
    challenger_mdape: Decimal,
    incumbent_within_10: Decimal,
    challenger_within_10: Decimal,
    incumbent_p90: Decimal,
    challenger_p90: Decimal,
    improved_windows: int,
    valid_predictions: bool,
) -> str:
    if not 0 <= improved_windows <= 4:
        raise ValueError("Improved-window count must be between zero and four")
    if (
        valid_predictions
        and improved_windows >= 3
        and challenger_mdape <= incumbent_mdape * Decimal("0.98")
        and challenger_within_10 >= incumbent_within_10 - Decimal("0.005")
        and challenger_p90 <= incumbent_p90 + Decimal("0.005")
    ):
        return "xgboost_comparable_residual"
    return "xgboost"


def _runtime_versions() -> dict[str, str]:
    import numpy
    import scipy
    import xgboost

    return {
        "python": platform.python_version(),
        "numpy": numpy.__version__,
        "scipy": scipy.__version__,
        "xgboost": xgboost.__version__,
        "platform": platform.platform(),
        "machine": platform.machine(),
    }


def _configuration() -> dict[str, object]:
    return {
        "model": MODEL_PARAMETERS,
        "neighbors": NEIGHBORS,
        "minimum_support": MIN_SUPPORT,
        "radii_km": RADII_KM,
        "sale_window_months": 12,
        "distance_scale_km": 1,
        "recency_scale_days": 365,
        "living_area_log_ratio_scale": 0.25,
        "residual_aggregation": "weighted_median",
        "weight": "1/(1+score)",
    }


def chronological_residuals(
    sales: Sequence[Sale],
) -> tuple[dict[str, float], dict[str, dict[str, int | str]]]:
    """Predict each candidate from a model trained before its calendar month."""
    ordered = tuple(sorted(sales, key=lambda item: (item.sale_date, item.row_id)))
    months = sorted({(item.sale_date.year, item.sale_date.month) for item in ordered})
    residuals: dict[str, float] = {}
    folds: dict[str, dict[str, int | str]] = {}
    for year, month in months:
        start = date(year, month, 1)
        training = tuple(item for item in ordered if item.sale_date < start)
        targets = tuple(
            item
            for item in ordered
            if item.sale_date.year == year and item.sale_date.month == month
        )
        if not training:
            continue
        predicted, _ = _fit_predict(training, targets, None)
        for item, prediction in zip(targets, predicted, strict=True):
            residual = math.log(float(item.price) / prediction)
            if not math.isfinite(residual):
                raise ValueError("Chronological comparable residual is invalid")
            residuals[item.row_id] = residual
        folds[f"{year:04d}-{month:02d}"] = {
            "training_count": len(training),
            "training_sha256": hashlib.sha256(
                ("\n".join(item.row_id for item in training) + "\n").encode()
            ).hexdigest(),
            "target_count": len(targets),
            "target_sha256": hashlib.sha256(
                ("\n".join(item.row_id for item in targets) + "\n").encode()
            ).hexdigest(),
        }
    return residuals, folds


def run(source: Path, output: Path) -> dict[str, object]:
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
    frozen = json.loads(FROZEN_MANIFEST.read_text(encoding="utf-8"))
    source_rows = read_development_source(source)
    eligible, quarantine = select_eligible_sales(source_rows)
    windows = monthly_windows(eligible)
    membership = membership_for(windows)
    verify_frozen_membership(membership, frozen)
    residuals, residual_folds = chronological_residuals(eligible)

    prediction_rows: list[tuple[Sale, str, float, CorrectedPrediction]] = []
    models: dict[str, object] = {}
    comparable_indexes: dict[str, ComparableIndex] = {}
    window_scores: dict[str, object] = {}
    improved_windows = 0
    for name, training, validation in windows:
        incumbent, model = _fit_predict(training, validation, None)
        index = build_index(training, residuals, cutoff=WINDOW_STARTS[name])
        comparable_indexes[name] = index
        corrected = tuple(
            correct_prediction(item, predicted, index)
            for item, predicted in zip(validation, incumbent, strict=True)
        )
        challenger = tuple(item.prediction for item in corrected)
        scores = {
            "xgboost": _score(validation, incumbent),
            "xgboost_comparable_residual": _score(validation, challenger),
        }
        improved_windows += int(
            scores["xgboost_comparable_residual"].mdape < scores["xgboost"].mdape
        )
        window_scores[name] = {
            key: _score_summary(value) for key, value in scores.items()
        }
        models[f"{name}-xgboost"] = model
        prediction_rows.extend(
            (sale_row, name, base, adjusted)
            for sale_row, base, adjusted in zip(
                validation, incumbent, corrected, strict=True
            )
        )

    validation = tuple(item[0] for item in prediction_rows)
    pooled = {
        "xgboost": _score(validation, tuple(item[2] for item in prediction_rows)),
        "xgboost_comparable_residual": _score(
            validation, tuple(item[3].prediction for item in prediction_rows)
        ),
    }
    valid = all(
        math.isfinite(item[3].prediction) and item[3].prediction > 0
        for item in prediction_rows
    )
    screening_candidate = screen_candidate(
        incumbent_mdape=pooled["xgboost"].mdape,
        challenger_mdape=pooled["xgboost_comparable_residual"].mdape,
        incumbent_within_10=pooled["xgboost"].within_10,
        challenger_within_10=pooled["xgboost_comparable_residual"].within_10,
        incumbent_p90=pooled["xgboost"].p90_ape,
        challenger_p90=pooled["xgboost_comparable_residual"].p90_ape,
        improved_windows=improved_windows,
        valid_predictions=valid,
    )
    summary = {
        "protocol": PROTOCOL,
        "evidence_class": "exploratory_partial_retrospective_sale_date_screen",
        "source_rows_parsed": len(source_rows),
        "eligible_rows": len(eligible),
        "quarantine_counts": quarantine,
        "windows": window_scores,
        "pooled": {key: _score_summary(value) for key, value in pooled.items()},
        "improved_windows": improved_windows,
        "development_screening_candidate": screening_candidate,
        "supported_prediction_count": sum(
            item[3].support == "supported" for item in prediction_rows
        ),
        "low_support_prediction_count": sum(
            item[3].support == "low_support" for item in prediction_rows
        ),
        "march_may_labels_parsed": 0,
        "march_may_rows_scored": 0,
        "valid_prediction_count": sum(
            math.isfinite(item[3].prediction) and item[3].prediction > 0
            for item in prediction_rows
        ),
        "promotion_eligible": False,
        "promotion_ineligibility_reason": (
            "exploratory partial screen: duplicate economic transfers, historical "
            "publication, and feature vintages are unresolved"
        ),
        "duplicate_transfer_control": "unavailable",
        "us10_satisfied": False,
        "certified_90_day_origin": False,
        "g_us_gate": "PENDING",
    }
    _write_outputs(
        output,
        summary,
        prediction_rows,
        models,
        comparable_indexes,
        residuals,
        residual_folds,
        membership,
        frozen,
        commit,
    )
    return summary


def _write_outputs(
    output: Path,
    summary: Mapping[str, object],
    rows: Sequence[tuple[Sale, str, float, CorrectedPrediction]],
    models: Mapping[str, object],
    comparable_indexes: Mapping[str, ComparableIndex],
    residuals: Mapping[str, float],
    residual_folds: Mapping[str, object],
    membership: Mapping[str, object],
    frozen: Mapping[str, object],
    commit: str,
) -> None:
    with tempfile.TemporaryDirectory(
        dir=PRIVATE_ROOT, prefix="comparable-"
    ) as directory:
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
                    "xgboost_comparable_residual_usd",
                    "support",
                    "comparable_count",
                    "radius_km",
                    "comparable_row_ids",
                )
            )
            for sale_row, window, incumbent, corrected in rows:
                writer.writerow(
                    (
                        sale_row.row_id,
                        sale_row.sale_date,
                        window,
                        sale_row.price,
                        incumbent,
                        corrected.prediction,
                        corrected.support,
                        corrected.comparable_count,
                        corrected.radius_km,
                        "|".join(corrected.row_ids),
                    )
                )
        (staging / "scorecards.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
        )
        for name, model in models.items():
            model.save_model(staging / f"{name}.json")
        for name, index in comparable_indexes.items():
            (staging / f"{name}-comparable-index.json").write_text(
                json.dumps(
                    {
                        "cutoff": index.cutoff.isoformat(),
                        "candidate_row_ids": [item.row_id for item in index.sales],
                        "log_residuals": index.residuals,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                encoding="utf-8",
            )
        (staging / "chronological-residuals.json").write_text(
            json.dumps(
                {
                    "fold_membership": residual_folds,
                    "residual_by_row_id": residuals,
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )
        outputs = {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in staging.iterdir()
            if path.is_file()
        }
        configuration = _configuration()
        manifest = {
            "run_id": output.name,
            "status": "complete",
            "code_commit": commit,
            "protocol": PROTOCOL,
            "source_sha256": SOURCE_SHA256,
            "declared_lock_sha256": hashlib.sha256(
                DECLARED_LOCK.read_bytes()
            ).hexdigest(),
            "runtime_versions": _runtime_versions(),
            "feature_policy_sha256": hashlib.sha256(
                json.dumps(FEATURES, separators=(",", ":")).encode()
            ).hexdigest(),
            "window_membership": membership,
            "residual_fold_membership": residual_folds,
            "residual_fold_sha256": _membership_sha256(residual_folds),
            "frozen_rolling_split_sha256": frozen["split_sha256"],
            "frozen_rolling_manifest_sha256": hashlib.sha256(
                FROZEN_MANIFEST.read_bytes()
            ).hexdigest(),
            "configuration": configuration,
            "configuration_sha256": hashlib.sha256(
                json.dumps(
                    configuration, sort_keys=True, separators=(",", ":")
                ).encode()
            ).hexdigest(),
            "outputs": outputs,
            "base_checkpoint_identities": {
                name: outputs[f"{name}.json"] for name in sorted(models)
            },
            "challenger_run_artifact_identities": {
                name: hashlib.sha256(
                    (
                        outputs[f"{name}-xgboost.json"]
                        + outputs[f"{name}-comparable-index.json"]
                        + outputs["chronological-residuals.json"]
                    ).encode()
                ).hexdigest()
                for name in sorted(comparable_indexes)
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
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.source, args.output), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
