"""Append-only provenance ledger for exact HCPA release captures."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any

from scripts.private_review_io import (
    advisory_lock,
    atomic_replace,
    private_path,
    real_directory,
    verify_acl,
)


SCHEMA_VERSION = "hcpa_release_observation_v1"
FILENAME_PATTERNS = {
    "allsales": re.compile(r"allsales_\d{2}_\d{2}_\d{4}\.zip\Z"),
    "parcels": re.compile(r"parcels_\d{2}_\d{2}_\d{4}\.zip\Z"),
}
DIFF_STATUSES = {
    "first_observation",
    "unchanged",
    "new_release",
    "same_name_content_changed",
    "renamed_same_content",
}
ENTRY_FIELDS = {
    "schema_version",
    "entry_id",
    "family",
    "listed_filename",
    "observed_at_utc",
    "file_sha256",
    "file_bytes",
    "capture_manifest_sha256",
    "predecessor_entry_id",
    "predecessor_filename",
    "predecessor_file_sha256",
    "diff_status",
    "previous_entry_sha256",
    "entry_sha256",
}
HEX64 = re.compile(r"[0-9a-f]{64}\Z")


def _canonical(value: dict[str, Any]) -> bytes:
    return json.dumps(
        value, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    ).encode("ascii")


def _digest_file(path: Path) -> tuple[int, str]:
    digest = sha256()
    size = 0
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            size += len(block)
            digest.update(block)
    return size, digest.hexdigest()


def _parse_utc(value: object) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("Observation time must be UTC")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise ValueError("Observation time is invalid") from error
    if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(parsed):
        raise ValueError("Observation time must be UTC")
    return parsed


def _regular_private_file(path: Path) -> None:
    if path.is_symlink() or not path.is_file() or path.stat().st_nlink != 1:
        raise ValueError("Capture artifact must be a regular, single-link file")


def _verified_capture(manifest_path: Path, root: Path) -> tuple[dict[str, Any], str]:
    """Validate a completed capture manifest against its exact archive bytes."""
    root = Path(root)
    manifest_path = Path(manifest_path)
    real_directory(root, root.parent)
    verify_acl(root)
    run_dir = manifest_path.parent
    if run_dir.parent != root:
        raise ValueError("Capture manifest must be in a direct private run directory")
    real_directory(run_dir, root)
    verify_acl(run_dir)
    if manifest_path.name != "manifest.json" or (run_dir / ".incomplete").exists():
        raise ValueError("Capture is incomplete")
    _regular_private_file(manifest_path)
    try:
        manifest_bytes = manifest_path.read_bytes()
        manifest = json.loads(manifest_bytes.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("Capture manifest is invalid") from error
    if not isinstance(manifest, dict):
        raise ValueError("Capture manifest is invalid")
    family = manifest.get("family")
    filename = manifest.get("filename")
    if (
        family not in FILENAME_PATTERNS
        or not isinstance(filename, str)
        or FILENAME_PATTERNS[family].fullmatch(filename) is None
    ):
        raise ValueError("Capture family or filename is invalid")
    if (
        manifest.get("status") != "observed_not_qualified"
        or manifest.get("first_public_availability_verified") is not False
        or manifest.get("certified_sale_labels") != 0
        or manifest.get("g_us_gate") != "PENDING"
    ):
        raise ValueError("Capture qualification state is invalid")
    _parse_utc(manifest.get("capture_completed_at_utc"))
    archive = run_dir / filename
    if archive.parent != run_dir:
        raise ValueError("Capture archive path is invalid")
    _regular_private_file(archive)
    size, digest = _digest_file(archive)
    if (
        type(manifest.get("raw_zip_bytes")) is not int
        or manifest["raw_zip_bytes"] <= 0
        or manifest["raw_zip_bytes"] != size
        or not isinstance(manifest.get("raw_zip_sha256"), str)
        or HEX64.fullmatch(manifest["raw_zip_sha256"]) is None
        or manifest["raw_zip_sha256"] != digest
    ):
        raise ValueError("Capture archive does not match its manifest")
    listing_hash = manifest.get("listing_html_sha256")
    if not isinstance(listing_hash, str) or HEX64.fullmatch(listing_hash) is None:
        raise ValueError("Capture listing hash is invalid")
    return manifest, sha256(manifest_bytes).hexdigest()


def verify_capture(manifest_path: Path, root: Path) -> dict[str, Any]:
    """Return the validated manifest without exposing archive contents."""
    manifest, _manifest_sha = _verified_capture(manifest_path, root)
    return manifest


def _status(previous: dict[str, Any] | None, filename: str, digest: str) -> str:
    if previous is None:
        return "first_observation"
    same_name = previous["listed_filename"] == filename
    same_bytes = previous["file_sha256"] == digest
    if same_name and same_bytes:
        return "unchanged"
    if same_name:
        return "same_name_content_changed"
    if same_bytes:
        return "renamed_same_content"
    return "new_release"


def _entry_hash(entry: dict[str, Any]) -> str:
    unsigned = {key: value for key, value in entry.items() if key != "entry_sha256"}
    return sha256(_canonical(unsigned)).hexdigest()


def _validate_entry(
    entry: object,
    previous_global: dict[str, Any] | None,
    previous_family: dict[str, Any] | None,
) -> dict[str, Any]:
    if not isinstance(entry, dict) or set(entry) != ENTRY_FIELDS:
        raise ValueError("Ledger entry schema is invalid")
    if entry["schema_version"] != SCHEMA_VERSION:
        raise ValueError("Ledger schema version is invalid")
    family = entry["family"]
    filename = entry["listed_filename"]
    if (
        family not in FILENAME_PATTERNS
        or not isinstance(filename, str)
        or FILENAME_PATTERNS[family].fullmatch(filename) is None
    ):
        raise ValueError("Ledger family or filename is invalid")
    observed = _parse_utc(entry["observed_at_utc"])
    if previous_global is not None:
        if observed <= _parse_utc(previous_global["observed_at_utc"]):
            raise ValueError("Ledger observations are not strictly chronological")
        expected_previous_hash = previous_global["entry_sha256"]
    else:
        expected_previous_hash = None
    if entry["previous_entry_sha256"] != expected_previous_hash:
        raise ValueError("Ledger hash chain is invalid")
    expected_predecessor = (
        None if previous_family is None else previous_family["entry_id"]
    )
    expected_filename = (
        None if previous_family is None else previous_family["listed_filename"]
    )
    expected_digest = (
        None if previous_family is None else previous_family["file_sha256"]
    )
    if (
        entry["predecessor_entry_id"] != expected_predecessor
        or entry["predecessor_filename"] != expected_filename
        or entry["predecessor_file_sha256"] != expected_digest
        or entry["diff_status"]
        != _status(previous_family, filename, entry["file_sha256"])
    ):
        raise ValueError("Ledger predecessor or classification is invalid")
    for key in ("entry_id", "file_sha256", "capture_manifest_sha256", "entry_sha256"):
        if not isinstance(entry[key], str) or HEX64.fullmatch(entry[key]) is None:
            raise ValueError("Ledger digest is invalid")
    if type(entry["file_bytes"]) is not int or entry["file_bytes"] <= 0:
        raise ValueError("Ledger byte count is invalid")
    if entry["diff_status"] not in DIFF_STATUSES:
        raise ValueError("Ledger classification is invalid")
    identity = {
        key: value
        for key, value in entry.items()
        if key not in {"entry_id", "entry_sha256"}
    }
    if entry["entry_id"] != sha256(_canonical(identity)).hexdigest():
        raise ValueError("Ledger entry identity is invalid")
    if entry["entry_sha256"] != _entry_hash(entry):
        raise ValueError("Ledger entry hash is invalid")
    return entry


def replay(ledger_path: Path, root: Path) -> list[dict[str, Any]]:
    """Validate and replay the entire immutable hash-chained history."""
    ledger_path = Path(ledger_path)
    root = Path(root)
    if not ledger_path.exists():
        return []
    private_path(ledger_path, root, must_exist=True)
    entries: list[dict[str, Any]] = []
    latest: dict[str, dict[str, Any]] = {}
    seen_ids: set[str] = set()
    try:
        lines = ledger_path.read_text(encoding="ascii").splitlines()
    except (OSError, UnicodeError) as error:
        raise ValueError("Ledger encoding is invalid") from error
    if not lines:
        raise ValueError("Ledger must not be empty")
    for line in lines:
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError("Ledger JSON is invalid") from error
        entry = _validate_entry(
            raw,
            entries[-1] if entries else None,
            latest.get(raw.get("family")) if isinstance(raw, dict) else None,
        )
        if entry["entry_id"] in seen_ids:
            raise ValueError("Ledger entry is duplicated")
        seen_ids.add(entry["entry_id"])
        entries.append(entry)
        latest[entry["family"]] = entry
    return entries


def append_observation(
    ledger_path: Path,
    manifest_path: Path,
    root: Path,
) -> dict[str, Any]:
    """Atomically append one verified completed capture observation."""
    ledger_path = Path(ledger_path)
    root = Path(root)
    if ledger_path.parent != root:
        raise ValueError("Ledger must be directly inside the private root")
    private_path(ledger_path, root)
    manifest, manifest_sha = _verified_capture(manifest_path, root)
    with advisory_lock(ledger_path.with_name(ledger_path.name + ".lock"), root):
        entries = replay(ledger_path, root)
        existing = next(
            (
                item
                for item in entries
                if item["capture_manifest_sha256"] == manifest_sha
            ),
            None,
        )
        if existing is not None:
            return existing
        observed = _parse_utc(manifest["capture_completed_at_utc"])
        if entries and observed <= _parse_utc(entries[-1]["observed_at_utc"]):
            raise ValueError("Observation predates or equals the ledger head")
        previous_family = next(
            (
                item
                for item in reversed(entries)
                if item["family"] == manifest["family"]
            ),
            None,
        )
        entry: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "family": manifest["family"],
            "listed_filename": manifest["filename"],
            "observed_at_utc": manifest["capture_completed_at_utc"],
            "file_sha256": manifest["raw_zip_sha256"],
            "file_bytes": manifest["raw_zip_bytes"],
            "capture_manifest_sha256": manifest_sha,
            "predecessor_entry_id": None
            if previous_family is None
            else previous_family["entry_id"],
            "predecessor_filename": None
            if previous_family is None
            else previous_family["listed_filename"],
            "predecessor_file_sha256": None
            if previous_family is None
            else previous_family["file_sha256"],
            "diff_status": _status(
                previous_family, manifest["filename"], manifest["raw_zip_sha256"]
            ),
            "previous_entry_sha256": None
            if not entries
            else entries[-1]["entry_sha256"],
        }
        entry["entry_id"] = sha256(_canonical(entry)).hexdigest()
        entry["entry_sha256"] = _entry_hash(entry)
        _validate_entry(entry, entries[-1] if entries else None, previous_family)
        prior = b"" if not ledger_path.exists() else ledger_path.read_bytes()
        atomic_replace(ledger_path, prior + _canonical(entry) + b"\n")
        return entry


def summarize(ledger_path: Path, root: Path) -> dict[str, Any]:
    """Return a strict privacy-safe aggregate projection."""
    entries = replay(ledger_path, root)
    latest: dict[str, dict[str, Any]] = {}
    for entry in entries:
        latest[entry["family"]] = {
            "listed_filename": entry["listed_filename"],
            "observed_at_utc": entry["observed_at_utc"],
            "file_sha256": entry["file_sha256"],
            "diff_status": entry["diff_status"],
        }
    return {
        "schema_version": SCHEMA_VERSION,
        "ledger_sha256": sha256(Path(ledger_path).read_bytes()).hexdigest(),
        "observation_count": len(entries),
        "counts_by_family": dict(sorted(Counter(x["family"] for x in entries).items())),
        "counts_by_diff_status": dict(
            sorted(Counter(x["diff_status"] for x in entries).items())
        ),
        "latest_by_family": dict(sorted(latest.items())),
        "certified_sale_labels": 0,
        "g_us_gate": "PENDING",
    }
