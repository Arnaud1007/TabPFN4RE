"""Score the frozen King later-sale cohort once as historical research only."""

from __future__ import annotations

import json
import math
import os
import tempfile
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from hashlib import sha256
from importlib.metadata import version
from pathlib import Path
from typing import TypeVar
import platform

from scripts.king_historical_benchmark import (
    SOURCE_SHA256,
    Sale,
    encode_features,
    read_pinned_source,
    select_eligible_sales,
    split_sales,
)
from scripts.king_research_predict import VerifiedBundle, load_bundle
from scripts.private_review_io import real_directory, secure_directory, verify_acl
from scripts.run_king_historical_benchmark import (
    MODEL_PARAMETERS,
    PRIVATE_ROOT,
    ROOT,
    _committed_code,
    _score,
    _score_summary,
    _write_predictions,
    baseline_predictions,
    verify_split_manifest,
)

PROTOCOL = "king_later_2015_research_v1"
RUN_ID = "king-later-2015-v1"
SOURCE_PATH = ROOT / "data/raw/openml-king-42092/house_sales.arff"
SPLIT_PATH = ROOT / "runs/king-historical-20261004-v1/split_manifest.json"
BUNDLE_PATH = PRIVATE_ROOT / "king-validation-20261004-v1"
OUTPUT_PATH = PRIVATE_ROOT / RUN_ID
LEDGER_PATH = PRIVATE_ROOT / f"{RUN_ID}.opened.json"
SPLIT_SHA256 = "55cfef3afd7e51c3f85b0ddc8af0c272f62a615c178bc509d04ba327aa009a75"
BUNDLE_MANIFEST_SHA256 = (
    "32c11c3ac12e69126d2e1b2b58ab9eb5403a001836cfeb102442b234fef7cbe9"
)
MODEL_SHA256 = "cead625a3b87d73f46fdf740bfb366b9ff3b17d52434011a63e0ca91849f0033"
EXPECTED_LATER_ROWS = 4_752
EXPECTED_RUNTIME = {"numpy": "2.4.6", "xgboost": "3.2.0"}
_T = TypeVar("_T")


def _digest(path: Path) -> str:
    if path.is_symlink() or not path.is_file() or path.stat().st_nlink != 1:
        raise ValueError("Frozen input is missing or redirects")
    return sha256(path.read_bytes()).hexdigest()


def verify_frozen_inputs(
    *,
    source_sha256: str,
    split_sha256: str,
    bundle_manifest_sha256: str,
    model_sha256: str,
    selected_candidate: str,
) -> None:
    """Reject a changed source, cohort, model or development choice."""
    expected = {
        "source_sha256": SOURCE_SHA256,
        "split_sha256": SPLIT_SHA256,
        "bundle_manifest_sha256": BUNDLE_MANIFEST_SHA256,
        "model_sha256": MODEL_SHA256,
        "selected_candidate": "xgboost",
    }
    received = {
        "source_sha256": source_sha256,
        "split_sha256": split_sha256,
        "bundle_manifest_sha256": bundle_manifest_sha256,
        "model_sha256": model_sha256,
        "selected_candidate": selected_candidate,
    }
    if received != expected:
        raise ValueError("King later research frozen input identity changed")


def verify_runtime_packages(packages: Mapping[str, str]) -> None:
    if dict(packages) != EXPECTED_RUNTIME:
        raise ValueError("King later research runtime differs from the pinned lock")


def consume_once(
    ledger_path: Path, intent: Mapping[str, object], action: Callable[[], _T]
) -> _T:
    """Persist an exclusive opening intent before parsing later labels."""
    if not ledger_path.is_absolute() or not ledger_path.parent.is_dir():
        raise ValueError("A durable opening-ledger path is required")
    payload = json.dumps(intent, sort_keys=True, separators=(",", ":")) + "\n"
    with ledger_path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    return action()


def summarize_later(
    sales: Sequence[Sale], model_predictions: Sequence[float], baseline: Sequence[float]
) -> dict[str, object]:
    """Use the common metric engine on the same complete later cohort."""
    if len(sales) != len(model_predictions) or len(sales) != len(baseline):
        raise ValueError("Prediction count differs from sale count")
    return {
        "protocol": PROTOCOL,
        "evidence_class": "historical_sale_date_research_only",
        "selected_on_prior_validation": "xgboost",
        "test_rows": len(sales),
        "later_period": {
            "xgboost": _score_summary(_score(sales, model_predictions)),
            "zipcode_median": _score_summary(_score(sales, baseline)),
        },
        "certified_90_day_origin": False,
        "g_us_gate": "PENDING",
    }


