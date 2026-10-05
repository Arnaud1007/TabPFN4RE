"""Run a bounded King County rolling development comparison."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import tempfile
from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from pathlib import Path

from scripts.king_historical_benchmark import (
    FEATURES,
    SOURCE_SHA256,
    Sale,
    encode_features,
    read_pinned_source,
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
    baseline_predictions,
)

PROTOCOL = "king_rolling_development_v1"
WINDOWS = (
    ("2014-11", date(2014, 11, 1), date(2014, 12, 1)),
    ("2014-12", date(2014, 12, 1), date(2015, 1, 1)),
    ("2015-01", date(2015, 1, 1), date(2015, 2, 1)),
    ("2015-02", date(2015, 2, 1), date(2015, 3, 1)),
)
WINDOW_STARTS = {name: start for name, start, _ in WINDOWS}


def monthly_windows(
    sales: Sequence[Sale],
) -> tuple[tuple[str, tuple[Sale, ...], tuple[Sale, ...]], ...]:
    """Return four expanding windows without touching March-May evaluation rows."""
    ordered = tuple(sorted(sales, key=lambda item: (item.sale_date, item.row_id)))
    result = []
    seen_validation: set[str] = set()
    for name, start, end in WINDOWS:
        training = tuple(item for item in ordered if item.sale_date < start)
        validation = tuple(item for item in ordered if start <= item.sale_date < end)
        if not training or not validation:
            raise ValueError(f"Rolling window {name} is empty")
        validation_ids = {item.row_id for item in validation}
        if seen_validation & validation_ids or max(
            item.sale_date for item in training
        ) >= min(item.sale_date for item in validation):
            raise ValueError(
                "Rolling windows are not strictly chronological and disjoint"
            )
        seen_validation.update(validation_ids)
        result.append((name, training, validation))
    return tuple(result)


def recency_weights(
    training: Sequence[Sale], *, cutoff: date, half_life_days: int = 180
) -> tuple[float, ...]:
    """Compute immutable exponential weights from dates strictly before cutoff."""
    if half_life_days <= 0 or not training:
        raise ValueError(
            "Recency weighting needs training rows and a positive half-life"
        )
    ages = tuple((cutoff - item.sale_date).days for item in training)
    if any(age <= 0 for age in ages):
        raise ValueError("Every weighted training sale must be before cutoff")
    return tuple(0.5 ** (age / half_life_days) for age in ages)


def choose_recency_challenger(
    *,
    incumbent_mdape: Decimal,
    challenger_mdape: Decimal,
    incumbent_within_10: Decimal,
    challenger_within_10: Decimal,
    incumbent_p90: Decimal,
    challenger_p90: Decimal,
    improved_windows: int,
) -> str:
    """Apply the predeclared useful-gain and non-inferiority rule."""
    if not 0 <= improved_windows <= 4:
        raise ValueError("Improved-window count must be between zero and four")
    if (
        improved_windows >= 3
        and challenger_mdape <= incumbent_mdape * Decimal("0.98")
        and challenger_within_10 >= incumbent_within_10 - Decimal("0.005")
        and challenger_p90 <= incumbent_p90 + Decimal("0.005")
    ):
        return "xgboost_recency_180d"
    return "xgboost"


def _fit_predict(
    training: Sequence[Sale],
    validation: Sequence[Sale],
    weights: Sequence[float] | None,
) -> tuple[tuple[float, ...], object]:
    import numpy as np
    from xgboost import XGBRegressor

    _, train_rows, validation_rows = encode_features(training, validation)
    model = XGBRegressor(**MODEL_PARAMETERS)
    labels = np.log(np.asarray([float(item.price) for item in training], dtype=float))
    fit_kwargs = (
        {} if weights is None else {"sample_weight": np.asarray(weights, dtype=float)}
    )
    model.fit(np.asarray(train_rows, dtype=float), labels, **fit_kwargs)
    predicted = tuple(
        float(value)
        for value in np.exp(model.predict(np.asarray(validation_rows, dtype=float)))
    )
    if len(predicted) != len(validation) or not all(
        math.isfinite(value) and value > 0 for value in predicted
    ):
        raise ValueError("Rolling model produced invalid predictions")
    return predicted, model


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
    sales = read_pinned_source(source)
    eligible, quarantine = select_eligible_sales(sales)
    windows = monthly_windows(eligible)
    membership = {
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
    split_sha256 = hashlib.sha256(
        json.dumps(membership, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    all_rows: list[tuple[Sale, float, float, float, str]] = []
    models: dict[str, object] = {}
    window_scores: dict[str, object] = {}
    improved = 0
    for name, training, validation in windows:
        incumbent, incumbent_model = _fit_predict(training, validation, None)
        weights = recency_weights(training, cutoff=WINDOW_STARTS[name])
        challenger, challenger_model = _fit_predict(training, validation, weights)
        models[f"{name}-xgboost"] = incumbent_model
        models[f"{name}-xgboost-recency-180d"] = challenger_model
        baseline = baseline_predictions(training, validation)
        scores = {
            "zipcode_median": _score(validation, baseline),
            "xgboost": _score(validation, incumbent),
            "xgboost_recency_180d": _score(validation, challenger),
        }
        improved += int(scores["xgboost_recency_180d"].mdape < scores["xgboost"].mdape)
        window_scores[name] = {
            key: _score_summary(value) for key, value in scores.items()
        }
        all_rows.extend(
            zip(
                validation,
                baseline,
                incumbent,
                challenger,
                (name for _ in validation),
                strict=True,
            )
        )
    validations = tuple(row[0] for row in all_rows)
    pooled = {
        "zipcode_median": _score(validations, tuple(row[1] for row in all_rows)),
        "xgboost": _score(validations, tuple(row[2] for row in all_rows)),
        "xgboost_recency_180d": _score(validations, tuple(row[3] for row in all_rows)),
    }
    champion = choose_recency_challenger(
        incumbent_mdape=pooled["xgboost"].mdape,
        challenger_mdape=pooled["xgboost_recency_180d"].mdape,
        incumbent_within_10=pooled["xgboost"].within_10,
        challenger_within_10=pooled["xgboost_recency_180d"].within_10,
        incumbent_p90=pooled["xgboost"].p90_ape,
        challenger_p90=pooled["xgboost_recency_180d"].p90_ape,
        improved_windows=improved,
    )
    summary = {
        "protocol": PROTOCOL,
        "evidence_class": "historical_sale_date_development_only",
        "source_rows": len(sales),
        "eligible_rows": len(eligible),
        "quarantine_counts": quarantine,
        "windows": window_scores,
        "pooled": {key: _score_summary(value) for key, value in pooled.items()},
        "improved_windows": improved,
        "selected_candidate": champion,
        "march_may_rows_scored": 0,
        "certified_90_day_origin": False,
        "g_us_gate": "PENDING",
    }
    with tempfile.TemporaryDirectory(dir=PRIVATE_ROOT, prefix="rolling-") as directory:
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
                    "zipcode_median_usd",
                    "xgboost_usd",
                    "xgboost_recency_180d_usd",
                )
            )
            for item, baseline, incumbent, challenger, window in all_rows:
                writer.writerow(
                    (
                        item.row_id,
                        item.sale_date,
                        window,
                        item.price,
                        baseline,
                        incumbent,
                        challenger,
                    )
                )
        (staging / "scorecards.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
        )
        for name, model in models.items():
            model.save_model(staging / f"{name}.json")
        outputs = {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in staging.iterdir()
            if path.is_file()
        }
        manifest = {
            "run_id": output.name,
            "status": "complete",
            "code_commit": commit,
            "protocol": PROTOCOL,
            "source_sha256": SOURCE_SHA256,
            "dependency_lock_sha256": hashlib.sha256(
                (ROOT / "locks/ames-prototype-requirements.txt").read_bytes()
            ).hexdigest(),
            "feature_policy_sha256": hashlib.sha256(
                json.dumps(FEATURES, separators=(",", ":")).encode()
            ).hexdigest(),
            "window_membership": membership,
            "split_sha256": split_sha256,
            "configuration_sha256": hashlib.sha256(
                json.dumps(
                    {
                        "model": MODEL_PARAMETERS,
                        "half_life_days": 180,
                        "windows": [
                            (name, start.isoformat(), end.isoformat())
                            for name, start, end in WINDOWS
                        ],
                    },
                    sort_keys=True,
                ).encode()
            ).hexdigest(),
            "outputs": outputs,
            "checkpoint_identities": {
                name: outputs[f"{name}.json"] for name in sorted(models)
            },
            "prediction_artifact_sha256": outputs["predictions.csv"],
        }
        (staging / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
        )
        real_directory(staging, PRIVATE_ROOT)
        verify_acl(staging)
        os.replace(staging, output)
        real_directory(output, PRIVATE_ROOT)
        verify_acl(output)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.source, args.output), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
