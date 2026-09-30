"""Capture only aggregate Socrata row-instance timestamps for NYC U0.

The result cannot establish a sale closing date or historical first publication.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import private_review_io


PROTOCOL = "nyc-row-system-timestamps-v1"
DATASET_IDS = ("usep-8jbt", "w2pb-icbu")
HOST = "https://data.cityofnewyork.us"
SELECT = (
    "count(*) as row_count,"
    "count(:created_at) as created_count,"
    "count(:updated_at) as updated_count,"
    "min(:created_at) as min_created_at,"
    "max(:created_at) as max_created_at,"
    "min(:updated_at) as min_updated_at,"
    "max(:updated_at) as max_updated_at"
)
COUNT_KEYS = ("row_count", "created_count", "updated_count")
TIME_KEYS = (
    "min_created_at",
    "max_created_at",
    "min_updated_at",
    "max_updated_at",
)
MAX_RESPONSE_BYTES = 4096
MAX_METADATA_BYTES = 2 * 1024 * 1024
TIMEOUT_SECONDS = 30
STAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z\Z")
ROOT = Path(__file__).resolve().parents[1]
PRIVATE_ROOT = ROOT / "data" / "raw" / "nyc_dof"
ENVIRONMENT_LOCK = ROOT / "locks" / "nyc-system-timestamps-environment.json"
MAX_MANIFEST_BYTES = 64 * 1024


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        raise ValueError("Source redirect rejected")


HTTP = build_opener(_NoRedirect())


def _dataset_id(dataset_id: object) -> str:
    if dataset_id not in DATASET_IDS:
        raise ValueError("Unapproved NYC dataset ID")
    return dataset_id


def build_url(dataset_id: str) -> str:
    """Build the only permitted aggregate request for a dataset."""
    dataset_id = _dataset_id(dataset_id)
    return f"{HOST}/resource/{dataset_id}.json?{urlencode({'$select': SELECT})}"


def metadata_url(dataset_id: str) -> str:
    return f"{HOST}/api/views/{_dataset_id(dataset_id)}"


def _unique_pairs(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def _json(body: bytes, limit: int) -> object:
    if not isinstance(body, bytes) or not body or len(body) > limit:
        raise ValueError("Source response invalid or exceeds byte limit")
    try:
        return json.loads(body.decode("utf-8"), object_pairs_hook=_unique_pairs)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("Source response is invalid JSON") from error


def _count(value: object, *, positive: bool = False) -> int:
    if not isinstance(value, str) or re.fullmatch(r"0|[1-9][0-9]*", value) is None:
        raise ValueError("Aggregate count is not canonical decimal")
    number = int(value)
    if positive and number == 0:
        raise ValueError("Aggregate is empty")
    return number


def _timestamp(value: object) -> str:
    if not isinstance(value, str) or STAMP.fullmatch(value) is None:
        raise ValueError("System timestamp is not canonical UTC")
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ")
    except ValueError as error:
        raise ValueError("System timestamp is invalid") from error
    return value


def parse_aggregate(dataset_id: str, body: bytes) -> dict:
    """Validate a single fixed-schema response; reject property-level fields."""
    _dataset_id(dataset_id)
    rows = _json(body, MAX_RESPONSE_BYTES)
    if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
        raise ValueError("Aggregate response must contain one object")
    row = rows[0]
    if set(row) != set(COUNT_KEYS + TIME_KEYS):
        raise ValueError("Aggregate response fields differ")
    counts = {key: _count(row[key], positive=key == "row_count") for key in COUNT_KEYS}
    if (
        counts["created_count"] != counts["row_count"]
        or counts["updated_count"] != counts["row_count"]
    ):
        raise ValueError("System timestamp fields have missing rows")
    times = {key: _timestamp(row[key]) for key in TIME_KEYS}
    if (
        times["min_created_at"] > times["max_created_at"]
        or times["min_updated_at"] > times["max_updated_at"]
        or times["min_created_at"] > times["min_updated_at"]
        or times["max_created_at"] > times["max_updated_at"]
    ):
        raise ValueError("System timestamp bounds are inconsistent")
    return {**counts, **times}


def _parse_metadata(dataset_id: str, body: bytes) -> dict:
    value = _json(body, MAX_METADATA_BYTES)
    if not isinstance(value, dict) or value.get("id") != _dataset_id(dataset_id):
        raise ValueError("Source metadata has wrong dataset ID")
    versions = (value.get("rowsUpdatedAt"), value.get("viewLastModified"))
    if any(type(item) is not int or item <= 0 for item in versions):
        raise ValueError("Source metadata update version is invalid")
    return {"rows_updated_at": versions[0], "view_last_modified": versions[1]}


def _utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def _http_get(url: str) -> bytes:
    allowed = {
        address
        for dataset_id in DATASET_IDS
        for address in (metadata_url(dataset_id), build_url(dataset_id))
    }
    if url not in allowed:
        raise ValueError("Source URL is not allowlisted")
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "TabPFN4RealEstate U0 timing audit",
        },
    )
    started = time.monotonic()
    with HTTP.open(request, timeout=TIMEOUT_SECONDS) as response:
        if response.geturl() != url or response.status != 200:
            raise ValueError("Source response status or URL differs")
        content_type = (
            response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        )
        if content_type != "application/json":
            raise ValueError("Source response content type differs")
        limit = MAX_RESPONSE_BYTES if "/resource/" in url else MAX_METADATA_BYTES
        chunks = []
        size = 0
        while True:
            remaining = TIMEOUT_SECONDS - (time.monotonic() - started)
            if remaining <= 0:
                raise TimeoutError("Source GET exceeded wall-clock limit")
            try:
                response.fp.raw._sock.settimeout(remaining)
            except (AttributeError, OSError) as error:
                raise ValueError("Cannot enforce source read deadline") from error
            chunk = response.read1(min(64 * 1024, limit - size + 1))
            if time.monotonic() - started > TIMEOUT_SECONDS:
                raise TimeoutError("Source GET exceeded wall-clock limit")
            if not chunk:
                break
            size += len(chunk)
            if size > limit:
                raise ValueError("Source response exceeds byte limit")
            chunks.append(chunk)
        body = b"".join(chunks)
    if len(body) > limit:
        raise ValueError("Source response exceeds byte limit")
    return body


def _write_new(path: Path, body: bytes) -> None:
    with path.open("xb") as output:
        output.write(body)
        output.flush()
        os.fsync(output.fileno())


def _check_git_ignored(path: Path) -> None:
    result = subprocess.run(
        ["git", "check-ignore", "-q", "--", str(path)],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise ValueError("Probe directory is not Git-ignored")


def _private_directory(path: Path, *, existing: bool) -> Path:
    root = PRIVATE_ROOT.absolute()
    private_review_io.real_directory(root, root.parent)
    target = Path(path).absolute()
    if (
        target.parent != root
        or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}", target.name) is None
    ):
        raise ValueError("Probe directory must be directly under private NYC raw root")
    if target.is_symlink():
        raise ValueError("Probe directory redirects")
    _check_git_ignored(target)
    if existing:
        private_review_io.real_directory(target, root)
        private_review_io.verify_acl(target)
    elif target.exists():
        raise FileExistsError("Probe directory already exists")
    return target


def _read_bounded(path: Path, limit: int, root: Path) -> bytes:
    path = private_review_io.private_path(path, root, must_exist=True)
    with path.open("rb") as source:
        body = source.read(limit + 1)
    if len(body) > limit:
        raise ValueError("Saved probe file exceeds byte limit")
    return body


def _encoded(value: dict) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _request_plan() -> tuple[tuple[str, str, str], ...]:
    return tuple(
        (dataset_id, stage, url)
        for dataset_id in DATASET_IDS
        for stage, url in (
            ("before", metadata_url(dataset_id)),
            ("aggregate", build_url(dataset_id)),
            ("after", metadata_url(dataset_id)),
        )
    )


def _result(raw: dict[str, bytes]) -> dict:
    datasets = {}
    stable = True
    for dataset_id in DATASET_IDS:
        before = _parse_metadata(dataset_id, raw[f"{dataset_id}-before.json"])
        after = _parse_metadata(dataset_id, raw[f"{dataset_id}-after.json"])
        summary = parse_aggregate(dataset_id, raw[f"{dataset_id}-aggregate.json"])
        unchanged = before == after
        stable = stable and unchanged
        datasets[dataset_id] = {
            **summary,
            "metadata_stable": unchanged,
            "rows_updated_at_before": before["rows_updated_at"],
            "rows_updated_at_after": after["rows_updated_at"],
        }
    return {
        "protocol": PROTOCOL,
        "status": "diagnostic_only" if stable else "inconclusive",
        "datasets": datasets,
        "historical_asof_eligible": False,
        "sale_labels_certified": 0,
    }


def _commit() -> tuple[str, bool]:
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


def capture(output_dir: Path, fetch=None) -> dict:
    """Make six fixed GETs, preserving raw aggregate/metadata responses."""
    output_dir = _private_directory(output_dir, existing=False)
    commit, dirty = _commit()
    output_dir.mkdir(mode=0o700)
    private_review_io.secure_directory(output_dir)
    private_review_io.verify_acl(output_dir)
    getter = _http_get if fetch is None else fetch
    raw = {}
    requests = []
    for dataset_id, stage, url in _request_plan():
        body = getter(url)
        if not isinstance(body, bytes):
            raise ValueError("Fetcher returned non-byte response")
        limit = MAX_RESPONSE_BYTES if stage == "aggregate" else MAX_METADATA_BYTES
        if len(body) > limit:
            raise ValueError("Source response exceeds byte limit")
        filename = f"{dataset_id}-{stage}.json"
        _write_new(output_dir / filename, body)
        raw[filename] = body
        requests.append(
            {
                "dataset_id": dataset_id,
                "stage": stage,
                "url": url,
                "file": filename,
                "bytes": len(body),
                "sha256": sha256(body).hexdigest(),
                "retrieved_at_utc": _utc_now(),
            }
        )
        if stage == "aggregate":
            parse_aggregate(dataset_id, body)
        else:
            _parse_metadata(dataset_id, body)
    aggregate = _result(raw)
    aggregate_bytes = _encoded(aggregate)
    _write_new(output_dir / "aggregate.json", aggregate_bytes)
    config = {"protocol": PROTOCOL, "dataset_ids": DATASET_IDS, "select": SELECT}
    manifest = {
        "run_id": output_dir.name,
        "protocol": PROTOCOL,
        "code_commit": commit,
        "dirty_tree_at_start": dirty,
        "code_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
        "environment_lock_sha256": sha256(ENVIRONMENT_LOCK.read_bytes()).hexdigest(),
        "configuration_sha256": sha256(_encoded(config)).hexdigest(),
        "source_snapshot_sha256": sha256(
            b"".join(raw[name] for name in sorted(raw))
        ).hexdigest(),
        "split_hash": None,
        "feature_policy_hash": None,
        "checkpoint_identity": None,
        "requests": requests,
        "aggregate_sha256": sha256(aggregate_bytes).hexdigest(),
        "completed_at_utc": _utc_now(),
    }
    _write_new(output_dir / "manifest.json", _encoded(manifest))
    return aggregate


def replay(output_dir: Path) -> dict:
    """Verify all saved bytes and rederive the aggregate with no network."""
    output_dir = _private_directory(output_dir, existing=True)
    path = output_dir / "manifest.json"
    if not path.is_file():
        raise ValueError("Probe is incomplete: manifest missing")
    manifest = _json(
        _read_bounded(path, MAX_MANIFEST_BYTES, output_dir), MAX_MANIFEST_BYTES
    )
    if not isinstance(manifest, dict) or manifest.get("protocol") != PROTOCOL:
        raise ValueError("Probe manifest protocol differs")
    if (
        re.fullmatch(r"[0-9a-f]{40}", str(manifest.get("code_commit"))) is None
        or type(manifest.get("dirty_tree_at_start")) is not bool
        or manifest.get("split_hash") is not None
        or manifest.get("feature_policy_hash") is not None
        or manifest.get("checkpoint_identity") is not None
    ):
        raise ValueError("Probe manifest provenance differs")
    if manifest.get("run_id") != output_dir.name:
        raise ValueError("Probe run identity differs")
    config = {"protocol": PROTOCOL, "dataset_ids": DATASET_IDS, "select": SELECT}
    if manifest.get("configuration_sha256") != sha256(_encoded(config)).hexdigest():
        raise ValueError("Probe configuration hash differs")
    if manifest.get("code_sha256") != sha256(Path(__file__).read_bytes()).hexdigest():
        raise ValueError("Probe code hash differs")
    if (
        manifest.get("environment_lock_sha256")
        != sha256(ENVIRONMENT_LOCK.read_bytes()).hexdigest()
    ):
        raise ValueError("Probe environment lock hash differs")
    completed_at = _timestamp(manifest.get("completed_at_utc"))
    requests = manifest.get("requests")
    plan = _request_plan()
    if not isinstance(requests, list) or len(requests) != len(plan):
        raise ValueError("Probe request plan differs")
    raw = {}
    previous_time = None
    for item, (dataset_id, stage, url) in zip(requests, plan, strict=True):
        filename = f"{dataset_id}-{stage}.json"
        if not isinstance(item, dict) or (
            item.get("dataset_id"),
            item.get("stage"),
            item.get("url"),
            item.get("file"),
        ) != (dataset_id, stage, url, filename):
            raise ValueError("Probe request identity differs")
        retrieved_at = _timestamp(item.get("retrieved_at_utc"))
        if (
            previous_time is not None and retrieved_at < previous_time
        ) or retrieved_at > completed_at:
            raise ValueError("Probe retrieval chronology differs")
        previous_time = retrieved_at
        limit = MAX_RESPONSE_BYTES if stage == "aggregate" else MAX_METADATA_BYTES
        body = _read_bounded(output_dir / filename, limit, output_dir)
        if (
            len(body) > limit
            or len(body) != item.get("bytes")
            or sha256(body).hexdigest() != item.get("sha256")
        ):
            raise ValueError("Probe response hash or size differs")
        raw[filename] = body
    if (
        manifest.get("source_snapshot_sha256")
        != sha256(b"".join(raw[name] for name in sorted(raw))).hexdigest()
    ):
        raise ValueError("Probe source snapshot hash differs")
    result = _result(raw)
    aggregate_bytes = _read_bounded(
        output_dir / "aggregate.json", MAX_RESPONSE_BYTES, output_dir
    )
    if sha256(aggregate_bytes).hexdigest() != manifest.get(
        "aggregate_sha256"
    ) or aggregate_bytes != _encoded(result):
        raise ValueError("Probe aggregate differs from saved responses")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("capture", "replay"))
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    result = (
        capture(args.output_dir)
        if args.action == "capture"
        else replay(args.output_dir)
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
