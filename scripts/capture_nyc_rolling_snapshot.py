"""Capture the current NYC rolling CSV as a private source inventory snapshot.

This does not establish per-row first availability or a historical as-of dataset.
Only aggregate capture metadata is printed. The CSV remains under ignored raw data.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import time
from typing import Callable
from urllib.request import HTTPRedirectHandler, build_opener
from uuid import uuid4


CSV_URL = (
    "https://data.cityofnewyork.us/api/views/usep-8jbt/rows.csv?accessType=DOWNLOAD"
)
METADATA_URL = "https://data.cityofnewyork.us/api/views/usep-8jbt"
COUNT_URL = (
    "https://data.cityofnewyork.us/resource/usep-8jbt.json?%24select=count%28%2A%29"
)
PRIVATE_ROOT = Path(__file__).resolve().parents[1] / "data" / "raw" / "nyc_dof"
MAX_CSV_BYTES = 128 * 1024 * 1024
MAX_METADATA_BYTES = 2 * 1024 * 1024
MAX_COUNT_BYTES = 1024
MAX_ROWS = 150_000
TIMEOUT_SECONDS = 30
MAX_TRANSFER_SECONDS = 240
CHUNK_BYTES = 1024 * 1024
REQUIRED_FIELDS = frozenset(("borough", "address", "sale_price", "sale_date"))


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        raise ValueError("Source redirect rejected before follow")


_HTTP_OPENER = build_opener(_NoRedirect)


def _strict_urlopen(url: str, *, timeout: int):
    return _HTTP_OPENER.open(url, timeout=timeout)


def _timestamp(now: Callable[[], datetime]) -> str:
    instant = now()
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError("Capture clock must be timezone-aware")
    return instant.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _new_filename(started_at: str) -> str:
    stamp = started_at.replace("-", "").replace(":", "").replace("+", "")
    return f"nyc-usep-8jbt-{stamp}-{uuid4().hex[:12]}.csv"


def _open_exact(opener, url: str):
    response = opener(url, timeout=TIMEOUT_SECONDS)
    if response.geturl() != url:
        response.close()
        raise ValueError("Source redirect rejected")
    if getattr(response, "status", 200) != 200:
        response.close()
        raise ValueError("Source did not return HTTP 200")
    return response


def _metadata(opener) -> tuple[dict, str]:
    with _open_exact(opener, METADATA_URL) as response:
        data = response.read(MAX_METADATA_BYTES + 1)
    if len(data) > MAX_METADATA_BYTES:
        raise ValueError("Source metadata exceeds byte limit")
    try:
        record = json.loads(data)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Source metadata is invalid JSON") from error
    if not isinstance(record, dict) or record.get("id") != "usep-8jbt":
        raise ValueError("Source metadata has wrong dataset ID")
    versions = (record.get("rowsUpdatedAt"), record.get("viewLastModified"))
    if any(type(value) is not int or value <= 0 for value in versions):
        raise ValueError("Source metadata has invalid update version")
    columns = record.get("columns")
    if not isinstance(columns, list) or not columns:
        raise ValueError("Source metadata has no columns")
    names = tuple(column.get("name") for column in columns if isinstance(column, dict))
    fields = tuple(
        column.get("fieldName") for column in columns if isinstance(column, dict)
    )
    if (
        len(names) != len(columns)
        or any(not isinstance(value, str) or not value for value in names + fields)
        or len(set(names)) != len(names)
        or len(set(fields)) != len(fields)
        or not REQUIRED_FIELDS.issubset(fields)
    ):
        raise ValueError("Source metadata has invalid CSV schema")
    return {
        "rows_updated_at": versions[0],
        "view_last_modified": versions[1],
        "column_names": names,
        "column_fields": fields,
    }, sha256(data).hexdigest()


def _private_root() -> Path:
    absolute = PRIVATE_ROOT.absolute()
    for candidate in (absolute, *absolute.parents):
        if candidate.is_symlink() or (
            candidate.exists()
            and os.path.normcase(str(candidate.resolve()))
            != os.path.normcase(str(candidate))
        ):
            raise ValueError(
                "Private root or ancestor redirects outside local raw data"
            )
    PRIVATE_ROOT.mkdir(parents=True, exist_ok=True)
    root = PRIVATE_ROOT.resolve(strict=True)
    if PRIVATE_ROOT.is_symlink() or os.path.normcase(
        str(PRIVATE_ROOT.absolute())
    ) != os.path.normcase(str(root)):
        raise ValueError("Private root or ancestor redirects outside local raw data")
    return root


def _count(opener) -> tuple[int, str]:
    with _open_exact(opener, COUNT_URL) as response:
        data = response.read(MAX_COUNT_BYTES + 1)
    if len(data) > MAX_COUNT_BYTES:
        raise ValueError("Source count response exceeds byte limit")
    try:
        record = json.loads(data)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Source count response is invalid JSON") from error
    if (
        not isinstance(record, list)
        or len(record) != 1
        or not isinstance(record[0], dict)
    ):
        raise ValueError("Source count response has invalid shape")
    value = record[0].get("count")
    if not isinstance(value, str) or not value.isdecimal():
        raise ValueError("Source count response has invalid count")
    count = int(value)
    if not 0 < count <= MAX_ROWS:
        raise ValueError("Source count exceeds row limit or is empty")
    return count, sha256(data).hexdigest()


def _download(opener, temp_path: Path) -> tuple[int, str, dict]:
    count = 0
    digest = sha256()
    started = time.monotonic()
    with _open_exact(opener, CSV_URL) as response, temp_path.open("xb") as output:
        content_type = (
            response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        )
        if content_type not in ("text/csv", "application/octet-stream"):
            raise ValueError("Unexpected CSV Content-Type")
        encoding = response.headers.get("Content-Encoding", "identity").lower()
        if encoding != "identity":
            raise ValueError("Compressed CSV response is unsupported")
        length = response.headers.get("Content-Length")
        if length is not None:
            if not length.isdecimal():
                raise ValueError("Invalid CSV Content-Length")
            if int(length) > MAX_CSV_BYTES:
                raise ValueError("CSV response exceeds byte limit")
        http = {
            "etag": response.headers.get("ETag"),
            "last_modified": response.headers.get("Last-Modified"),
            "content_type": response.headers.get("Content-Type"),
        }
        while True:
            if time.monotonic() - started > MAX_TRANSFER_SECONDS:
                raise TimeoutError("CSV transfer exceeded elapsed-time limit")
            chunk = response.read(min(CHUNK_BYTES, MAX_CSV_BYTES - count + 1))
            if not chunk:
                break
            count += len(chunk)
            if count > MAX_CSV_BYTES:
                raise ValueError("CSV response exceeds byte limit")
            output.write(chunk)
            digest.update(chunk)
        output.flush()
        os.fsync(output.fileno())
    if length is not None and count != int(length):
        raise ValueError("CSV Content-Length differs from received bytes")
    return count, digest.hexdigest(), http


def _check_csv(path: Path, schema: dict) -> tuple[int, str]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as source:
            reader = csv.reader(source, strict=True)
            header = next(reader, None)
            if header == list(schema["column_names"]):
                header_kind = "name"
            elif header == list(schema["column_fields"]):
                header_kind = "fieldName"
            else:
                raise ValueError("CSV header differs from source metadata")
            rows = 0
            for record in reader:
                rows += 1
                if rows > MAX_ROWS:
                    raise ValueError("CSV row limit exceeded")
                if len(record) != len(header):
                    raise ValueError("CSV record has wrong field count")
    except (csv.Error, UnicodeError) as error:
        raise ValueError("CSV record cannot be parsed") from error
    if rows == 0:
        raise ValueError("CSV contains no data rows")
    return rows, header_kind


def capture_snapshot(
    *, opener=None, now: Callable[[], datetime] = lambda: datetime.now(timezone.utc)
) -> dict:
    """Capture one bounded immutable file; return only aggregate inventory metadata."""
    started_at = _timestamp(now)
    root = _private_root()
    opener = _strict_urlopen if opener is None else opener
    before, before_hash = _metadata(opener)
    count_before, count_hash_before = _count(opener)
    target = root / _new_filename(started_at)
    if target.exists():
        raise FileExistsError("Snapshot target already exists")
    temp = root / f".nyc-capture-{uuid4().hex}.part"
    try:
        size, checksum, http = _download(opener, temp)
        rows, header_kind = _check_csv(temp, before)
        after, after_hash = _metadata(opener)
        count_after, count_hash_after = _count(opener)
        if before != after or before_hash != after_hash:
            raise ValueError("Source metadata changed during capture")
        if count_before != count_after or rows != count_before:
            raise ValueError("CSV count differs from source aggregate count")
        if root != _private_root():
            raise ValueError("Private root changed during capture")
        completed_at = _timestamp(now)
        os.link(temp, target)
    finally:
        temp.unlink(missing_ok=True)
    return {
        "source_id": "nyc_dof_rolling_usep_8jbt",
        "source_url": CSV_URL,
        "raw_filename": target.name,
        "sha256": checksum,
        "bytes": size,
        "rows": rows,
        "source_count_before": count_before,
        "source_count_after": count_after,
        "source_count_sha256_before": count_hash_before,
        "source_count_sha256_after": count_hash_after,
        "header_kind": header_kind,
        "metadata_sha256_before": before_hash,
        "metadata_sha256_after": after_hash,
        "rows_updated_at": before["rows_updated_at"],
        "view_last_modified": before["view_last_modified"],
        "capture_started_at_utc": started_at,
        "capture_completed_at_utc": completed_at,
        "conservative_known_by_at_utc": completed_at,
        "http": http,
        "capture_status": "inventory_only_not_asof_eligible",
        "availability_note": (
            "Capture completion is the conservative known-by time for this file; "
            "HTTP Last-Modified and portal update timestamps do not establish "
            "per-row first availability or historical as-of eligibility."
        ),
    }


def dry_run() -> dict:
    """Describe the capture without opening the network or writing a file."""
    return {
        "source_url": CSV_URL,
        "metadata_url": METADATA_URL,
        "count_url": COUNT_URL,
        "private_root": str(PRIVATE_ROOT),
        "max_bytes": MAX_CSV_BYTES,
        "max_rows": MAX_ROWS,
        "timeout_seconds": TIMEOUT_SECONDS,
        "max_transfer_seconds": MAX_TRANSFER_SECONDS,
        "capture_status": "dry_run_no_network",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", action="store_true", help="download the live CSV")
    options = parser.parse_args()
    result = capture_snapshot() if options.capture else dry_run()
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
