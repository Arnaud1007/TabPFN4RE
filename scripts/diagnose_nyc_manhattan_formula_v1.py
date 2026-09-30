"""Privately diagnose the one frozen Manhattan preamble formula and replay it."""

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

import inspect_nyc_dof_borough_exports as earlier
from nyc_manhattan_formula_xml_v1 import PROTOCOL, diagnose_workbook
from private_review_io import new_file, secure_directory, verify_acl


PRIVATE_ROOT = earlier.PRIVATE_ROOT
ENVIRONMENT_LOCK = earlier.PROJECT_ROOT / "locks" / "nyc-worksheet-v3-environment.json"
CAPTURE_RUN_ID = "official-exports-20260929T033558Z-62ad417fb39f"
MANHATTAN_SHA256 = "8903566fa59c9ce4c2b427ce24e268cc448d8c04f8c779839df942f29a05397a"


def _run_dir(directory: Path, *, new: bool) -> Path:
    target = Path(directory).absolute()
    earlier._check_ancestors(PRIVATE_ROOT)
    earlier._check_ancestors(target)
    match = re.fullmatch(
        r"manhattan-formula-v1-(\d{8}T\d{6}Z)-([0-9a-f]{12})", target.name
    )
    if target.parent != PRIVATE_ROOT.absolute() or match is None:
        raise ValueError("Manhattan diagnostic path is outside private NYC root")
    try:
        datetime.strptime(match.group(1), "%Y%m%dT%H%M%SZ")
    except ValueError as error:
        raise ValueError("Manhattan diagnostic run ID is invalid") from error
    if not PRIVATE_ROOT.is_dir():
        raise ValueError("Private NYC root is missing")
    verify_acl(PRIVATE_ROOT)
    if new and (target.exists() or earlier._reparse(target)):
        raise FileExistsError("Manhattan diagnostic run already exists")
    if not new and not target.is_dir():
        raise ValueError("Manhattan diagnostic run does not exist")
    return target


def _input(capture_dir: Path) -> tuple[Path, dict]:
    source, manifest, _ = earlier._capture(capture_dir)
    if source.name != CAPTURE_RUN_ID:
        raise ValueError("Manhattan diagnostic capture ID differs")
    entries = [
        entry
        for entry in earlier._expected_files(manifest)
        if entry["borough"] == "Manhattan"
    ]
    if len(entries) != 1 or entries[0]["sha256"] != MANHATTAN_SHA256:
        raise ValueError("Manhattan diagnostic workbook hash differs")
    return source, entries[0]


def _inspect_file(source: Path, entry: dict, timer, start: float) -> dict:
    path = source / entry["filename"]
    expected_size = entry["bytes"]
    expected_sha = entry["sha256"]
    earlier._check_file(path, expected_size, expected_sha)
    with path.open("rb") as handle:
        before = os.fstat(handle.fileno())
        if before.st_nlink != 1 or before.st_size != expected_size:
            raise ValueError("Manhattan diagnostic input handle differs")
        earlier._hash_handle(handle, expected_size, expected_sha)
        earlier._check_time(timer, start)
        result = diagnose_workbook(handle, timer=timer, start=start)
        earlier._hash_handle(handle, expected_size, expected_sha)
        earlier._check_time(timer, start)
        after = os.fstat(handle.fileno())
        if (before.st_dev, before.st_ino, before.st_nlink, before.st_size) != (
            after.st_dev,
            after.st_ino,
            after.st_nlink,
            after.st_size,
        ):
            raise ValueError("Manhattan diagnostic input changed during parsing")
    earlier._check_file(path, expected_size, expected_sha)
    if (path.stat().st_dev, path.stat().st_ino) != (before.st_dev, before.st_ino):
        raise ValueError("Manhattan diagnostic path changed during parsing")
    return result


def _public_projection(private: dict) -> dict:
    return {
        "protocol": PROTOCOL,
        "projection": "private_only_v1",
        "diagnostic_completed": True,
        "v3_worksheet_qualified": False,
        "sale_labels_certified": 0,
    }


