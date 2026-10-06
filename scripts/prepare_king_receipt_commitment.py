"""Verify a private King receipt and prepare a PII-free public commitment."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
from typing import Callable, Mapping

from scripts import capture_king_prediction as capture


MAX_RECEIPT_BYTES = 32_000
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
COMMIT_PATTERN = re.compile(r"[0-9a-f]{40}\Z")
RECEIPT_KEYS = frozenset(
    {
        "protocol",
        "receipt_id",
        "captured_at_utc",
        "timestamp_authority",
        "external_timestamped",
        "scope",
        "integrity_limit",
        "request",
        "request_raw_utf8",
        "request_raw_sha256",
        "request_sha256",
        "request_bytes",
        "enrollment_reference_sha256",
        "privacy_nonce",
        "response_sha256",
        "prediction",
        "manifest_sha256",
        "model_sha256",
        "code_commit",
        "dirty_tree_at_capture",
        "certification_eligible",
        "g_us_gate",
        "outcome_status",
    }
)
RECEIPT_LITERALS = {
    "protocol": "king-research-prospective-receipt-v2",
    "timestamp_authority": "local_system_clock_untrusted",
    "external_timestamped": False,
    "scope": "prospective_research_observation",
    "integrity_limit": (
        "Local owner can modify or delete this capture; an external timestamp "
        "or commitment is required before certification."
    ),
    "certification_eligible": False,
    "g_us_gate": "PENDING",
    "outcome_status": "pending",
}
COMMITMENT_LIMIT = (
    "The prediction time uses an untrusted local clock. Repository publication "
    "can commit these bytes but does not certify accuracy, outcome maturity, or "
    "that the prediction preceded an unknown outcome."
)
canonical_bytes = capture.canonical_bytes


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate receipt field: {key}")
        result[key] = value
    return result


def _canonical_timestamp(moment: datetime) -> str:
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError("Commitment clock must be timezone-aware")
    return moment.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _parse_timestamp(value: object) -> str:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("Receipt timestamp is invalid")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise ValueError("Receipt timestamp is invalid") from error
    if _canonical_timestamp(parsed) != value:
        raise ValueError("Receipt timestamp is not canonical")
    return value


def _read_private_receipt(path: Path) -> tuple[bytes, dict[str, object]]:
    selected = Path(path)
    try:
        descriptor = os.open(
            selected,
            os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
        with os.fdopen(descriptor, "rb") as stream:
            opened = os.fstat(stream.fileno())
            current = os.stat(selected, follow_symlinks=False)
            if (
                not stat.S_ISREG(opened.st_mode)
                or not stat.S_ISREG(current.st_mode)
                or opened.st_nlink != 1
                or (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino)
            ):
                raise ValueError("Receipt must be one regular private file")
            raw = stream.read(MAX_RECEIPT_BYTES + 1)
    except OSError as error:
        raise ValueError("Private receipt could not be read") from error
    if not 0 < len(raw) <= MAX_RECEIPT_BYTES:
        raise ValueError("Private receipt size is invalid")
    try:
        receipt = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, ValueError, RecursionError) as error:
        raise ValueError("Private receipt JSON is invalid") from error
    if type(receipt) is not dict or raw != canonical_bytes(receipt):
        raise ValueError("Private receipt is not canonical")
    return raw, receipt


def _validate_receipt(receipt: Mapping[str, object]) -> None:
    if set(receipt) != RECEIPT_KEYS or any(
        receipt.get(key) != value for key, value in RECEIPT_LITERALS.items()
    ):
        raise ValueError("Private receipt schema or scope is incompatible")
    captured = _parse_timestamp(receipt["captured_at_utc"])
    hashes = (
        "request_raw_sha256",
        "request_sha256",
        "enrollment_reference_sha256",
        "response_sha256",
        "manifest_sha256",
        "model_sha256",
        "privacy_nonce",
    )
    if any(
        not isinstance(receipt.get(name), str)
        or SHA256_PATTERN.fullmatch(receipt[name]) is None
        for name in hashes
    ):
        raise ValueError("Private receipt hash is invalid")
    if (
        type(receipt.get("request_bytes")) is not int
        or not 0 < receipt["request_bytes"] <= capture.MAX_REQUEST_BYTES
        or not isinstance(receipt.get("request"), dict)
        or not isinstance(receipt.get("request_raw_utf8"), str)
        or not isinstance(receipt.get("prediction"), dict)
        or not isinstance(receipt.get("code_commit"), str)
        or COMMIT_PATTERN.fullmatch(receipt["code_commit"]) is None
        or type(receipt.get("dirty_tree_at_capture")) is not bool
    ):
        raise ValueError("Private receipt field type is invalid")
    try:
        raw_request = receipt["request_raw_utf8"].encode("utf-8")
        parsed_raw = json.loads(raw_request, object_pairs_hook=_unique_object)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as error:
        raise ValueError("Private receipt raw request is invalid") from error
    request_digest = sha256(canonical_bytes(receipt["request"])).hexdigest()
    response_digest = sha256(canonical_bytes(receipt["prediction"])).hexdigest()
    if (
        type(parsed_raw) is not dict
        or canonical_bytes(parsed_raw) != canonical_bytes(receipt["request"])
        or len(raw_request) != receipt["request_bytes"]
        or sha256(raw_request).hexdigest() != receipt["request_raw_sha256"]
        or request_digest != receipt["request_sha256"]
        or response_digest != receipt["response_sha256"]
    ):
        raise ValueError("Private receipt content hash mismatch")
    prediction = capture._validate_response(
        receipt["prediction"],
        receipt["manifest_sha256"],
        allow_legacy_absolute=True,
    )
    if (
        receipt["model_sha256"] != prediction["model_sha256"]
        or receipt["manifest_sha256"] != prediction["manifest_sha256"]
    ):
        raise ValueError("Private receipt model identity mismatch")
    expected_id = captured.replace("-", "").replace(":", "") + (
        f"-{str(receipt['privacy_nonce'])[:24]}"
    )
    if receipt["receipt_id"] != expected_id:
        raise ValueError("Private receipt identity mismatch")


def _real_output_directory(path: Path) -> Path:
    directory = Path(path)
    if not directory.is_dir() or directory.is_symlink():
        raise ValueError("Commitment output directory must be real")
    if directory.resolve(strict=True) != directory.absolute():
        raise ValueError("Commitment output directory redirects")
    return directory


def _publish(directory: Path, filename: str, content: bytes) -> None:
    destination = directory / filename
    if destination.parent != directory or destination.exists():
        raise FileExistsError("Public receipt commitment already exists")
    temporary: Path | None = None
    linked = False
    try:
        _real_output_directory(directory)
        with tempfile.NamedTemporaryFile(
            dir=directory, prefix=f".{filename}-", delete=False
        ) as output:
            temporary = Path(output.name)
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
            opened = os.fstat(output.fileno())
            current = os.stat(temporary, follow_symlinks=False)
            if not stat.S_ISREG(opened.st_mode) or (opened.st_dev, opened.st_ino) != (
                current.st_dev,
                current.st_ino,
            ):
                raise OSError("Public commitment staging identity changed")
            os.link(temporary, destination)
            linked = True
            published = os.stat(destination, follow_symlinks=False)
            if (opened.st_dev, opened.st_ino) != (
                published.st_dev,
                published.st_ino,
            ):
                raise OSError("Public commitment publication identity changed")
        if destination.read_bytes() != content:
            raise OSError("Public commitment verification failed")
    except Exception:
        if linked:
            destination.unlink(missing_ok=True)
        raise
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def prepare_public_commitment(
    receipt_path: Path,
    output_dir: Path,
    *,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> dict[str, object]:
    """Validate one private receipt and publish a nonce-hardened commitment."""
    raw, receipt = _read_private_receipt(receipt_path)
    _validate_receipt(receipt)
    receipt_digest = sha256(raw).hexdigest()
    result: dict[str, object] = {
        "protocol": "king-research-public-commitment-v1",
        "commitment_id": receipt_digest[:24],
        "committed_at_utc": _canonical_timestamp(clock()),
        "timestamp_authority": "local_system_clock_untrusted",
        "external_timestamped": False,
        "scope": "public_integrity_commitment_only",
        "receipt_sha256": receipt_digest,
        "receipt_bytes": len(raw),
        "manifest_sha256": receipt["manifest_sha256"],
        "model_sha256": receipt["model_sha256"],
        "code_commit": receipt["code_commit"],
        "dirty_tree_at_capture": receipt["dirty_tree_at_capture"],
        "certification_eligible": False,
        "g_us_gate": "PENDING",
        "outcome_status": "pending",
        "property_inputs_published": False,
        "integrity_limit": COMMITMENT_LIMIT,
    }
    directory = _real_output_directory(output_dir)
    filename = f"king-research-commitment-{receipt_digest}.json"
    _publish(directory, filename, canonical_bytes(result))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = prepare_public_commitment(args.receipt, args.output_dir)
    except (OSError, ValueError, TypeError, OverflowError, RecursionError):
        print("Public King receipt commitment unavailable.", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
