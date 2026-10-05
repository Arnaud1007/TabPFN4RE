"""Predict with a saved historical King County research checkpoint."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
import sys
from typing import Mapping

from scripts.king_historical_benchmark import NUMERIC_FEATURES, SOURCE_SHA256
from scripts.private_review_io import real_directory, verify_acl
from scripts.run_king_historical_benchmark import MODEL_PARAMETERS, PRIVATE_ROOT, ROOT

_MAX_MANIFEST_BYTES = 20_000
_MAX_MODEL_BYTES = 4_000_000
_MAX_OTHER_BYTES = 500_000
_MAX_REQUEST_BYTES = 8_000
_SPLIT_PATH = ROOT / "runs/king-historical-20261004-v1/split_manifest.json"
_LOCK_PATH = ROOT / "locks/ames-prototype-requirements.txt"
_REQUIRED_FILES = ("candidate.json", "feature_names.json", "xgboost_model.json")


@dataclass(frozen=True)
class VerifiedBundle:
    feature_names: tuple[str, ...]
    model_bytes: bytes
    manifest_sha256: str
    model_sha256: str


@dataclass(frozen=True)
class LoadedPredictor:
    """One verified checkpoint loaded once for repeated local predictions."""

    bundle: VerifiedBundle
    model: object

    @property
    def feature_names(self) -> tuple[str, ...]:
        return self.bundle.feature_names

    def predict(self, request: Mapping[str, object]) -> dict[str, object]:
        values = validate_request(request, self.feature_names)
        amount = predict_price(self.model, encode_request(values, self.feature_names))
        return _prediction_response(amount, self.bundle)


def _read_limited(path: Path, limit: int) -> bytes:
    if path.is_symlink() or not path.is_file() or path.stat().st_nlink != 1:
        raise ValueError("Bundle file is missing or redirects")
    with path.open("rb") as stream:
        content = stream.read(limit + 1)
    if len(content) > limit:
        raise ValueError("Bundle file exceeds its size limit")
    return content


def _digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _feature_names(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(name, str) for name in value):
        raise ValueError("Bundle feature names are invalid")
    names = tuple(value)
    if (
        names[: len(NUMERIC_FEATURES)] != NUMERIC_FEATURES
        or len(names) <= len(NUMERIC_FEATURES)
        or len(names) != len(set(names))
        or any(
            not re.fullmatch(r"zipcode=\d{5}", name)
            for name in names[len(NUMERIC_FEATURES) :]
        )
    ):
        raise ValueError("Bundle feature names are incompatible")
    return names


def load_bundle(bundle_dir: Path, expected_manifest_sha256: str) -> VerifiedBundle:
    """Load only the digest-pinned research checkpoint from the private root."""
    bundle_dir = bundle_dir.absolute()
    if not re.fullmatch(r"[0-9a-f]{64}", expected_manifest_sha256):
        raise ValueError("Expected manifest SHA-256 is invalid")
    real_directory(PRIVATE_ROOT, PRIVATE_ROOT.parent)
    verify_acl(PRIVATE_ROOT)
    if bundle_dir.parent != PRIVATE_ROOT:
        raise ValueError("Bundle must be directly inside the private King directory")
    real_directory(bundle_dir, PRIVATE_ROOT)
    verify_acl(bundle_dir)
    manifest_bytes = _read_limited(bundle_dir / "manifest.json", _MAX_MANIFEST_BYTES)
    if _digest(manifest_bytes) != expected_manifest_sha256:
        raise ValueError("Bundle manifest checksum mismatch")
    manifest = json.loads(manifest_bytes)
    if not isinstance(manifest, dict) or any(
        manifest.get(key) != value
        for key, value in {
            "run_id": bundle_dir.name,
            "scope": "historical_research_only",
            "status": "validation_complete_test_unscored",
            "selected_candidate": "xgboost",
            "source_sha256": SOURCE_SHA256,
            "split_manifest_sha256": _digest(_SPLIT_PATH.read_bytes()),
            "dependency_lock_sha256": _digest(_LOCK_PATH.read_bytes()),
            "configuration_sha256": _digest(
                json.dumps(MODEL_PARAMETERS, sort_keys=True).encode()
            ),
        }.items()
    ):
        raise ValueError("Bundle provenance or research scope is incompatible")
    outputs = manifest.get("outputs")
    if not isinstance(outputs, dict) or not set(_REQUIRED_FILES).issubset(outputs):
        raise ValueError("Bundle output manifest is incomplete")
    contents: dict[str, bytes] = {}
    for name, expected in outputs.items():
        if not isinstance(name, str) or not re.fullmatch(r"[a-z_]+\.(json|csv)", name):
            raise ValueError("Bundle output filename is invalid")
        limit = _MAX_MODEL_BYTES if name == "xgboost_model.json" else _MAX_OTHER_BYTES
        content = _read_limited(bundle_dir / name, limit)
        if not isinstance(expected, str) or _digest(content) != expected:
            raise ValueError("Bundle output checksum mismatch")
        contents[name] = content
    candidate = json.loads(contents["candidate.json"])
    if candidate != {
        "selected_on_validation": "xgboost",
        "artifact": "xgboost_model.json",
    }:
        raise ValueError("Bundle candidate selection is incompatible")
    names = _feature_names(json.loads(contents["feature_names.json"]))
    model_sha = _digest(contents["xgboost_model.json"])
    if manifest.get("checkpoint_identity") != model_sha or manifest.get(
        "feature_policy_sha256"
    ) != _digest(contents["feature_names.json"]):
        raise ValueError("Bundle checkpoint identity is incompatible")
    return VerifiedBundle(
        names, contents["xgboost_model.json"], expected_manifest_sha256, model_sha
    )


def validate_request(
    request: Mapping[str, object], feature_names: tuple[str, ...]
) -> dict[str, float | str]:
    """Validate a complete historical King feature vector without a sale price."""
    if not isinstance(request, dict) or set(request) != {*NUMERIC_FEATURES, "zipcode"}:
        raise ValueError("King request must have exactly the 15 property fields")
    numeric: dict[str, float] = {}
    for name in NUMERIC_FEATURES:
        raw = request[name]
        if type(raw) not in (int, float):
            raise ValueError(f"King request {name} must be a finite number")
        try:
            number = float(raw)
        except OverflowError as error:
            raise ValueError(f"King request {name} must be a finite number") from error
        if not math.isfinite(number):
            raise ValueError(f"King request {name} must be a finite number")
        numeric[name] = number
    zipcode = request["zipcode"]
    if (
        not isinstance(zipcode, str)
        or not re.fullmatch(r"\d{5}", zipcode)
        or f"zipcode={zipcode}" not in feature_names
    ):
        raise ValueError("King request zipcode must be a supported training ZIP code")
    for name in ("bedrooms", "view", "condition", "grade", "yr_built"):
        if not numeric[name].is_integer():
            raise ValueError(f"King request {name} must be a whole number")
    _validate_numeric_ranges(numeric)
    return {**numeric, "zipcode": zipcode}


def _validate_numeric_ranges(values: Mapping[str, float]) -> None:
    constraints = (
        ("sqft_living", values["sqft_living"] > 0, "greater than 0"),
        ("sqft_lot", values["sqft_lot"] > 0, "greater than 0"),
        ("sqft_above", values["sqft_above"] >= 0, "0 or greater"),
        ("sqft_basement", values["sqft_basement"] >= 0, "0 or greater"),
        ("bedrooms", 0 <= values["bedrooms"] <= 20, "between 0 and 20"),
        ("bathrooms", 0 <= values["bathrooms"] <= 20, "between 0 and 20"),
        ("floors", 0 < values["floors"] <= 8, "greater than 0 and at most 8"),
        ("waterfront", values["waterfront"] in (0, 1), "0 or 1"),
        ("view", 0 <= values["view"] <= 4, "between 0 and 4"),
        ("condition", 1 <= values["condition"] <= 5, "between 1 and 5"),
        ("grade", 1 <= values["grade"] <= 13, "between 1 and 13"),
        ("yr_built", 1800 <= values["yr_built"] <= 2015, "between 1800 and 2015"),
        ("lat", 47 <= values["lat"] <= 48, "between 47 and 48"),
        ("long", -123 <= values["long"] <= -121, "between -123 and -121"),
    )
    for name, accepted, guidance in constraints:
        if not accepted:
            raise ValueError(f"King request {name} must be {guidance}")


def encode_request(
    values: Mapping[str, float | str], feature_names: tuple[str, ...]
) -> tuple[float, ...]:
    return (
        *(float(values[name]) for name in NUMERIC_FEATURES),
        *(
            float(feature == f"zipcode={values['zipcode']}")
            for feature in feature_names[len(NUMERIC_FEATURES) :]
        ),
    )


def predict_price(model: object, vector: tuple[float, ...]) -> float:
    log_price = float(model.predict([vector])[0])
    try:
        price = math.exp(log_price)
    except OverflowError as error:
        raise ValueError(
            "King model produced an invalid sale-price estimate"
        ) from error
    if not math.isfinite(price) or price <= 0:
        raise ValueError("King model produced an invalid sale-price estimate")
    return price


def load_predictor(bundle_dir: Path, manifest_sha256: str) -> LoadedPredictor:
    """Verify and deserialize a checkpoint once for a serving session."""
    bundle = load_bundle(bundle_dir, manifest_sha256)
    from xgboost import XGBRegressor

    model = XGBRegressor()
    model.load_model(bytearray(bundle.model_bytes))
    return LoadedPredictor(bundle, model)


def _prediction_response(amount: float, bundle: VerifiedBundle) -> dict[str, object]:
    return {
        "amount": amount,
        "currency": "USD",
        "model": "xgboost",
        "status": "historical_research_only",
        "reference_period": "King County sales, January-February 2015",
        "certified_90_day_origin": False,
        "g_us_gate": "PENDING",
        "manifest_sha256": bundle.manifest_sha256,
        "model_sha256": bundle.model_sha256,
    }


def predict(
    bundle_dir: Path, request: Mapping[str, object], manifest_sha256: str
) -> dict[str, object]:
    return load_predictor(bundle_dir, manifest_sha256).predict(request)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--request", type=Path, required=True)
    arguments = parser.parse_args()
    try:
        raw = _read_limited(arguments.request, _MAX_REQUEST_BYTES)
        result = predict(arguments.bundle, json.loads(raw), arguments.manifest_sha256)
    except (OSError, ValueError, TypeError, KeyError, IndexError) as error:
        print(f"King historical prediction unavailable: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
