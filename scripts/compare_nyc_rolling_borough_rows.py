"""Compare pinned NYC API and borough exports offline without admitting labels."""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import capture_nyc_dof_borough_exports as capture
import inspect_nyc_dof_borough_exports as earlier
import nyc_row_concordance_core as core
import nyc_row_concordance_input as scanner
import profile_nyc_rolling_snapshot as profile
from private_review_io import new_file, secure_directory, verify_acl

PROJECT_ROOT = earlier.PROJECT_ROOT
PRIVATE_ROOT = earlier.PRIVATE_ROOT
CAPTURE_DIR = PRIVATE_ROOT / "official-exports-20260929T033558Z-62ad417fb39f"
V3_DIR = PRIVATE_ROOT / "worksheet-inspection-v3-20260930T092659Z-6acaf2c84265"
SNAPSHOT_MANIFEST = (
    PROJECT_ROOT / "runs/u0-nyc-rolling-snapshot-20260928T225512Z/snapshot.json"
)
ENVIRONMENT_LOCK = PROJECT_ROOT / "locks/nyc-row-concordance-environment.json"
PROTOCOL = "nyc-dof-same-publisher-row-concordance-v1"
SNAPSHOT_MANIFEST_SHA = (
    "45049ce1622ba4a819f29c79097869c9f3601d049139869982ec7327ee11962b"
)
CAPTURE_MANIFEST_SHA = earlier.CAPTURE_MANIFEST_SHA256
V3_ARTIFACT_SHA = {
    "intent.json": "9bfa345ed8dbdb155fdc4b79395ef340e3cbfb40db365ea78047ab677a02a486",
    "result.json": "61dcb9bce362658c475df5e43fa2407e18cb0d85779654941ab67bbb8ee00f83",
    "public.json": "f2a76cf11a47580f3534366474646695eb427ac2149370465955040863fdd314",
    "hash_manifest.json": "e375dbb7480ad909d5d49cbbf33d0a042549d53bcaeab303d4a4f3f9baa7e880",
}
SELECTED = (
    ("Bronx", "2", 6424),
    ("Brooklyn", "3", 23041),
    ("Queens", "4", 26461),
    ("Staten Island", "5", 6866),
)
CSV_COUNTS = {"1": 19553, "2": 6424, "3": 23041, "4": 26461, "5": 6866, "unknown": 0}
MAX_PRIVATE_RESULT_BYTES = 64 * 1024 * 1024
CODE_PATHS = (
    "scripts/compare_nyc_rolling_borough_rows.py",
    "scripts/nyc_row_concordance_core.py",
    "scripts/nyc_row_concordance_input.py",
    "scripts/nyc_workbook_xml_v3.py",
    "scripts/nyc_workbook_xml.py",
    "scripts/profile_nyc_rolling_snapshot.py",
    "scripts/capture_nyc_dof_borough_exports.py",
    "scripts/inspect_nyc_dof_borough_exports.py",
    "scripts/private_review_io.py",
)


def _sha(body: bytes) -> str:
    return earlier._sha(body)


def _json_bytes(value: dict) -> bytes:
    return earlier._json_bytes(value)


def _pinned_bytes(path: Path, limit: int, expected: str | None, kind: str) -> bytes:
    if earlier._reparse(path) or not path.is_file() or path.stat().st_nlink != 1:
        raise ValueError(f"Pinned {kind} is missing or linked")
    if path.stat().st_size > limit:
        raise ValueError(f"Pinned {kind} exceeds size cap")
    with path.open("rb") as handle:
        before = os.fstat(handle.fileno())
        if before.st_nlink != 1 or before.st_size > limit:
            raise ValueError(f"Pinned {kind} exceeds size cap or changed")
        body = handle.read(limit + 1)
        after = os.fstat(handle.fileno())
    if (
        len(body) > limit
        or len(body) != before.st_size
        or (before.st_dev, before.st_ino, before.st_size)
        != (after.st_dev, after.st_ino, after.st_size)
    ):
        raise ValueError(f"Pinned {kind} exceeds size cap or changed")
    if expected is not None and _sha(body) != expected:
        raise ValueError(f"Pinned {kind} digest differs")
    if (
        earlier._reparse(path)
        or path.stat().st_nlink != 1
        or (path.stat().st_dev, path.stat().st_ino, path.stat().st_size)
        != (before.st_dev, before.st_ino, before.st_size)
    ):
        raise ValueError(f"Pinned {kind} changed during read")
    return body


