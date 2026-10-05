"""Build the selected King model from a private pre-March-only stage."""

from __future__ import annotations

import argparse
from datetime import date
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import tempfile
from types import MappingProxyType
from typing import Mapping, Protocol, Sequence

from scripts.king_historical_benchmark import (
    FEATURES,
    NUMERIC_FEATURES,
    SOURCE_SHA256,
    Sale,
    encode_features,
    select_eligible_sales,
)
from scripts.private_review_io import real_directory, secure_directory, verify_acl
from scripts.run_king_absolute_error_development import (
    DECLARED_LOCK,
    read_regular_snapshot,
)
from scripts.run_king_historical_benchmark import PRIVATE_ROOT, ROOT, _committed_code
from scripts.stage_king_pre_march_training import (
    ARTIFACT_NAME,
    PROTOCOL as STAGE_PROTOCOL,
)

PROTOCOL = "king_log_absolute_error_serving_refit_v1"
OBJECTIVE = "reg:absoluteerror"
ABSOLUTE_MODEL_CONFIGURATION = MappingProxyType(
    {
        "n_estimators": 250,
        "max_depth": 6,
        "learning_rate": 0.05,
        "min_child_weight": 10,
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "tree_method": "hist",
        "n_jobs": 4,
        "random_state": 42,
        "objective": OBJECTIVE,
    }
)
TRAINING_CUTOFF_EXCLUSIVE = "2015-03-01"
EXPECTED_SOURCE_ROWS = 16_861
EXPECTED_TRAINING_ROWS = 16_849
EXPECTED_RUN_ID = "king-absolute-error-serving-20261006-v1"
SELECTION_MANIFEST = (
    ROOT / "runs/king-log-absolute-error-development-20261006-v1/manifest.json"
)
SELECTION_AGGREGATE = (
    ROOT / "runs/king-log-absolute-error-development-20261006-v1/aggregate.json"
)
SELECTION_MANIFEST_SHA256 = (
    "6b28a8bd0e22f9c0856c2faf15568992d2c139f24d51b63928d550f13bf108c5"
)
SELECTION_AGGREGATE_SHA256 = (
    "1b2dfe8132382297245dcc9ed4afd80b7282b6371d21a93e00a565862eaaa504"
)
DECLARED_LOCK_SHA256 = (
    "e877af0954e9493b7118f8f302833def58ee13e474164b82b86e46f2b2c04e3f"
)
EXPECTED_RUNTIME = {
    "machine": "AMD64",
    "numpy": "2.4.6",
    "platform": "Windows-10-10.0.26200-SP0",
    "python": "3.11.6",
    "xgboost": "3.2.0",
}
MAX_EVIDENCE_BYTES = 1_000_000
MAX_STAGE_MANIFEST_BYTES = 100_000
MAX_TRAINING_BYTES = 50_000_000
MAX_LOCK_BYTES = 100_000


class SavableRegressor(Protocol):
    def fit(self, matrix: object, labels: object) -> SavableRegressor: ...
    def predict(self, matrix: object) -> Sequence[float]: ...
    def save_model(self, path: Path) -> None: ...


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json_snapshot(path: Path, expected_sha256: str, label: str) -> dict[str, object]:
    content = read_regular_snapshot(path, MAX_EVIDENCE_BYTES, label)
    if hashlib.sha256(content).hexdigest() != expected_sha256:
        raise ValueError(f"{label} selection evidence hash is incompatible")
    try:
        value = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} selection evidence is invalid") from error
    if not isinstance(value, dict):
        raise ValueError(f"{label} selection evidence must be an object")
    return value


def load_selection_evidence() -> dict[str, object]:
    manifest = _json_snapshot(
        SELECTION_MANIFEST, SELECTION_MANIFEST_SHA256, "Selection manifest"
    )
    aggregate = _json_snapshot(
        SELECTION_AGGREGATE, SELECTION_AGGREGATE_SHA256, "Selection aggregate"
    )
    outputs = manifest.get("outputs")
    configuration_value = manifest.get("configuration")
    runtime = manifest.get("runtime_versions")
    if (
        manifest.get("protocol") != "king_log_absolute_error_development_screen_v1"
        or manifest.get("status") != "complete"
        or manifest.get("source_sha256") != SOURCE_SHA256
        or manifest.get("declared_lock_sha256") != DECLARED_LOCK_SHA256
        or not isinstance(runtime, dict)
        or any(
            runtime.get(name) != version for name, version in EXPECTED_RUNTIME.items()
        )
        or not isinstance(outputs, dict)
        or outputs.get("scorecards.json") != SELECTION_AGGREGATE_SHA256
        or not isinstance(configuration_value, dict)
        or configuration_value.get("model") != dict(ABSOLUTE_MODEL_CONFIGURATION)
        or configuration_value.get("challenger_objective") != OBJECTIVE
        or aggregate.get("development_screening_candidate")
        != "xgboost_log_absolute_error"
        or aggregate.get("eligible_rows") != EXPECTED_TRAINING_ROWS
        or aggregate.get("improved_windows") != 4
        or aggregate.get("march_may_labels_parsed") != 0
        or aggregate.get("march_may_rows_scored") != 0
    ):
        raise ValueError("Frozen selection evidence is incompatible")
    return aggregate


