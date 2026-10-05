"""Create one private, non-attested HCPA property-record comparison candidate."""

from __future__ import annotations

import argparse
from datetime import datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
from typing import Any

from scripts.hcpa_property_record_pdf import (
    compare_sample_row,
    extract_ordered_fields,
)
from scripts.private_review_io import verify_acl


PRIVATE_ROOT = Path(__file__).resolve().parents[1] / "data" / "raw" / "hcpa"
PROTOCOL = "hcpa-property-record-candidate-v1"
AGGREGATE_PROTOCOL = "hcpa-property-record-candidate-aggregate-v1"
MAX_PRIVATE_BYTES = 10_000_000
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
STATE_FIELDS = (
    "document_identity",
    "parcel_unit_identity",
    "property_class",
    "qualification_code",
)
REQUIRED_ROW_FIELDS = frozenset(("record_ordinal", "PIN", "DOC_NUM", "DOR_CODE", "QU"))
CANDIDATE_KEYS = frozenset(
    {
        "protocol",
        "pdf_sha256",
        "pdf_bytes",
        "sample_sha256",
        "sample_bytes",
        "record_ordinal",
        "observed_at",
        *STATE_FIELDS,
        "candidate_only",
        "attested",
        "ledger_appended",
        "model_eligible",
        "date_semantics",
        "consideration_scope",
        "historical_availability",
        "reuse_rights",
    }
)


def _valid_hash(value: object) -> bool:
    return isinstance(value, str) and HEX64.fullmatch(value) is not None


def _utc_timestamp(value: object) -> bool:
    if not isinstance(value, str) or not value.endswith("Z"):
        return False
    try:
        parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError:
        return False
    return parsed.utcoffset() is not None and parsed.utcoffset().total_seconds() == 0


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Private JSONL contains a duplicate key")
        result[key] = value
    return result


def _sample_row(
    sample_bytes: bytes, sample_sha256: str, record_ordinal: int
) -> dict[str, Any]:
    if (
        not _valid_hash(sample_sha256)
        or sha256(sample_bytes).hexdigest() != sample_sha256
    ):
        raise ValueError("Frozen sample hash mismatch")
    if type(record_ordinal) is not int or record_ordinal <= 0:
        raise ValueError("Record ordinal must be a positive integer")
    if not sample_bytes or not sample_bytes.endswith(b"\n"):
        raise ValueError("Frozen sample must be newline-terminated JSONL")
    try:
        rows = [
            json.loads(line, object_pairs_hook=_strict_object)
            for line in sample_bytes.decode("utf-8").splitlines()
        ]
    except (UnicodeError, json.JSONDecodeError, RecursionError) as error:
        raise ValueError("Frozen sample is malformed JSONL") from error
    if any(not isinstance(row, dict) for row in rows):
        raise ValueError("Frozen sample rows must be objects")
    matches = [row for row in rows if row.get("record_ordinal") == record_ordinal]
    if len(matches) != 1:
        raise ValueError("Frozen sample must contain exactly one target record")
    row = matches[0]
    if not REQUIRED_ROW_FIELDS.issubset(row) or any(
        not isinstance(row[field], str)
        for field in ("PIN", "DOC_NUM", "DOR_CODE", "QU")
    ):
        raise ValueError("Frozen sample target lacks required fields")
    if type(row["record_ordinal"]) is not int or row["record_ordinal"] <= 0:
        raise ValueError("Frozen sample target has an invalid ordinal")
    return row