def _publish_json(output: Path, name: str, body: bytes) -> None:
    temporary = output / (".row-concordance-" + secrets.token_hex(16))
    try:
        new_file(temporary, body)
        os.link(temporary, output / name)
    finally:
        temporary.unlink(missing_ok=True)


def _run_dir(directory: Path, *, new: bool) -> Path:
    target = Path(directory).absolute()
    earlier._check_ancestors(PRIVATE_ROOT)
    earlier._check_ancestors(target)
    match = re.fullmatch(
        r"row-concordance-v1-(\d{8}T\d{6}Z)-([0-9a-f]{12})", target.name
    )
    if target.parent != PRIVATE_ROOT.absolute() or match is None:
        raise ValueError("Row-concordance path is outside private NYC root")
    try:
        datetime.strptime(match.group(1), "%Y%m%dT%H%M%SZ")
    except ValueError as error:
        raise ValueError("Row-concordance run ID is invalid") from error
    if not PRIVATE_ROOT.is_dir():
        raise ValueError("Private NYC root is missing")
    verify_acl(PRIVATE_ROOT)
    if new and (target.exists() or earlier._reparse(target)):
        raise FileExistsError("Row-concordance run already exists")
    if not new and not target.is_dir():
        raise ValueError("Row-concordance run does not exist")
    return target


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
    return {"code_commit": commit, "dirty_tree": bool(status.strip())}


def _code_hashes() -> dict[str, str]:
    return {
        name: _sha(_pinned_bytes(PROJECT_ROOT / name, 1024 * 1024, None, "code file"))
        for name in CODE_PATHS
    }


def _verify_v3() -> dict:
    earlier._check_ancestors(V3_DIR)
    verify_acl(V3_DIR)
    inventory = {item.name for item in V3_DIR.iterdir()}
    if inventory != set(V3_ARTIFACT_SHA):
        raise ValueError("Pinned v3 artifact inventory differs")
    documents = {}
    for name, expected in V3_ARTIFACT_SHA.items():
        path = V3_DIR / name
        body = _pinned_bytes(path, earlier.MAX_JSON_BYTES, expected, "v3 artifact")
        try:
            value = json.loads(body)
        except (UnicodeError, json.JSONDecodeError) as error:
            raise ValueError("Pinned v3 artifact is invalid JSON") from error
        if not isinstance(value, dict) or body != _json_bytes(value):
            raise ValueError("Pinned v3 artifact is not canonical")
        documents[name] = value
    result = documents["result.json"]
    hashes = documents["hash_manifest.json"]
    if (
        result.get("protocol") != "nyc-borough-worksheet-inspection-v3"
        or result.get("worksheet_qualified_count") != 4
        or result.get("sale_labels_certified") != 0
        or len(result.get("files", [])) != 5
        or hashes.get("result_sha256") != V3_ARTIFACT_SHA["result.json"]
        or hashes.get("public_sha256") != V3_ARTIFACT_SHA["public.json"]
    ):
        raise ValueError("Pinned v3 result is incompatible")
    status = {item["borough"]: item for item in result["files"]}
    if status.get("Manhattan", {}).get("worksheet_qualified") is not False:
        raise ValueError("Pinned Manhattan exclusion differs")
    for borough, _, rows in SELECTED:
        item = status.get(borough, {})
        if not item.get("worksheet_qualified") or item.get("data_rows") != rows:
            raise ValueError("Pinned qualified borough differs")
    return status


