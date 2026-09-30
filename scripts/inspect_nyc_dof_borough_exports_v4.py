"""Inspect five pinned NYC worksheets with the Manhattan-only v4 exception."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import time

from defusedxml.common import DefusedXmlException

import diagnose_nyc_manhattan_formula_v1 as diagnostic
import inspect_nyc_dof_borough_exports as earlier
import inspect_nyc_dof_borough_exports_v3 as previous_runner
from nyc_workbook_xml_v4 import PROTOCOL, inspect_workbook
from private_review_io import new_file, secure_directory, verify_acl


PRIVATE_ROOT = earlier.PRIVATE_ROOT
ENVIRONMENT_LOCK = earlier.PROJECT_ROOT / "locks" / "nyc-worksheet-v3-environment.json"
CAPTURE_RUN_ID = diagnostic.CAPTURE_RUN_ID
MANHATTAN_SHA256 = diagnostic.MANHATTAN_SHA256
DIAGNOSTIC_RUN_ID = "manhattan-formula-v1-20260930T201602Z-6d714e014144"
SAFE_FILE_KEYS = (
    *previous_runner.SAFE_FILE_KEYS,
    "v3_worksheet_qualified",
    "formula_exception_count",
)


def _run_dir(directory: Path, *, new: bool) -> Path:
    target = Path(directory).absolute()
    earlier._check_ancestors(PRIVATE_ROOT)
    earlier._check_ancestors(target)
    match = re.fullmatch(
        r"worksheet-inspection-v4-(\d{8}T\d{6}Z)-([0-9a-f]{12})", target.name
    )
    if target.parent != PRIVATE_ROOT.absolute() or match is None:
        raise ValueError("V4 inspection path is outside private NYC root")
    try:
        datetime.strptime(match.group(1), "%Y%m%dT%H%M%SZ")
    except ValueError as error:
        raise ValueError("V4 inspection run ID is invalid") from error
    if not PRIVATE_ROOT.is_dir():
        raise ValueError("Private NYC root is missing")
    verify_acl(PRIVATE_ROOT)
    if new and (target.exists() or earlier._reparse(target)):
        raise FileExistsError("V4 inspection run already exists")
    if not new and not target.is_dir():
        raise ValueError("V4 inspection run does not exist")
    return target


def _input(capture_dir: Path) -> tuple[Path, list[dict]]:
    source, manifest, _ = earlier._capture(capture_dir)
    if source.name != CAPTURE_RUN_ID:
        raise ValueError("V4 capture run ID differs from frozen input")
    entries = earlier._expected_files(manifest)
    manhattan = [entry for entry in entries if entry["borough"] == "Manhattan"]
    if len(manhattan) != 1 or manhattan[0]["sha256"] != MANHATTAN_SHA256:
        raise ValueError("V4 Manhattan workbook differs from frozen input")
    return source, entries


def _diagnostic_record(source: Path, timer, start: float) -> dict:
    path = PRIVATE_ROOT / DIAGNOSTIC_RUN_ID
    diagnostic.replay(source, path, timer=timer)
    earlier._check_time(timer, start)
    record, _ = earlier._load_private_json(path, "result.json")
    if (
        record.get("protocol") != diagnostic.PROTOCOL
        or record.get("v3_worksheet_qualified") is not False
        or record.get("sale_labels_certified") != 0
        or not isinstance(record.get("formula"), dict)
    ):
        raise ValueError("V4 private formula diagnostic is incompatible")
    return record["formula"]


def _inspect_file(
    source: Path, entry: dict, expected_formula: dict, timer, start: float
) -> dict:
    path = source / entry["filename"]
    expected_size = entry["bytes"]
    expected_sha = entry["sha256"]
    earlier._check_file(path, expected_size, expected_sha)
    with path.open("rb") as handle:
        before = os.fstat(handle.fileno())
        if before.st_nlink != 1 or before.st_size != expected_size:
            raise ValueError("V4 input handle differs from captured bytes")
        earlier._hash_handle(handle, expected_size, expected_sha)
        earlier._check_time(timer, start)
        try:
            parsed = inspect_workbook(
                handle,
                borough=entry["borough"],
                expected_formula=(
                    expected_formula if entry["borough"] == "Manhattan" else None
                ),
                timer=timer,
                start=start,
            )
        except (ValueError, DefusedXmlException) as error:
            parsed = {
                "status": "rejected_structure",
                "failure_category": type(error).__name__,
            }
        else:
            parsed = {
                "status": (
                    "worksheet_qualified"
                    if parsed["worksheet_qualified"]
                    else "unqualified"
                ),
                **parsed,
            }
        earlier._hash_handle(handle, expected_size, expected_sha)
        earlier._check_time(timer, start)
        after = os.fstat(handle.fileno())
        if (before.st_dev, before.st_ino, before.st_nlink, before.st_size) != (
            after.st_dev,
            after.st_ino,
            after.st_nlink,
            after.st_size,
        ):
            raise ValueError("V4 input changed during parsing")
    earlier._check_file(path, expected_size, expected_sha)
    if (path.stat().st_dev, path.stat().st_ino) != (before.st_dev, before.st_ino):
        raise ValueError("V4 input path changed during parsing")
    return {
        "borough": entry["borough"],
        "sha256": expected_sha,
        "bytes": expected_size,
        **parsed,
    }


def _aggregate(
    source: Path, entries: list[dict], formula: dict, timer, start: float
) -> dict:
    files = []
    for entry in entries:
        earlier._check_time(timer, start)
        files.append(_inspect_file(source, entry, formula, timer, start))
    return {
        "protocol": PROTOCOL,
        "capture_run_id": source.name,
        "capture_manifest_sha256": earlier.CAPTURE_MANIFEST_SHA256,
        "worksheet_qualified_count": sum(
            file["status"] == "worksheet_qualified" for file in files
        ),
        "label_status": "unqualified",
        "sale_labels_certified": 0,
        "files": files,
    }


def _public_projection(private: dict) -> dict:
    return {
        "protocol": PROTOCOL,
        "capture_run_id": private["capture_run_id"],
        "capture_manifest_sha256": private["capture_manifest_sha256"],
        "worksheet_qualified_count": private["worksheet_qualified_count"],
        "label_status": "unqualified",
        "sale_labels_certified": 0,
        "files": [
            {key: item[key] for key in SAFE_FILE_KEYS if key in item}
            for item in private["files"]
        ],
    }


def _intent(source: Path, output: Path, entries: list[dict]) -> dict:
    provenance = earlier._provenance()
    return {
        "protocol": PROTOCOL,
        "run_id": output.name,
        "capture_run_id": source.name,
        "capture_manifest_sha256": earlier.CAPTURE_MANIFEST_SHA256,
        "diagnostic_run_id": DIAGNOSTIC_RUN_ID,
        "files": [
            {key: entry[key] for key in ("borough", "sha256", "bytes")}
            for entry in entries
        ],
        "started_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        **provenance,
        "inherited_environment_lock_sha256": provenance["environment_lock_sha256"],
        "environment_lock_sha256": earlier._sha(ENVIRONMENT_LOCK.read_bytes()),
    }


def _hash_manifest(output: Path, intent: bytes, private: bytes, public: bytes) -> dict:
    return {
        "protocol": PROTOCOL,
        "run_id": output.name,
        "capture_manifest_sha256": earlier.CAPTURE_MANIFEST_SHA256,
        "intent_sha256": earlier._sha(intent),
        "result_sha256": earlier._sha(private),
        "public_sha256": earlier._sha(public),
    }


def inspect_capture(
    capture_dir: Path, output_dir: Path, *, timer=time.monotonic
) -> dict:
    """Create an exclusive private v4 run and return its safe projection."""
    start = timer()
    source, entries = _input(capture_dir)
    formula = _diagnostic_record(source, timer, start)
    earlier._check_time(timer, start)
    output = _run_dir(output_dir, new=True)
    intent_bytes = earlier._json_bytes(_intent(source, output, entries))
    output.mkdir(mode=0o700)
    try:
        secure_directory(output)
        verify_acl(output)
        new_file(output / "intent.json", intent_bytes)
        private = _aggregate(source, entries, formula, timer, start)
        earlier._check_time(timer, start)
        public = _public_projection(private)
        private_bytes = earlier._json_bytes(private)
        public_bytes = earlier._json_bytes(public)
        new_file(output / "result.json", private_bytes)
        new_file(output / "public.json", public_bytes)
        new_file(
            output / "hash_manifest.json",
            earlier._json_bytes(
                _hash_manifest(output, intent_bytes, private_bytes, public_bytes)
            ),
        )
        return public
    except Exception as error:
        category = (
            "timeout" if isinstance(error, TimeoutError) else "integrity_or_io_failure"
        )
        try:
            new_file(
                output / "failure.json",
                earlier._json_bytes(
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
                "V4 failure artifact could not be saved: "
                + type(artifact_error).__name__
            )
        raise


def replay(capture_dir: Path, output_dir: Path, *, timer=time.monotonic) -> dict:
    """Recompute and compare canonical private and public v4 results."""
    start = timer()
    source, entries = _input(capture_dir)
    formula = _diagnostic_record(source, timer, start)
    output = _run_dir(output_dir, new=False)
    verify_acl(output)
    if (output / "failure.json").exists() or earlier._reparse(output / "failure.json"):
        raise ValueError("V4 inspection run is incomplete")
    intent, intent_bytes = earlier._load_private_json(output, "intent.json")
    _, private_bytes = earlier._load_private_json(output, "result.json")
    _, public_bytes = earlier._load_private_json(output, "public.json")
    hashes, _ = earlier._load_private_json(output, "hash_manifest.json")
    expected_files = [
        {key: entry[key] for key in ("borough", "sha256", "bytes")} for entry in entries
    ]
    if (
        intent.get("protocol"),
        intent.get("run_id"),
        intent.get("capture_run_id"),
        intent.get("capture_manifest_sha256"),
        intent.get("diagnostic_run_id"),
        intent.get("files"),
    ) != (
        PROTOCOL,
        output.name,
        source.name,
        earlier.CAPTURE_MANIFEST_SHA256,
        DIAGNOSTIC_RUN_ID,
        expected_files,
    ):
        raise ValueError("V4 inspection intent differs from frozen capture")
    if intent.get("environment_lock_sha256") != earlier._sha(
        ENVIRONMENT_LOCK.read_bytes()
    ) or intent.get("inherited_environment_lock_sha256") != earlier._sha(
        earlier.ENVIRONMENT_LOCK.read_bytes()
    ):
        raise ValueError("V4 inspection environment lock differs")
    if hashes != _hash_manifest(output, intent_bytes, private_bytes, public_bytes):
        raise ValueError("V4 inspection hash manifest differs")
    recomputed = _aggregate(source, entries, formula, timer, start)
    public = _public_projection(recomputed)
    if (
        earlier._json_bytes(recomputed) != private_bytes
        or earlier._json_bytes(public) != public_bytes
    ):
        raise ValueError("V4 inspection replay differs from saved result")
    return public


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("inspect", "replay"))
    parser.add_argument("capture_dir", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    try:
        if args.action == "inspect":
            result = inspect_capture(args.capture_dir, args.output_dir)
        else:
            result = replay(args.capture_dir, args.output_dir)
    except (
        OSError,
        ValueError,
        TimeoutError,
        DefusedXmlException,
        subprocess.CalledProcessError,
    ) as error:
        parser.exit(2, f"V4 worksheet inspection failed: {type(error).__name__}\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