def verify_runtime_versions() -> dict[str, str]:
    import numpy
    import xgboost

    lock = read_regular_snapshot(DECLARED_LOCK, MAX_LOCK_BYTES, "Declared lock")
    if hashlib.sha256(lock).hexdigest() != DECLARED_LOCK_SHA256:
        raise ValueError("Declared lock hash does not match frozen selection evidence")
    pinned = {
        name: version
        for line in lock.decode("utf-8").splitlines()
        if "==" in line
        for name, version in (line.strip().split("==", maxsplit=1),)
    }
    observed = {
        "python": platform.python_version(),
        "numpy": numpy.__version__,
        "xgboost": xgboost.__version__,
        "platform": platform.platform(),
        "machine": platform.machine(),
    }
    if (
        any(observed[name] != version for name, version in EXPECTED_RUNTIME.items())
        or observed["numpy"] != pinned.get("numpy")
        or observed["xgboost"] != pinned.get("xgboost")
    ):
        raise ValueError("Runtime dependency versions do not match the frozen lock")
    return observed


def configuration() -> dict[str, object]:
    return dict(ABSOLUTE_MODEL_CONFIGURATION)


def membership_sha256(rows: Sequence[Sale]) -> str:
    return hashlib.sha256(
        ("\n".join(item.row_id for item in rows) + "\n").encode()
    ).hexdigest()


def _sale(value: object) -> Sale:
    required = {"row_id", "property_id", "sale_date", "price_usd", "features"}
    if not isinstance(value, dict) or set(value) != required:
        raise ValueError("Staged training record schema is incompatible")
    features = value["features"]
    if not isinstance(features, dict) or set(features) != set(FEATURES):
        raise ValueError("Staged training feature schema is incompatible")
    try:
        when = date.fromisoformat(value["sale_date"])
        price = Decimal(value["price_usd"])
        numeric = {name: float(features[name]) for name in NUMERIC_FEATURES}
    except (TypeError, ValueError, KeyError, InvalidOperation) as error:
        raise ValueError("Staged training record is invalid") from error
    row_id = value["row_id"]
    if (
        not isinstance(row_id, str)
        or len(row_id) != 64
        or any(character not in "0123456789abcdef" for character in row_id)
        or not isinstance(value["property_id"], str)
        or not isinstance(features["zipcode"], str)
        or len(features["zipcode"]) != 5
        or not features["zipcode"].isdigit()
        or when >= date(2015, 3, 1)
        or not price.is_finite()
        or price <= 0
        or any(not math.isfinite(number) for number in numeric.values())
    ):
        raise ValueError("Staged training record is invalid")
    return Sale(
        row_id,
        value["property_id"],
        when,
        price,
        MappingProxyType({**numeric, "zipcode": features["zipcode"]}),
    )