def _preflight() -> dict:
    earlier._check_ancestors(PRIVATE_ROOT)
    verify_acl(PRIVATE_ROOT)
    snapshot_body = _pinned_bytes(
        SNAPSHOT_MANIFEST,
        profile.MAX_MANIFEST_BYTES,
        SNAPSHOT_MANIFEST_SHA,
        "CSV snapshot manifest",
    )
    csv_manifest = profile._manifest_bytes(snapshot_body)
    if csv_manifest["rows"] != 82345:
        raise ValueError("Pinned CSV row count differs")
    source = capture._run_directory(CAPTURE_DIR, new=False)
    verify_acl(source)
    capture_manifest, body = capture._load_json(
        source / "manifest.json", capture.MAX_MANIFEST_BYTES
    )
    if _sha(body) != CAPTURE_MANIFEST_SHA:
        raise ValueError("Pinned borough capture manifest differs")
    entries = earlier._expected_files(capture_manifest)
    if len(entries) != 5:
        raise ValueError("Pinned borough capture inventory differs")
    by_borough = {item["borough"]: item for item in entries}
    v3_status = _verify_v3()
    for borough, _, _ in SELECTED:
        if by_borough[borough]["sha256"] != v3_status[borough]["sha256"]:
            raise ValueError("V3 and capture workbook hashes differ")
    return {
        "capture_manifest_sha256": CAPTURE_MANIFEST_SHA,
        "csv_snapshot_sha256": csv_manifest["sha256"],
        "v3_result_sha256": V3_ARTIFACT_SHA["result.json"],
        "csv_manifest": csv_manifest,
        "borough_entries": by_borough,
    }


def _checked_scan(path: Path, size: int, digest: str, scan, timer, start):
    earlier._check_file(path, size, digest)
    with path.open("rb") as handle:
        before = os.fstat(handle.fileno())
        if before.st_nlink != 1 or before.st_size != size:
            raise ValueError("Row-concordance input handle differs")
        earlier._hash_handle(handle, size, digest)
        earlier._check_time(timer, start)
        value = scan(handle)
        earlier._hash_handle(handle, size, digest)
        earlier._check_time(timer, start)
        after = os.fstat(handle.fileno())
        if (before.st_dev, before.st_ino, before.st_nlink, before.st_size) != (
            after.st_dev,
            after.st_ino,
            after.st_nlink,
            after.st_size,
        ):
            raise ValueError("Row-concordance input changed during parsing")
    earlier._check_file(path, size, digest)
    if (path.stat().st_dev, path.stat().st_ino) != (before.st_dev, before.st_ino):
        raise ValueError("Row-concordance input path changed during parsing")
    return value


def _csv_rows(inputs: dict, code: str, timer, start) -> list:
    manifest = inputs["csv_manifest"]
    path = PRIVATE_ROOT / profile._basename(manifest["raw_filename"])
    rows = []
    counts = dict.fromkeys(CSV_COUNTS, 0)

    def scan(handle):
        def receive(ordinal, values):
            observed = values[0].strip()
            bucket = (
                observed
                if observed in CSV_COUNTS and observed != "unknown"
                else "unknown"
            )
            counts[bucket] += 1
            if observed == code:
                rows.append((ordinal, values))

        return scanner.scan_pinned_csv(
            handle, manifest["rows"], receive, timer=timer, start=start
        )

    _checked_scan(path, manifest["bytes"], manifest["sha256"], scan, timer, start)
    if counts != CSV_COUNTS:
        raise ValueError("Pinned CSV borough counts differ")
    return rows


def _xlsx_rows(inputs: dict, borough: str, code: str, timer, start) -> list:
    entry = inputs["borough_entries"][borough]
    path = CAPTURE_DIR / entry["filename"]
    rows = []

    def scan(handle):
        return scanner.scan_qualified_workbook(
            handle,
            code,
            lambda ordinal, values: rows.append((ordinal, values)),
            timer=timer,
            start=start,
        )

    _checked_scan(path, entry["bytes"], entry["sha256"], scan, timer, start)
    return rows