def _predict(
    bundle: VerifiedBundle, training: Sequence[Sale], later: Sequence[Sale]
) -> tuple[float, ...]:
    import numpy as np
    from xgboost import XGBRegressor

    names, _, later_rows = encode_features(training, later)
    if names != bundle.feature_names:
        raise ValueError("Frozen King feature order changed")
    model = XGBRegressor()
    model.load_model(bytearray(bundle.model_bytes))
    with np.errstate(over="ignore", invalid="ignore"):
        values = tuple(
            float(value)
            for value in np.exp(model.predict(np.asarray(later_rows, dtype=float)))
        )
    if not all(math.isfinite(value) and value > 0 for value in values):
        raise ValueError("Frozen King model produced an invalid prediction")
    return values


def _evaluate(
    bundle: VerifiedBundle, intent: Mapping[str, object]
) -> dict[str, object]:
    sales = read_pinned_source(SOURCE_PATH)
    eligible, quarantine = select_eligible_sales(sales)
    splits = split_sales(eligible)
    frozen = json.loads(SPLIT_PATH.read_text(encoding="utf-8"))
    verify_split_manifest(
        splits,
        frozen,
        expected_source_sha256=SOURCE_SHA256,
        quarantine_counts=quarantine,
    )
    training, later = splits["train"], splits["test"]
    if len(later) != EXPECTED_LATER_ROWS:
        raise ValueError("Frozen King later cohort count changed")
    model_predictions = _predict(bundle, training, later)
    baseline = baseline_predictions(training, later)
    with tempfile.TemporaryDirectory(
        dir=PRIVATE_ROOT, prefix="king-later-staging-"
    ) as name:
        staging = Path(name)
        secure_directory(staging)
        real_directory(staging, PRIVATE_ROOT)
        prediction_path = staging / "later_predictions.csv"
        _write_predictions(prediction_path, later, model_predictions, baseline)
        with prediction_path.open("r+b") as stream:
            os.fsync(stream.fileno())
        summary = summarize_later(later, model_predictions, baseline)
        summary_path = staging / "scorecards.json"
        summary_path.write_text(
            json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8"
        )
        manifest = {
            **intent,
            "status": "complete_research_only",
            "test_rows": len(later),
            "outputs": {
                path.name: _digest(path) for path in (prediction_path, summary_path)
            },
            "completed_at_utc": datetime.now(UTC).isoformat(),
        }
        (staging / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
        )
        os.replace(staging, OUTPUT_PATH)
    return summary


def run_later() -> dict[str, object]:
    """Open once and score without fitting, tuning or changing the champion."""
    commit = _committed_code()
    real_directory(PRIVATE_ROOT, PRIVATE_ROOT.parent)
    verify_acl(PRIVATE_ROOT)
    if OUTPUT_PATH.exists() or OUTPUT_PATH.is_symlink():
        raise FileExistsError("King later research output already exists")
    bundle = load_bundle(BUNDLE_PATH, BUNDLE_MANIFEST_SHA256)
    runtime_packages = {name: version(name) for name in EXPECTED_RUNTIME}
    verify_runtime_packages(runtime_packages)
    verify_frozen_inputs(
        source_sha256=_digest(SOURCE_PATH),
        split_sha256=_digest(SPLIT_PATH),
        bundle_manifest_sha256=bundle.manifest_sha256,
        model_sha256=bundle.model_sha256,
        selected_candidate="xgboost",
    )
    intent = {
        "run_id": RUN_ID,
        "protocol": PROTOCOL,
        "source_sha256": SOURCE_SHA256,
        "split_sha256": SPLIT_SHA256,
        "bundle_manifest_sha256": BUNDLE_MANIFEST_SHA256,
        "model_sha256": MODEL_SHA256,
        "dependency_lock_sha256": _digest(
            ROOT / "locks/ames-prototype-requirements.txt"
        ),
        "feature_policy_sha256": _digest(BUNDLE_PATH / "feature_names.json"),
        "configuration_sha256": sha256(
            json.dumps(MODEL_PARAMETERS, sort_keys=True).encode()
        ).hexdigest(),
        "runtime_packages": runtime_packages,
        "python_version": platform.python_version(),
        "code_commit": commit,
        "scope": "historical_research_only",
        "certified_90_day_origin": False,
        "g_us_gate": "PENDING",
        "opened_at_utc": datetime.now(UTC).isoformat(),
    }
    return consume_once(LEDGER_PATH, intent, lambda: _evaluate(bundle, intent))


def main() -> int:
    print(json.dumps(run_later(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