def _intent(source: Path, output: Path, entry: dict) -> dict:
    provenance = earlier._provenance()
    return {
        "protocol": PROTOCOL,
        "run_id": output.name,
        "capture_run_id": source.name,
        "capture_manifest_sha256": earlier.CAPTURE_MANIFEST_SHA256,
        "manhattan_sha256": MANHATTAN_SHA256,
        "manhattan_bytes": entry["bytes"],
        "started_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        **provenance,
        "capture_inspection_environment_lock_sha256": provenance[
            "environment_lock_sha256"
        ],
        "environment_lock_sha256": earlier._sha(ENVIRONMENT_LOCK.read_bytes()),
    }


def _hash_manifest(output: Path, intent: bytes, private: bytes, public: bytes) -> dict:
    return {
        "protocol": PROTOCOL,
        "run_id": output.name,
        "capture_manifest_sha256": earlier.CAPTURE_MANIFEST_SHA256,
        "manhattan_sha256": MANHATTAN_SHA256,
        "intent_sha256": earlier._sha(intent),
        "result_sha256": earlier._sha(private),
        "public_sha256": earlier._sha(public),
    }


def inspect_capture(
    capture_dir: Path, output_dir: Path, *, timer=time.monotonic
) -> dict:
    """Create an exclusive private diagnostic; expose only fixed public fields."""
    start = timer()
    source, entry = _input(capture_dir)
    earlier._check_time(timer, start)
    output = _run_dir(output_dir, new=True)
    intent_bytes = earlier._json_bytes(_intent(source, output, entry))
    output.mkdir(mode=0o700)
    try:
        secure_directory(output)
        verify_acl(output)
        new_file(output / "intent.json", intent_bytes)
        private = _inspect_file(source, entry, timer, start)
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
                "Manhattan failure artifact could not be saved: "
                + type(artifact_error).__name__
            )
        raise


def replay(capture_dir: Path, output_dir: Path, *, timer=time.monotonic) -> dict:
    """Recompute the formula privately and compare canonical saved bytes."""
    start = timer()
    source, entry = _input(capture_dir)
    output = _run_dir(output_dir, new=False)
    verify_acl(output)
    if (output / "failure.json").exists() or earlier._reparse(output / "failure.json"):
        raise ValueError("Manhattan diagnostic run is incomplete")
    intent, intent_bytes = earlier._load_private_json(output, "intent.json")
    _, private_bytes = earlier._load_private_json(output, "result.json")
    _, public_bytes = earlier._load_private_json(output, "public.json")
    hashes, _ = earlier._load_private_json(output, "hash_manifest.json")
    if (
        intent.get("protocol"),
        intent.get("run_id"),
        intent.get("capture_run_id"),
        intent.get("capture_manifest_sha256"),
        intent.get("manhattan_sha256"),
        intent.get("manhattan_bytes"),
    ) != (
        PROTOCOL,
        output.name,
        source.name,
        earlier.CAPTURE_MANIFEST_SHA256,
        MANHATTAN_SHA256,
        entry["bytes"],
    ):
        raise ValueError("Manhattan diagnostic intent differs from frozen capture")
    if intent.get("environment_lock_sha256") != earlier._sha(
        ENVIRONMENT_LOCK.read_bytes()
    ) or intent.get("capture_inspection_environment_lock_sha256") != earlier._sha(
        earlier.ENVIRONMENT_LOCK.read_bytes()
    ):
        raise ValueError("Manhattan diagnostic environment lock differs")
    if hashes != _hash_manifest(output, intent_bytes, private_bytes, public_bytes):
        raise ValueError("Manhattan diagnostic hash manifest differs")
    recomputed = _inspect_file(source, entry, timer, start)
    public = _public_projection(recomputed)
    if (
        earlier._json_bytes(recomputed) != private_bytes
        or earlier._json_bytes(public) != public_bytes
    ):
        raise ValueError("Manhattan diagnostic replay differs from saved result")
    return public


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("diagnose", "replay"))
    parser.add_argument("capture_dir", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    try:
        if args.action == "diagnose":
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
        parser.exit(2, f"Manhattan diagnostic failed: {type(error).__name__}\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
