"""Inspect pinned NYC borough XLSX structure offline, without admitting labels.

The five private source files stay unchanged. The CLI prints only a safe
aggregate; it creates a protected, immutable intent and result for replay.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from defusedxml.common import DefusedXmlException
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import time

import capture_nyc_dof_borough_exports as capture
from nyc_workbook_xml import PROTOCOL, inspect_workbook, _check_time
from private_review_io import new_file, secure_directory, verify_acl


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PRIVATE_ROOT = PROJECT_ROOT / "data" / "raw" / "nyc_dof"
CAPTURE_MANIFEST_SHA256 = (
    "e29928b44a1b1f733219dac86b8d7e18704bf8c301b458afc2bf1a53895bb9e2"
)
ENVIRONMENT_LOCK = PROJECT_ROOT / "locks" / "nyc-workbook-inspection-environment.json"
MAX_JSON_BYTES = 64 * 1024
CHUNK = 1024 * 1024


def _sha(data: bytes) -> str:
    return sha256(data).hexdigest()


def _json_bytes(value: dict) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _reparse(path: Path) -> bool:
    if path.is_symlink():
        return True
    if os.name == "nt" and path.exists():
        return bool(
            getattr(path.lstat(), "st_file_attributes", 0)
            & stat.FILE_ATTRIBUTE_REPARSE_POINT
        )
    return False


def _check_ancestors(path: Path) -> None:
    absolute = path.absolute()
    for candidate in (absolute, *absolute.parents):
        if _reparse(candidate):
            raise ValueError("Private inspection path redirects")


def _inspection_dir(directory: Path, *, new: bool) -> Path:
    target = Path(directory).absolute()
    _check_ancestors(PRIVATE_ROOT)
    _check_ancestors(target)
    match = re.fullmatch(
        r"worksheet-inspection-(\d{8}T\d{6}Z)-([0-9a-f]{12})", target.name
    )
    if target.parent != PRIVATE_ROOT.absolute() or match is None:
        raise ValueError("Inspection run path is outside private NYC root")
    try:
        datetime.strptime(match.group(1), "%Y%m%dT%H%M%SZ")
    except ValueError as error:
        raise ValueError("Inspection run ID is invalid") from error
    if not PRIVATE_ROOT.is_dir():
        raise ValueError("Private NYC root is missing")
    verify_acl(PRIVATE_ROOT)
    if new and (target.exists() or _reparse(target)):
        raise FileExistsError("Inspection run already exists")
    if not new and not target.is_dir():
        raise ValueError("Inspection run does not exist")
    return target


def _capture(capture_dir: Path) -> tuple[Path, dict, bytes]:
    source = capture._run_directory(capture_dir, new=False)
    verify_acl(source)
    replay_report = capture.replay(source)
    manifest, body = capture._load_json(
        source / "manifest.json", capture.MAX_MANIFEST_BYTES
    )
    if (
        _sha(body) != CAPTURE_MANIFEST_SHA256
        or replay_report.get("manifest_sha256") != CAPTURE_MANIFEST_SHA256
    ):
        raise ValueError("Capture manifest differs from frozen input")
    if (
        manifest.get("protocol") != capture.PROTOCOL
        or manifest.get("run_id") != source.name
    ):
        raise ValueError("Capture manifest is incompatible")
    return source, manifest, body


def _provenance() -> dict:
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    ).stdout.strip()
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    ).stdout
    return {
        "code_commit": commit,
        "dirty_tree": bool(status.strip()),
        "environment_lock_sha256": _sha(ENVIRONMENT_LOCK.read_bytes()),
    }


def _load_private_json(directory: Path, name: str) -> tuple[dict, bytes]:
    path = directory / name
    if (
        _reparse(path)
        or not path.is_file()
        or path.stat().st_nlink != 1
        or path.stat().st_size > MAX_JSON_BYTES
    ):
        raise ValueError("Inspection private artifact missing, linked or oversized")
    body = path.read_bytes()
    try:
        value = json.loads(body)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("Inspection private JSON is invalid") from error
    if not isinstance(value, dict) or body != _json_bytes(value):
        raise ValueError("Inspection private JSON is not canonical")
    return value, body


def _hash_handle(source, expected_bytes: int, expected_sha: str) -> None:
    source.seek(0)
    digest = sha256()
    count = 0
    for chunk in iter(lambda: source.read(CHUNK), b""):
        count += len(chunk)
        if count > capture.MAX_FILE_BYTES:
            raise ValueError("Inspection input exceeds captured size cap")
        digest.update(chunk)
    if count != expected_bytes or digest.hexdigest() != expected_sha:
        raise ValueError("Inspection input differs from captured bytes")
    source.seek(0)


def _check_file(path: Path, expected_bytes: int, expected_sha: str) -> None:
    if (
        _reparse(path)
        or not path.is_file()
        or path.stat().st_nlink != 1
        or path.stat().st_size != expected_bytes
        or not re.fullmatch(r"[0-9a-f]{64}", expected_sha)
    ):
        raise ValueError("Inspection input is missing, linked or resized")


def _inspect_file(directory: Path, entry: dict, timer, start: float) -> dict:
    name = entry["filename"]
    path = directory / name
    expected_bytes = entry["bytes"]
    expected_sha = entry["sha256"]
    _check_file(path, expected_bytes, expected_sha)
    with path.open("rb") as source:
        before = os.fstat(source.fileno())
        if before.st_nlink != 1 or before.st_size != expected_bytes:
            raise ValueError("Inspection input handle differs from captured bytes")
        _hash_handle(source, expected_bytes, expected_sha)
        try:
            inspected = inspect_workbook(source, timer=timer, start=start)
        except (ValueError, DefusedXmlException, TimeoutError) as error:
            if isinstance(error, TimeoutError):
                raise
            inspected = {
                "qualified": False,
                "status": "rejected_package",
                "failure_category": type(error).__name__,
            }
        _hash_handle(source, expected_bytes, expected_sha)
        after = os.fstat(source.fileno())
        if (before.st_dev, before.st_ino, before.st_nlink, before.st_size) != (
            after.st_dev,
            after.st_ino,
            after.st_nlink,
            after.st_size,
        ):
            raise ValueError("Inspection input changed during parsing")
    _check_file(path, expected_bytes, expected_sha)
    if (path.stat().st_dev, path.stat().st_ino) != (before.st_dev, before.st_ino):
        raise ValueError("Inspection input path changed during parsing")
    status = inspected.get(
        "status", "qualified" if inspected["qualified"] else "unqualified"
    )
    details = {key: value for key, value in inspected.items() if key != "status"}
    return {
        "borough": entry["borough"],
        "sha256": expected_sha,
        "bytes": expected_bytes,
        "status": status,
        **details,
    }


def _expected_files(manifest: dict) -> list[dict]:
    entries = manifest.get("files")
    if not isinstance(entries, list) or len(entries) != len(capture.BOROUGHS):
        raise ValueError("Capture manifest does not contain five workbooks")
    for (borough, url), entry in zip(capture.BOROUGHS, entries, strict=True):
        if not isinstance(entry, dict) or (
            entry.get("borough"),
            entry.get("url"),
            entry.get("filename"),
        ) != (borough, url, capture._filename(borough)):
            raise ValueError("Capture workbook identity is invalid")
        if (
            type(entry.get("bytes")) is not int
            or not 0 < entry["bytes"] <= capture.MAX_FILE_BYTES
            or not isinstance(entry.get("sha256"), str)
        ):
            raise ValueError("Capture workbook size or hash is invalid")
    return entries


def _aggregate(capture_dir: Path, manifest: dict, timer, start: float) -> dict:
    files = []
    for entry in _expected_files(manifest):
        _check_time(timer, start)
        files.append(_inspect_file(capture_dir, entry, timer, start))
    return {
        "protocol": PROTOCOL,
        "capture_run_id": capture_dir.name,
        "capture_manifest_sha256": CAPTURE_MANIFEST_SHA256,
        "advertised_period_start": "2025-09-01",
        "advertised_period_end": "2026-08-31",
        "qualified_borough_count": sum(item["status"] == "qualified" for item in files),
        "files": files,
        "label_status": "source_structure_only_not_sale_eligibility",
        "historical_asof_eligible": False,
    }


def inspect_capture(
    capture_dir: Path, output_dir: Path, *, timer=time.monotonic
) -> dict:
    """Create a new protected inspection run and a replayable safe aggregate."""
    start = timer()
    source, manifest, _ = _capture(capture_dir)
    _check_time(timer, start)
    output = _inspection_dir(output_dir, new=True)
    output.mkdir(mode=0o700)
    secure_directory(output)
    verify_acl(output)
    intent = {
        "protocol": PROTOCOL,
        "run_id": output.name,
        "capture_run_id": source.name,
        "capture_manifest_sha256": CAPTURE_MANIFEST_SHA256,
        "files": [
            {
                "borough": entry["borough"],
                "sha256": entry["sha256"],
                "bytes": entry["bytes"],
            }
            for entry in _expected_files(manifest)
        ],
        "started_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        **_provenance(),
    }
    intent_bytes = _json_bytes(intent)
    new_file(output / "intent.json", intent_bytes)
    try:
        result = _aggregate(source, manifest, timer, start)
        _check_time(timer, start)
        result_bytes = _json_bytes(result)
        new_file(output / "result.json", result_bytes)
        hash_manifest = {
            "protocol": PROTOCOL,
            "run_id": output.name,
            "capture_manifest_sha256": CAPTURE_MANIFEST_SHA256,
            "intent_sha256": _sha(intent_bytes),
            "result_sha256": _sha(result_bytes),
            "files": intent["files"],
        }
        new_file(output / "hash_manifest.json", _json_bytes(hash_manifest))
        return result
    except Exception as error:
        category = (
            "timeout" if isinstance(error, TimeoutError) else "integrity_or_io_failure"
        )
        try:
            new_file(
                output / "failure.json",
                _json_bytes(
                    {
                        "protocol": PROTOCOL,
                        "run_id": output.name,
                        "status": "incomplete",
                        "category": category,
                    }
                ),
            )
        except Exception as artifact_error:
            error.add_note(
                "Inspection failure artifact could not be saved: "
                + type(artifact_error).__name__
            )
        raise


def replay(capture_dir: Path, output_dir: Path, *, timer=time.monotonic) -> dict:
    """Reparse pinned source bytes and compare with the immutable private result."""
    start = timer()
    source, manifest, _ = _capture(capture_dir)
    output = _inspection_dir(output_dir, new=False)
    verify_acl(output)
    if (output / "failure.json").exists() or _reparse(output / "failure.json"):
        raise ValueError("Inspection run has a failure artifact")
    intent, intent_bytes = _load_private_json(output, "intent.json")
    recorded, result_bytes = _load_private_json(output, "result.json")
    hashes, _ = _load_private_json(output, "hash_manifest.json")
    expected_files = [
        {
            "borough": entry["borough"],
            "sha256": entry["sha256"],
            "bytes": entry["bytes"],
        }
        for entry in _expected_files(manifest)
    ]
    if (
        intent.get("protocol"),
        intent.get("run_id"),
        intent.get("capture_run_id"),
        intent.get("capture_manifest_sha256"),
        intent.get("files"),
    ) != (PROTOCOL, output.name, source.name, CAPTURE_MANIFEST_SHA256, expected_files):
        raise ValueError("Inspection intent differs from frozen capture")
    if hashes != {
        "protocol": PROTOCOL,
        "run_id": output.name,
        "capture_manifest_sha256": CAPTURE_MANIFEST_SHA256,
        "intent_sha256": _sha(intent_bytes),
        "result_sha256": _sha(result_bytes),
        "files": expected_files,
    }:
        raise ValueError("Inspection private hash manifest differs")
    recomputed = _aggregate(source, manifest, timer, start)
    if recomputed != recorded:
        raise ValueError("Inspection replay differs from saved result")
    return recomputed


def plan() -> dict:
    """Describe the frozen offline inputs without opening any workbook."""
    return {
        "protocol": PROTOCOL,
        "capture_manifest_sha256": CAPTURE_MANIFEST_SHA256,
        "expected_borough_count": len(capture.BOROUGHS),
        "expected_period_start": "2025-09-01",
        "expected_period_end": "2026-08-31",
        "status": "plan_only_no_workbook_open",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("plan")
    for name in ("inspect", "replay"):
        command = commands.add_parser(name)
        command.add_argument("capture_dir", type=Path)
        command.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "plan":
            result = plan()
        elif args.command == "inspect":
            result = inspect_capture(args.capture_dir, args.output_dir)
        else:
            result = replay(args.capture_dir, args.output_dir)
    except (OSError, ValueError, TimeoutError, subprocess.CalledProcessError) as error:
        parser.exit(2, f"Workbook inspection failed: {type(error).__name__}\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
