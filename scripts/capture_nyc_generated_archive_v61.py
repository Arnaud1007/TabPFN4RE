"""Capture the already-generated NYC rolling-sales archive version 61 only.

This separate collector preserves byte-identical replay of the frozen v62 run.
Private source rows are inventory material, not certified sale labels.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import sys
import time
from urllib.request import build_opener

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import capture_nyc_generated_archive as base
else:
    from . import capture_nyc_generated_archive as base


PROTOCOL = "nyc-ready-rolling-archive-v61-v1"
DATASET_ID = base.DATASET_ID
VERSION = 61
REVISION_CREATED_AT = "2026-01-27T14:48:20.467Z"
BACKEND_DATASET = "foxtrot.67157"
HOST = "https://data.cityofnewyork.us"
LIST_URL = f"{HOST}/api/archival?id={DATASET_ID}&version=1"
STATUS_URL = f"{HOST}/api/archival?id={DATASET_ID}&version=61&method=status"
CSV_URL = f"{HOST}/api/archival.csv?id={DATASET_ID}&version=61&method=export"
REQUEST_PLAN = (
    ("list_before", LIST_URL, "list-before.json"),
    ("status_before", STATUS_URL, "status-before.json"),
    ("csv", CSV_URL, "archive.csv"),
    ("status_after", STATUS_URL, "status-after.json"),
    ("list_after", LIST_URL, "list-after.json"),
)
ROW_PATH = "compressed/materializations/v3/foxtrot.67157/61/rows"
COLUMN_PATH = "compressed/materializations/v3/foxtrot.67157/61/columns"
HTTP = build_opener(base._NoRedirect())
HTTP.addheaders = [("User-Agent", "TabPFN4RealEstate U0 v61 archive audit")]


def _http_open(url: str, *, timeout: int):
    if url not in (LIST_URL, STATUS_URL, CSV_URL):
        raise ValueError("Unapproved NYC v61 archive URL")
    return HTTP.open(url, timeout=timeout)


def _parse_list(body: bytes) -> dict:
    rows = base._json(body, base.MAX_LIST_BYTES)
    if not isinstance(rows, list) or not 1 <= len(rows) <= 64:
        raise ValueError("Archive version list is invalid")
    seen: set[int] = set()
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
        base._timestamp(row["createdAt"])
        seen.add(version)
        if version == VERSION:
            selected = row
    if selected != {
        "createdAt": REVISION_CREATED_AT,
        "version": VERSION,
        "startVersion": 60,
        "visible": True,
    }:
        raise ValueError("Pinned v61 revision is unavailable or changed")
    return dict(selected)


def _parse_status(body: bytes) -> dict:
    value = base._json(body, base.MAX_STATUS_BYTES)
    if not isinstance(value, dict) or set(value) != {"type", "value"}:
        raise ValueError("Archive status shape differs")
    detail = value["value"]
    if (
        value["type"] != "done"
        or not isinstance(detail, dict)
        or set(detail)
        != {
            "datasetName",
            "version",
            "rowLocation",
            "columnLocation",
            "refSize",
            "gzipped",
        }
        or type(detail["version"]) is not int
        or detail["version"] != VERSION
        or detail["datasetName"] != BACKEND_DATASET
        or detail["rowLocation"] != ROW_PATH
        or detail["columnLocation"] != COLUMN_PATH
        or type(detail["refSize"]) is not int
        or not 0 < detail["refSize"] <= base.MAX_CSV_BYTES
        or detail["gzipped"] is not True
    ):
        raise ValueError("Pinned v61 archive is not already generated")
    return dict(detail)


def _open_exact(opener, url: str, *, csv_response: bool):
    if url not in (LIST_URL, STATUS_URL, CSV_URL):
        raise ValueError("Unapproved NYC v61 archive URL")
    response = opener(url, timeout=base.TIMEOUT_SECONDS)
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
        chunks: list[bytes] = []
        size = 0
        while True:
            remaining = base.TIMEOUT_SECONDS - (time.monotonic() - started)
            if remaining <= 0:
                raise TimeoutError("Archive JSON GET exceeded elapsed-time budget")
            base._set_socket_timeout(response, remaining)
            chunk = response.read(min(64 * 1024, limit - size + 1))
            if time.monotonic() - started > base.TIMEOUT_SECONDS:
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


def _download_csv(opener, destination: Path) -> tuple[int, str]:
    size = 0
    digest = sha256()
    start = time.monotonic()
    with _open_exact(opener, CSV_URL, csv_response=True) as response:
        declared = response.headers.get("Content-Length")
        if declared is not None and (
            re.fullmatch(r"0|[1-9][0-9]*", declared) is None
            or int(declared) > base.MAX_CSV_BYTES
        ):
            raise ValueError("Archive CSV Content-Length is invalid or oversized")
        with destination.open("xb") as output:
            while True:
                remaining = base.MAX_TRANSFER_SECONDS - (time.monotonic() - start)
                if remaining <= 0:
                    raise TimeoutError(
                        "Archive CSV transfer exceeded elapsed-time budget"
                    )
                base._set_socket_timeout(response, remaining)
                chunk = response.read(
                    min(base.CHUNK_BYTES, base.MAX_CSV_BYTES - size + 1)
                )
                if time.monotonic() - start > base.MAX_TRANSFER_SECONDS:
                    raise TimeoutError(
                        "Archive CSV transfer exceeded elapsed-time budget"
                    )
                if not chunk:
                    break
                size += len(chunk)
                if size > base.MAX_CSV_BYTES:
                    raise ValueError("Archive CSV exceeds byte limit")
                output.write(chunk)
                digest.update(chunk)
            output.flush()
            os.fsync(output.fileno())
    if not size or (declared is not None and size != int(declared)):
        raise ValueError("Archive CSV is empty or truncated")
    return size, digest.hexdigest()


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
        raise ValueError("Pinned v61 archive changed during capture")
    rows, header_hash = base._check_csv(csv_path)
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


def _configuration() -> dict:
    return {
        "protocol": PROTOCOL,
        "dataset_id": DATASET_ID,
        "version": VERSION,
        "revision_created_at": REVISION_CREATED_AT,
        "backend_dataset": BACKEND_DATASET,
        "row_path": ROW_PATH,
        "column_path": COLUMN_PATH,
        "request_plan": REQUEST_PLAN,
        "max_csv_bytes": base.MAX_CSV_BYTES,
        "max_rows": base.MAX_ROWS,
    }


def capture(
    run_dir: Path, opener=None, clock=lambda: datetime.now(timezone.utc)
) -> dict:
    """Capture five fixed GET responses in a protected create-only directory."""
    run_dir = base._private_directory(run_dir, existing=False)
    commit, dirty = base._git_state()
    if dirty or re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        raise ValueError("Archive capture requires a clean committed checkout")
    opened = _http_open if opener is None else opener
    run_dir.mkdir(mode=0o700)
    base.private_review_io.secure_directory(run_dir)
    base.private_review_io.verify_acl(run_dir)
    started_at = base._utc_now(clock)
    requests: list[dict] = []
    raw: dict[str, bytes] = {}
    csv_size, csv_hash = 0, ""
    for stage, url, filename in REQUEST_PLAN:
        if stage == "csv":
            csv_size, csv_hash = _download_csv(opened, run_dir / filename)
            size, digest = csv_size, csv_hash
        else:
            limit = (
                base.MAX_LIST_BYTES
                if stage.startswith("list_")
                else base.MAX_STATUS_BYTES
            )
            body = _read_small(opened, url, limit)
            base._save_new(run_dir / filename, body)
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
                "retrieved_at_utc": base._utc_now(clock),
            }
        )
    completed_at = base._utc_now(clock)
    result = _aggregate(raw, run_dir / "archive.csv", csv_size, csv_hash, completed_at)
    aggregate_bytes = base._encoded(result)
    base._save_new(run_dir / "aggregate.json", aggregate_bytes)
    manifest = {
        "run_id": run_dir.name,
        "protocol": PROTOCOL,
        "version": VERSION,
        "code_commit": commit,
        "dirty_tree_at_start": dirty,
        "code_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
        "helper_code_sha256": sha256(Path(base.__file__).read_bytes()).hexdigest(),
        "environment_lock_sha256": sha256(
            base.ENVIRONMENT_LOCK.read_bytes()
        ).hexdigest(),
        "configuration_sha256": sha256(base._encoded(_configuration())).hexdigest(),
        "source_snapshot_sha256": csv_hash,
        "split_hash": None,
        "feature_policy_hash": None,
        "checkpoint_identity": None,
        "started_at_utc": started_at,
        "completed_at_utc": completed_at,
        "requests": requests,
        "aggregate_sha256": sha256(aggregate_bytes).hexdigest(),
    }
    base._save_new(run_dir / "manifest.json", base._encoded(manifest))
    return result


def replay(run_dir: Path) -> dict:
    """Recheck the saved v61 responses without opening the network."""
    run_dir = base._private_directory(run_dir, existing=True)
    manifest = base._json(
        base._read_private(run_dir / "manifest.json", run_dir, base.MAX_MANIFEST_BYTES),
        base.MAX_MANIFEST_BYTES,
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
        or manifest.get("helper_code_sha256")
        != sha256(Path(base.__file__).read_bytes()).hexdigest()
        or manifest.get("environment_lock_sha256")
        != sha256(base.ENVIRONMENT_LOCK.read_bytes()).hexdigest()
        or manifest.get("configuration_sha256")
        != sha256(base._encoded(_configuration())).hexdigest()
        or manifest.get("split_hash") is not None
        or manifest.get("feature_policy_hash") is not None
        or manifest.get("checkpoint_identity") is not None
    ):
        raise ValueError("Archive manifest environment or configuration differs")
    started_at = base._timestamp(manifest.get("started_at_utc"))
    completed_at = base._timestamp(manifest.get("completed_at_utc"))
    if started_at > completed_at:
        raise ValueError("Archive manifest chronology differs")
    requests = manifest.get("requests")
    if not isinstance(requests, list) or len(requests) != len(REQUEST_PLAN):
        raise ValueError("Archive request count differs")
    raw: dict[str, bytes] = {}
    previous_time = started_at
    for item, (stage, url, filename) in zip(requests, REQUEST_PLAN, strict=True):
        if not isinstance(item, dict) or (
            item.get("stage"),
            item.get("url"),
            item.get("file"),
        ) != (stage, url, filename):
            raise ValueError("Archive request identity differs")
        recorded = base._timestamp(item.get("retrieved_at_utc"))
        if recorded < previous_time or recorded > completed_at:
            raise ValueError("Archive request chronology differs")
        previous_time = recorded
        cap = (
            base.MAX_CSV_BYTES
            if stage == "csv"
            else (
                base.MAX_LIST_BYTES
                if stage.startswith("list_")
                else base.MAX_STATUS_BYTES
            )
        )
        path = base.private_review_io.private_path(
            run_dir / filename, run_dir, must_exist=True
        )
        if stage == "csv":
            digest = sha256()
            size = 0
            with path.open("rb") as stream:
                while chunk := stream.read(base.CHUNK_BYTES):
                    size += len(chunk)
                    if size > cap:
                        raise ValueError("Saved archive CSV exceeds byte limit")
                    digest.update(chunk)
            digest_text = digest.hexdigest()
        else:
            body = base._read_private(path, run_dir, cap)
            size, digest_text = len(body), sha256(body).hexdigest()
            raw[filename] = body
        if size != item.get("bytes") or digest_text != item.get("sha256"):
            raise ValueError("Saved archive response hash or size differs")
    csv_size, csv_hash = requests[2]["bytes"], requests[2]["sha256"]
    if manifest.get("source_snapshot_sha256") != csv_hash:
        raise ValueError("Saved archive source snapshot hash differs")
    result = _aggregate(raw, run_dir / "archive.csv", csv_size, csv_hash, completed_at)
    aggregate_bytes = base._read_private(
        run_dir / "aggregate.json", run_dir, base.MAX_STATUS_BYTES
    )
    if aggregate_bytes != base._encoded(result) or sha256(
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
        "max_csv_bytes": base.MAX_CSV_BYTES,
        "max_rows": base.MAX_ROWS,
        "private_root": str(base.PRIVATE_ROOT),
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
