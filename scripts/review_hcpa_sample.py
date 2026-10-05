"""Append private HCPA source reviews; emit only aggregate audit counts.

The frozen sample and this ledger contain source identifiers. Both must remain
under Git-ignored data/raw/hcpa. A completed review may explicitly conclude
"unknown" when the checked evidence cannot establish a fact.

If a hard kill leaves LEDGER.jsonl.lock, inspect its PID, hostname and creation
time. Verify that process has exited on that host and no review job is using the
ledger, then manually remove only that lock file. Never clear a lock based on age
alone. Replay the exact private entry with the CLI if a summary write failed;
changed duplicate entry IDs are rejected.

The private directory is assumed to be writable only by trusted local
processes while this command runs. Static path and link checks do not protect
against a concurrent same-privilege process swapping a directory junction.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import socket
import sys
import tempfile
from typing import Iterator
from urllib.parse import urlsplit


PRIVATE_ROOT = Path(__file__).resolve().parents[1] / "data" / "raw" / "hcpa"
PROTOCOL_VERSION = "hcpa-review-v1"
MAX_PRIVATE_FILE_BYTES = 10_000_000
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
CODE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,63}\Z")
DATE_VALUES = {"before", "same", "after", "unknown", "not_applicable"}
REQUIRED_DIMENSIONS = {
    "document_identity": {"match", "mismatch", "unknown", "not_applicable"},
    "parcel_unit_identity": {"match", "mismatch", "unknown", "not_applicable"},
    "date_vs_deed_execution": DATE_VALUES,
    "date_vs_recording": DATE_VALUES,
    "date_vs_closing": DATE_VALUES,
    "price_scope": {
        "single_property",
        "multi_property",
        "partial_interest",
        "other",
        "unknown",
    },
    "property_class": {
        "single_family",
        "condominium",
        "small_multifamily",
        "manufactured",
        "other_residential",
        "nonresidential",
        "vacant_land",
        "unknown",
    },
    "qualification_code": {"corroborated", "conflicting", "unknown", "not_applicable"},
    "reason_code": {"corroborated", "conflicting", "unknown", "not_applicable"},
    "multi_parcel_consideration": {
        "single_parcel_confirmed",
        "multiple_parcels",
        "unknown",
    },
    "missing_fields": {
        "none_in_checked_sources",
        "critical_missing",
        "noncritical_missing",
        "unknown",
    },
    "duplicate_status": {"no_duplicate_in_checked_sources", "duplicate", "unknown"},
    "evidence_quality": {"high", "medium", "low", "unknown"},
    "reuse_rights": {"permitted", "restricted", "unknown"},
}
EVIDENCE_KINDS = {
    "source_record",
    "clerk_index",
    "clerk_instrument",
    "closing_record",
    "rights_document",
    "official_documentation",
    "hcpa_property_record",
    "unavailable_attempt",
}
SPECIAL_EVIDENCE = {
    "document_identity": {
        "clerk_index",
        "clerk_instrument",
        "hcpa_property_record",
    },
    "parcel_unit_identity": {
        "clerk_index",
        "clerk_instrument",
        "hcpa_property_record",
    },
    "date_vs_deed_execution": {"clerk_instrument"},
    "date_vs_recording": {"clerk_index", "clerk_instrument"},
    "date_vs_closing": {"closing_record"},
    "price_scope": {"clerk_instrument"},
    "property_class": {
        "clerk_index",
        "clerk_instrument",
        "hcpa_property_record",
    },
    "qualification_code": {"official_documentation", "hcpa_property_record"},
    "reason_code": {"official_documentation"},
    "multi_parcel_consideration": {"clerk_instrument"},
    "reuse_rights": {"rights_document"},
}
ENTRY_KEYS = {
    "entry_id",
    "sample_sha256",
    "record_ordinal",
    "revision",
    "supersedes_entry_id",
    "review_status",
    "reviewer_code",
    "reviewed_at",
    "attested",
    "evidence",
    "rubric",
}


def _sha256(data: bytes) -> str:
    return sha256(data).hexdigest()


def _write_all(descriptor: int, content: bytes) -> None:
    offset = 0
    while offset < len(content):
        written = os.write(descriptor, content[offset:])
        if written <= 0:
            raise OSError("Private audit write made no progress")
        offset += written


def _private_path(path: Path) -> Path:
    path = Path(path)
    if not PRIVATE_ROOT.is_dir() or PRIVATE_ROOT.is_symlink():
        raise ValueError("Private HCPA root must be a real directory")
    root_real = PRIVATE_ROOT.resolve(strict=True)
    if os.path.normcase(str(PRIVATE_ROOT.absolute())) != os.path.normcase(
        str(root_real)
    ):
        raise ValueError("Private HCPA root or ancestor redirects")
    if not path.parent.is_dir():
        raise ValueError("Private file parent directory does not exist")
    resolved = path.resolve()
    if not resolved.is_relative_to(root_real):
        raise ValueError("Path must stay inside the private HCPA directory")
    if path.is_symlink() or os.path.normcase(str(path.absolute())) != os.path.normcase(
        str(resolved)
    ):
        raise ValueError("Private file or ancestor redirects through a symlink")
    if path.exists() and not path.is_file():
        raise ValueError("Private path is not a regular file")
    if path.exists() and path.stat().st_nlink > 1:
        raise ValueError("Private file must not be a hard link")
    return path


def _read_bytes(path: Path) -> bytes:
    if path.stat().st_size > MAX_PRIVATE_FILE_BYTES:
        raise ValueError("Private file exceeds review size limit")
    return path.read_bytes()


def _json_lines(data: bytes, description: str) -> list[dict]:
    if data and not data.endswith(b"\n"):
        raise ValueError(f"Malformed {description}: missing final newline")
    try:
        rows = [json.loads(line) for line in data.decode("utf-8").splitlines()]
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"Malformed {description}") from error
    if not all(isinstance(row, dict) for row in rows):
        raise ValueError(f"Malformed {description}: expected JSON objects")
    return rows


def _sample_ordinals(sample: Path, expected_sha256: str) -> set[int]:
    if not isinstance(expected_sha256, str) or not HEX64.fullmatch(expected_sha256):
        raise ValueError("Expected sample hash must be lowercase SHA-256")
    data = _read_bytes(sample)
    if _sha256(data) != expected_sha256:
        raise ValueError("Frozen sample hash mismatch")
    rows = _json_lines(data, "sample")
    ordinals = [row.get("record_ordinal") for row in rows]
    if not ordinals or any(type(item) is not int or item < 1 for item in ordinals):
        raise ValueError("Malformed sample ordinals")
    if len(set(ordinals)) != len(ordinals):
        raise ValueError("Malformed sample: repeated ordinals")
    return set(ordinals)


def _utc_timestamp(value: object) -> bool:
    if not isinstance(value, str) or not value.endswith("Z"):
        return False
    try:
        parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError:
        return False
    return parsed.utcoffset().total_seconds() == 0


def _validate_evidence(evidence: object, sample_sha256: str) -> dict[str, str]:
    if not isinstance(evidence, dict) or set(evidence) != {
        "evidence_id",
        "kind",
        "reference",
        "observed_at",
    }:
        raise ValueError("Invalid evidence fields")
    identifier, kind = evidence["evidence_id"], evidence["kind"]
    if not isinstance(identifier, str) or not CODE.fullmatch(identifier):
        raise ValueError("Invalid evidence identifier")
    if (
        not isinstance(kind, str)
        or kind not in EVIDENCE_KINDS
        or not _utc_timestamp(evidence["observed_at"])
    ):
        raise ValueError("Invalid evidence type or observation time")
    reference = evidence["reference"]
    if not isinstance(reference, str) or len(reference) > 2048:
        raise ValueError("Invalid evidence reference")
    if kind == "source_record":
        if not reference.startswith("sha256:") or not HEX64.fullmatch(reference[7:]):
            raise ValueError("Invalid evidence source checksum")
        if reference[7:] != sample_sha256:
            raise ValueError("HCPA evidence must reference the frozen sample hash")
    else:
        try:
            url = urlsplit(reference)
            hostname = url.hostname
            username = url.username
            password = url.password
            port = url.port
        except ValueError as error:
            raise ValueError("Invalid evidence HTTPS reference") from error
        if (
            url.scheme != "https"
            or not hostname
            or username is not None
            or password is not None
        ):
            raise ValueError("Invalid evidence HTTPS reference")
        if kind == "hcpa_property_record" and (
            hostname != "gis.hcpafl.org"
            or port is not None
            or url.path != "/PropertySearch/"
            or url.query
            or re.fullmatch(
                r"/parcel/basic/[0-9]{6}[A-Z0-9]{3}[0-9]{12}[A-Z]",
                url.fragment,
            )
            is None
        ):
            raise ValueError("Invalid HCPA property-record evidence")
    return evidence


def _validate_rubric(rubric: object, evidence: dict[str, dict]) -> None:
    if (
        not isinstance(rubric, dict)
        or not rubric
        or not set(rubric) <= REQUIRED_DIMENSIONS.keys()
    ):
        raise ValueError("Invalid review rubric")
    for dimension, finding in rubric.items():
        if not isinstance(finding, dict) or set(finding) != {
            "value",
            "evidence_ids",
            "limitation",
        }:
            raise ValueError("Invalid review rubric finding")
        value = finding["value"]
        refs = finding["evidence_ids"]
        limitation = finding["limitation"]
        if not isinstance(value, str) or value not in REQUIRED_DIMENSIONS[dimension]:
            raise ValueError("Invalid review rubric value")
        if (
            not isinstance(refs, list)
            or not refs
            or any(not isinstance(ref, str) or ref not in evidence for ref in refs)
        ):
            raise ValueError("Review rubric contains an invalid evidence reference")
        if value == "unknown" and (
            not isinstance(limitation, str) or not limitation.strip()
        ):
            raise ValueError("An unknown review finding needs a limitation")
        if limitation is not None and (
            not isinstance(limitation, str) or len(limitation) > 2000
        ):
            raise ValueError("Invalid review rubric limitation")
        required_kinds = SPECIAL_EVIDENCE.get(dimension)
        if (
            value not in {"unknown", "not_applicable"}
            and required_kinds
            and not any(evidence[ref]["kind"] in required_kinds for ref in refs)
        ):
            raise ValueError("Review conclusion needs source-specific evidence")


def _validate_entry(entry: object, sample_sha256: str, ordinals: set[int]) -> dict:
    if not isinstance(entry, dict) or set(entry) != ENTRY_KEYS:
        raise ValueError("Invalid review entry fields")
    if entry["sample_sha256"] != sample_sha256:
        raise ValueError("Review sample hash mismatch")
    if (
        type(entry["record_ordinal"]) is not int
        or entry["record_ordinal"] not in ordinals
    ):
        raise ValueError("Review references an unsampled ordinal")
    if not isinstance(entry["entry_id"], str) or not CODE.fullmatch(entry["entry_id"]):
        raise ValueError("Invalid review entry identifier")
    if type(entry["revision"]) is not int or entry["revision"] < 1:
        raise ValueError("Invalid review revision")
    if entry["supersedes_entry_id"] is not None and (
        not isinstance(entry["supersedes_entry_id"], str)
        or not CODE.fullmatch(entry["supersedes_entry_id"])
    ):
        raise ValueError("Invalid review supersession identifier")
    if not isinstance(entry["review_status"], str) or entry["review_status"] not in {
        "partial",
        "complete",
    }:
        raise ValueError("Invalid review status")
    if not isinstance(entry["reviewer_code"], str) or not CODE.fullmatch(
        entry["reviewer_code"]
    ):
        raise ValueError("Invalid reviewer code")
    if not _utc_timestamp(entry["reviewed_at"]) or type(entry["attested"]) is not bool:
        raise ValueError("Invalid review attestation")
    reviewed_at = datetime.fromisoformat(
        entry["reviewed_at"].removesuffix("Z") + "+00:00"
    )
    sources = entry["evidence"]
    if not isinstance(sources, list) or not sources:
        raise ValueError("Review needs evidence")
    validated = [_validate_evidence(source, sample_sha256) for source in sources]
    if any(
        datetime.fromisoformat(source["observed_at"].removesuffix("Z") + "+00:00")
        > reviewed_at
        for source in validated
    ):
        raise ValueError("Source evidence must be observed by review time")
    evidence = {source["evidence_id"]: source for source in validated}
    if len(evidence) != len(validated):
        raise ValueError("Duplicate evidence identifiers")
    _validate_rubric(entry["rubric"], evidence)
    if entry["review_status"] == "complete":
        if set(entry["rubric"]) != REQUIRED_DIMENSIONS.keys():
            raise ValueError("A complete review needs every rubric dimension")
        if not entry["attested"]:
            raise ValueError("A complete review needs reviewer attestation")
        evidence_kinds = {source["kind"] for source in validated}
        if "source_record" not in evidence_kinds:
            raise ValueError("A complete review needs HCPA source evidence")
        if not evidence_kinds & {
            "clerk_index",
            "clerk_instrument",
            "unavailable_attempt",
        }:
            raise ValueError(
                "A complete review needs Clerk evidence or an access attempt"
            )
    return entry


def _reject_future_review(entry: dict) -> None:
    reviewed_at = datetime.fromisoformat(
        entry["reviewed_at"].removesuffix("Z") + "+00:00"
    )
    if reviewed_at > datetime.now(timezone.utc):
        raise ValueError("Review time cannot be in the future")


def _validate_history(
    entries: list[dict], sample_sha256: str, ordinals: set[int]
) -> dict[int, dict]:
    latest: dict[int, dict] = {}
    identifiers: set[str] = set()
    for entry in entries:
        _validate_entry(entry, sample_sha256, ordinals)
        identifier = entry["entry_id"]
        if identifier in identifiers:
            raise ValueError("Duplicate review entry identifiers")
        previous = latest.get(entry["record_ordinal"])
        if previous is None:
            valid_revision = (
                entry["revision"] == 1 and entry["supersedes_entry_id"] is None
            )
        else:
            valid_revision = (
                entry["revision"] == previous["revision"] + 1
                and entry["supersedes_entry_id"] == previous["entry_id"]
            )
        if not valid_revision:
            raise ValueError("Invalid review revision or supersession")
        identifiers.add(identifier)
        latest[entry["record_ordinal"]] = entry
    return latest


def _ledger_entries(ledger: Path) -> tuple[list[dict], bytes]:
    if not ledger.exists():
        return [], b""
    data = _read_bytes(ledger)
    return _json_lines(data, "review ledger"), data


def _aggregate(
    sample_sha256: str, ordinals: set[int], entries: list[dict], ledger_bytes: bytes
) -> dict:
    latest = _validate_history(entries, sample_sha256, ordinals)
    complete = [
        entry for entry in latest.values() if entry["review_status"] == "complete"
    ]
    partial = len(latest) - len(complete)
    return {
        "review_protocol_version": PROTOCOL_VERSION,
        "sample_sha256": sample_sha256,
        "ledger_sha256": _sha256(ledger_bytes),
        "sampled_records": len(ordinals),
        "review_entries": len(entries),
        "reviewed_records": len(latest),
        "superseded_entries": len(entries) - len(latest),
        "partial_records": partial,
        "complete_records": len(complete),
        "completion_basis": (
            "rubric completion attested by reviewer; unknown findings and access "
            "limits remain unverified source facts"
        ),
        "unreviewed_records": len(ordinals) - len(latest),
        "unknown_counts": {
            dimension: sum(
                entry["rubric"][dimension]["value"] == "unknown" for entry in complete
            )
            for dimension in REQUIRED_DIMENSIONS
        },
    }


@contextmanager
def _exclusive_lock(ledger: Path) -> Iterator[None]:
    lock = _private_path(ledger.with_name(ledger.name + ".lock"))
    try:
        descriptor = os.open(
            lock,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0),
            0o600,
        )
    except FileExistsError as error:
        raise FileExistsError("Review ledger lock already exists") from error
    try:
        metadata = {
            "pid": os.getpid(),
            "hostname": socket.gethostname(),
            "created_at_utc": datetime.now(timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
        }
        try:
            _write_all(
                descriptor,
                (json.dumps(metadata, sort_keys=True) + "\n").encode("utf-8"),
            )
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        yield
    finally:
        lock.unlink(missing_ok=True)


def summarize_reviews(sample: Path, sample_sha256: str, ledger: Path) -> dict:
    """Validate private history and return an aggregate-only summary."""
    sample, ledger = _private_path(sample), _private_path(ledger)
    if sample.resolve() == ledger.resolve():
        raise ValueError("Sample and ledger must be different files")
    ordinals = _sample_ordinals(sample, sample_sha256)
    with _exclusive_lock(ledger):
        entries, content = _ledger_entries(ledger)
        return _aggregate(sample_sha256, ordinals, entries, content)


def append_review(sample: Path, sample_sha256: str, ledger: Path, entry: dict) -> dict:
    """Append one validated review revision without altering the frozen sample."""
    return _append_review(sample, sample_sha256, ledger, entry, allow_replay=False)


def _write_ledger_atomic(ledger: Path, content: bytes) -> None:
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=ledger.parent, prefix=".hcpa-review-ledger-", delete=False
        ) as stream:
            temporary = Path(stream.name)
            _write_all(stream.fileno(), content)
            os.fsync(stream.fileno())
        os.replace(temporary, ledger)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _append_review(
    sample: Path, sample_sha256: str, ledger: Path, entry: dict, *, allow_replay: bool
) -> dict:
    sample, ledger = _private_path(sample), _private_path(ledger)
    if sample.resolve() == ledger.resolve():
        raise ValueError("Sample and ledger must be different files")
    with _exclusive_lock(ledger):
        ordinals = _sample_ordinals(sample, sample_sha256)
        entries, content = _ledger_entries(ledger)
        _validate_history(entries, sample_sha256, ordinals)
        _validate_entry(entry, sample_sha256, ordinals)
        if entries and entries[-1]["entry_id"] == entry["entry_id"]:
            if allow_replay and entries[-1] == entry:
                return _aggregate(sample_sha256, ordinals, entries, content)
            raise ValueError("Duplicate review entry identifier with changed content")
        _reject_future_review(entry)
        _validate_history([*entries, entry], sample_sha256, ordinals)
        line = (json.dumps(entry, sort_keys=True, ensure_ascii=False) + "\n").encode(
            "utf-8"
        )
        if len(content) + len(line) > MAX_PRIVATE_FILE_BYTES:
            raise ValueError("Review ledger would exceed its size limit")
        _write_ledger_atomic(ledger, content + line)
        return _aggregate(sample_sha256, ordinals, [*entries, entry], content + line)


def _validate_summary_target(destination: Path, inputs: tuple[Path, ...]) -> None:
    destination = Path(destination)
    if not destination.parent.is_dir() or destination.is_symlink():
        raise ValueError(
            "Aggregate summary parent must exist and target cannot be a symlink"
        )
    if any(destination.resolve() == path.resolve() for path in inputs):
        raise ValueError("Aggregate summary must differ from private inputs")
    if destination.exists():
        raise FileExistsError("Aggregate summary already exists")


def _write_summary_new(
    destination: Path, result: dict, inputs: tuple[Path, ...]
) -> None:
    destination = Path(destination)
    _validate_summary_target(destination, inputs)
    content = (json.dumps(result, indent=2, sort_keys=True) + "\n").encode("utf-8")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=destination.parent, prefix=".hcpa-review-", delete=False
        ) as stream:
            temporary = Path(stream.name)
            _write_all(stream.fileno(), content)
            os.fsync(stream.fileno())
        os.link(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main(arguments: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Validate and append private HCPA source reviews"
    )
    parser.add_argument("action", choices=("append", "summary"))
    parser.add_argument("sample", type=Path)
    parser.add_argument("ledger", type=Path)
    parser.add_argument(
        "entry", type=Path, help="Private JSON entry for append; use '-' for summary"
    )
    parser.add_argument("summary", type=Path, help="New aggregate-only JSON output")
    parser.add_argument("--sample-sha256", required=True)
    options = parser.parse_args(arguments)
    inputs = (options.sample, options.ledger)
    if options.action == "append":
        private_entry = _private_path(options.entry)
        inputs = (*inputs, private_entry)
    elif str(options.entry) != "-":
        parser.error("The summary action requires '-' in the entry slot")
    _validate_summary_target(options.summary, inputs)
    if options.action == "append":
        try:
            entry = json.loads(_read_bytes(private_entry))
        except (UnicodeError, json.JSONDecodeError) as error:
            raise ValueError("Malformed private review entry") from error
        result = _append_review(
            options.sample,
            options.sample_sha256,
            options.ledger,
            entry,
            allow_replay=True,
        )
    else:
        result = summarize_reviews(
            options.sample, options.sample_sha256, options.ledger
        )
    _write_summary_new(options.summary, result, inputs)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
