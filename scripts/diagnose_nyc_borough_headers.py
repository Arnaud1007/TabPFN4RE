"""Offline private candidate-only diagnosis for pinned NYC borough workbooks."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from defusedxml.common import DefusedXmlException
import json
import os
from pathlib import Path
import re
import subprocess
import time

import capture_nyc_dof_borough_exports as capture
import inspect_nyc_dof_borough_exports as inspection
from nyc_header_diagnostic_xml import PROTOCOL, scan_workbook
from private_review_io import new_file, secure_directory, verify_acl


PRIVATE_ROOT = inspection.PRIVATE_ROOT
ENVIRONMENT_LOCK = (
    inspection.PROJECT_ROOT / "locks" / "nyc-header-diagnostic-environment.json"
)


def _diagnostic_dir(directory: Path, *, new: bool) -> Path:
    target = Path(directory).absolute()
    inspection._check_ancestors(PRIVATE_ROOT)
    inspection._check_ancestors(target)
    match = re.fullmatch(
        r"header-diagnostic-(\d{8}T\d{6}Z)-([0-9a-f]{12})", target.name
    )
    if target.parent != PRIVATE_ROOT.absolute() or match is None:
        raise ValueError("Header diagnostic path is outside private NYC root")
    try:
        datetime.strptime(match.group(1), "%Y%m%dT%H%M%SZ")
    except ValueError as error:
        raise ValueError("Header diagnostic run ID is invalid") from error
    if not PRIVATE_ROOT.is_dir():
        raise ValueError("Private NYC root is missing")
    verify_acl(PRIVATE_ROOT)
    if new and (target.exists() or inspection._reparse(target)):
        raise FileExistsError("Header diagnostic run already exists")
    if not new and not target.is_dir():
        raise ValueError("Header diagnostic run does not exist")
    return target


def _inspect_file(directory: Path, entry: dict, timer, start: float) -> dict:
    name = entry["filename"]
    path = directory / name
    expected_bytes = entry["bytes"]
    expected_sha = entry["sha256"]
    inspection._check_file(path, expected_bytes, expected_sha)
    with path.open("rb") as source:
        before = os.fstat(source.fileno())
        if before.st_nlink != 1 or before.st_size != expected_bytes:
            raise ValueError("Diagnostic input handle differs from captured bytes")
        inspection._hash_handle(source, expected_bytes, expected_sha)
        try:
            scanned = scan_workbook(source, timer=timer, start=start)
        except (ValueError, DefusedXmlException) as error:
            scanned = {
                "status": "rejected_structure",
                "failure_category": type(error).__name__,
            }
        inspection._hash_handle(source, expected_bytes, expected_sha)
        after = os.fstat(source.fileno())
        if (before.st_dev, before.st_ino, before.st_nlink, before.st_size) != (
            after.st_dev,
            after.st_ino,
            after.st_nlink,
            after.st_size,
        ):
            raise ValueError("Diagnostic input changed during parsing")
    inspection._check_file(path, expected_bytes, expected_sha)
    if (path.stat().st_dev, path.stat().st_ino) != (before.st_dev, before.st_ino):
        raise ValueError("Diagnostic input path changed during parsing")
    return {
        "borough": entry["borough"],
        "sha256": expected_sha,
        "bytes": expected_bytes,
        **scanned,
    }


def _aggregate(source: Path, manifest: dict, timer, start: float) -> dict:
    files = []
    for entry in inspection._expected_files(manifest):
        inspection._check_time(timer, start)
        files.append(_inspect_file(source, entry, timer, start))
    return {
        "protocol": PROTOCOL,
        "capture_run_id": source.name,
        "capture_manifest_sha256": inspection.CAPTURE_MANIFEST_SHA256,
        "scope": "candidate_only",
        "qualified_borough_count": 0,
        "label_status": "unqualified",
        "files": files,
    }


def _public_projection(private: dict) -> dict:
    files = []
    for item in private["files"]:
        safe = {key: item[key] for key in ("borough", "sha256", "bytes", "status")}
        if "failure_category" in item:
            safe = {**safe, "failure_category": item["failure_category"]}
        if "physical_rows" in item:
            safe = {**safe, "physical_rows": item["physical_rows"]}
        if item["status"] == "rejected_formula_candidate":
            safe = {
                **safe,
                **{
                    key: item[key]
                    for key in (
                        "candidate_score",
                        "source_row_number",
                        "physical_ordinal",
                        "nonempty_count",
                        "formula_cells",
                        "beyond_21_count",
                    )
                },
            }
        if "candidate" in item:
            candidate = item["candidate"]
            safe = {
                **safe,
                "candidate": {
                    key: candidate[key]
                    for key in (
                        "source_row_number",
                        "physical_ordinal",
                        "score",
                        "nonempty_count",
                        "formula_cells",
                        "beyond_21_count",
                        "fingerprint_sha256",
                    )
                },
            }
        files.append(safe)
    return {
        "protocol": PROTOCOL,
        "capture_run_id": private["capture_run_id"],
        "capture_manifest_sha256": private["capture_manifest_sha256"],
        "scope": "candidate_only",
        "qualified_borough_count": 0,
        "label_status": "unqualified",
        "files": files,
    }


def _intent(source: Path, output: Path, manifest: dict) -> dict:
    provenance = inspection._provenance()
    return {
        "protocol": PROTOCOL,
        "run_id": output.name,
        "capture_run_id": source.name,
        "capture_manifest_sha256": inspection.CAPTURE_MANIFEST_SHA256,
        "files": [
            {key: entry[key] for key in ("borough", "sha256", "bytes")}
            for entry in inspection._expected_files(manifest)
        ],
        "started_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        **provenance,
        "worksheet_inspection_environment_lock_sha256": provenance[
            "environment_lock_sha256"
        ],
        "environment_lock_sha256": inspection._sha(ENVIRONMENT_LOCK.read_bytes()),
    }


def _hash_manifest(
    output: Path, intent: bytes, private: bytes, public: bytes, files: list
) -> dict:
    return {
        "protocol": PROTOCOL,
        "run_id": output.name,
        "capture_manifest_sha256": inspection.CAPTURE_MANIFEST_SHA256,
        "intent_sha256": inspection._sha(intent),
        "result_sha256": inspection._sha(private),
        "public_sha256": inspection._sha(public),
        "files": files,
    }


def diagnose_capture(
    capture_dir: Path, output_dir: Path, *, timer=time.monotonic
) -> dict:
    """Create an immutable private run and return its redacted projection."""
    start = timer()
    source, manifest, _ = inspection._capture(capture_dir)
    inspection._check_time(timer, start)
    output = _diagnostic_dir(output_dir, new=True)
    intent = _intent(source, output, manifest)
    intent_bytes = inspection._json_bytes(intent)
    output.mkdir(mode=0o700)
    secure_directory(output)
    verify_acl(output)
    new_file(output / "intent.json", intent_bytes)
    try:
        private = _aggregate(source, manifest, timer, start)
        inspection._check_time(timer, start)
        public = _public_projection(private)
        private_bytes = inspection._json_bytes(private)
        public_bytes = inspection._json_bytes(public)
        new_file(output / "result.json", private_bytes)
        new_file(output / "public.json", public_bytes)
        hashes = _hash_manifest(
            output, intent_bytes, private_bytes, public_bytes, intent["files"]
        )
        new_file(output / "hash_manifest.json", inspection._json_bytes(hashes))
        return public
    except Exception as error:
        category = (
            "timeout" if isinstance(error, TimeoutError) else "integrity_or_io_failure"
        )
        try:
            new_file(
                output / "failure.json",
                inspection._json_bytes(
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
                "Header diagnosis failure artifact could not be saved: "
                + type(artifact_error).__name__
            )
        raise


def replay(capture_dir: Path, output_dir: Path, *, timer=time.monotonic) -> dict:
    """Recompute both private and public canonical JSON from pinned source bytes."""
    start = timer()
    source, manifest, _ = inspection._capture(capture_dir)
    output = _diagnostic_dir(output_dir, new=False)
    verify_acl(output)
    if (output / "failure.json").exists() or inspection._reparse(
        output / "failure.json"
    ):
        raise ValueError("Header diagnosis run is incomplete")
    intent, intent_bytes = inspection._load_private_json(output, "intent.json")
    _, private_bytes = inspection._load_private_json(output, "result.json")
    _, public_bytes = inspection._load_private_json(output, "public.json")
    hashes, _ = inspection._load_private_json(output, "hash_manifest.json")
    expected_files = [
        {key: entry[key] for key in ("borough", "sha256", "bytes")}
        for entry in inspection._expected_files(manifest)
    ]
    if (
        intent.get("protocol"),
        intent.get("run_id"),
        intent.get("capture_run_id"),
        intent.get("capture_manifest_sha256"),
        intent.get("files"),
    ) != (
        PROTOCOL,
        output.name,
        source.name,
        inspection.CAPTURE_MANIFEST_SHA256,
        expected_files,
    ):
        raise ValueError("Header diagnosis intent differs from frozen capture")
    if hashes != _hash_manifest(
        output, intent_bytes, private_bytes, public_bytes, expected_files
    ):
        raise ValueError("Header diagnosis hash manifest differs")
    recomputed = _aggregate(source, manifest, timer, start)
    public = _public_projection(recomputed)
    if (
        inspection._json_bytes(recomputed) != private_bytes
        or inspection._json_bytes(public) != public_bytes
    ):
        raise ValueError("Header diagnosis replay differs from saved result")
    return public


def plan() -> dict:
    """Return fixed inputs without opening any workbook cell or source file."""
    return {
        "protocol": PROTOCOL,
        "capture_manifest_sha256": inspection.CAPTURE_MANIFEST_SHA256,
        "expected_borough_count": len(capture.BOROUGHS),
        "status": "plan_only_no_workbook_open",
        "scope": "candidate_only",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("plan")
    for name in ("diagnose", "replay"):
        command = commands.add_parser(name)
        command.add_argument("capture_dir", type=Path)
        command.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "plan":
            result = plan()
        elif args.command == "diagnose":
            result = diagnose_capture(args.capture_dir, args.output_dir)
        else:
            result = replay(args.capture_dir, args.output_dir)
    except (
        OSError,
        ValueError,
        TimeoutError,
        DefusedXmlException,
        subprocess.CalledProcessError,
    ) as error:
        parser.exit(2, f"Header diagnosis failed: {type(error).__name__}\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
