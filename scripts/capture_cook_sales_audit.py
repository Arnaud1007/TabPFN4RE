"""Capture a bounded Cook County parcel-sales sample for private source audit.

This is source inventory. Recorded sale dates are not verified close dates, and the
capture does not establish historical first availability or label eligibility.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from typing import Callable
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, build_opener
from uuid import uuid4


DATASET_ID = "wvhk-k5uv"
METADATA_URL = f"https://datacatalog.cookcountyil.gov/api/views/{DATASET_ID}.json"
API_URL = f"https://datacatalog.cookcountyil.gov/resource/{DATASET_ID}.json"
PRIVATE_ROOT = Path(__file__).resolve().parents[1] / "data" / "raw" / "cook_county"
SELECT_FIELDS = (
    "row_id",
    "pin",
    "year",
    "township_code",
    "nbhd",
    "class",
    "sale_date",
    "is_mydec_date",
    "sale_price",
    "doc_no",
    "deed_type",
    "mydec_deed_type",
    "is_multisale",
    "num_parcels_sale",
    "sale_type",
    "sale_filter_same_sale_within_365",
    "sale_filter_less_than_10k",
    "sale_filter_deed_type",
)
REQUIRED_SOURCE_FIELDS = SELECT_FIELDS
MAX_METADATA_BYTES = 2 * 1024 * 1024
MAX_COUNT_BYTES = 1024
MAX_ROW_BYTES = 64 * 1024
TIMEOUT_SECONDS = 45
MAX_MANIFEST_BYTES = 256 * 1024
_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?)?$")


@dataclass(frozen=True)
class Cell:
    slug: str
    start_date: str
    end_date: str
    min_price: int | None
    max_price: int | None


DATE_BANDS = (
    ("old", "2015-01-01", "2020-01-01"),
    ("recent", "2024-01-01", "2026-01-01"),
)
PRICE_BANDS = (
    ("low", None, 10_000),
    ("lower", 10_000, 100_000),
    ("middle", 100_000, 300_000),
    ("upper", 300_000, 1_000_000),
    ("high", 1_000_000, None),
)
CELLS = tuple(
    Cell(f"{date_name}-{price_name}", start, end, low, high)
    for date_name, start, end in DATE_BANDS
    for price_name, low, high in PRICE_BANDS
)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        raise ValueError("Source redirect rejected before follow")


_HTTP_OPENER = build_opener(_NoRedirect)


def _strict_urlopen(url: str, *, timeout: int):
    return _HTTP_OPENER.open(url, timeout=timeout)


def cell_where(cell: Cell) -> str:
    terms = [
        f"sale_date >= '{cell.start_date}T00:00:00'",
        f"sale_date < '{cell.end_date}T00:00:00'",
    ]
    if cell.min_price is not None:
        terms.append(f"sale_price >= {cell.min_price}")
    if cell.max_price is not None:
        terms.append(f"sale_price < {cell.max_price}")
    return " AND ".join(terms)


def _query_url(params: dict[str, str | int]) -> str:
    return f"{API_URL}?{urlencode(params)}"


def _clock(now: Callable[[], datetime]) -> str:
    instant = now()
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError("Capture clock must be timezone-aware")
    return instant.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


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
    return PRIVATE_ROOT.resolve(strict=True)


def _fetch(opener, url: str, cap: int) -> tuple[bytes, dict[str, str | None]]:
    with opener(url, timeout=TIMEOUT_SECONDS) as response:
        if response.geturl() != url:
            raise ValueError("Source redirect rejected")
        if getattr(response, "status", 200) != 200:
            raise ValueError("Source did not return HTTP 200")
        content_type = response.headers.get("Content-Type", "").split(";", 1)[0]
        if content_type.lower().strip() != "application/json":
            raise ValueError("Unexpected source Content-Type")
        data = response.read(cap + 1)
        if len(data) > cap:
            raise ValueError("Source response exceeds byte cap")
        return data, {
            "etag": response.headers.get("ETag"),
            "last_modified": response.headers.get("Last-Modified"),
        }


def _parse_json(data: bytes):
    try:
        return json.loads(data)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("Source response is invalid JSON") from error


def _metadata(data: bytes) -> dict:
    record = _parse_json(data)
    if not isinstance(record, dict) or record.get("id") != DATASET_ID:
        raise ValueError("Source metadata has wrong dataset ID")
    versions = (record.get("rowsUpdatedAt"), record.get("viewLastModified"))
    if any(type(value) is not int or value <= 0 for value in versions):
        raise ValueError("Source metadata has invalid version")
    columns = record.get("columns")
    if not isinstance(columns, list) or not columns:
        raise ValueError("Source metadata has invalid column names")
    fields = set()
    for column in columns:
        field = column.get("fieldName") if isinstance(column, dict) else None
        if not isinstance(field, str) or not field:
            raise ValueError("Source metadata has invalid column names")
        fields.add(field)
    if not set(REQUIRED_SOURCE_FIELDS).issubset(fields):
        raise ValueError("Source metadata is missing required columns")
    return {
        "rows_updated_at": versions[0],
        "view_last_modified": versions[1],
        "fields": sorted(fields),
    }


def _count(data: bytes) -> int:
    record = _parse_json(data)
    if (
        not isinstance(record, list)
        or len(record) != 1
        or not isinstance(record[0], dict)
    ):
        raise ValueError("Source count has invalid shape")
    value = record[0].get("n")
    if not isinstance(value, str) or not value.isdecimal():
        raise ValueError("Source count is invalid")
    return int(value)


def _offsets(count: int) -> tuple[int, int]:
    if count < 20:
        raise ValueError("A preregistered cell has fewer than 20 rows")
    gap = count - 20
    return gap // 4, 3 * gap // 4 + 10


def _rows(data: bytes, cell: Cell) -> list[str]:
    records = _parse_json(data)
    if not isinstance(records, list) or len(records) != 10:
        raise ValueError("Source row page length is not ten")
    ids = []
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("Source row has invalid shape")
        if set(record) - set(SELECT_FIELDS):
            raise ValueError("Source row contains unrequested field")
        row_id = record.get("row_id")
        if not isinstance(row_id, str) or not row_id:
            raise ValueError("Source row has invalid row_id")
        value = record.get("sale_price")
        try:
            price = Decimal(value) if isinstance(value, str) else Decimal("NaN")
        except InvalidOperation as error:
            raise ValueError("Source row has invalid price") from error
        raw_date = record.get("sale_date")
        try:
            if not isinstance(raw_date, str) or not _DATE_PATTERN.fullmatch(raw_date):
                raise ValueError("Invalid date representation")
            parsed_date = (
                date.fromisoformat(raw_date)
                if len(raw_date) == 10
                else datetime.fromisoformat(raw_date.replace("Z", "+00:00")).date()
            )
        except ValueError as error:
            raise ValueError("Source row has invalid date") from error
        if (
            not price.is_finite()
            or not (
                date.fromisoformat(cell.start_date)
                <= parsed_date
                < date.fromisoformat(cell.end_date)
            )
            or (cell.min_price is not None and price < cell.min_price)
            or (cell.max_price is not None and price >= cell.max_price)
        ):
            raise ValueError("Source row violates cell membership")
        ids.append(row_id)
    if len(set(ids)) != 10:
        raise ValueError("Source page has duplicate row_id")
    return ids


def _save(
    directory: Path,
    filename: str,
    data: bytes,
    url: str,
    headers: dict,
    now: Callable[[], datetime],
) -> dict:
    path = directory / filename
    with path.open("xb") as output:
        output.write(data)
        output.flush()
        os.fsync(output.fileno())
    return {
        "file": filename,
        "url": url,
        "sha256": sha256(data).hexdigest(),
        "bytes": len(data),
        "retrieved_at": _clock(now),
        **headers,
    }


def _get_and_save(
    opener,
    directory: Path,
    filename: str,
    url: str,
    cap: int,
    now: Callable[[], datetime],
) -> tuple[bytes, dict]:
    data, headers = _fetch(opener, url, cap)
    return data, _save(directory, filename, data, url, headers, now)


def _count_url(cell: Cell) -> str:
    return _query_url({"$select": "count(*) AS n", "$where": cell_where(cell)})


def _page_url(cell: Cell, offset: int) -> str:
    return _query_url(
        {
            "$select": ",".join(SELECT_FIELDS),
            "$where": cell_where(cell),
            "$order": "row_id ASC",
            "$limit": 10,
            "$offset": offset,
        }
    )


def capture_sample(
    *, opener=None, now: Callable[[], datetime] = lambda: datetime.now(timezone.utc)
) -> dict:
    """Capture one private sample; return aggregate inventory evidence only."""
    root = _private_root()
    claim = root / ".cook-sales-v1.claim"
    try:
        with claim.open("xb") as output:
            output.write(b"adr-0051-cook-sales-v1\n")
            output.flush()
            os.fsync(output.fileno())
    except FileExistsError as error:
        raise FileExistsError(
            "A v1 capture already exists; review or version before retry"
        ) from error
    opener = _strict_urlopen if opener is None else opener
    started = _clock(now)
    token = uuid4().hex[:12]
    stamp = started.replace("-", "").replace(":", "")
    final = root / f"cook-sales-v1-{stamp}-{token}"
    working = root / f".cook-sales-v1-{stamp}-{token}.incomplete"
    working.mkdir(exist_ok=False)
    responses = []
    before_bytes, entry = _get_and_save(
        opener, working, "metadata-before.json", METADATA_URL, MAX_METADATA_BYTES, now
    )
    responses.append(entry)
    before = _metadata(before_bytes)
    counts = {}
    for cell in CELLS:
        data, entry = _get_and_save(
            opener,
            working,
            f"count-before-{cell.slug}.json",
            _count_url(cell),
            MAX_COUNT_BYTES,
            now,
        )
        responses.append(entry)
        counts[cell.slug] = _count(data)
    for cell in CELLS:
        _offsets(counts[cell.slug])
    row_ids = []
    for cell in CELLS:
        for page_index, offset in enumerate(_offsets(counts[cell.slug])):
            url = _page_url(cell, offset)
            data, headers = _fetch(opener, url, MAX_ROW_BYTES)
            ids = _rows(data, cell)
            entry = _save(
                working, f"rows-{cell.slug}-{page_index}.json", data, url, headers, now
            )
            responses.append(entry)
            row_ids.extend(ids)
    if len(row_ids) != 200 or len(set(row_ids)) != 200:
        raise ValueError("Sample has duplicate row_id or wrong row count")
    after_bytes, entry = _get_and_save(
        opener, working, "metadata-after.json", METADATA_URL, MAX_METADATA_BYTES, now
    )
    responses.append(entry)
    if _metadata(after_bytes) != before:
        raise ValueError("Source metadata changed during capture")
    for cell in CELLS:
        data, entry = _get_and_save(
            opener,
            working,
            f"count-after-{cell.slug}.json",
            _count_url(cell),
            MAX_COUNT_BYTES,
            now,
        )
        responses.append(entry)
        if _count(data) != counts[cell.slug]:
            raise ValueError("Source counts changed during capture")
    completed = _clock(now)
    manifest = {
        "protocol": "adr-0051-cook-sales-v1",
        "started_at": started,
        "completed_at": completed,
        "dataset_id": DATASET_ID,
        "source_version": before,
        "cell_counts": counts,
        "sample_row_ids": row_ids,
        "responses": responses,
        "capture_status": "private_source_audit_only",
        "historical_asof_eligible": False,
    }
    with (working / "manifest.json").open("x", encoding="utf-8") as output:
        json.dump(manifest, output, indent=2, sort_keys=True)
        output.flush()
        os.fsync(output.fileno())
    working.rename(final)
    return {
        "dataset_id": DATASET_ID,
        "protocol": manifest["protocol"],
        "started_at": started,
        "completed_at": completed,
        "private_directory": final.name,
        "sample_rows": len(row_ids),
        "cell_count": len(CELLS),
        "cell_counts": counts,
        "metadata_sha256": sha256(before_bytes).hexdigest(),
        "manifest_sha256": sha256((final / "manifest.json").read_bytes()).hexdigest(),
        "capture_status": "private_source_audit_only",
        "historical_asof_eligible": False,
    }


def _private_file(directory: Path, filename: str, cap: int) -> bytes:
    if Path(filename).name != filename:
        raise ValueError("Invalid private response filename")
    path = directory / filename
    if path.is_symlink() or not path.is_file() or path.stat().st_size > cap:
        raise ValueError("Private response is symlinked, missing or oversized")
    with path.open("rb") as source:
        data = source.read(cap + 1)
    if len(data) > cap:
        raise ValueError("Private response exceeds byte cap")
    return data


def _expected_response_urls(counts: dict[str, int]) -> dict[str, str]:
    expected = {
        "metadata-before.json": METADATA_URL,
        "metadata-after.json": METADATA_URL,
    }
    for cell in CELLS:
        expected[f"count-before-{cell.slug}.json"] = _count_url(cell)
        expected[f"count-after-{cell.slug}.json"] = _count_url(cell)
        for page_index, offset in enumerate(_offsets(counts[cell.slug])):
            expected[f"rows-{cell.slug}-{page_index}.json"] = _page_url(cell, offset)
    return expected


def _response_cap(filename: str) -> int:
    if filename.startswith("metadata-"):
        return MAX_METADATA_BYTES
    if filename.startswith("count-"):
        return MAX_COUNT_BYTES
    return MAX_ROW_BYTES


def _checked_manifest(directory: Path) -> tuple[dict, dict[str, str]]:
    root = _private_root()
    if (
        directory.is_symlink()
        or directory.parent.resolve() != root
        or directory.resolve(strict=True) != root / directory.name
        or not directory.name.startswith("cook-sales-v1-")
    ):
        raise ValueError("Capture directory must be a direct child of private root")
    manifest = _parse_json(
        _private_file(directory, "manifest.json", MAX_MANIFEST_BYTES)
    )
    if (
        not isinstance(manifest, dict)
        or manifest.get("protocol") != "adr-0051-cook-sales-v1"
    ):
        raise ValueError("Unknown private capture protocol")
    counts = manifest.get("cell_counts")
    if not isinstance(counts, dict) or set(counts) != {cell.slug for cell in CELLS}:
        raise ValueError("Invalid private cell counts")
    if any(type(n) is not int or n < 20 for n in counts.values()):
        raise ValueError("Invalid private cell count")
    expected = _expected_response_urls(counts)
    entries = manifest.get("responses")
    if not isinstance(entries, list) or len(entries) != len(expected):
        raise ValueError("Private response inventory differs from protocol")
    by_file = {entry.get("file"): entry for entry in entries if isinstance(entry, dict)}
    if len(by_file) != len(expected) or set(by_file) != set(expected):
        raise ValueError("Private response inventory differs from protocol")
    return manifest, expected


def verify_capture(directory: Path) -> dict:
    """Replay every private response, source bracket and sample membership."""
    manifest, expected = _checked_manifest(directory)
    by_file = {entry["file"]: entry for entry in manifest["responses"]}
    bodies = {}
    for filename, url in expected.items():
        entry = by_file[filename]
        if entry.get("url") != url:
            raise ValueError("Private response query differs from protocol")
        data = _private_file(directory, filename, _response_cap(filename))
        if sha256(data).hexdigest() != entry.get("sha256") or len(data) != entry.get(
            "bytes"
        ):
            raise ValueError("Private response hash mismatch")
        bodies[filename] = data
    before = _metadata(bodies["metadata-before.json"])
    if (
        before != manifest.get("source_version")
        or _metadata(bodies["metadata-after.json"]) != before
    ):
        raise ValueError("Private metadata bracket differs")
    ids = []
    for cell in CELLS:
        for stage in ("before", "after"):
            if (
                _count(bodies[f"count-{stage}-{cell.slug}.json"])
                != manifest["cell_counts"][cell.slug]
            ):
                raise ValueError("Private count bracket differs")
        for page_index in range(2):
            ids.extend(_rows(bodies[f"rows-{cell.slug}-{page_index}.json"], cell))
    if ids != manifest.get("sample_row_ids") or len(ids) != 200 or len(set(ids)) != 200:
        raise ValueError("Private sample membership mismatch")
    return {
        "sample_rows": 200,
        "cell_count": len(CELLS),
        "historical_asof_eligible": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--verify", type=Path, help="Replay an existing private capture"
    )
    args = parser.parse_args()
    result = verify_capture(args.verify) if args.verify else capture_sample()
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
