"""Run and replay the frozen NYC v3 worksheet inspection on private bytes."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import capture_nyc_dof_borough_exports as capture
import inspect_nyc_dof_borough_exports as earlier
from defusedxml.common import DefusedXmlException
from nyc_workbook_xml_v3 import PROTOCOL, inspect_workbook
from private_review_io import new_file, secure_directory, verify_acl

PRIVATE_ROOT = earlier.PRIVATE_ROOT
ENVIRONMENT_LOCK = earlier.PROJECT_ROOT / "locks" / "nyc-worksheet-v3-environment.json"
SAFE_FILE_KEYS = (
    "borough",
    "sha256",
    "bytes",
    "status",
    "failure_category",
    "protocol",
    "sheet_count",
    "date_system",
    "physical_rows",
    "preamble_rows",
    "data_rows",
    "header_status",
    "raw_header_sha256",
    "missing_or_unparseable_dates",
    "out_of_period_dates",
    "repeated_header_rows",
    "formula_cells",
    "formula_preamble",
    "formula_header",
    "formula_data",
    "extra_preamble_cells",
    "extra_header_cells",
    "extra_data_cells",
    "invalid_header_candidate_rows",
    "date_min",
    "date_max",
    "worksheet_qualified",
    "label_status",
    "sale_labels_certified",
)


def _run_dir(directory: Path, *, new: bool) -> Path:
    target = Path(directory).absolute()
    earlier._check_ancestors(PRIVATE_ROOT)
    earlier._check_ancestors(target)
    match = re.fullmatch(
        r"worksheet-inspection-v3-(\d{8}T\d{6}Z)-([0-9a-f]{12})", target.name
    )
    if target.parent != PRIVATE_ROOT.absolute() or match is None:
        raise ValueError("V3 inspection path is outside private NYC root")
    try:
        datetime.strptime(match.group(1), "%Y%m%dT%H%M%SZ")
    except ValueError as error:
        raise ValueError("V3 inspection run ID is invalid") from error
    if not PRIVATE_ROOT.is_dir():
        raise ValueError("Private NYC root is missing")
    verify_acl(PRIVATE_ROOT)
    if new and (target.exists() or earlier._reparse(target)):
        raise FileExistsError("V3 inspection run already exists")
    if not new and not target.is_dir():
        raise ValueError("V3 inspection run does not exist")
    return target


def _inspect_file(source: Path, entry: dict, timer, start: float) -> dict:
    path = source / entry["filename"]
    expected_size = entry["bytes"]
    expected_sha = entry["sha256"]
    earlier._check_file(path, expected_size, expected_sha)
    with path.open("rb") as handle:
        before = os.fstat(handle.fileno())
        if before.st_nlink != 1 or before.st_size != expected_size:
            raise ValueError("V3 input handle differs from captured bytes")
        earlier._hash_handle(handle, expected_size, expected_sha)
        earlier._check_time(timer, start)
        try:
            parsed = inspect_workbook(handle, timer=timer, start=start)
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
            raise ValueError("V3 input changed during parsing")
    earlier._check_file(path, expected_size, expected_sha)
    if (path.stat().st_dev, path.stat().st_ino) != (before.st_dev, before.st_ino):
        raise ValueError("V3 input path changed during parsing")
    return {
        "borough": entry["borough"],
        "sha256": expected_sha,
        "bytes": expected_size,
        **parsed,
    }


def _aggregate(source: Path, manifest: dict, timer, start: float) -> dict:
    files = []
    for entry in earlier._expected_files(manifest):
        earlier._check_time(timer, start)
        files.append(_inspect_file(source, entry, timer, start))
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


def _intent(source: Path, output: Path, manifest: dict) -> dict:
    provenance = earlier._provenance()
    return {
        "protocol": PROTOCOL,
        "run_id": output.name,
        "capture_run_id": source.name,
        "capture_manifest_sha256": earlier.CAPTURE_MANIFEST_SHA256,
        "files": [
            {key: entry[key] for key in ("borough", "sha256", "bytes")}
            for entry in earlier._expected_files(manifest)
        ],
        "started_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        **provenance,
        "worksheet_inspection_environment_lock_sha256": provenance[
            "environment_lock_sha256"
        ],
        "environment_lock_sha256": earlier._sha(ENVIRONMENT_LOCK.read_bytes()),
    }


def _hash_manifest(
    output: Path, intent: bytes, private: bytes, public: bytes, files: list
) -> dict:
    return {
        "protocol": PROTOCOL,
        "run_id": output.name,
        "capture_manifest_sha256": earlier.CAPTURE_MANIFEST_SHA256,
        "intent_sha256": earlier._sha(intent),
        "result_sha256": earlier._sha(private),
        "public_sha256": earlier._sha(public),
        "files": files,
    }


def inspect_capture(
    capture_dir: Path, output_dir: Path, *, timer=time.monotonic
) -> dict:
    """Create an exclusive private run and return its redacted projection."""
    start = timer()
    source, manifest, _ = earlier._capture(capture_dir)
    earlier._check_time(timer, start)
    output = _run_dir(output_dir, new=True)
    intent = _intent(source, output, manifest)
    intent_bytes = earlier._json_bytes(intent)
    output.mkdir(mode=0o700)
    try:
        secure_directory(output)
        verify_acl(output)
        new_file(output / "intent.json", intent_bytes)
        private = _aggregate(source, manifest, timer, start)
        earlier._check_time(timer, start)
        public = _public_projection(private)
        private_bytes = earlier._json_bytes(private)
        public_bytes = earlier._json_bytes(public)
        new_file(output / "result.json", private_bytes)
        new_file(output / "public.json", public_bytes)
        hashes = _hash_manifest(
            output, intent_bytes, private_bytes, public_bytes, intent["files"]
        )
        new_file(output / "hash_manifest.json", earlier._json_bytes(hashes))
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
                "V3 failure artifact could not be saved: "
                + type(artifact_error).__name__
            )
        raise


def replay(capture_dir: Path, output_dir: Path, *, timer=time.monotonic) -> dict:
    """Recompute and compare canonical private and public result bytes."""
    start = timer()
    source, manifest, _ = earlier._capture(capture_dir)
    output = _run_dir(output_dir, new=False)
    verify_acl(output)
    if (output / "failure.json").exists() or earlier._reparse(output / "failure.json"):
        raise ValueError("V3 inspection run is incomplete")
    intent, intent_bytes = earlier._load_private_json(output, "intent.json")
    _, private_bytes = earlier._load_private_json(output, "result.json")
    _, public_bytes = earlier._load_private_json(output, "public.json")
    hashes, _ = earlier._load_private_json(output, "hash_manifest.json")
    expected_files = [
        {key: entry[key] for key in ("borough", "sha256", "bytes")}
        for entry in earlier._expected_files(manifest)
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
        earlier.CAPTURE_MANIFEST_SHA256,
        expected_files,
    ):
        raise ValueError("V3 inspection intent differs from frozen capture")
    if intent.get("environment_lock_sha256") != earlier._sha(
        ENVIRONMENT_LOCK.read_bytes()
    ) or intent.get("worksheet_inspection_environment_lock_sha256") != earlier._sha(
        earlier.ENVIRONMENT_LOCK.read_bytes()
    ):
        raise ValueError("V3 inspection environment lock differs")
    if hashes != _hash_manifest(
        output, intent_bytes, private_bytes, public_bytes, expected_files
    ):
        raise ValueError("V3 inspection hash manifest differs")
    recomputed = _aggregate(source, manifest, timer, start)
    public = _public_projection(recomputed)
    if (
        earlier._json_bytes(recomputed) != private_bytes
        or earlier._json_bytes(public) != public_bytes
    ):
        raise ValueError("V3 inspection replay differs from saved result")
    return public


def plan() -> dict:
    """Expose only fixed plan metadata without opening workbook cells."""
    return {
        "protocol": PROTOCOL,
        "capture_manifest_sha256": earlier.CAPTURE_MANIFEST_SHA256,
        "expected_borough_count": len(capture.BOROUGHS),
        "status": "plan_only_no_workbook_open",
        "label_status": "unqualified",
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
    except (
        OSError,
        ValueError,
        TimeoutError,
        DefusedXmlException,
        subprocess.CalledProcessError,
    ) as error:
        parser.exit(2, f"V3 worksheet inspection failed: {type(error).__name__}\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