def build_candidate(
    *,
    pdf_bytes: bytes,
    pdf_sha256: str,
    sample_bytes: bytes,
    sample_sha256: str,
    record_ordinal: int,
    observed_at: str,
) -> dict[str, object]:
    """Build a private candidate without attesting or changing a review ledger."""
    if not _valid_hash(pdf_sha256) or sha256(pdf_bytes).hexdigest() != pdf_sha256:
        raise ValueError("Property-record PDF hash mismatch")
    if not _utc_timestamp(observed_at):
        raise ValueError("Observation time must be an exact UTC timestamp")
    row = _sample_row(sample_bytes, sample_sha256, record_ordinal)
    fields = extract_ordered_fields(
        pdf_bytes,
        expected_sha256=pdf_sha256,
        max_pdf_bytes=MAX_PRIVATE_BYTES,
        max_decoded_bytes=MAX_PRIVATE_BYTES,
    )
    comparison = compare_sample_row(row, fields)
    return {
        "protocol": PROTOCOL,
        "pdf_sha256": pdf_sha256,
        "pdf_bytes": len(pdf_bytes),
        "sample_sha256": sample_sha256,
        "sample_bytes": len(sample_bytes),
        "record_ordinal": record_ordinal,
        "observed_at": observed_at,
        **{field: comparison[field] for field in STATE_FIELDS},
        "candidate_only": True,
        "attested": False,
        "ledger_appended": False,
        "model_eligible": False,
        "date_semantics": "unknown",
        "consideration_scope": "unknown",
        "historical_availability": "unknown",
        "reuse_rights": "unknown",
    }


def canonical_bytes(candidate: dict[str, object]) -> bytes:
    """Return the stable private serialization."""
    _validate_candidate(candidate)
    return (json.dumps(candidate, sort_keys=True, separators=(",", ":")) + "\n").encode(
        "utf-8"
    )


def _validate_candidate(candidate: object) -> dict[str, object]:
    if not isinstance(candidate, dict) or set(candidate) != CANDIDATE_KEYS:
        raise ValueError("Private candidate schema is invalid")
    if (
        candidate["protocol"] != PROTOCOL
        or not _valid_hash(candidate["pdf_sha256"])
        or not _valid_hash(candidate["sample_sha256"])
        or not _utc_timestamp(candidate["observed_at"])
        or any(
            type(candidate[field]) is not int or candidate[field] <= 0
            for field in ("pdf_bytes", "sample_bytes", "record_ordinal")
        )
        or any(
            candidate[field] not in ("match", "mismatch", "unknown")
            for field in STATE_FIELDS
        )
        or candidate["candidate_only"] is not True
        or any(
            candidate[field] is not False
            for field in ("attested", "ledger_appended", "model_eligible")
        )
        or any(
            candidate[field] != "unknown"
            for field in (
                "date_semantics",
                "consideration_scope",
                "historical_availability",
                "reuse_rights",
            )
        )
    ):
        raise ValueError("Private candidate values are invalid")
    return candidate


def _real_root(root: Path) -> Path:
    if not root.is_dir() or root.is_symlink():
        raise ValueError("Private root must be a real directory")
    resolved = root.resolve(strict=True)
    if os.path.normcase(str(root.absolute())) != os.path.normcase(str(resolved)):
        raise ValueError("Private root redirects")
    verify_acl(root)
    return resolved


def _private_path(path: Path, root: Path, *, existing: bool) -> Path:
    root_resolved = _real_root(root)
    if (
        not path.parent.is_dir()
        or path.parent.is_symlink()
        or path.parent.resolve(strict=True) != root_resolved
    ):
        raise ValueError("Private path parent is invalid")
    resolved = path.resolve(strict=existing)
    if not resolved.is_relative_to(root_resolved):
        raise ValueError("Private path escapes the approved root")
    if path.is_symlink() or (path.exists() and path.stat().st_nlink != 1):
        raise ValueError("Private path may not be linked")
    if existing and not path.is_file():
        raise ValueError("Private input is not a regular file")
    return path


def _read_pinned_private(path: Path, expected_hash: str, root: Path) -> bytes:
    if not _valid_hash(expected_hash):
        raise ValueError("Expected hash must be lowercase SHA-256")
    _private_path(path, root, existing=True)
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
            or not 0 < opened.st_size <= MAX_PRIVATE_BYTES
        ):
            raise ValueError("Private input exceeds its file or size contract")
        named = path.stat()
        if (opened.st_dev, opened.st_ino) != (named.st_dev, named.st_ino):
            raise ValueError("Private input changed while opening")
        chunks = []
        remaining = MAX_PRIVATE_BYTES + 1
        while remaining:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        content = b"".join(chunks)
        opened_after = os.fstat(descriptor)
        named_after = path.stat()
        if (
            (opened.st_dev, opened.st_ino, opened.st_size)
            != (opened_after.st_dev, opened_after.st_ino, opened_after.st_size)
            or (opened.st_dev, opened.st_ino)
            != (named_after.st_dev, named_after.st_ino)
            or len(content) != opened.st_size
            or len(content) > MAX_PRIVATE_BYTES
        ):
            raise ValueError("Private input changed while reading")
    finally:
        os.close(descriptor)
    if sha256(content).hexdigest() != expected_hash:
        raise ValueError("Private input hash mismatch")
    return content


