"""Issue one King research prediction, private receipt, and public commitment."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import stat
from types import MappingProxyType
from typing import Callable, Mapping

from scripts import capture_king_prediction as capture
from scripts import prepare_king_receipt_commitment as commitment


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_OUTPUT_DIR = ROOT / "runs/king-prospective-commitments-v1"
PUBLIC_COMMITMENT_KEYS = frozenset(
    {
        "protocol",
        "commitment_id",
        "committed_at_utc",
        "timestamp_authority",
        "external_timestamped",
        "scope",
        "receipt_sha256",
        "receipt_bytes",
        "manifest_sha256",
        "model_sha256",
        "code_commit",
        "dirty_tree_at_capture",
        "certification_eligible",
        "g_us_gate",
        "outcome_status",
        "property_inputs_published",
        "integrity_limit",
    }
)


@dataclass(frozen=True)
class EnrollmentResult:
    """Paths and immutable result data for one enrollment operation."""

    receipt_path: Path
    commitment_path: Path
    prediction: Mapping[str, object] | None
    commitment: Mapping[str, object]


class EnrollmentCommitmentPending(RuntimeError):
    """The private prediction is durable but its public commitment is pending."""

    def __init__(self, receipt_path: Path) -> None:
        super().__init__(
            "Private prediction receipt saved; public commitment is pending"
        )
        self.receipt_path = Path(receipt_path)


def _real_directory(path: Path, description: str) -> Path:
    directory = Path(path)
    if (
        not directory.is_dir()
        or directory.is_symlink()
        or directory.resolve(strict=True) != directory.absolute()
    ):
        raise ValueError(f"{description} must be a real directory")
    return directory


def _request_snapshot(request: Mapping[str, object]) -> bytes:
    """Create immutable canonical bytes submitted to the receipt contract."""
    content = capture.canonical_bytes(dict(request))
    if not 0 < len(content) <= capture.MAX_REQUEST_BYTES:
        raise ValueError("Request snapshot exceeds the size limit")
    return content


def _freeze_json(value: object) -> object:
    if isinstance(value, dict):
        return MappingProxyType(
            {str(key): _freeze_json(item) for key, item in value.items()}
        )
    if isinstance(value, list):
        return tuple(_freeze_json(item) for item in value)
    return value


def _freeze_mapping(value: Mapping[str, object]) -> Mapping[str, object]:
    frozen = _freeze_json(dict(value))
    if not isinstance(frozen, Mapping):
        raise TypeError("Frozen result must remain a mapping")
    return frozen


def _commitment_path(public_output_dir: Path, prepared: Mapping[str, object]) -> Path:
    digest = prepared.get("receipt_sha256")
    if not isinstance(digest, str) or capture.SHA256_PATTERN.fullmatch(digest) is None:
        raise ValueError("Public commitment identity is invalid")
    path = public_output_dir / f"king-research-commitment-{digest}.json"
    if not path.is_file() or path.is_symlink():
        raise OSError("Public commitment was not published")
    return path


def _read_regular_file(path: Path, maximum_bytes: int) -> bytes:
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
                or opened.st_nlink != 1
                or (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino)
            ):
                raise ValueError("Commitment must be one regular file")
            raw = stream.read(maximum_bytes + 1)
    except OSError as error:
        raise ValueError("Commitment could not be read") from error
    if not 0 < len(raw) <= maximum_bytes:
        raise ValueError("Commitment size is invalid")
    return raw


def _existing_commitment(
    receipt_path: Path, public_output_dir: Path
) -> tuple[Path, dict[str, object]] | None:
    raw_receipt, receipt = commitment._read_private_receipt(receipt_path)
    commitment._validate_receipt(receipt)
    digest = sha256(raw_receipt).hexdigest()
    path = public_output_dir / f"king-research-commitment-{digest}.json"
    if not path.exists():
        return None
    raw = _read_regular_file(path, commitment.MAX_RECEIPT_BYTES)
    try:
        published = json.loads(
            raw.decode("utf-8"), object_pairs_hook=commitment._unique_object
        )
    except (UnicodeError, ValueError, RecursionError) as error:
        raise ValueError("Existing public commitment is invalid") from error
    expected = {
        "protocol": "king-research-public-commitment-v1",
        "commitment_id": digest[:24],
        "timestamp_authority": "local_system_clock_untrusted",
        "external_timestamped": False,
        "scope": "public_integrity_commitment_only",
        "receipt_sha256": digest,
        "receipt_bytes": len(raw_receipt),
        "manifest_sha256": receipt["manifest_sha256"],
        "model_sha256": receipt["model_sha256"],
        "code_commit": receipt["code_commit"],
        "dirty_tree_at_capture": receipt["dirty_tree_at_capture"],
        "certification_eligible": False,
        "g_us_gate": "PENDING",
        "outcome_status": "pending",
        "property_inputs_published": False,
        "integrity_limit": commitment.COMMITMENT_LIMIT,
    }
    if (
        type(published) is not dict
        or set(published) != PUBLIC_COMMITMENT_KEYS
        or any(published.get(key) != value for key, value in expected.items())
        or raw != commitment.canonical_bytes(published)
    ):
        raise ValueError("Existing public commitment conflicts with receipt")
    commitment._parse_timestamp(published.get("committed_at_utc"))
    return path, published


def _result(
    receipt_path: Path,
    commitment_path: Path,
    prediction: Mapping[str, object] | None,
    prepared: Mapping[str, object],
) -> EnrollmentResult:
    frozen_prediction = None if prediction is None else _freeze_mapping(prediction)
    frozen_commitment = _freeze_mapping(prepared)
    return EnrollmentResult(
        receipt_path=Path(receipt_path),
        commitment_path=Path(commitment_path),
        prediction=frozen_prediction,
        commitment=frozen_commitment,
    )


def commit_saved_receipt(
    receipt_path: Path,
    public_output_dir: Path = PUBLIC_OUTPUT_DIR,
    *,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> EnrollmentResult:
    """Publish or verify a commitment without predicting again."""
    directory = _real_directory(public_output_dir, "Commitment output directory")
    existing = _existing_commitment(Path(receipt_path), directory)
    if existing is not None:
        path, prepared = existing
        return _result(receipt_path, path, None, prepared)
    try:
        prepared = commitment.prepare_public_commitment(
            Path(receipt_path), directory, clock=clock
        )
    except FileExistsError:
        existing = _existing_commitment(Path(receipt_path), directory)
        if existing is None:
            raise
        path, prepared = existing
        return _result(receipt_path, path, None, prepared)
    return _result(
        receipt_path,
        _commitment_path(directory, prepared),
        None,
        prepared,
    )


def verify_commitment_result(result: object, expected_receipt: Path | None) -> bool:
    """Verify a retry result against both canonical artifacts on disk."""
    if (
        not isinstance(result, EnrollmentResult)
        or expected_receipt is None
        or result.receipt_path != expected_receipt
    ):
        return False
    try:
        directory = _real_directory(
            result.commitment_path.parent, "Commitment output directory"
        )
        existing = _existing_commitment(expected_receipt, directory)
    except (OSError, ValueError, TypeError, KeyError, IndexError):
        return False
    if existing is None:
        return False
    path, prepared = existing
    return path == result.commitment_path and dict(result.commitment) == prepared


def find_pending_receipts(
    private_root: Path = capture.PRIVATE_ROOT,
    public_output_dir: Path = PUBLIC_OUTPUT_DIR,
) -> tuple[Path, ...]:
    """Return validated receipts lacking a matching verified commitment."""
    capture.prepare_private_root(private_root)
    private_directory = _real_directory(private_root, "Private prediction directory")
    public_directory = _real_directory(public_output_dir, "Commitment output directory")
    pending = []
    for receipt_path in sorted(private_directory.glob("*.json")):
        _raw, candidate = commitment._read_private_receipt(receipt_path)
        protocol = candidate.get("protocol")
        if protocol == "king-research-prospective-receipt-v1":
            continue
        if protocol != "king-research-prospective-receipt-v2":
            raise ValueError("Private receipt protocol is unknown")
        if _existing_commitment(receipt_path, public_directory) is None:
            pending.append(receipt_path)
    return tuple(pending)


def enroll_prediction(
    *,
    bundle: Path,
    manifest_sha256: str,
    request: Mapping[str, object],
    enrollment_reference: str,
    fhfa_source: Path | None,
    private_root: Path = capture.PRIVATE_ROOT,
    public_output_dir: Path = PUBLIC_OUTPUT_DIR,
    predictor: Callable[[Mapping[str, object]], dict[str, object]],
    code_state: Callable[[], tuple[str, bool]] = capture._code_state,
    capture_clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    commitment_clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    privacy_nonce_factory: Callable[[], str] = lambda: capture.secrets.token_hex(32),
) -> EnrollmentResult:
    """Predict exactly once, save its private receipt, then publish commitment."""
    capture.prepare_private_root(private_root)
    private_directory = _real_directory(private_root, "Private prediction directory")
    public_directory = _real_directory(public_output_dir, "Commitment output directory")
    request_bytes = _request_snapshot(request)

    def loaded_predictor(
        _bundle: Path,
        submitted: Mapping[str, object],
        _manifest_sha256: str,
        _fhfa_source: Path | None,
    ) -> dict[str, object]:
        return predictor(dict(submitted))

    receipt = capture.capture_prediction(
        bundle=bundle,
        manifest_sha256=manifest_sha256,
        request_bytes=request_bytes,
        enrollment_reference=enrollment_reference,
        fhfa_source=fhfa_source,
        clock=capture_clock,
        predictor=loaded_predictor,
        code_state=code_state,
        privacy_nonce_factory=privacy_nonce_factory,
        private_root=private_directory,
    )
    receipt_path = private_directory / f"{receipt['receipt_id']}.json"
    try:
        prepared = commitment.prepare_public_commitment(
            receipt_path, public_directory, clock=commitment_clock
        )
        prepared_path = _commitment_path(public_directory, prepared)
    except Exception as error:
        raise EnrollmentCommitmentPending(receipt_path) from error
    return _result(
        receipt_path,
        prepared_path,
        receipt["prediction"],
        prepared,
    )
