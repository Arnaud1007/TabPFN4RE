"""Compare pinned NYC archive versions 61 and 62 without admitting sale labels."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import compare_nyc_archive_snapshot_v1 as prior
import private_review_io

ROOT = Path(__file__).resolve().parents[1]
PRIVATE_ROOT = ROOT / "data/raw/nyc_dof"
V61_RUN = PRIVATE_ROOT / "ready-archive-v61-20261002T230327Z"
V62_RUN = PRIVATE_ROOT / "ready-archive-v2-20261002T210520Z"
V61_MANIFEST = ROOT / "runs/u0-nyc-ready-archive-v61-20261002T230327Z/manifest.json"
V62_MANIFEST = (
    ROOT / "runs/u0-nyc-ready-archive-v2-captured-20261002T210520Z/manifest.json"
)
ENVIRONMENT_LOCK = ROOT / "locks/nyc-adjacent-archives-environment.json"
ENVIRONMENT_LOCK_SHA256 = (
    "fcf7f52c014c9af3277b12cd85330171ba492b7cd8a24f12ad2df33b4ebd25d8"
)
PROTOCOL = "nyc-adjacent-archives-v1"
V61_MANIFEST_SHA256 = "52090b7c0279868c54adfbc4b5b043d87d896f79f3ec963a06a8e501b8b4cdab"
V62_MANIFEST_SHA256 = "a85186c249503435494e9c06e4274bbea85d986bba058375cbe7d3537b6e01bc"
V61_SHA256 = "19ecb0eb368df66f60758098213fd4855109e6afa20c82e99787930b893ba0f7"
V62_SHA256 = "0746355101b245fb469ce97e19e088fa2b16f0f95728d7a5b07dd670e98c345f"
V61_BYTES = 11_120_362
V62_BYTES = 11_302_195
V61_ROWS = 79_335
V62_ROWS = 81_567
CODE_FILES = (
    "scripts/compare_nyc_adjacent_archives_v1.py",
    "scripts/compare_nyc_archive_snapshot_v1.py",
    "scripts/private_review_io.py",
)
_RUN_ID = re.compile(r"archive-adjacent-v1-([0-9]{8}T[0-9]{6}Z)-[0-9a-f]{12}\Z")
_STAGES = ("list_before", "status_before", "csv", "status_after", "list_after")
_PINNED_PYTHON = (3, 11, 6)

_pinned_bytes = prior._pinned_bytes
_checked_run_artifact = prior._checked_run_artifact
scan_csv = prior.scan_csv


def _sha(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def _encoded(value: dict) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def validate_source_manifest(
    body: bytes, *, version: int, expected_sha: str, expected_bytes: int
) -> dict:
    """Verify source identity before opening its private CSV."""
    try:
        value = json.loads(body)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("NYC archive manifest is malformed") from error
    if not isinstance(value, dict):
        raise ValueError("NYC archive manifest is malformed")
    expected_protocol = (
        "nyc-ready-rolling-archive-v61-v1"
        if version == 61
        else "nyc-ready-rolling-archive-v2"
        if version == 62
        else None
    )
    requests = value.get("requests")
    if (
        expected_protocol is None
        or value.get("protocol") != expected_protocol
        or type(value.get("version")) is not int
        or value["version"] != version
        or value.get("source_snapshot_sha256") != expected_sha
        or not isinstance(requests, list)
        or len(requests) != len(_STAGES)
        or any(not isinstance(item, dict) for item in requests)
        or tuple(item.get("stage") for item in requests) != _STAGES
    ):
        raise ValueError("NYC archive manifest differs from frozen source")
    csv_request = requests[2]
    if (
        csv_request.get("file") != "archive.csv"
        or csv_request.get("sha256") != expected_sha
        or type(csv_request.get("bytes")) is not int
        or csv_request["bytes"] != expected_bytes
        or csv_request.get("url")
        != (
            "https://data.cityofnewyork.us/api/archival.csv"
            f"?id=usep-8jbt&version={version}&method=export"
        )
    ):
        raise ValueError("NYC archive CSV identity differs from frozen source")
    return value


def compare_archive_rows(
    v61_rows: list[tuple[str, ...]], v62_rows: list[tuple[str, ...]]
) -> dict:
    """Measure strict source-row multiset agreement, preserving duplicates."""
    result = prior.compare_rows(v61_rows, v62_rows)
    return {
        "v61_rows": result["archive_rows"],
        "v62_rows": result["current_rows"],
        "raw_full_row_multiset_matches": result["raw_full_row_multiset_matches"],
        "v61_raw_residual_rows": result["archive_raw_residual_rows"],
        "v62_raw_residual_rows": result["current_raw_residual_rows"],
        "date_canonical_full_row_multiset_matches": result[
            "date_canonical_full_row_multiset_matches"
        ],
        "v61_invalid_date_rows": result["archive_invalid_date_rows"],
        "v62_invalid_date_rows": result["current_invalid_date_rows"],
        "v61_date_eligible_rows": result["archive_date_eligible_rows"],
        "v62_date_eligible_rows": result["current_date_eligible_rows"],
        "v61_date_residual_rows": result["archive_date_residual_rows"],
        "v62_date_residual_rows": result["current_date_residual_rows"],
        "sale_labels_certified": 0,
        "historical_asof_eligible": False,
        "u0_status": "PENDING",
        "u3_status": "PENDING",
        "g_us_status": "PENDING",
    }


def _bucket(value: int) -> str:
    if value == 0:
        return "zero"
    if value < 5:
        return "suppressed_1_to_4"
    if value < 100:
        return "5_to_99"
    if value < 1000:
        return "100_to_999"
    return "1000_plus"


def public_projection(private: dict) -> dict:
    """Expose fixed denominators and broad buckets, never row content."""
    names = (
        "v61_rows",
        "v62_rows",
        "raw_full_row_multiset_matches",
        "date_canonical_full_row_multiset_matches",
    )
    if any(type(private.get(name)) is not int or private[name] < 0 for name in names):
        raise ValueError("Private comparison counters are invalid")
    if any(
        private[name] > min(private["v61_rows"], private["v62_rows"])
        for name in names[2:]
    ):
        raise ValueError("Private overlap exceeds source rows")
    return {
        "protocol": PROTOCOL,
        "v61_rows": private["v61_rows"],
        "v62_rows": private["v62_rows"],
        "raw_overlap_bucket": _bucket(private["raw_full_row_multiset_matches"]),
        "date_overlap_bucket": _bucket(
            private["date_canonical_full_row_multiset_matches"]
        ),
        "sale_labels_certified": 0,
        "historical_asof_eligible": False,
        "u0_status": "PENDING",
        "u3_status": "PENDING",
        "g_us_status": "PENDING",
    }


def _manifests() -> None:
    private_review_io.real_directory(PRIVATE_ROOT, PRIVATE_ROOT.parent)
    private_review_io.verify_acl(PRIVATE_ROOT)
    for run, public, manifest_sha, version, csv_sha, csv_bytes in (
        (V61_RUN, V61_MANIFEST, V61_MANIFEST_SHA256, 61, V61_SHA256, V61_BYTES),
        (V62_RUN, V62_MANIFEST, V62_MANIFEST_SHA256, 62, V62_SHA256, V62_BYTES),
    ):
        private_review_io.real_directory(run, PRIVATE_ROOT)
        private_review_io.verify_acl(run)
        public_body = _pinned_bytes(public, limit=64 * 1024, expected_sha=manifest_sha)
        private_body = _pinned_bytes(
            run / "manifest.json", limit=64 * 1024, expected_sha=manifest_sha
        )
        if public_body != private_body:
            raise ValueError("Archive private/public manifests differ")
        validate_source_manifest(
            public_body,
            version=version,
            expected_sha=csv_sha,
            expected_bytes=csv_bytes,
        )


def _code_hashes() -> dict[str, str]:
    return {name: _sha((ROOT / name).read_bytes()) for name in CODE_FILES}


def _configuration_sha() -> str:
    return _sha(
        _encoded(
            {
                "protocol": PROTOCOL,
                "version_61": [V61_SHA256, V61_BYTES, V61_ROWS, V61_MANIFEST_SHA256],
                "version_62": [V62_SHA256, V62_BYTES, V62_ROWS, V62_MANIFEST_SHA256],
                "header": prior.ARCHIVE_HEADER,
                "date_range": [str(prior._LOW_DATE), str(prior._HIGH_DATE)],
                "max_csv_bytes": prior.MAX_CSV_BYTES,
                "max_rows": prior.MAX_ROWS,
                "max_field_chars": prior.MAX_FIELD_CHARS,
                "max_cell_chars": prior.MAX_CELL_CHARS,
            }
        )
    )


def _git_state() -> tuple[str, bool]:
    return prior._git_state()


def _remote_tracking_commit() -> str:
    return prior._remote_tracking_commit()


def _run_dir(output: Path, *, new: bool) -> Path:
    target = Path(output).absolute()
    private_review_io.real_directory(PRIVATE_ROOT, PRIVATE_ROOT.parent)
    private_review_io.verify_acl(PRIVATE_ROOT)
    match = _RUN_ID.fullmatch(target.name)
    if target.parent != PRIVATE_ROOT.absolute() or match is None or target.is_symlink():
        raise ValueError("Comparison run is outside private NYC root")
    datetime.strptime(match.group(1), "%Y%m%dT%H%M%SZ")
    ignored = subprocess.run(
        ["git", "check-ignore", "-q", "--", str(target)],
        cwd=ROOT,
        capture_output=True,
        check=False,
        timeout=10,
    )
    if ignored.returncode != 0:
        raise ValueError("Comparison run is not Git-ignored")
    if new and target.exists():
        raise FileExistsError("Comparison run already exists")
    if not new:
        private_review_io.real_directory(target, PRIVATE_ROOT)
        private_review_io.verify_acl(target)
    return target


def _assert_runtime() -> None:
    if sys.implementation.name != "cpython" or sys.version_info[:3] != _PINNED_PYTHON:
        raise ValueError("Comparison Python runtime differs from environment lock")


def _intent(output: Path) -> dict:
    commit, dirty = _git_state()
    if dirty:
        raise ValueError("Comparison requires a clean pushed code tree")
    if commit != _remote_tracking_commit():
        raise ValueError(
            "Comparison code commit differs from pushed branch tracking ref"
        )
    _assert_runtime()
    _pinned_bytes(
        ENVIRONMENT_LOCK, limit=64 * 1024, expected_sha=ENVIRONMENT_LOCK_SHA256
    )
    return {
        "protocol": PROTOCOL,
        "run_id": output.name,
        "code_commit": commit,
        "remote_tracking_commit": commit,
        "dirty_tree_at_start": dirty,
        "code_hashes": _code_hashes(),
        "configuration_sha256": _configuration_sha(),
        "environment_lock_sha256": ENVIRONMENT_LOCK_SHA256,
        "v61_manifest_sha256": V61_MANIFEST_SHA256,
        "v62_manifest_sha256": V62_MANIFEST_SHA256,
        "v61_csv_sha256": V61_SHA256,
        "v62_csv_sha256": V62_SHA256,
        "feature_policy_hash": None,
        "split_hash": None,
        "checkpoint_identity": None,
        "started_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }


def _compute() -> dict:
    v61_body = _pinned_bytes(
        V61_RUN / "archive.csv",
        limit=prior.MAX_CSV_BYTES,
        expected_sha=V61_SHA256,
        expected_bytes=V61_BYTES,
    )
    v62_body = _pinned_bytes(
        V62_RUN / "archive.csv",
        limit=prior.MAX_CSV_BYTES,
        expected_sha=V62_SHA256,
        expected_bytes=V62_BYTES,
    )
    v61_rows = scan_csv(v61_body, source="archive", expected_rows=V61_ROWS)
    v62_rows = scan_csv(v62_body, source="archive", expected_rows=V62_ROWS)
    return {"protocol": PROTOCOL, **compare_archive_rows(v61_rows, v62_rows)}


def _write_new(output: Path, name: str, value: dict) -> bytes:
    body = _encoded(value)
    private_review_io.new_file(output / name, body)
    return body


def compare(output: Path) -> dict:
    """Record an intent before either source CSV read and write create-only results."""
    target = _run_dir(output, new=True)
    _manifests()
    intent = _intent(target)
    target.mkdir(mode=0o700)
    try:
        private_review_io.secure_directory(target)
        private_review_io.verify_acl(target)
        intent_body = _write_new(target, "intent.json", intent)
        private = _compute()
        public = public_projection(private)
        result_body = _write_new(target, "result.json", private)
        public_body = _write_new(target, "public.json", public)
        _write_new(
            target,
            "hash_manifest.json",
            {
                "intent_sha256": _sha(intent_body),
                "result_sha256": _sha(result_body),
                "public_sha256": _sha(public_body),
            },
        )
        return public
    except BaseException as error:
        try:
            _write_new(
                target,
                "failure.json",
                {
                    "protocol": PROTOCOL,
                    "run_id": target.name,
                    "status": "incomplete",
                    "category": (
                        "interrupted"
                        if isinstance(error, (KeyboardInterrupt, SystemExit))
                        else "integrity_or_io_failure"
                    ),
                },
            )
        except Exception as artifact_error:
            error.add_note(
                "Comparison failure artifact could not be saved: "
                + type(artifact_error).__name__
            )
        raise


def replay(output: Path) -> dict:
    """Verify saved artifacts and regenerate the aggregate without network access."""
    _assert_runtime()
    target = _run_dir(output, new=False)
    if {item.name for item in target.iterdir()} != {
        "intent.json",
        "result.json",
        "public.json",
        "hash_manifest.json",
    }:
        raise ValueError("Comparison run inventory is incomplete")
    intent_body = _checked_run_artifact(target / "intent.json")
    result_body = _checked_run_artifact(target / "result.json")
    public_body = _checked_run_artifact(target / "public.json")
    hashes = json.loads(_checked_run_artifact(target / "hash_manifest.json"))
    if hashes != {
        "intent_sha256": _sha(intent_body),
        "result_sha256": _sha(result_body),
        "public_sha256": _sha(public_body),
    }:
        raise ValueError("Comparison run artifact hashes differ")
    intent = json.loads(intent_body)
    if (
        intent.get("protocol") != PROTOCOL
        or intent.get("run_id") != target.name
        or intent.get("dirty_tree_at_start") is not False
        or not re.fullmatch(r"[0-9a-f]{40}", intent.get("code_commit", ""))
        or intent.get("remote_tracking_commit") != intent.get("code_commit")
        or intent.get("code_hashes") != _code_hashes()
        or intent.get("configuration_sha256") != _configuration_sha()
        or intent.get("environment_lock_sha256") != ENVIRONMENT_LOCK_SHA256
        or intent.get("v61_manifest_sha256") != V61_MANIFEST_SHA256
        or intent.get("v62_manifest_sha256") != V62_MANIFEST_SHA256
        or intent.get("v61_csv_sha256") != V61_SHA256
        or intent.get("v62_csv_sha256") != V62_SHA256
    ):
        raise ValueError("Comparison run intent differs from pinned code or inputs")
    _manifests()
    _pinned_bytes(
        ENVIRONMENT_LOCK, limit=64 * 1024, expected_sha=ENVIRONMENT_LOCK_SHA256
    )
    private = _compute()
    public = public_projection(private)
    if result_body != _encoded(private) or public_body != _encoded(public):
        raise ValueError("Comparison offline replay differs")
    return public


def plan() -> dict:
    return {
        "protocol": PROTOCOL,
        "v61_csv_sha256": V61_SHA256,
        "v62_csv_sha256": V62_SHA256,
        "v61_rows": V61_ROWS,
        "v62_rows": V62_ROWS,
        "status": "plan_only_no_source_row_read",
        "sale_labels_certified": 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("plan")
    for name in ("compare", "replay"):
        commands.add_parser(name).add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        result = (
            plan()
            if args.command == "plan"
            else compare(args.output)
            if args.command == "compare"
            else replay(args.output)
        )
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(
            2, f"NYC adjacent archive comparison failed: {type(error).__name__}\n"
        )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
