"""Create and replay a protected NYC same-publisher verified-export pilot.

The public projection is fixed and carries no row-derived findings. Private
candidate statuses are comparison aids, never certified sale labels.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import compare_nyc_rolling_borough_rows as v1
import diagnose_nyc_representation_fields_v1 as field
import diagnose_nyc_representations_v2 as v2
import nyc_verified_export_core as core
from private_review_io import new_file, secure_directory, verify_acl

PROJECT_ROOT = v1.PROJECT_ROOT
PRIVATE_ROOT = v1.PRIVATE_ROOT
SAMPLE_PATH = PRIVATE_ROOT / "review-usep-8jbt-20260928T234700Z.jsonl"
SAMPLE_SHA256 = "e137de2cf73aa4a9fea6d024e4564ef6e907020e73fc8dbec3e4026786b189ca"
ENVIRONMENT_LOCK = PROJECT_ROOT / "locks/nyc-verified-export-pilot-environment.json"
PROTOCOL = core.PROTOCOL
SELECTED = v1.SELECTED
CODE_PATHS = (
    "scripts/verify_nyc_review_artifacts_v2.py",
    "scripts/nyc_verified_export_core.py",
)
MAX_SAMPLE_BYTES = 100_000
MAX_PRIVATE_RESULT_BYTES = 1_000_000
MAX_ARTIFACT_BYTES = 1_000_000
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_check_ancestors = v1.earlier._check_ancestors
_provenance = v1._provenance
_remote_pushed = field._remote_pushed
_sha = v1._sha
_json_bytes = v1._json_bytes
_pinned_bytes = v1._pinned_bytes
_publish_json = v1._publish_json


def _environment_sha() -> str:
    body = _pinned_bytes(ENVIRONMENT_LOCK, 64 * 1024, None, "pilot environment lock")
    value = v2._parse_pinned(body, "pilot environment lock")
    if (
        value.get("schema_version") != 1
        or value.get("sample_sha256") != SAMPLE_SHA256
        or value.get("csv_snapshot_sha256") != v1.profile.APPROVED_SNAPSHOT_SHA256
        or value.get("capture_manifest_sha256") != v1.CAPTURE_MANIFEST_SHA
        or value.get("v3_result_sha256") != v1.V3_ARTIFACT_SHA["result.json"]
    ):
        raise ValueError("Pilot environment lock is incompatible")
    return _sha(body)


def _code_hashes() -> dict[str, str]:
    return {
        **v2._code_hashes(),
        "scripts/diagnose_nyc_representation_fields_v1.py": _sha(
            _pinned_bytes(
                PROJECT_ROOT / "scripts/diagnose_nyc_representation_fields_v1.py",
                1024 * 1024,
                None,
                "field runner code",
            )
        ),
        **{
            name: _sha(
                _pinned_bytes(PROJECT_ROOT / name, 1024 * 1024, None, "pilot code")
            )
            for name in CODE_PATHS
        },
    }


def _preflight() -> dict:
    inputs = v1._preflight()
    v3_status = v1._verify_v3()
    if any(
        v3_status[name].get("date_system") != "1900_default" for name, _, _ in SELECTED
    ):
        raise ValueError("Qualified workbook date system differs")
    if (
        inputs["csv_snapshot_sha256"] != v1.profile.APPROVED_SNAPSHOT_SHA256
        or inputs["capture_manifest_sha256"] != v1.CAPTURE_MANIFEST_SHA
        or inputs["v3_result_sha256"] != v1.V3_ARTIFACT_SHA["result.json"]
        or inputs["csv_manifest"]["rows"] != 82_345
    ):
        raise ValueError("Pilot source provenance differs from frozen protocol")
    return {**inputs, "v3_status": v3_status}


def _run_dir(directory: Path, *, new: bool) -> Path:
    target = Path(directory).absolute()
    _check_ancestors(PRIVATE_ROOT)
    _check_ancestors(target)
    match = re.fullmatch(
        r"verified-export-pilot-v1-(\d{8}T\d{6}Z)-([0-9a-f]{12})", target.name
    )
    if target.parent != PRIVATE_ROOT.absolute() or match is None:
        raise ValueError("Pilot path is outside private NYC root")
    try:
        datetime.strptime(match.group(1), "%Y%m%dT%H%M%SZ")
    except ValueError as error:
        raise ValueError("Pilot run ID is invalid") from error
    if not PRIVATE_ROOT.is_dir():
        raise ValueError("Private NYC root is missing")
    verify_acl(PRIVATE_ROOT)
    if new and (target.exists() or v1.earlier._reparse(target)):
        raise FileExistsError("Pilot run already exists")
    if not new and not target.is_dir():
        raise ValueError("Pilot run does not exist")
    return target


def _read_sample() -> set[int]:
    _check_ancestors(SAMPLE_PATH)
    verify_acl(PRIVATE_ROOT)
    data = _pinned_bytes(SAMPLE_PATH, MAX_SAMPLE_BYTES, SAMPLE_SHA256, "frozen sample")
    if not data.endswith(b"\n"):
        raise ValueError("Frozen sample lacks final newline")
    try:
        records = [json.loads(line) for line in data.decode("utf-8").splitlines()]
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("Frozen sample is malformed") from error
    ordinals = [item.get("ordinal") for item in records if isinstance(item, dict)]
    if (
        len(records) != core.SAMPLE_COUNT
        or len(ordinals) != core.SAMPLE_COUNT
        or any(type(item) is not int or not 1 <= item <= 82_345 for item in ordinals)
        or len(set(ordinals)) != core.SAMPLE_COUNT
    ):
        raise ValueError("Frozen sample ordinals are invalid")
    return set(ordinals)


def _sample_boroughs(
    inputs: dict, sample: set[int], timer, start: float
) -> dict[int, str]:
    manifest = inputs["csv_manifest"]
    path = PRIVATE_ROOT / v1.profile._basename(manifest["raw_filename"])
    observed: dict[int, str] = {}
    counts = dict.fromkeys(v1.CSV_COUNTS, 0)

    def scan(handle):
        def receive(ordinal, values):
            code = values[0].strip()
            bucket = code if code in {"1", "2", "3", "4", "5"} else "unknown"
            counts[bucket] += 1
            if ordinal in sample:
                observed[ordinal] = code

        return v1.scanner.scan_pinned_csv(
            handle, manifest["rows"], receive, timer=timer, start=start
        )

    v1._checked_scan(path, manifest["bytes"], manifest["sha256"], scan, timer, start)
    if counts != v1.CSV_COUNTS or set(observed) != sample:
        raise ValueError("Frozen sample CSV scan did not reconcile")
    return observed


def _aggregate(inputs: dict) -> dict:
    """Read the frozen sample and all borough rows only after durable intent."""
    timer, start = time.monotonic, time.monotonic()
    sample = _read_sample()
    boroughs = _sample_boroughs(inputs, sample, timer, start)
    chosen = core.select_pilot(sample, boroughs, SAMPLE_SHA256)
    assessed = []
    for name, code, expected in SELECTED:
        csv = v1._csv_rows(inputs, code, timer, start)
        xlsx = v1._xlsx_rows(inputs, name, code, timer, start)
        if len(csv) != expected or len(xlsx) != expected:
            raise ValueError("Pilot borough row counts differ")
        selected = {item for item in chosen if boroughs[item] == code}
        entries = core.compare_borough(
            csv, xlsx, selected=selected, borough=name, borough_code=code
        )
        for item in entries:
            assessed.append(
                {
                    **item,
                    "csv_source_sha256": inputs["csv_snapshot_sha256"],
                    "workbook_source_sha256": inputs["borough_entries"][name]["sha256"],
                }
            )
        v1.earlier._check_time(timer, start)
    if {item["ordinal"] for item in assessed} != set(chosen):
        raise ValueError("Pilot comparisons do not reconcile with frozen selection")
    return {
        "protocol": PROTOCOL,
        "sample_sha256": SAMPLE_SHA256,
        "capture_manifest_sha256": inputs["capture_manifest_sha256"],
        "csv_snapshot_sha256": inputs["csv_snapshot_sha256"],
        "v3_result_sha256": inputs["v3_result_sha256"],
        "pilot_ordinals": list(chosen),
        "rows": sorted(assessed, key=lambda item: item["ordinal"]),
        "label_status": "unqualified",
        "sale_labels_certified": 0,
    }


def public_projection() -> dict:
    """Return a constant private-only projection; findings never enter it."""
    return {
        "protocol": PROTOCOL,
        "boroughs": [
            {"borough": name, "findings": None, "suppression_reason": "private_only_v1"}
            for name, _, _ in SELECTED
        ],
        "label_status": "unqualified",
        "sale_labels_certified": 0,
    }


def _validate_private(private: dict, inputs: dict) -> None:
    """Reject extra fields or copied source values before saving private output."""
    expected_top = {
        "protocol",
        "sample_sha256",
        "capture_manifest_sha256",
        "csv_snapshot_sha256",
        "v3_result_sha256",
        "pilot_ordinals",
        "rows",
        "label_status",
        "sale_labels_certified",
    }
    if (
        not isinstance(private, dict)
        or set(private) != expected_top
        or type(private["sale_labels_certified"]) is not int
        or (
            private["protocol"],
            private["sample_sha256"],
            private["capture_manifest_sha256"],
            private["csv_snapshot_sha256"],
            private["v3_result_sha256"],
            private["label_status"],
            private["sale_labels_certified"],
        )
        != (
            PROTOCOL,
            SAMPLE_SHA256,
            inputs["capture_manifest_sha256"],
            inputs["csv_snapshot_sha256"],
            inputs["v3_result_sha256"],
            "unqualified",
            0,
        )
    ):
        raise ValueError("Pilot private result metadata differs")
    chosen, rows = private["pilot_ordinals"], private["rows"]
    if (
        not isinstance(chosen, list)
        or len(chosen) != core.PILOT_COUNT
        or any(type(item) is not int or item < 1 for item in chosen)
        or len(set(chosen)) != core.PILOT_COUNT
        or not isinstance(rows, list)
        or len(rows) != core.PILOT_COUNT
        or [item.get("ordinal") for item in rows if isinstance(item, dict)]
        != sorted(chosen)
    ):
        raise ValueError("Pilot private row membership differs")
    allowed = {
        "ordinal",
        "borough",
        "status",
        "workbook_row_number",
        "difference_positions",
        "csv_source_sha256",
        "workbook_source_sha256",
    }
    matched = {
        "unique_candidate_with_field_disagreement",
        "canonical_full_21_concordance",
        "raw_full_21_concordance",
    }
    for item in rows:
        if not isinstance(item, dict) or set(item) != allowed:
            raise ValueError("Pilot private row schema differs")
        name, status = item["borough"], item["status"]
        if (
            type(name) is not str
            or type(status) is not str
            or name not in inputs["borough_entries"]
            or status not in core.STATUSES
        ):
            raise ValueError("Pilot private row scope differs")
        positions = item["difference_positions"]
        if (
            item["csv_source_sha256"] != inputs["csv_snapshot_sha256"]
            or item["workbook_source_sha256"]
            != inputs["borough_entries"][name]["sha256"]
            or not isinstance(positions, list)
            or any(
                type(index) is not int
                or not 1 <= index <= 21
                or index - 1 in core.KEY_COLUMNS
                for index in positions
            )
            or len(set(positions)) != len(positions)
            or (status == "unique_candidate_with_field_disagreement") != bool(positions)
            or (
                status in matched
                and (
                    type(item["workbook_row_number"]) is not int
                    or item["workbook_row_number"] <= 0
                )
            )
            or (status not in matched and item["workbook_row_number"] is not None)
        ):
            raise ValueError("Pilot private row findings differ")


def _intent(output: Path, inputs: dict, provenance: dict, environment_sha: str) -> dict:
    return {
        "protocol": PROTOCOL,
        "run_id": output.name,
        "started_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "selection_algorithm": "two_per_qualified_borough_plus_two_ranked_residual_v1",
        "sample_sha256": SAMPLE_SHA256,
        "capture_manifest_sha256": inputs["capture_manifest_sha256"],
        "csv_snapshot_sha256": inputs["csv_snapshot_sha256"],
        "v3_result_sha256": inputs["v3_result_sha256"],
        "environment_lock_sha256": environment_sha,
        "code_hashes": _code_hashes(),
        **provenance,
    }


def _hash_manifest(output: Path, intent: bytes, private: bytes, public: bytes) -> dict:
    return {
        "protocol": PROTOCOL,
        "run_id": output.name,
        "intent_sha256": _sha(intent),
        "result_sha256": _sha(private),
        "public_sha256": _sha(public),
    }


def _durable_intent(output: Path, body: bytes) -> None:
    # new_file fsyncs its writable descriptor before returning.
    new_file(output / "intent.json", body)
    if os.name != "nt":
        directory_fd = os.open(output, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)


def analyze(output_dir: Path) -> dict:
    """Reserve a create-only intent before opening the sample or source rows."""
    inputs = _preflight()
    environment_sha = _environment_sha()
    provenance = _provenance()
    if provenance["dirty_tree"] or not _remote_pushed(provenance["code_commit"]):
        raise ValueError("Pilot requires a clean pushed code commit")
    output = _run_dir(output_dir, new=True)
    intent = _json_bytes(_intent(output, inputs, provenance, environment_sha))
    output.mkdir(mode=0o700)
    try:
        secure_directory(output)
        verify_acl(output)
        _durable_intent(output, intent)
        private = _aggregate(inputs)
        _validate_private(private, inputs)
        private_bytes = _json_bytes(private)
        if len(private_bytes) > MAX_PRIVATE_RESULT_BYTES:
            raise ValueError("Pilot private result exceeds size cap")
        public = public_projection()
        public_bytes = _json_bytes(public)
        _publish_json(output, "result.json", private_bytes)
        _publish_json(output, "public.json", public_bytes)
        _publish_json(
            output,
            "hash_manifest.json",
            _json_bytes(_hash_manifest(output, intent, private_bytes, public_bytes)),
        )
        return public
    except BaseException as error:
        category = (
            "timeout"
            if isinstance(error, TimeoutError)
            else "interrupted"
            if isinstance(error, (KeyboardInterrupt, SystemExit))
            else "integrity_or_io_failure"
        )
        try:
            _publish_json(
                output,
                "failure.json",
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
                "Pilot failure artifact could not be saved: "
                + type(artifact_error).__name__
            )
        raise


def replay(output_dir: Path) -> dict:
    """Recompute private and public bytes without changing a completed run."""
    output = _run_dir(output_dir, new=False)
    verify_acl(output)
    inventory = {item.name for item in output.iterdir()}
    if inventory != {"intent.json", "result.json", "public.json", "hash_manifest.json"}:
        raise ValueError("Pilot run is incomplete or inventory differs")
    bodies = {
        name: _pinned_bytes(
            output / name,
            MAX_PRIVATE_RESULT_BYTES if name == "result.json" else MAX_ARTIFACT_BYTES,
            None,
            "pilot artifact",
        )
        for name in inventory
    }
    documents = {
        name: v2._parse_pinned(body, "pilot artifact") for name, body in bodies.items()
    }
    inputs = _preflight()
    intent = documents["intent.json"]
    if (
        intent.get("protocol") != PROTOCOL
        or intent.get("run_id") != output.name
        or intent.get("selection_algorithm")
        != "two_per_qualified_borough_plus_two_ranked_residual_v1"
        or intent.get("sample_sha256") != SAMPLE_SHA256
        or intent.get("capture_manifest_sha256") != inputs["capture_manifest_sha256"]
        or intent.get("csv_snapshot_sha256") != inputs["csv_snapshot_sha256"]
        or intent.get("v3_result_sha256") != inputs["v3_result_sha256"]
        or intent.get("environment_lock_sha256") != _environment_sha()
        or intent.get("code_hashes") != _code_hashes()
        or intent.get("dirty_tree") is not False
        or not isinstance(intent.get("code_commit"), str)
        or re.fullmatch(r"[0-9a-f]{40}", intent["code_commit"]) is None
        or documents["hash_manifest.json"]
        != _hash_manifest(
            output, bodies["intent.json"], bodies["result.json"], bodies["public.json"]
        )
    ):
        raise ValueError("Pilot provenance differs")
    private = _aggregate(inputs)
    _validate_private(private, inputs)
    public = public_projection()
    if (
        _json_bytes(private) != bodies["result.json"]
        or _json_bytes(public) != bodies["public.json"]
    ):
        raise ValueError("Pilot replay differs")
    return public


def plan() -> dict:
    return {
        "protocol": PROTOCOL,
        "sample_sha256": SAMPLE_SHA256,
        "csv_snapshot_sha256": v1.profile.APPROVED_SNAPSHOT_SHA256,
        "capture_manifest_sha256": v1.CAPTURE_MANIFEST_SHA,
        "v3_result_sha256": v1.V3_ARTIFACT_SHA["result.json"],
        "expected_boroughs": [name for name, _, _ in SELECTED],
        "status": "plan_only_no_private_read",
        "label_status": "unqualified",
        "sale_labels_certified": 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("plan")
    for name in ("analyze", "replay"):
        command = commands.add_parser(name)
        command.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    try:
        result = (
            plan()
            if args.command == "plan"
            else analyze(args.output_dir)
            if args.command == "analyze"
            else replay(args.output_dir)
        )
    except (
        OSError,
        ValueError,
        TimeoutError,
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
    ) as error:
        parser.exit(2, f"NYC verified-export pilot failed: {type(error).__name__}\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
