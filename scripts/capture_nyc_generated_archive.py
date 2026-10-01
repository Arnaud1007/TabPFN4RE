"""Capture one already-generated NYC rolling-sales archive, for U0 inventory.

No archive generation is permitted. Raw source bytes remain private and do not
constitute certified sale labels or historical as-of features.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from urllib.request import HTTPRedirectHandler, build_opener

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import private_review_io


PROTOCOL = "nyc-ready-rolling-archive-v1"
DATASET_ID = "usep-8jbt"
VERSION = 62
REVISION_CREATED_AT = "2026-04-20T18:29:25.966Z"
ARCHIVE_DATASET_NAME = "foxtrot.67157"
HOST = "https://data.cityofnewyork.us"
LIST_URL = f"{HOST}/api/archival?id={DATASET_ID}&version=1"
STATUS_URL = f"{HOST}/api/archival?id={DATASET_ID}&version={VERSION}&method=status"
CSV_URL = f"{HOST}/api/archival.csv?id={DATASET_ID}&version={VERSION}&method=export"
REQUEST_PLAN = (
    ("list_before", LIST_URL, "list-before.json"),
    ("status_before", STATUS_URL, "status-before.json"),
    ("csv", CSV_URL, "archive.csv"),
    ("status_after", STATUS_URL, "status-after.json"),
    ("list_after", LIST_URL, "list-after.json"),
)
ROOT = Path(__file__).resolve().parents[1]
PRIVATE_ROOT = ROOT / "data" / "raw" / "nyc_dof"
ENVIRONMENT_LOCK = ROOT / "locks" / "nyc-ready-archive-environment.json"
MAX_LIST_BYTES = 1024 * 1024
MAX_STATUS_BYTES = 4096
MAX_CSV_BYTES = 128 * 1024 * 1024
MAX_ROWS = 150_000
MAX_MANIFEST_BYTES = 64 * 1024
TIMEOUT_SECONDS = 30
MAX_TRANSFER_SECONDS = 240
CHUNK_BYTES = 1024 * 1024
REQUIRED_FIELDS = frozenset({"borough", "address", "sale_price", "sale_date"})
TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z\Z")


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        raise ValueError("Source redirect rejected")


HTTP = build_opener(_NoRedirect())
HTTP.addheaders = [("User-Agent", "TabPFN4RealEstate U0 ready archive audit")]


def _http_open(url: str, *, timeout: int):
    if url not in (LIST_URL, STATUS_URL, CSV_URL):
        raise ValueError("Unapproved NYC archive URL")
    return HTTP.open(url, timeout=timeout)


def _pairs(items: list[tuple[str, object]]) -> dict:
    value = {}
    for key, item in items:
        if key in value:
            raise ValueError("Duplicate JSON key")
        value[key] = item
    return value


def _json(body: bytes, limit: int) -> object:
    if not isinstance(body, bytes) or not body or len(body) > limit:
        raise ValueError("Source JSON is empty or oversized")
    try:
        return json.loads(body.decode("utf-8"), object_pairs_hook=_pairs)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("Source JSON is invalid") from error


def _timestamp(value: object) -> str:
    if not isinstance(value, str) or TIMESTAMP.fullmatch(value) is None:
        raise ValueError("Archive timestamp format differs")
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ")
    except ValueError as error:
        raise ValueError("Archive timestamp is invalid") from error
    return value


def _parse_list(body: bytes) -> dict:
    rows = _json(body, MAX_LIST_BYTES)
    if not isinstance(rows, list) or not 1 <= len(rows) <= 64:
        raise ValueError("Archive version list is invalid")
    seen = set()
    selected = None
    for row in rows:
        if not isinstance(row, dict) or set(row) != {
            "createdAt",
            "version",
            "startVersion",
            "visible",
        }:
            raise ValueError("Archive version metadata differs")
        version = row["version"]
        if (
            type(version) is not int
            or version <= 0
            or version in seen
            or type(row["startVersion"]) is not int
            or row["startVersion"] < 0
            or type(row["visible"]) is not bool
        ):
            raise ValueError("Archive version identity differs")
        _timestamp(row["createdAt"])
        seen.add(version)
        if version == VERSION:
            selected = row
    if selected != {
        "createdAt": REVISION_CREATED_AT,
        "version": VERSION,
        "startVersion": 61,
        "visible": True,
    }:
        raise ValueError("Pinned archive revision is unavailable or changed")
    return dict(selected)


def _parse_status(body: bytes) -> dict:
    value = _json(body, MAX_STATUS_BYTES)
    if not isinstance(value, dict) or set(value) != {"type", "value"}:
        raise ValueError("Archive status shape differs")
    detail = value["value"]
    if (
        value["type"] != "done"
        or not isinstance(detail, dict)
        or set(detail) != {"datasetName", "version"}
        or type(detail["version"]) is not int
        or detail["version"] != VERSION
        or detail["datasetName"] != ARCHIVE_DATASET_NAME
    ):
        raise ValueError("Pinned archive is not already generated")
    return dict(detail)


def _utc_now(clock) -> str:
    instant = clock()
    if (
        not isinstance(instant, datetime)
        or instant.tzinfo is None
        or instant.utcoffset() is None
    ):
        raise ValueError("Capture clock must be timezone-aware")
    return (
        instant.astimezone(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def _git_state() -> tuple[str, bool]:
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    dirty = bool(
        subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    )
    return commit, dirty


def _check_git_ignored(path: Path) -> None:
    result = subprocess.run(
        ["git", "check-ignore", "-q", "--", str(path)],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise ValueError("Archive run is not Git-ignored")


def _private_directory(path: Path, *, existing: bool) -> Path:
    root = PRIVATE_ROOT.absolute()
    private_review_io.real_directory(root, root.parent)
    target = Path(path).absolute()
    if (
        target.parent != root
        or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}", target.name) is None
    ):
        raise ValueError("Archive run must be directly inside the private NYC root")
    if target.is_symlink():
        raise ValueError("Archive run redirects")
    _check_git_ignored(target)
    if existing:
        private_review_io.real_directory(target, root)
        private_review_io.verify_acl(target)
    elif target.exists():
        raise FileExistsError("Archive run already exists")
    return target


def _open_exact(opener, url: str, *, csv_response: bool):
    if url not in (LIST_URL, STATUS_URL, CSV_URL):
        raise ValueError("Unapproved NYC archive URL")
    response = opener(url, timeout=TIMEOUT_SECONDS)
    if response.geturl() != url or response.status != 200:
        response.close()
        raise ValueError("Archive response URL or status differs")
    content_type = (
        response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
    )
    expected = "text/csv" if csv_response else "application/json"
    if (
        content_type != expected
        or response.headers.get("Content-Encoding", "identity").lower() != "identity"
    ):
        response.close()
        raise ValueError("Archive response type or encoding differs")
    return response


def _read_small(opener, url: str, limit: int) -> bytes:
    started = time.monotonic()
    with _open_exact(opener, url, csv_response=False) as response:
        declared = response.headers.get("Content-Length")
        if declared is not None and (
            re.fullmatch(r"0|[1-9][0-9]*", declared) is None or int(declared) > limit
        ):
            raise ValueError("Archive JSON Content-Length is invalid or oversized")
        chunks = []
        size = 0
        while True:
            remaining = TIMEOUT_SECONDS - (time.monotonic() - started)
            if remaining <= 0:
                raise TimeoutError("Archive JSON GET exceeded elapsed-time budget")
            _set_socket_timeout(response, remaining)
            chunk = response.read(min(64 * 1024, limit - size + 1))
            if time.monotonic() - started > TIMEOUT_SECONDS:
                raise TimeoutError("Archive JSON GET exceeded elapsed-time budget")
            if not chunk:
                break
            size += len(chunk)
            if size > limit:
                raise ValueError("Archive JSON response exceeds byte limit")
            chunks.append(chunk)
        body = b"".join(chunks)
    if (
        not body
        or len(body) > limit
        or (declared is not None and len(body) != int(declared))
    ):
        raise ValueError("Archive JSON response is empty, oversized or truncated")
    return body


def _set_socket_timeout(response, remaining: float) -> None:
    socket = getattr(getattr(getattr(response, "fp", None), "raw", None), "_sock", None)
    if socket is not None:
        socket.settimeout(min(TIMEOUT_SECONDS, remaining))


def _save_new(path: Path, body: bytes) -> None:
    private_review_io.new_file(path, body)


def _download_csv(opener, destination: Path) -> tuple[int, str]:
    size = 0
    digest = sha256()
    start = time.monotonic()
    with _open_exact(opener, CSV_URL, csv_response=True) as response:
        declared = response.headers.get("Content-Length")
        if declared is not None and (
            re.fullmatch(r"0|[1-9][0-9]*", declared) is None
            or int(declared) > MAX_CSV_BYTES
        ):
            raise ValueError("Archive CSV Content-Length is invalid or oversized")
        with destination.open("xb") as output:
            while True:
                remaining = MAX_TRANSFER_SECONDS - (time.monotonic() - start)
                if remaining <= 0:
                    raise TimeoutError(
                        "Archive CSV transfer exceeded elapsed-time budget"
                    )
                _set_socket_timeout(response, remaining)
                chunk = response.read(min(CHUNK_BYTES, MAX_CSV_BYTES - size + 1))
                if time.monotonic() - start > MAX_TRANSFER_SECONDS:
                    raise TimeoutError(
                        "Archive CSV transfer exceeded elapsed-time budget"
                    )
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_CSV_BYTES:
                    raise ValueError("Archive CSV exceeds byte limit")
                output.write(chunk)
                digest.update(chunk)
            output.flush()
            os.fsync(output.fileno())
    if not size or (declared is not None and size != int(declared)):
        raise ValueError("Archive CSV is empty or truncated")
    return size, digest.hexdigest()


def _normalize_field(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def _check_csv(path: Path) -> tuple[int, str]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.reader(stream, strict=True)
            header = next(reader, None)
            if not header or any(not field.strip() for field in header):
                raise ValueError("Archive CSV header is empty")
            normalized = [_normalize_field(field) for field in header]
            if len(set(normalized)) != len(normalized) or not REQUIRED_FIELDS.issubset(
                normalized
            ):
                raise ValueError("Archive CSV header lacks unique required fields")
            rows = 0
            for record in reader:
                rows += 1
                if rows > MAX_ROWS or len(record) != len(header):
                    raise ValueError("Archive CSV row count or width differs")
    except (csv.Error, UnicodeError) as error:
        raise ValueError("Archive CSV cannot be parsed") from error
    if rows == 0:
        raise ValueError("Archive CSV has no data rows")
    header_hash = sha256(
        json.dumps(header, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    return rows, header_hash


def _encoded(value: dict) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _configuration() -> dict:
    return {
        "protocol": PROTOCOL,
        "dataset_id": DATASET_ID,
        "version": VERSION,
        "request_plan": REQUEST_PLAN,
        "max_csv_bytes": MAX_CSV_BYTES,
        "max_rows": MAX_ROWS,
    }


def _aggregate(
    raw: dict[str, bytes],
    csv_path: Path,
    csv_size: int,
    csv_hash: str,
    completed_at: str,
) -> dict:
    before = _parse_list(raw["list-before.json"])
    after = _parse_list(raw["list-after.json"])
    status_before = _parse_status(raw["status-before.json"])
    status_after = _parse_status(raw["status-after.json"])
    if before != after or status_before != status_after:
        raise ValueError("Pinned archive changed during capture")
    rows, header_hash = _check_csv(csv_path)
    return {
        "protocol": PROTOCOL,
        "status": "inventory_only",
        "dataset_id": DATASET_ID,
        "version": VERSION,
        "revision_created_at": before["createdAt"],
        "captured_at_utc": completed_at,
        "rows": rows,
        "bytes": csv_size,
        "csv_sha256": csv_hash,
        "header_sha256": header_hash,
        "historical_asof_eligible": False,
        "sale_labels_certified": 0,
    }


def capture(
    run_dir: Path, opener=None, clock=lambda: datetime.now(timezone.utc)
) -> dict:
    """Capture five fixed GET responses into a private create-only run."""
    run_dir = _private_directory(run_dir, existing=False)
    commit, dirty = _git_state()
    if dirty or re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        raise ValueError(
            "Archive capture requires a committed checkout with no dirty files"
        )
    opened = _http_open if opener is None else opener
    run_dir.mkdir(mode=0o700)
    private_review_io.secure_directory(run_dir)
    private_review_io.verify_acl(run_dir)
    started_at = _utc_now(clock)
    requests = []
    raw = {}
    csv_size = 0
    csv_hash = ""
    for stage, url, filename in REQUEST_PLAN:
        if stage == "csv":
            csv_size, csv_hash = _download_csv(opened, run_dir / filename)
            size, digest = csv_size, csv_hash
        else:
            limit = MAX_LIST_BYTES if stage.startswith("list_") else MAX_STATUS_BYTES
            body = _read_small(opened, url, limit)
            _save_new(run_dir / filename, body)
            raw[filename] = body
            size, digest = len(body), sha256(body).hexdigest()
            if stage.startswith("list_"):
                _parse_list(body)
            else:
                _parse_status(body)
        requests.append(
            {
                "stage": stage,
                "url": url,
                "file": filename,
                "bytes": size,
                "sha256": digest,
                "retrieved_at_utc": _utc_now(clock),
            }
        )
    completed_at = _utc_now(clock)
    result = _aggregate(raw, run_dir / "archive.csv", csv_size, csv_hash, completed_at)
    aggregate_bytes = _encoded(result)
    _save_new(run_dir / "aggregate.json", aggregate_bytes)
    manifest = {
        "run_id": run_dir.name,
        "protocol": PROTOCOL,
        "version": VERSION,
        "code_commit": commit,
        "dirty_tree_at_start": dirty,
        "code_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
        "environment_lock_sha256": sha256(ENVIRONMENT_LOCK.read_bytes()).hexdigest(),
        "configuration_sha256": sha256(_encoded(_configuration())).hexdigest(),
        "source_snapshot_sha256": csv_hash,
        "split_hash": None,
        "feature_policy_hash": None,
        "checkpoint_identity": None,
        "started_at_utc": started_at,
        "completed_at_utc": completed_at,
        "requests": requests,
        "aggregate_sha256": sha256(aggregate_bytes).hexdigest(),
    }
    _save_new(run_dir / "manifest.json", _encoded(manifest))
    return result


def _read_private(path: Path, root: Path, cap: int) -> bytes:
    path = private_review_io.private_path(path, root, must_exist=True)
    with path.open("rb") as stream:
        body = stream.read(cap + 1)
    if not body or len(body) > cap:
        raise ValueError("Saved archive response is empty or oversized")
    return body


def replay(run_dir: Path) -> dict:
    """Revalidate saved responses and aggregate without opening the network."""
    run_dir = _private_directory(run_dir, existing=True)
    manifest = _json(
        _read_private(run_dir / "manifest.json", run_dir, MAX_MANIFEST_BYTES),
        MAX_MANIFEST_BYTES,
    )
    if not isinstance(manifest, dict) or (
        manifest.get("run_id"),
        manifest.get("protocol"),
        manifest.get("version"),
    ) != (run_dir.name, PROTOCOL, VERSION):
        raise ValueError("Archive manifest identity differs")
    if (
        manifest.get("dirty_tree_at_start") is not False
        or re.fullmatch(r"[0-9a-f]{40}", str(manifest.get("code_commit"))) is None
    ):
        raise ValueError("Archive manifest code provenance differs")
    if (
        manifest.get("code_sha256") != sha256(Path(__file__).read_bytes()).hexdigest()
        or manifest.get("environment_lock_sha256")
        != sha256(ENVIRONMENT_LOCK.read_bytes()).hexdigest()
        or manifest.get("configuration_sha256")
        != sha256(_encoded(_configuration())).hexdigest()
        or manifest.get("split_hash") is not None
        or manifest.get("feature_policy_hash") is not None
        or manifest.get("checkpoint_identity") is not None
    ):
        raise ValueError("Archive manifest environment or configuration differs")
    started_at = _timestamp(manifest.get("started_at_utc"))
    completed_at = _timestamp(manifest.get("completed_at_utc"))
    if started_at > completed_at:
        raise ValueError("Archive manifest chronology differs")
    requests = manifest.get("requests")
    if not isinstance(requests, list) or len(requests) != len(REQUEST_PLAN):
        raise ValueError("Archive request count differs")
    raw = {}
    previous_time = started_at
    for item, (stage, url, filename) in zip(requests, REQUEST_PLAN, strict=True):
        if not isinstance(item, dict) or (
            item.get("stage"),
            item.get("url"),
            item.get("file"),
        ) != (stage, url, filename):
            raise ValueError("Archive request identity differs")
        recorded = _timestamp(item.get("retrieved_at_utc"))
        if recorded < previous_time or recorded > completed_at:
            raise ValueError("Archive request chronology differs")
        previous_time = recorded
        cap = (
            MAX_CSV_BYTES
            if stage == "csv"
            else (MAX_LIST_BYTES if stage.startswith("list_") else MAX_STATUS_BYTES)
        )
        path = private_review_io.private_path(
            run_dir / filename, run_dir, must_exist=True
        )
        if stage == "csv":
            digest = sha256()
            size = 0
            with path.open("rb") as stream:
                while chunk := stream.read(CHUNK_BYTES):
                    size += len(chunk)
                    if size > cap:
                        raise ValueError("Saved archive CSV exceeds byte limit")
                    digest.update(chunk)
            digest_text = digest.hexdigest()
        else:
            body = _read_private(path, run_dir, cap)
            size, digest_text = len(body), sha256(body).hexdigest()
            raw[filename] = body
        if size != item.get("bytes") or digest_text != item.get("sha256"):
            raise ValueError("Saved archive response hash or size differs")
    csv_hash = requests[2]["sha256"]
    csv_size = requests[2]["bytes"]
    if manifest.get("source_snapshot_sha256") != csv_hash:
        raise ValueError("Saved archive source snapshot hash differs")
    result = _aggregate(raw, run_dir / "archive.csv", csv_size, csv_hash, completed_at)
    aggregate_bytes = _read_private(
        run_dir / "aggregate.json", run_dir, MAX_STATUS_BYTES
    )
    if aggregate_bytes != _encoded(result) or sha256(
        aggregate_bytes
    ).hexdigest() != manifest.get("aggregate_sha256"):
        raise ValueError("Saved archive aggregate differs")
    return result


def plan() -> dict:
    return {
        "protocol": PROTOCOL,
        "version": VERSION,
        "dataset_id": DATASET_ID,
        "requests": [
            {"method": "GET", "stage": stage, "url": url}
            for stage, url, _ in REQUEST_PLAN
        ],
        "max_csv_bytes": MAX_CSV_BYTES,
        "max_rows": MAX_ROWS,
        "private_root": str(PRIVATE_ROOT),
        "status": "planned_no_network",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("plan", "capture", "replay"))
    parser.add_argument("run_dir", nargs="?", type=Path)
    args = parser.parse_args()
    if args.action == "plan":
        if args.run_dir is not None:
            parser.error("plan does not accept a run directory")
        result = plan()
    else:
        if args.run_dir is None:
            parser.error("capture or replay requires a private run directory")
        result = (
            capture(args.run_dir) if args.action == "capture" else replay(args.run_dir)
        )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