def _aggregate(inputs: dict, timer, start: float) -> dict:
    boroughs = []
    for borough, code, expected in SELECTED:
        csv_rows = _csv_rows(inputs, code, timer, start)
        xlsx_rows = _xlsx_rows(inputs, borough, code, timer, start)
        if len(csv_rows) != expected or len(xlsx_rows) != expected:
            raise ValueError("Pinned borough row count differs")
        boroughs.append(
            core.compare_borough(
                csv_rows, xlsx_rows, borough=borough, borough_code=code
            )
        )
        earlier._check_time(timer, start)
    return {
        "protocol": PROTOCOL,
        "capture_manifest_sha256": inputs["capture_manifest_sha256"],
        "csv_snapshot_sha256": inputs["csv_snapshot_sha256"],
        "v3_result_sha256": inputs["v3_result_sha256"],
        "csv_source_rows": 82345,
        "excluded_manhattan_csv_rows": CSV_COUNTS["1"],
        "csv_frame_rows": sum(item["csv_rows"] for item in boroughs),
        "xlsx_frame_rows": sum(item["xlsx_rows"] for item in boroughs),
        "boroughs": boroughs,
        "label_status": "unqualified",
        "sale_labels_certified": 0,
    }


def _public_projection(private: dict) -> dict:
    return {
        "protocol": PROTOCOL,
        "capture_manifest_sha256": private["capture_manifest_sha256"],
        "csv_snapshot_sha256": private["csv_snapshot_sha256"],
        "v3_result_sha256": private["v3_result_sha256"],
        "csv_source_rows": private["csv_source_rows"],
        "excluded_manhattan_csv_rows": private["excluded_manhattan_csv_rows"],
        "csv_frame_rows": private["csv_frame_rows"],
        "xlsx_frame_rows": private["xlsx_frame_rows"],
        "boroughs": [core.public_projection(item) for item in private["boroughs"]],
        "label_status": "unqualified",
        "sale_labels_certified": 0,
    }


def _intent(output: Path, inputs: dict) -> dict:
    provenance = _provenance()
    return {
        "protocol": PROTOCOL,
        "run_id": output.name,
        "started_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "capture_manifest_sha256": inputs["capture_manifest_sha256"],
        "csv_snapshot_sha256": inputs["csv_snapshot_sha256"],
        "v3_result_sha256": inputs["v3_result_sha256"],
        **provenance,
        "environment_lock_sha256": _sha(
            _pinned_bytes(ENVIRONMENT_LOCK, 64 * 1024, None, "environment lock")
        ),
        "code_hashes": _code_hashes(),
    }


def _hash_manifest(output: Path, intent: bytes, private: bytes, public: bytes) -> dict:
    return {
        "protocol": PROTOCOL,
        "run_id": output.name,
        "intent_sha256": _sha(intent),
        "result_sha256": _sha(private),
        "public_sha256": _sha(public),
    }


def compare_sources(output_dir: Path, *, timer=time.monotonic) -> dict:
    """Create a protected comparison, leaving all labels unqualified."""
    start = timer()
    inputs = _preflight()
    output = _run_dir(output_dir, new=True)
    intent = _intent(output, inputs)
    if intent["dirty_tree"]:
        raise ValueError("Row-concordance run requires a clean code tree")
    intent_bytes = _json_bytes(intent)
    output.mkdir(mode=0o700)
    try:
        secure_directory(output)
        verify_acl(output)
        _publish_json(output, "intent.json", intent_bytes)
        private = _aggregate(inputs, timer, start)
        private_bytes = _json_bytes(private)
        if len(private_bytes) > MAX_PRIVATE_RESULT_BYTES:
            raise ValueError("Row-concordance private result exceeds cap")
        public = _public_projection(private)
        public_bytes = _json_bytes(public)
        _publish_json(output, "result.json", private_bytes)
        _publish_json(output, "public.json", public_bytes)
        hashes = _hash_manifest(output, intent_bytes, private_bytes, public_bytes)
        _publish_json(output, "hash_manifest.json", _json_bytes(hashes))
        return public
    except BaseException as error:
        if isinstance(error, TimeoutError):
            category = "timeout"
        elif isinstance(error, (KeyboardInterrupt, SystemExit)):
            category = "interrupted"
        else:
            category = "integrity_or_io_failure"
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
                "Row-concordance failure artifact could not be saved: "
                + type(artifact_error).__name__
            )
        raise


