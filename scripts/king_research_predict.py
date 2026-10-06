"""Predict with a saved historical King County research checkpoint."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date
import hashlib
from importlib import metadata
import json
import math
import os
from pathlib import Path
import platform
import re
import stat
import sys
from typing import Mapping, Protocol, Sequence

from tabpfn4realestate.features.fhfa_hpi import (
    HpiSeries,
    adjust_price,
    load_verified_metro_series,
)
from scripts.king_historical_benchmark import NUMERIC_FEATURES, SOURCE_SHA256
from scripts.build_king_absolute_error_bundle import ABSOLUTE_MODEL_CONFIGURATION
from scripts.private_review_io import real_directory, verify_acl
from scripts.run_king_historical_benchmark import MODEL_PARAMETERS, PRIVATE_ROOT, ROOT

_MAX_MANIFEST_BYTES = 20_000
_MAX_MODEL_BYTES = 4_000_000
_MAX_OTHER_BYTES = 500_000
_MAX_REQUEST_BYTES = 8_000
_SPLIT_PATH = ROOT / "runs/king-historical-20261004-v1/split_manifest.json"
_LOCK_PATH = ROOT / "locks/ames-prototype-requirements.txt"
_REQUIRED_FILES = ("candidate.json", "feature_names.json", "xgboost_model.json")
_ABSOLUTE_REGISTRY_MANIFEST = (
    ROOT / "runs/king-absolute-error-serving-20261006-v1/manifest.json"
)
_MAX_TOTAL_BUNDLE_BYTES = 5_000_000
ABSOLUTE_PROTOCOL = "king_log_absolute_error_serving_refit_v1"
ABSOLUTE_SELECTION_MANIFEST_SHA256 = (
    "6b28a8bd0e22f9c0856c2faf15568992d2c139f24d51b63928d550f13bf108c5"
)
ABSOLUTE_SELECTION_AGGREGATE_SHA256 = (
    "1b2dfe8132382297245dcc9ed4afd80b7282b6371d21a93e00a565862eaaa504"
)
ABSOLUTE_LOCK_SHA256 = (
    "e877af0954e9493b7118f8f302833def58ee13e474164b82b86e46f2b2c04e3f"
)
ABSOLUTE_RUNTIME = {
    "machine": "AMD64",
    "numpy": "2.4.6",
    "platform": "Windows-10-10.0.26200-SP0",
    "python": "3.11.6",
    "xgboost": "3.2.0",
}
ABSOLUTE_INFERENCE_RUNTIME = "stdlib_xgboost_json_v1"
ABSOLUTE_RESPONSE_SCHEMA = "king_historical_prediction_response_v2"
ABSOLUTE_EVIDENCE_LIMITATIONS = (
    "No certified 90-day valuation-origin evaluation is available.",
    "The G-US release gate is pending.",
    "No calibrated prediction interval artifact is bundled.",
    "No property-specific comparable evidence is produced by this predictor.",
)
ABSOLUTE_LIMITATIONS = (
    "Historical King County research estimate; not a current market valuation.",
    "The 90-day conditional-sale target is intended semantics, not a certified capability.",
    "Do not use this result as a national or production valuation.",
)
FHFA_SOURCE_SHA256 = "d664a8e2e92f64aa17201b3bdd84d0ab4d1a4d00e9c6c15d5b34fb400c10d842"
FHFA_CBSA = "42644"
FHFA_GEOGRAPHY = "Seattle-Bellevue-Kent, WA (MSAD)"
FHFA_BASE_QUARTER = "2015Q1"
FHFA_TARGET_QUARTER = "2026Q2"
FHFA_SNAPSHOT_DATE = date(2026, 10, 5)
FHFA_RELEASE_DATE = date(2026, 8, 25)


@dataclass(frozen=True)
class VerifiedBundle:
    feature_names: tuple[str, ...]
    model_bytes: bytes
    manifest_sha256: str
    model_sha256: str
    protocol: str = "king_historical_sale_date_v1"
    objective: str = "reg:squarederror"
    training_cutoff_exclusive: str = "2015-01-01"
    training_period: str = "King County sales before January 2015"
    selection_period: str = "King County sales, January-February 2015"


class PredictorModel(Protocol):
    def predict(self, matrix: Sequence[Sequence[float]]) -> Sequence[float]: ...


@dataclass(frozen=True)
class LoadedPredictor:
    """One verified checkpoint loaded once for repeated local predictions."""

    bundle: VerifiedBundle
    model: PredictorModel
    hpi_series: HpiSeries | None = None

    @property
    def feature_names(self) -> tuple[str, ...]:
        return self.bundle.feature_names

    def predict(self, request: Mapping[str, object]) -> dict[str, object]:
        values = validate_request(request, self.feature_names)
        amount = predict_price(self.model, encode_request(values, self.feature_names))
        response = _prediction_response(amount, self.bundle)
        if self.hpi_series is None:
            return response
        return with_hpi_research_adjustment(
            response,
            series=self.hpi_series,
            base_quarter=FHFA_BASE_QUARTER,
            target_quarter=FHFA_TARGET_QUARTER,
            as_of=FHFA_SNAPSHOT_DATE,
        )


def _read_limited(path: Path, limit: int) -> bytes:
    if path.is_symlink():
        raise ValueError("Bundle file is missing or redirects")
    try:
        with path.open("rb") as stream:
            metadata = os.fstat(stream.fileno())
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
                raise ValueError("Bundle file is missing or redirects")
            if metadata.st_size > limit:
                raise ValueError("Bundle file exceeds its size limit")
            content = stream.read(limit + 1)
    except OSError as error:
        raise ValueError("Bundle file is missing or redirects") from error
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


def _valid_save_load_verification(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    absolute_tolerance = value.get("absolute_tolerance")
    relative_tolerance = value.get("relative_tolerance")
    maximum_absolute = value.get("maximum_absolute_difference")
    maximum_relative = value.get("maximum_relative_difference")
    numeric = (
        absolute_tolerance,
        relative_tolerance,
        maximum_absolute,
        maximum_relative,
    )
    return (
        value.get("status") == "passed"
        and value.get("probe_count") == 8
        and absolute_tolerance == 1e-12
        and relative_tolerance == 1e-12
        and all(
            type(item) in (int, float) and math.isfinite(float(item))
            for item in numeric
        )
        and 0 <= maximum_absolute <= absolute_tolerance
        and 0 <= maximum_relative <= relative_tolerance
        and all(
            isinstance(value.get(name), str)
            and re.fullmatch(r"[0-9a-f]{64}", value[name])
            for name in ("probe_sha256", "prediction_sha256")
        )
    )


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
    if not isinstance(manifest, dict):
        raise ValueError("Bundle provenance or research scope is incompatible")
    protocol = manifest.get("protocol")
    if protocol not in (None, ABSOLUTE_PROTOCOL):
        raise ValueError("Bundle protocol is unsupported")
    if protocol == ABSOLUTE_PROTOCOL:
        registry_bytes = _read_limited(_ABSOLUTE_REGISTRY_MANIFEST, _MAX_MANIFEST_BYTES)
        registry_sha256 = _digest(registry_bytes)
        if (
            expected_manifest_sha256 != registry_sha256
            or manifest_bytes != registry_bytes
        ):
            raise ValueError("Bundle manifest does not match the committed registry")
    legacy_expected = {
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
    }
    absolute_configuration = dict(ABSOLUTE_MODEL_CONFIGURATION)
    absolute_expected = {
        "run_id": bundle_dir.name,
        "protocol": ABSOLUTE_PROTOCOL,
        "scope": "historical_research_only",
        "status": "development_refit_complete_test_unscored",
        "selected_candidate": "xgboost_log_absolute_error",
        "objective": "reg:absoluteerror",
        "training_cutoff_exclusive": "2015-03-01",
        "training_rows": 16_849,
        "runtime_versions": ABSOLUTE_RUNTIME,
        "source_rows_parsed": 16_861,
        "quarantine_counts": {"future_year_built": 12},
        "fit_count": 1,
        "march_may_labels_parsed": 0,
        "march_may_rows_scored": 0,
        "source_sha256": SOURCE_SHA256,
        "dependency_lock_sha256": ABSOLUTE_LOCK_SHA256,
        "configuration": absolute_configuration,
        "configuration_sha256": _digest(
            json.dumps(
                absolute_configuration, sort_keys=True, separators=(",", ":")
            ).encode()
        ),
        "selection_manifest_sha256": ABSOLUTE_SELECTION_MANIFEST_SHA256,
        "selection_aggregate_sha256": ABSOLUTE_SELECTION_AGGREGATE_SHA256,
    }
    code_commit = manifest.get("code_commit")
    training_membership = manifest.get("training_membership_sha256")
    stage_manifest_sha256 = manifest.get("stage_manifest_sha256")
    if protocol == ABSOLUTE_PROTOCOL and any(
        not isinstance(value, str) or not re.fullmatch(pattern, value)
        for value, pattern in (
            (code_commit, r"[0-9a-f]{40}"),
            (training_membership, r"[0-9a-f]{64}"),
            (stage_manifest_sha256, r"[0-9a-f]{64}"),
        )
    ):
        raise ValueError("Bundle identity metadata is incompatible")
    verification = manifest.get("save_load_verification")
    if protocol == ABSOLUTE_PROTOCOL and not _valid_save_load_verification(
        verification
    ):
        raise ValueError("Bundle save/load verification is incompatible")
    expected = absolute_expected if protocol == ABSOLUTE_PROTOCOL else legacy_expected
    if any(manifest.get(key) != value for key, value in expected.items()):
        raise ValueError("Bundle provenance or research scope is incompatible")
    outputs = manifest.get("outputs")
    required_files = (
        (*_REQUIRED_FILES, "summary.json")
        if protocol == ABSOLUTE_PROTOCOL
        else _REQUIRED_FILES
    )
    if not isinstance(outputs, dict) or (
        set(outputs) != set(required_files)
        if protocol == ABSOLUTE_PROTOCOL
        else not set(required_files).issubset(outputs)
    ):
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
    if (
        protocol == ABSOLUTE_PROTOCOL
        and sum(len(content) for content in contents.values()) > _MAX_TOTAL_BUNDLE_BYTES
    ):
        raise ValueError("Bundle files exceed their aggregate size limit")
    candidate = json.loads(contents["candidate.json"])
    expected_candidate = (
        {
            "selected_on_development": "xgboost_log_absolute_error",
            "artifact": "xgboost_model.json",
        }
        if protocol == ABSOLUTE_PROTOCOL
        else {"selected_on_validation": "xgboost", "artifact": "xgboost_model.json"}
    )
    if candidate != expected_candidate:
        raise ValueError("Bundle candidate selection is incompatible")
    if protocol == ABSOLUTE_PROTOCOL:
        summary = json.loads(contents["summary.json"])
        expected_summary = {
            "protocol": ABSOLUTE_PROTOCOL,
            "objective": "reg:absoluteerror",
            "training_cutoff_exclusive": "2015-03-01",
            "source_rows_parsed": 16_861,
            "training_rows": 16_849,
            "fit_count": 1,
            "march_may_labels_parsed": 0,
            "march_may_rows_scored": 0,
            "certified_90_day_origin": False,
            "g_us_gate": "PENDING",
        }
        if (
            not isinstance(summary, dict)
            or any(summary.get(key) != value for key, value in expected_summary.items())
            or summary.get("save_load_verification") != verification
        ):
            raise ValueError("Bundle summary is incompatible")
    names = _feature_names(json.loads(contents["feature_names.json"]))
    model_sha = _digest(contents["xgboost_model.json"])
    if manifest.get("checkpoint_identity") != model_sha or manifest.get(
        "feature_policy_sha256"
    ) != _digest(contents["feature_names.json"]):
        raise ValueError("Bundle checkpoint identity is incompatible")
    return VerifiedBundle(
        names,
        contents["xgboost_model.json"],
        expected_manifest_sha256,
        model_sha,
        ABSOLUTE_PROTOCOL
        if protocol == ABSOLUTE_PROTOCOL
        else "king_historical_sale_date_v1",
        "reg:absoluteerror" if protocol == ABSOLUTE_PROTOCOL else "reg:squarederror",
        "2015-03-01" if protocol == ABSOLUTE_PROTOCOL else "2015-01-01",
        (
            "King County sales before March 2015"
            if protocol == ABSOLUTE_PROTOCOL
            else "King County sales before January 2015"
        ),
        "King County sales, November 2014-February 2015"
        if protocol == ABSOLUTE_PROTOCOL
        else "King County sales, January-February 2015",
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


def predict_price(model: PredictorModel, vector: tuple[float, ...]) -> float:
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


def load_predictor(
    bundle_dir: Path, manifest_sha256: str, fhfa_source: Path | None = None
) -> LoadedPredictor:
    """Verify and deserialize a checkpoint once for a serving session."""
    bundle = load_bundle(bundle_dir, manifest_sha256)
    if bundle.protocol == ABSOLUTE_PROTOCOL:
        if _absolute_runtime_versions() != ABSOLUTE_RUNTIME:
            raise ValueError("Absolute-error bundle runtime is incompatible")
        from scripts.king_xgboost_json import load_xgboost_json

        model = load_xgboost_json(
            bundle.model_bytes,
            len(bundle.feature_names),
            expected_objective=bundle.objective,
        )
        hpi_series = (
            None if fhfa_source is None else _load_king_fhfa_series(fhfa_source)
        )
        return LoadedPredictor(bundle, model, hpi_series)
    from xgboost import XGBRegressor

    model = XGBRegressor()
    model.load_model(bytearray(bundle.model_bytes))
    hpi_series = None if fhfa_source is None else _load_king_fhfa_series(fhfa_source)
    return LoadedPredictor(bundle, model, hpi_series)


def _absolute_runtime_versions() -> dict[str, str]:
    """Read pinned package identities without importing scientific libraries."""
    return {
        "machine": platform.machine(),
        "numpy": metadata.version("numpy"),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "xgboost": metadata.version("xgboost"),
    }


def _load_king_fhfa_series(path: Path) -> HpiSeries:
    return load_verified_metro_series(
        path,
        expected_sha256=FHFA_SOURCE_SHA256,
        cbsa_code=FHFA_CBSA,
        geography=FHFA_GEOGRAPHY,
        quarters=("2014Q3", FHFA_BASE_QUARTER, "2015Q2", FHFA_TARGET_QUARTER),
        source_release_date=FHFA_RELEASE_DATE,
        retrieved_at=FHFA_SNAPSHOT_DATE,
    )


def _prediction_response(amount: float, bundle: VerifiedBundle) -> dict[str, object]:
    legacy = {
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
    if bundle.protocol != ABSOLUTE_PROTOCOL:
        return legacy
    return {
        **legacy,
        **_absolute_disclosures(bundle.training_cutoff_exclusive),
        "reference_period": (
            "King County rolling development, November 2014-February 2015"
        ),
        "bundle_protocol": bundle.protocol,
        "inference_runtime": (
            ABSOLUTE_INFERENCE_RUNTIME
            if bundle.protocol == ABSOLUTE_PROTOCOL
            else "xgboost_native_v1"
        ),
        "objective": bundle.objective,
        "training_cutoff_exclusive": bundle.training_cutoff_exclusive,
        "training_period": bundle.training_period,
        "selection_period": bundle.selection_period,
        "point_estimate_semantics": "median-like sale price from log absolute-error loss",
        "horizon_days": 90,
        "conditional_sale_interpretation": (
            "Recorded sale consideration conditional on a qualifying sale within "
            "the next 90 calendar days"
        ),
    }


def _absolute_disclosures(training_cutoff_exclusive: str) -> dict[str, object]:
    """Build a fresh, deterministic disclosure contract for one response."""
    return {
        "response_schema_version": ABSOLUTE_RESPONSE_SCHEMA,
        "valuation_reference": {
            "kind": "historical_king_county_sales",
            "training_cutoff_exclusive": training_cutoff_exclusive,
            "current_market_valuation": False,
        },
        "data_freshness": {
            "status": "historical_only",
            "known_through_exclusive": training_cutoff_exclusive,
            "current_market_inputs_included": False,
        },
        "support": {
            "status": "schema_supported_research_only",
            "service_area_status": "not_validated",
            "reason": (
                "Input matches the saved King County research feature schema; "
                "market support has not passed G-US."
            ),
        },
        "uncertainty": {
            "status": "unavailable",
            "interval_80": None,
            "interval_90": None,
            "reason": (
                "No calibrated interval artifact is bundled with this historical "
                "predictor."
            ),
        },
        "evidence_limitations": list(ABSOLUTE_EVIDENCE_LIMITATIONS),
        "limitations": list(ABSOLUTE_LIMITATIONS),
    }


def with_hpi_research_adjustment(
    response: Mapping[str, object],
    *,
    series: HpiSeries,
    base_quarter: str,
    target_quarter: str,
    as_of: date,
) -> dict[str, object]:
    """Return a copy with a clearly bounded FHFA market-level illustration."""
    reference_compatible = response.get("reference_period") == (
        "King County sales, January-February 2015"
    ) or (
        response.get("bundle_protocol") == ABSOLUTE_PROTOCOL
        and response.get("reference_period")
        == "King County rolling development, November 2014-February 2015"
    )
    if any(
        (
            response.get("currency") != "USD",
            response.get("status") != "historical_research_only",
            response.get("certified_90_day_origin") is not False,
            response.get("g_us_gate") != "PENDING",
            not reference_compatible,
            series.series_id != "FHFA_PO_NSA_SEATTLE_BELLEVUE_KENT",
            series.cbsa_code != FHFA_CBSA,
            series.geography != FHFA_GEOGRAPHY,
            series.source_sha256 != FHFA_SOURCE_SHA256,
            series.source_release_date != FHFA_RELEASE_DATE,
            series.retrieved_at != FHFA_SNAPSHOT_DATE,
            base_quarter != FHFA_BASE_QUARTER,
            target_quarter != FHFA_TARGET_QUARTER,
            as_of != FHFA_SNAPSHOT_DATE,
        )
    ):
        raise ValueError("HPI adjustment requires a historical King response")
    amount = response.get("amount")
    adjustment = adjust_price(
        amount=amount,  # type: ignore[arg-type]
        series=series,
        base_quarter=base_quarter,
        target_quarter=target_quarter,
        as_of=as_of,
    )
    selected = {
        item.quarter: item
        for item in series.observations
        if item.quarter in (base_quarter, target_quarter)
    }
    metadata = {
        "amount": adjustment.amount,
        "currency": "USD",
        "status": "research_only",
        "series_id": series.series_id,
        "cbsa_code": series.cbsa_code,
        "geography": series.geography,
        "index_type": series.index_type,
        "seasonality": series.seasonality,
        "base_quarter": adjustment.base_quarter,
        "target_quarter": adjustment.target_quarter,
        "factor": adjustment.factor,
        "as_of": adjustment.as_of.isoformat(),
        "source_release_date": series.source_release_date.isoformat(),
        "retrieved_at": series.retrieved_at.isoformat(),
        "snapshot_available_at": series.retrieved_at.isoformat(),
        "base_index": adjustment.base_index,
        "target_index": adjustment.target_index,
        "base_available_at": selected[base_quarter].available_at.isoformat(),
        "target_available_at": selected[target_quarter].available_at.isoformat(),
        "source_sha256": series.source_sha256,
        "warning": (
            "Research only: this applies average market appreciation and is not "
            "a current valuation, not a 90-day estimate, and not property-specific."
        ),
    }
    return {**response, "experimental_hpi_adjustment": metadata}


def predict(
    bundle_dir: Path,
    request: Mapping[str, object],
    manifest_sha256: str,
    fhfa_source: Path | None = None,
) -> dict[str, object]:
    return load_predictor(bundle_dir, manifest_sha256, fhfa_source).predict(request)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--fhfa-source", type=Path)
    arguments = parser.parse_args()
    try:
        raw = _read_limited(arguments.request, _MAX_REQUEST_BYTES)
        result = predict(
            arguments.bundle,
            json.loads(raw),
            arguments.manifest_sha256,
            arguments.fhfa_source,
        )
    except (OSError, ValueError, TypeError, KeyError, IndexError) as error:
        print(f"King historical prediction unavailable: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