def load_staged_training(
    stage_dir: Path, expected_manifest_sha256: str
) -> tuple[tuple[Sale, ...], dict[str, object]]:
    stage_dir = stage_dir.absolute()
    if len(expected_manifest_sha256) != 64 or any(
        character not in "0123456789abcdef" for character in expected_manifest_sha256
    ):
        raise ValueError("Expected staged manifest SHA-256 is invalid")
    real_directory(PRIVATE_ROOT, PRIVATE_ROOT.parent)
    verify_acl(PRIVATE_ROOT)
    if stage_dir.parent != PRIVATE_ROOT:
        raise ValueError("Stage must be directly inside the private King directory")
    real_directory(stage_dir, PRIVATE_ROOT)
    verify_acl(stage_dir)
    manifest_content = read_regular_snapshot(
        stage_dir / "manifest.json", MAX_STAGE_MANIFEST_BYTES, "Stage manifest"
    )
    if hashlib.sha256(manifest_content).hexdigest() != expected_manifest_sha256:
        raise ValueError("Staged manifest checksum mismatch")
    manifest = json.loads(manifest_content)
    expected = {
        "run_id": stage_dir.name,
        "protocol": STAGE_PROTOCOL,
        "scope": "private_historical_research_training_only",
        "status": "complete",
        "source_sha256": SOURCE_SHA256,
        "source_rows_parsed": EXPECTED_SOURCE_ROWS,
        "training_rows": EXPECTED_TRAINING_ROWS,
        "training_cutoff_exclusive": TRAINING_CUTOFF_EXCLUSIVE,
        "quarantine_counts": {"future_year_built": 12},
        "schema": ["row_id", "property_id", "sale_date", "price_usd", "features"],
        "feature_names": list(FEATURES),
        "march_may_labels_parsed": 0,
    }
    if not isinstance(manifest, dict) or any(
        manifest.get(key) != value for key, value in expected.items()
    ):
        raise ValueError("Staged manifest provenance is incompatible")
    if not isinstance(manifest.get("code_commit"), str) or not re.fullmatch(
        r"[0-9a-f]{40}", manifest["code_commit"]
    ):
        raise ValueError("Staged code identity is incompatible")
    outputs = manifest.get("outputs")
    if not isinstance(outputs, dict) or set(outputs) != {ARTIFACT_NAME}:
        raise ValueError("Staged output manifest is incompatible")
    content = read_regular_snapshot(
        stage_dir / ARTIFACT_NAME, MAX_TRAINING_BYTES, "Staged training artifact"
    )
    if outputs[ARTIFACT_NAME] != hashlib.sha256(content).hexdigest():
        raise ValueError("Staged training artifact checksum mismatch")
    try:
        rows = tuple(
            _sale(json.loads(line)) for line in content.decode("utf-8").splitlines()
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Staged training artifact is invalid") from error
    eligible, quarantine = select_eligible_sales(rows)
    if (
        len(rows) != EXPECTED_TRAINING_ROWS
        or len({item.row_id for item in rows}) != EXPECTED_TRAINING_ROWS
        or eligible != rows
        or quarantine
        or manifest.get("training_membership_sha256") != membership_sha256(rows)
    ):
        raise ValueError("Staged training membership is incompatible")
    return rows, manifest


def fit_bundle(training: Sequence[Sale]) -> tuple[SavableRegressor, tuple[str, ...]]:
    import numpy as np
    from xgboost import XGBRegressor

    names, rows, _ = encode_features(training, ())
    model: SavableRegressor = XGBRegressor(**configuration())
    labels = np.log(np.asarray([float(item.price) for item in training], dtype=float))
    matrix = np.asarray(rows, dtype=float)
    model.fit(matrix, labels)
    predicted = model.predict(matrix[:1])
    probe = float(predicted[0])
    if not math.isfinite(probe):
        raise ValueError("Absolute-error refit produced an invalid prediction")
    return model, names


def _verify_saved_model(
    model: SavableRegressor,
    model_path: Path,
    training: Sequence[Sale],
) -> dict[str, object]:
    """Compare a real save/load cycle on one deterministic training-only batch."""
    import numpy as np
    from xgboost import XGBRegressor

    probes = tuple(training[:8])
    if len(probes) != 8:
        raise ValueError("Save/load verification requires eight training probes")
    _, _, encoded = encode_features(training, probes)
    matrix = np.asarray(encoded, dtype=float)
    before = tuple(float(value) for value in model.predict(matrix))
    loaded = XGBRegressor()
    loaded.load_model(model_path)
    after = tuple(float(value) for value in loaded.predict(matrix))
    absolute_tolerance = 1e-12
    relative_tolerance = 1e-12
    if (
        len(before) != 8
        or len(after) != 8
        or any(not math.isfinite(value) for value in (*before, *after))
    ):
        raise ValueError("Saved model verification produced invalid predictions")
    differences = tuple(
        abs(left - right) for left, right in zip(before, after, strict=True)
    )
    relative = tuple(
        difference / max(abs(left), abs(right), 1.0)
        for left, right, difference in zip(before, after, differences, strict=True)
    )
    if any(
        not math.isclose(
            left,
            right,
            rel_tol=relative_tolerance,
            abs_tol=absolute_tolerance,
        )
        for left, right in zip(before, after, strict=True)
    ):
        raise ValueError("Saved model predictions differ after reload")
    return {
        "status": "passed",
        "probe_count": 8,
        "probe_sha256": hashlib.sha256(
            json.dumps(encoded, separators=(",", ":")).encode()
        ).hexdigest(),
        "prediction_sha256": hashlib.sha256(
            json.dumps(before, separators=(",", ":")).encode()
        ).hexdigest(),
        "absolute_tolerance": absolute_tolerance,
        "relative_tolerance": relative_tolerance,
        "maximum_absolute_difference": max(differences),
        "maximum_relative_difference": max(relative),
    }


def build(
    stage_dir: Path, stage_manifest_sha256: str, output: Path
) -> dict[str, object]:
    commit = _committed_code()
    evidence = load_selection_evidence()
    runtime = verify_runtime_versions()
    training, stage_manifest = load_staged_training(stage_dir, stage_manifest_sha256)
    if (
        output.name != EXPECTED_RUN_ID
        or output.parent.resolve() != PRIVATE_ROOT.resolve()
        or output.exists()
        or output.is_symlink()
    ):
        raise ValueError("Output must be a new private King benchmark directory")
    model, feature_names = fit_bundle(training)
    summary = {
        "protocol": PROTOCOL,
        "objective": OBJECTIVE,
        "training_cutoff_exclusive": TRAINING_CUTOFF_EXCLUSIVE,
        "source_rows_parsed": EXPECTED_SOURCE_ROWS,
        "training_rows": len(training),
        "fit_count": 1,
        "march_may_labels_parsed": 0,
        "march_may_rows_scored": 0,
        "selection_evidence": evidence.get("development_screening_candidate"),
        "certified_90_day_origin": False,
        "g_us_gate": "PENDING",
    }
    verification = _write_bundle(
        output,
        model,
        feature_names,
        training,
        runtime,
        commit,
        summary,
        stage_manifest_sha256,
        stage_manifest,
    )
    return {**summary, "save_load_verification": verification}


def _write_bundle(
    output: Path,
    model: SavableRegressor,
    feature_names: tuple[str, ...],
    training: Sequence[Sale],
    runtime: Mapping[str, str],
    commit: str,
    summary: Mapping[str, object],
    stage_manifest_sha256: str,
    stage_manifest: Mapping[str, object],
) -> dict[str, object]:
    with tempfile.TemporaryDirectory(
        dir=PRIVATE_ROOT, prefix="absolute-bundle-"
    ) as temporary:
        staging = Path(temporary)
        secure_directory(staging)
        model.save_model(staging / "xgboost_model.json")
        verification = _verify_saved_model(
            model, staging / "xgboost_model.json", training
        )
        verified_summary = {**summary, "save_load_verification": verification}
        (staging / "feature_names.json").write_text(
            json.dumps(feature_names), encoding="utf-8"
        )
        (staging / "candidate.json").write_text(
            json.dumps(
                {
                    "selected_on_development": "xgboost_log_absolute_error",
                    "artifact": "xgboost_model.json",
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        (staging / "summary.json").write_text(
            json.dumps(verified_summary, indent=2, sort_keys=True), encoding="utf-8"
        )
        outputs = {
            path.name: digest(path) for path in staging.iterdir() if path.is_file()
        }
        configured = configuration()
        manifest = {
            "run_id": output.name,
            "code_commit": commit,
            "protocol": PROTOCOL,
            "scope": "historical_research_only",
            "status": "development_refit_complete_test_unscored",
            "selected_candidate": "xgboost_log_absolute_error",
            "objective": OBJECTIVE,
            "training_cutoff_exclusive": TRAINING_CUTOFF_EXCLUSIVE,
            "source_sha256": SOURCE_SHA256,
            "source_rows_parsed": EXPECTED_SOURCE_ROWS,
            "training_rows": EXPECTED_TRAINING_ROWS,
            "training_membership_sha256": stage_manifest["training_membership_sha256"],
            "quarantine_counts": {"future_year_built": 12},
            "fit_count": 1,
            "march_may_labels_parsed": 0,
            "march_may_rows_scored": 0,
            "dependency_lock_sha256": DECLARED_LOCK_SHA256,
            "runtime_versions": dict(runtime),
            "configuration": configured,
            "configuration_sha256": hashlib.sha256(
                json.dumps(configured, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest(),
            "feature_policy_sha256": outputs["feature_names.json"],
            "checkpoint_identity": outputs["xgboost_model.json"],
            "selection_manifest_sha256": SELECTION_MANIFEST_SHA256,
            "selection_aggregate_sha256": SELECTION_AGGREGATE_SHA256,
            "stage_manifest_sha256": stage_manifest_sha256,
            "save_load_verification": verification,
            "outputs": outputs,
        }
        (staging / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
        )
        real_directory(staging, PRIVATE_ROOT)
        verify_acl(staging)
        os.replace(staging, output)
        # Keep a renamed output if verification fails; it is evidence and cleanup
        # is unsafe until its exact identity is established.
        real_directory(output, PRIVATE_ROOT)
        verify_acl(output)
        return verification


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", type=Path, required=True)
    parser.add_argument("--stage-manifest-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            build(args.stage, args.stage_manifest_sha256, args.output), sort_keys=True
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