def _load_private_result(output: Path) -> tuple[dict, bytes]:
    path = output / "result.json"
    if (
        earlier._reparse(path)
        or not path.is_file()
        or path.stat().st_nlink != 1
        or path.stat().st_size > MAX_PRIVATE_RESULT_BYTES
    ):
        raise ValueError("Row-concordance private result is missing or unsafe")
    body = path.read_bytes()
    try:
        value = json.loads(body)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("Row-concordance private result is invalid JSON") from error
    if not isinstance(value, dict) or body != _json_bytes(value):
        raise ValueError("Row-concordance private result is not canonical")
    return value, body


def replay(output_dir: Path, *, timer=time.monotonic) -> dict:
    """Recompute exact private and public outputs from unchanged pinned sources."""
    start = timer()
    output = _run_dir(output_dir, new=False)
    verify_acl(output)
    if (output / "failure.json").exists() or earlier._reparse(output / "failure.json"):
        raise ValueError("Row-concordance run is incomplete")
    intent, intent_bytes = earlier._load_private_json(output, "intent.json")
    _, private_bytes = _load_private_result(output)
    _, public_bytes = earlier._load_private_json(output, "public.json")
    hashes, _ = earlier._load_private_json(output, "hash_manifest.json")
    inputs = _preflight()
    if (
        intent.get("protocol"),
        intent.get("run_id"),
        intent.get("capture_manifest_sha256"),
        intent.get("csv_snapshot_sha256"),
        intent.get("v3_result_sha256"),
        intent.get("environment_lock_sha256"),
        intent.get("code_hashes"),
        bool(re.fullmatch(r"[0-9a-f]{40}", intent.get("code_commit", ""))),
        intent.get("dirty_tree"),
    ) != (
        PROTOCOL,
        output.name,
        inputs["capture_manifest_sha256"],
        inputs["csv_snapshot_sha256"],
        inputs["v3_result_sha256"],
        _sha(_pinned_bytes(ENVIRONMENT_LOCK, 64 * 1024, None, "environment lock")),
        _code_hashes(),
        True,
        False,
    ):
        raise ValueError("Row-concordance intent differs from pinned inputs")
    if hashes != _hash_manifest(output, intent_bytes, private_bytes, public_bytes):
        raise ValueError("Row-concordance hash manifest differs")
    recomputed = _aggregate(inputs, timer, start)
    public = _public_projection(recomputed)
    if _json_bytes(recomputed) != private_bytes or _json_bytes(public) != public_bytes:
        raise ValueError("Row-concordance replay differs from saved result")
    return public


def plan() -> dict:
    """Expose fixed safe metadata without opening source rows."""
    return {
        "protocol": PROTOCOL,
        "capture_manifest_sha256": CAPTURE_MANIFEST_SHA,
        "csv_snapshot_sha256": profile.APPROVED_SNAPSHOT_SHA256,
        "v3_result_sha256": V3_ARTIFACT_SHA["result.json"],
        "expected_boroughs": [item[0] for item in SELECTED],
        "expected_rows_per_source": sum(item[2] for item in SELECTED),
        "status": "plan_only_no_row_read",
        "label_status": "unqualified",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("plan")
    for name in ("compare", "replay"):
        command = commands.add_parser(name)
        command.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "plan":
            result = plan()
        elif args.command == "compare":
            result = compare_sources(args.output_dir)
        else:
            result = replay(args.output_dir)
    except (OSError, ValueError, TimeoutError, subprocess.CalledProcessError) as error:
        parser.exit(2, f"NYC row concordance failed: {type(error).__name__}\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
