"""Append-only aggregate observations of the NYC rolling-sales CSV.

Each entry references an immutable private capture. Row fingerprints exist only
in memory during comparison; no property or sale identity is inferred.
"""

from __future__ import annotations

import argparse
from collections import Counter
from contextlib import contextmanager
import csv
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from io import StringIO
import json
import os
from pathlib import Path
import re
from typing import Iterator
from uuid import uuid4


HEADER = (
    "BOROUGH", "NEIGHBORHOOD", "BUILDING CLASS CATEGORY", "TAX CLASS AT PRESENT",
    "BLOCK", "LOT", "EASE-MENT", "BUILDING CLASS AT PRESENT", "ADDRESS",
    "APARTMENT NUMBER", "ZIP CODE", "RESIDENTIAL UNITS", "COMMERCIAL UNITS",
    "TOTAL UNITS", "LAND SQUARE FEET", "GROSS SQUARE FEET", "YEAR BUILT",
    "TAX CLASS AT TIME OF SALE", "BUILDING CLASS AT TIME OF SALE",
    "SALE PRICE", "SALE DATE",
)
SOURCE_ID = "nyc_dof_rolling_usep_8jbt"
MAX_CSV_BYTES = 128 * 1024 * 1024
MAX_ROWS = 150_000
MAX_MANIFEST_BYTES = 64 * 1024
MAX_ENTRY_BYTES = 64 * 1024
MAX_HISTORY_ENTRIES = 1_000
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")


