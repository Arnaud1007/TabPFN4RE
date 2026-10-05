"""Create one exclusive local receipt for a King research prediction."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import re
import secrets
import stat
import subprocess
import sys
import tempfile
from typing import Callable, Mapping

from scripts import king_research_predict as serving
from scripts.private_review_io import real_directory, secure_directory, verify_acl


ROOT = Path(__file__).resolve().parents[1]
PRIVATE_ROOT = ROOT / "data/raw/king/prospective-predictions"
MAX_REQUEST_BYTES = 8_000
REFERENCE_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
REFERENCE_PERIOD = "King County sales, January-February 2015"
BASE_RESPONSE_KEYS = frozenset(
    {
        "amount",
        "currency",
        "model",
        "status",
        "reference_period",
        "certified_90_day_origin",
        "g_us_gate",
        "manifest_sha256",
        "model_sha256",
    }
)
HPI_KEYS = frozenset(
    {
        "amount",
        "currency",
        "status",
        "series_id",
        "cbsa_code",
        "geography",
        "index_type",
        "seasonality",
        "base_quarter",
        "target_quarter",
        "factor",
        "as_of",
        "source_release_date",
        "retrieved_at",
        "snapshot_available_at",
        "base_index",
        "target_index",
        "base_available_at",
        "target_available_at",
        "source_sha256",
        "warning",
    }
)


def canonical_bytes(value: object) -> bytes:
    """Encode strict deterministic JSON without accepting non-finite numbers."""
    try:
        return (
            json.dumps(
                value,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError, RecursionError) as error:
        raise ValueError("Receipt content is not strict JSON") from error


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate request field: {key}")
        result[key] = value
    return result


def _read_request(path: Path) -> tuple[bytes, dict[str, object]]:
    selected = Path(path)
    try:
        descriptor = os.open(
            selected,
            os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
        with os.fdopen(descriptor, "rb") as stream:
            metadata = os.fstat(stream.fileno())
            current = os.stat(selected, follow_symlinks=False)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or not stat.S_ISREG(current.st_mode)
                or metadata.st_nlink != 1
                or (metadata.st_dev, metadata.st_ino)
                != (current.st_dev, current.st_ino)
            ):
                raise ValueError("Request must be one regular file")
            raw = stream.read(MAX_REQUEST_BYTES + 1)
    except OSError as error:
        raise ValueError("Request file could not be read") from error
    return _parse_request_bytes(raw)


def _parse_request_bytes(raw: bytes) -> tuple[bytes, dict[str, object]]:
    if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_REQUEST_BYTES:
        raise ValueError("Request file exceeds the size limit")
    try:
        request = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
        raise ValueError("Request file must contain valid UTF-8 JSON") from error
    if type(request) is not dict:
        raise ValueError("Request JSON must be an object")
    canonical_bytes(request)
    return raw, request


def _timestamp(moment: datetime) -> str:
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError("Prediction clock must be timezone-aware")
    return moment.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _validate_response(
    response: object, expected_manifest_sha256: str
) -> dict[str, object]:
    if (
        type(response) is not dict
        or set(response)
        not in (
            BASE_RESPONSE_KEYS,
            BASE_RESPONSE_KEYS | {"experimental_hpi_adjustment"},
        )
        or any(
            (
                response.get("currency") != "USD",
                response.get("model") != "xgboost",
                response.get("status") != "historical_research_only",
                response.get("reference_period") != REFERENCE_PERIOD,
                response.get("certified_90_day_origin") is not False,
                response.get("g_us_gate") != "PENDING",
                not isinstance(response.get("manifest_sha256"), str),
                not isinstance(response.get("model_sha256"), str),
            )
        )
    ):
        raise ValueError("Prediction is incompatible with a King research receipt")
    if (
        SHA256_PATTERN.fullmatch(response["manifest_sha256"]) is None
        or SHA256_PATTERN.fullmatch(response["model_sha256"]) is None
        or response["manifest_sha256"] != expected_manifest_sha256
    ):
        raise ValueError("Prediction model identity is invalid")
    amount = response.get("amount")
    if (
        type(amount) not in (int, float)
        or not math.isfinite(float(amount))
        or amount <= 0
    ):
        raise ValueError("Prediction amount is invalid")
    hpi = response.get("experimental_hpi_adjustment")
    if hpi is not None and (
        type(hpi) is not dict
        or set(hpi) != HPI_KEYS
        or hpi.get("status") != "research_only"
        or not isinstance(hpi.get("warning"), str)
        or "not a current valuation" not in hpi["warning"]
        or "not a 90-day estimate" not in hpi["warning"]
    ):
        raise ValueError("HPI illustration is incompatible with a research receipt")
    if hpi is not None:
        _validate_hpi(hpi, float(amount))
    canonical_bytes(response)
    return response


def _validate_hpi(hpi: Mapping[str, object], base_amount: float) -> None:
    expected = {
        "currency": "USD",
        "status": "research_only",
        "series_id": "FHFA_PO_NSA_SEATTLE_BELLEVUE_KENT",
        "cbsa_code": serving.FHFA_CBSA,
        "geography": serving.FHFA_GEOGRAPHY,
        "index_type": "purchase-only",
        "seasonality": "not-seasonally-adjusted",
        "base_quarter": serving.FHFA_BASE_QUARTER,
        "target_quarter": serving.FHFA_TARGET_QUARTER,
        "as_of": serving.FHFA_SNAPSHOT_DATE.isoformat(),
        "source_release_date": serving.FHFA_RELEASE_DATE.isoformat(),
        "retrieved_at": serving.FHFA_SNAPSHOT_DATE.isoformat(),
        "snapshot_available_at": serving.FHFA_SNAPSHOT_DATE.isoformat(),
        "base_available_at": serving.FHFA_SNAPSHOT_DATE.isoformat(),
        "target_available_at": serving.FHFA_SNAPSHOT_DATE.isoformat(),
        "source_sha256": serving.FHFA_SOURCE_SHA256,
        "warning": (
            "Research only: this applies average market appreciation and is not "
            "a current valuation, not a 90-day estimate, and not property-specific."
        ),
    }
    if any(hpi.get(key) != value for key, value in expected.items()):
        raise ValueError("HPI illustration provenance is invalid")
    for key in ("amount", "factor", "base_index", "target_index"):
        value = hpi.get(key)
        if (
            type(value) not in (int, float)
            or not math.isfinite(float(value))
            or value <= 0
        ):
            raise ValueError(f"HPI illustration {key} is invalid")
    expected_factor = float(hpi["target_index"]) / float(hpi["base_index"])
    if not math.isclose(
        float(hpi["factor"]), expected_factor, rel_tol=1e-12, abs_tol=1e-12
    ) or not math.isclose(
        float(hpi["amount"]),
        base_amount * expected_factor,
        rel_tol=1e-12,
        abs_tol=1e-6,
    ):
        raise ValueError("HPI illustration values are inconsistent")


def _code_state() -> tuple[str, bool]:
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=normal"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return commit, bool(status)


def _publish_receipt(
    receipt_id: str,
    receipt: dict[str, object],
    private_root: Path | None = None,
) -> None:
    """Hard-link a complete hidden file to a new final name without replacement."""
    directory = PRIVATE_ROOT if private_root is None else Path(private_root)
    if (
        not directory.is_dir()
        or directory.is_symlink()
        or directory.resolve(strict=True) != directory.absolute()
    ):
        raise ValueError("Private prediction directory must be real")
    if private_root is not None:
        verify_acl(directory)
    destination = directory / f"{receipt_id}.json"
    if destination.parent != directory or destination.exists():
        raise FileExistsError("Prediction receipt already exists")
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=directory, prefix=f".{receipt_id}-", delete=False
        ) as output:
            temporary = Path(output.name)
            output.write(canonical_bytes(receipt))
            output.flush()
            os.fsync(output.fileno())
        os.link(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def capture_prediction(
    *,
    bundle: Path,
    manifest_sha256: str,
    request_path: Path | None = None,
    request_bytes: bytes | None = None,
    enrollment_reference: str,
    fhfa_source: Path | None,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    predictor: Callable[..., dict[str, object]] = serving.predict,
    code_state: Callable[[], tuple[str, bool]] = _code_state,
    privacy_nonce_factory: Callable[[], str] = lambda: secrets.token_hex(32),
    private_root: Path | None = None,
) -> dict[str, object]:
    """Predict first, then exclusively publish one private receipt."""
    if REFERENCE_PATTERN.fullmatch(enrollment_reference) is None:
        raise ValueError("Enrollment reference must be 1-64 safe characters")
    if SHA256_PATTERN.fullmatch(manifest_sha256) is None:
        raise ValueError("Expected manifest SHA-256 is invalid")
    predicted_at = _timestamp(clock())
    before_state = code_state()
    if (request_path is None) == (request_bytes is None):
        raise ValueError("Provide exactly one request source")
    if request_bytes is None:
        raw_request, request = _read_request(Path(request_path))
    else:
        raw_request, request = _parse_request_bytes(request_bytes)
    response = _validate_response(
        predictor(bundle, request, manifest_sha256, fhfa_source), manifest_sha256
    )
    after_state = code_state()
    if before_state != after_state:
        raise ValueError("Code state changed during prediction")
    commit, dirty_tree = before_state
    if re.fullmatch(r"[0-9a-f]{40}", commit) is None or type(dirty_tree) is not bool:
        raise ValueError("Code state is invalid")
    request_canonical = canonical_bytes(request)
    response_canonical = canonical_bytes(response)
    request_digest = sha256(request_canonical).hexdigest()
    enrollment_digest = sha256(enrollment_reference.encode("utf-8")).hexdigest()
    privacy_nonce = privacy_nonce_factory()
    if (
        not isinstance(privacy_nonce, str)
        or SHA256_PATTERN.fullmatch(privacy_nonce) is None
    ):
        raise ValueError(
            "Privacy nonce must be 32 random bytes encoded as lowercase hex"
        )
    receipt_id = (
        predicted_at.replace("-", "").replace(":", "") + f"-{privacy_nonce[:24]}"
    )
    receipt: dict[str, object] = {
        "protocol": "king-research-prospective-receipt-v2",
        "receipt_id": receipt_id,
        "captured_at_utc": predicted_at,
        "timestamp_authority": "local_system_clock_untrusted",
        "external_timestamped": False,
        "scope": "prospective_research_observation",
        "integrity_limit": (
            "Local owner can modify or delete this capture; an external timestamp "
            "or commitment is required before certification."
        ),
        "request": request,
        "request_raw_utf8": raw_request.decode("utf-8"),
        "request_raw_sha256": sha256(raw_request).hexdigest(),
        "request_sha256": request_digest,
        "request_bytes": len(raw_request),
        "enrollment_reference_sha256": enrollment_digest,
        "privacy_nonce": privacy_nonce,
        "response_sha256": sha256(response_canonical).hexdigest(),
        "prediction": response,
        "manifest_sha256": response["manifest_sha256"],
        "model_sha256": response["model_sha256"],
        "code_commit": commit,
        "dirty_tree_at_capture": dirty_tree,
        "certification_eligible": False,
        "g_us_gate": "PENDING",
        "outcome_status": "pending",
    }
    _publish_receipt(receipt_id, receipt, private_root)
    return receipt


def prepare_private_root(private_root: Path | None = None) -> None:
    if private_root is not None:
        directory = Path(private_root)
        if directory.is_symlink():
            raise ValueError("Private prediction directory redirects")
        if directory.exists():
            real_directory(directory, directory.parent)
        else:
            real_directory(directory.parent, directory.parent.parent)
            directory.mkdir(mode=0o700)
            real_directory(directory, directory.parent)
        secure_directory(directory)
        verify_acl(directory)
        return
    for directory in (
        ROOT / "data/raw",
        ROOT / "data/raw/king",
        PRIVATE_ROOT,
    ):
        if directory.is_symlink():
            raise ValueError("Private prediction directory redirects")
        if not directory.exists():
            directory.mkdir(mode=0o700)
            secure_directory(directory)
        real_directory(directory, directory.parent)
    verify_acl(PRIVATE_ROOT)


def public_capture_result(receipt: Mapping[str, object]) -> dict[str, object]:
    """Return a non-sensitive acknowledgement safe for terminal output."""
    prediction = receipt["prediction"]
    if not isinstance(prediction, Mapping):
        raise ValueError("Receipt prediction is invalid")
    return {
        "receipt_id": receipt["receipt_id"],
        "captured_at_utc": receipt["captured_at_utc"],
        "scope": receipt["scope"],
        "status": prediction["status"],
        "amount": prediction["amount"],
        "currency": prediction["currency"],
        "manifest_sha256": receipt["manifest_sha256"],
        "model_sha256": receipt["model_sha256"],
        "dirty_tree_at_capture": receipt["dirty_tree_at_capture"],
        "certification_eligible": False,
        "g_us_gate": "PENDING",
        "integrity_limit": receipt["integrity_limit"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--enrollment-reference", required=True)
    parser.add_argument("--fhfa-source", type=Path)
    args = parser.parse_args()
    try:
        prepare_private_root()
        receipt = capture_prediction(
            bundle=args.bundle,
            manifest_sha256=args.manifest_sha256,
            request_path=args.request,
            enrollment_reference=args.enrollment_reference,
            fhfa_source=args.fhfa_source,
        )
    except (
        OSError,
        ValueError,
        TypeError,
        OverflowError,
        RecursionError,
        subprocess.SubprocessError,
    ) as error:
        print(f"King research prediction capture unavailable: {error}", file=sys.stderr)
        return 2
    print(json.dumps(public_capture_result(receipt), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