def write_private_candidate_new(
    path: Path, candidate: dict[str, object], private_root: Path = PRIVATE_ROOT
) -> None:
    """Create one private candidate without replacing an existing artifact."""
    _private_path(path, private_root, existing=False)
    content = canonical_bytes(candidate)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "wb", dir=path.parent, prefix=f".{path.name}-", suffix=".tmp", delete=False
        ) as destination:
            temporary_path = Path(destination.name)
            destination.write(content)
            destination.flush()
            os.fsync(destination.fileno())
        os.link(temporary_path, path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def aggregate_candidate(candidate: dict[str, object]) -> dict[str, object]:
    """Return aggregate counts with no ordinal, time, path or source values."""
    _validate_candidate(candidate)
    states: dict[str, dict[str, int]] = {}
    for field in STATE_FIELDS:
        value = candidate.get(field)
        if value not in ("match", "mismatch", "unknown"):
            raise ValueError("Candidate contains an invalid comparison state")
        states[field] = {
            state: int(value == state) for state in ("match", "mismatch", "unknown")
        }
    return {
        "protocol": AGGREGATE_PROTOCOL,
        "candidate_protocol": candidate["protocol"],
        "sample_sha256": candidate["sample_sha256"],
        "sample_bytes": candidate["sample_bytes"],
        "candidate_count": 1,
        "state_counts": states,
    }


def _write_public_new(path: Path, aggregate: dict[str, object]) -> None:
    if not path.parent.is_dir() or path.is_symlink():
        raise ValueError("Aggregate destination is invalid")
    content = (json.dumps(aggregate, indent=2, sort_keys=True) + "\n").encode("utf-8")
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "wb", dir=path.parent, prefix=f".{path.name}-", suffix=".tmp", delete=False
        ) as destination:
            temporary_path = Path(destination.name)
            destination.write(content)
            destination.flush()
            os.fsync(destination.fileno())
        os.link(temporary_path, path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _ensure_private_candidate(
    path: Path, candidate: dict[str, object], private_root: Path
) -> None:
    content = canonical_bytes(candidate)
    if path.exists():
        existing = _read_pinned_private(path, sha256(content).hexdigest(), private_root)
        if existing != content:
            raise FileExistsError("Private candidate differs from requested candidate")
        return
    write_private_candidate_new(path, candidate, private_root)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("build",))
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--pdf-sha256", required=True)
    parser.add_argument("--sample", type=Path, required=True)
    parser.add_argument("--sample-sha256", required=True)
    parser.add_argument("--record-ordinal", type=int, required=True)
    parser.add_argument("--observed-at", required=True)
    parser.add_argument("--private-output", type=Path, required=True)
    parser.add_argument("--aggregate-output", type=Path, required=True)
    options = parser.parse_args(argv)
    try:
        pdf = _read_pinned_private(options.pdf, options.pdf_sha256, PRIVATE_ROOT)
        sample = _read_pinned_private(
            options.sample, options.sample_sha256, PRIVATE_ROOT
        )
        candidate = build_candidate(
            pdf_bytes=pdf,
            pdf_sha256=options.pdf_sha256,
            sample_bytes=sample,
            sample_sha256=options.sample_sha256,
            record_ordinal=options.record_ordinal,
            observed_at=options.observed_at,
        )
        aggregate = aggregate_candidate(candidate)
        _ensure_private_candidate(options.private_output, candidate, PRIVATE_ROOT)
        _write_public_new(options.aggregate_output, aggregate)
    except (FileExistsError, OSError, ValueError):
        print("HCPA property-record candidate is unavailable", file=sys.stderr)
        return 2
    print(json.dumps(aggregate, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