def _utc(value: object) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("Capture time must be an explicit UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise ValueError("Capture time is invalid") from error
    if parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError("Capture time must be UTC")
    return parsed


def _check_private_dir(path: Path) -> Path:
    absolute = path.absolute()
    for candidate in (absolute, *absolute.parents):
        if candidate.is_symlink():
            raise ValueError("Private directory redirects through a symlink")
    path.mkdir(parents=True, exist_ok=True)
    if absolute.resolve(strict=True) != absolute:
        raise ValueError("Private directory redirects outside its path")
    return absolute


def _manifest(path: Path) -> tuple[dict, str, datetime]:
    if path.is_symlink() or not path.is_file() or path.stat().st_nlink != 1:
        raise ValueError("Capture manifest is not a regular single-link file")
    if not 0 < path.stat().st_size <= MAX_MANIFEST_BYTES:
        raise ValueError("Capture manifest has invalid size")
    with path.open("rb") as source:
        raw = source.read(MAX_MANIFEST_BYTES + 1)
    if len(raw) > MAX_MANIFEST_BYTES:
        raise ValueError("Capture manifest exceeds byte limit")
    try:
        record = json.loads(raw)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("Capture manifest is not valid JSON") from error
    if not isinstance(record, dict) or record.get("source_id") != SOURCE_ID:
        raise ValueError("Capture manifest has wrong source ID")
    if record.get("capture_status") != "inventory_only_not_asof_eligible":
        raise ValueError("Capture manifest is not a completed inventory capture")
    if record.get("header_kind") != "name":
        raise ValueError("Capture CSV schema variant is unsupported")
    name = record.get("raw_filename")
    if (
        not isinstance(name, str)
        or not name.startswith("nyc-usep-8jbt-")
        or not name.endswith(".csv")
        or Path(name).name != name
        or "/" in name
        or "\\" in name
        or ".." in name
    ):
        raise ValueError("Capture raw filename is invalid")
    digest = record.get("sha256")
    if not isinstance(digest, str) or _DIGEST.fullmatch(digest) is None:
        raise ValueError("Capture CSV hash is invalid")
    if type(record.get("bytes")) is not int or not 0 < record["bytes"] <= MAX_CSV_BYTES:
        raise ValueError("Capture CSV size is invalid")
    if type(record.get("rows")) is not int or not 0 < record["rows"] <= MAX_ROWS:
        raise ValueError("Capture row count is invalid")
    started = _utc(record.get("capture_started_at_utc"))
    completed = _utc(record.get("capture_completed_at_utc"))
    if started > completed or record.get("conservative_known_by_at_utc") != record.get(
        "capture_completed_at_utc"
    ):
        raise ValueError("Capture time order or known-by time is invalid")
    if completed > datetime.now(timezone.utc) + timedelta(minutes=5):
        raise ValueError("Capture completion time is in the future")
    return record, sha256(raw).hexdigest(), completed


def _representations(path: Path, manifest: dict) -> tuple[Counter[str], str]:
    if path.is_symlink() or not path.is_file() or path.stat().st_nlink != 1:
        raise ValueError("Capture CSV is not a regular single-link file")
    if path.stat().st_size != manifest["bytes"]:
        raise ValueError("Capture CSV size differs from manifest")
    with path.open("rb") as source:
        raw = source.read(MAX_CSV_BYTES + 1)
    if len(raw) > MAX_CSV_BYTES or len(raw) != manifest["bytes"]:
        raise ValueError("Capture CSV size exceeds limit or differs from manifest")
    if sha256(raw).hexdigest() != manifest["sha256"]:
        raise ValueError("Capture CSV hash differs from manifest")
    try:
        reader = csv.reader(StringIO(raw.decode("utf-8-sig"), newline=""), strict=True)
        header = next(reader, None)
        if header != list(HEADER):
            raise ValueError("Capture CSV header differs from v1 schema")
        counts: Counter[str] = Counter()
        rows = 0
        for row in reader:
            rows += 1
            if rows > MAX_ROWS or len(row) != len(HEADER):
                raise ValueError("Capture CSV row has invalid field count")
            representation = json.dumps(row, ensure_ascii=False, separators=(",", ":"))
            counts[sha256(("nyc-usep-8jbt-row-v1\0" + representation).encode()).hexdigest()] += 1
    except (csv.Error, UnicodeError) as error:
        raise ValueError("Capture CSV cannot be parsed") from error
    if rows != manifest["rows"]:
        raise ValueError("Capture CSV row count differs from manifest")
    header_hash = sha256(json.dumps(HEADER, separators=(",", ":")).encode()).hexdigest()
    return counts, header_hash


def _entries(root: Path, raw_root: Path) -> list[tuple[Path, dict, Counter[str], datetime]]:
    paths = list(root.glob("*.json"))
    if len(paths) > MAX_HISTORY_ENTRIES:
        raise ValueError("Observation history exceeds entry limit")
    found: list[tuple[Path, dict, Counter[str], datetime]] = []
    for path in paths:
        if path.is_symlink() or not path.is_file() or path.stat().st_nlink != 1:
            raise ValueError("Observation entry is not a regular single-link file")
        if not 0 < path.stat().st_size <= MAX_ENTRY_BYTES:
            raise ValueError("Observation entry has invalid size")
        try:
            with path.open("rb") as source:
                entry = json.loads(source.read(MAX_ENTRY_BYTES + 1))
        except (UnicodeError, json.JSONDecodeError) as error:
            raise ValueError("Observation entry is invalid") from error
        if not isinstance(entry, dict) or entry.get("protocol") != "nyc-observation-v1":
            raise ValueError("Observation entry has wrong protocol")
        if set(entry) != {
            "protocol", "manifest_path", "manifest_sha256", "raw_sha256",
            "known_by_utc", "header_sha256", "rows",
        }:
            raise ValueError("Observation entry has invalid fields")
        manifest_path = Path(entry["manifest_path"])
        manifest, manifest_hash, completed = _manifest(manifest_path)
        if (
            entry["manifest_sha256"] != manifest_hash
            or entry["raw_sha256"] != manifest["sha256"]
            or entry["known_by_utc"] != manifest["capture_completed_at_utc"]
            or entry["rows"] != manifest["rows"]
        ):
            raise ValueError("Observation entry differs from pinned capture")
        expected_name = (
            f"nyc-observation-{completed.strftime('%Y%m%dT%H%M%S%fZ')}-"
            f"{manifest_hash[:16]}.json"
        )
        if path.name != expected_name:
            raise ValueError("Observation entry filename differs from capture")
        counts, header_hash = _representations(raw_root / manifest["raw_filename"], manifest)
        if entry["header_sha256"] != header_hash:
            raise ValueError("Observation entry schema differs from capture")
        found.append((path, entry, counts, completed))
    found.sort(key=lambda item: item[3])
    if len({item[3] for item in found}) != len(found):
        raise ValueError("Observation history has duplicate capture times")
    return found


def _bucket(count: int) -> str:
    if count == 0:
        return "zero"
    if count < 10:
        return "1_to_9"
    if count < 100:
        return "10_to_99"
    return "100_plus"


def _summary(
    entry: dict, entry_path: Path, old: Counter[str], new: Counter[str], *, replay: bool
) -> dict:
    return {
        "source_id": SOURCE_ID,
        "capture_status": "inventory_only",
        "write_status": "replayed" if replay else "recorded",
        "manifest_sha256": entry["manifest_sha256"],
        "observation_sha256": sha256(entry_path.read_bytes()).hexdigest(),
        "known_by_utc": entry["known_by_utc"],
        "rows": entry["rows"],
        "added_occurrences_bucket": _bucket(sum((new - old).values())),
        "removed_occurrences_bucket": _bucket(sum((old - new).values())),
        "first_public_availability_verified": False,
        "asof_eligible": False,
        "certified_sale_labels": 0,
    }


@contextmanager
def _write_lock(root: Path) -> Iterator[None]:
    path = root / ".write.lock"
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as error:
        raise FileExistsError("Observation history write lock already exists") from error
    try:
        os.close(fd)
        yield
    finally:
        path.unlink(missing_ok=True)


def record_snapshot(manifest_path: Path, *, raw_root: Path, ledger_root: Path) -> dict:
    """Record a validated capture, keeping row fingerprints in memory only."""
    manifest, manifest_hash, completed = _manifest(manifest_path)
    raw = _check_private_dir(raw_root)
    counts, header_hash = _representations(raw / manifest["raw_filename"], manifest)
    ledger = _check_private_dir(ledger_root)
    with _write_lock(ledger):
        history = _entries(ledger, raw)
        for index, (path, entry, previous_counts, _) in enumerate(history):
            if entry["manifest_sha256"] == manifest_hash:
                if previous_counts != counts:
                    raise ValueError("Replayed observation differs from capture")
                old = history[index - 1][2] if index else Counter()
                return _summary(entry, path, old, counts, replay=True)
        if history and completed <= history[-1][3]:
            raise ValueError("New observation is not chronologically after history")
        entry = {
            "protocol": "nyc-observation-v1",
            "manifest_path": str(manifest_path.absolute()),
            "manifest_sha256": manifest_hash,
            "raw_sha256": manifest["sha256"],
            "known_by_utc": manifest["capture_completed_at_utc"],
            "header_sha256": header_hash,
            "rows": manifest["rows"],
        }
        stamp = completed.strftime("%Y%m%dT%H%M%S%fZ")
        target = ledger / f"nyc-observation-{stamp}-{manifest_hash[:16]}.json"
        payload = (json.dumps(entry, sort_keys=True, separators=(",", ":")) + "\n").encode()
        temp = ledger / f".nyc-observation-{uuid4().hex}.part"
        try:
            with temp.open("xb") as output:
                output.write(payload)
                output.flush()
                os.fsync(output.fileno())
            os.link(temp, target)
        finally:
            temp.unlink(missing_ok=True)
        old = history[-1][2] if history else Counter()
        return _summary(entry, target, old, counts, replay=False)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--raw-root", type=Path, required=True)
    parser.add_argument("--ledger-root", type=Path, required=True)
    options = parser.parse_args()
    result = record_snapshot(
        options.manifest, raw_root=options.raw_root, ledger_root=options.ledger_root
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
