"""Offline, aggregate-only comparison of two pinned NYC source representations."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import subprocess
import sys
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path

import private_review_io

ROOT = Path(__file__).resolve().parents[1]
PRIVATE_ROOT = ROOT / "data/raw/nyc_dof"
ARCHIVE_RUN = PRIVATE_ROOT / "ready-archive-v2-20261002T210520Z"
ARCHIVE_MANIFEST = (
    ROOT / "runs/u0-nyc-ready-archive-v2-captured-20261002T210520Z/manifest.json"
)
SNAPSHOT_MANIFEST = ROOT / "runs/u0-nyc-rolling-snapshot-20260928T225512Z/snapshot.json"
ENVIRONMENT_LOCK = ROOT / "locks/nyc-archive-compare-environment.json"
ENVIRONMENT_LOCK_SHA256 = (
    "324a2084ea010b4bf83b4c823b2b5532ba5ceb3ade40f4604b846ea951db5ef6"
)
PROTOCOL = "nyc-archive-current-concordance-v1"
ARCHIVE_SHA256 = "0746355101b245fb469ce97e19e088fa2b16f0f95728d7a5b07dd670e98c345f"
CURRENT_SHA256 = "84c06057c52a2822f982cd98fb77ef7edf2c14134d00f46b073d2e4b762b2ef2"
ARCHIVE_MANIFEST_SHA256 = (
    "a85186c249503435494e9c06e4274bbea85d986bba058375cbe7d3537b6e01bc"
)
SNAPSHOT_MANIFEST_SHA256 = (
    "45049ce1622ba4a819f29c79097869c9f3601d049139869982ec7327ee11962b"
)
ARCHIVE_BYTES = 11_302_195
CURRENT_BYTES = 10_397_977
ARCHIVE_ROWS = 81_567
CURRENT_ROWS = 82_345
MAX_CSV_BYTES = 128 * 1024 * 1024
MAX_ROWS = 150_000
MAX_FIELD_CHARS = 16_384
MAX_CELL_CHARS = 64_000_000

CURRENT_HEADER = (
    "BOROUGH",
    "NEIGHBORHOOD",
    "BUILDING CLASS CATEGORY",
    "TAX CLASS AT PRESENT",
    "BLOCK",
    "LOT",
    "EASE-MENT",
    "BUILDING CLASS AT PRESENT",
    "ADDRESS",
    "APARTMENT NUMBER",
    "ZIP CODE",
    "RESIDENTIAL UNITS",
    "COMMERCIAL UNITS",
    "TOTAL UNITS",
    "LAND SQUARE FEET",
    "GROSS SQUARE FEET",
    "YEAR BUILT",
    "TAX CLASS AT TIME OF SALE",
    "BUILDING CLASS AT TIME OF SALE",
    "SALE PRICE",
    "SALE DATE",
)
ARCHIVE_HEADER = (
    "neighborhood",
    "building_class_category",
    "lot",
    "ease_ment",
    "building_class_at_present",
    "address",
    "apartment_number",
    "borough",
    "residential_units",
    "commercial_units",
    "total_units",
    "gross_square_feet",
    "block",
    "tax_class_at_time_of_sale",
    "building_class_at_time_of",
    "land_square_feet",
    "sale_date",
    "tax_class_at_present",
    "sale_price",
    "year_built",
    "zip_code",
)
ARCHIVE_FIELDS_IN_CURRENT_ORDER = (
    "borough",
    "neighborhood",
    "building_class_category",
    "tax_class_at_present",
    "block",
    "lot",
    "ease_ment",
    "building_class_at_present",
    "address",
    "apartment_number",
    "zip_code",
    "residential_units",
    "commercial_units",
    "total_units",
    "land_square_feet",
    "gross_square_feet",
    "year_built",
    "tax_class_at_time_of_sale",
    "building_class_at_time_of",
    "sale_price",
    "sale_date",
)
ARCHIVE_INDICES = tuple(
    ARCHIVE_HEADER.index(field) for field in ARCHIVE_FIELDS_IN_CURRENT_ORDER
)
CODE_FILES = (
    "scripts/compare_nyc_archive_snapshot_v1.py",
    "scripts/private_review_io.py",
)
_ISO = re.compile(r"([0-9]{4})-([0-9]{2})-([0-9]{2})\Z")
_US = re.compile(r"([0-9]{2})/([0-9]{2})/([0-9]{4})\Z")
_MIDNIGHT = re.compile(r"([0-9]{4})-([0-9]{2})-([0-9]{2})[T ]00:00:00(?:\.0{1,6})?\Z")
_RUN_ID = re.compile(r"archive-current-v1-([0-9]{8}T[0-9]{6}Z)-[0-9a-f]{12}\Z")
_LOW_DATE = date(1900, 1, 1)
_HIGH_DATE = date(2026, 10, 2)


def _sha(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def _encoded(value: dict) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def reorder_archive_row(
    row: tuple[str, ...], *, header: tuple[str, ...] = ARCHIVE_HEADER
) -> tuple[str, ...]:
    if header != ARCHIVE_HEADER or len(row) != 21:
        raise ValueError("Archive schema differs from frozen 21-column map")
    return tuple(row[index] for index in ARCHIVE_INDICES)


def canonical_date(value: str) -> str | None:
    """Normalize only exact calendar forms in the frozen archive-safe range."""
    if type(value) is not str:
        raise TypeError("Sale date must be a string")
    match = _ISO.fullmatch(value) or _MIDNIGHT.fullmatch(value)
    if match:
        year, month, day = (int(part) for part in match.groups()[:3])
    else:
        match = _US.fullmatch(value)
        if match is None:
            return None
        month, day, year = (int(part) for part in match.groups())
    try:
        result = date(year, month, day)
    except ValueError:
        return None
    return result.isoformat() if _LOW_DATE <= result <= _HIGH_DATE else None


def scan_csv(body: bytes, *, source: str, expected_rows: int) -> list[tuple[str, ...]]:
    """Validate a whole pinned CSV and return rows in current-header order."""
    if source not in {"archive", "current"}:
        raise ValueError("Unknown NYC source representation")
    if type(expected_rows) is not int or not 0 <= expected_rows <= MAX_ROWS:
        raise ValueError("Expected NYC row count is invalid")
    if len(body) > MAX_CSV_BYTES:
        raise ValueError("NYC CSV exceeds byte cap")
    try:
        text = body.decode("utf-8-sig", errors="strict")
        if "\x00" in text:
            raise ValueError("NYC CSV contains a null character")
        reader = csv.reader(io.StringIO(text, newline=""), strict=True)
        header = tuple(next(reader, ()))
        expected = ARCHIVE_HEADER if source == "archive" else CURRENT_HEADER
        if header != expected or len(set(header)) != 21:
            raise ValueError("NYC CSV header differs from frozen schema")
        rows: list[tuple[str, ...]] = []
        characters = 0
        for record in reader:
            if len(record) != 21 or len(rows) >= MAX_ROWS:
                raise ValueError("NYC CSV row width or count exceeds contract")
            if any(len(value) > MAX_FIELD_CHARS for value in record):
                raise ValueError("NYC CSV field exceeds character cap")
            characters += sum(map(len, record))
            if characters > MAX_CELL_CHARS:
                raise ValueError("NYC CSV aggregate cell characters exceed cap")
            row = tuple(record)
            rows.append(reorder_archive_row(row) if source == "archive" else row)
    except (csv.Error, UnicodeError) as error:
        raise ValueError("NYC CSV is malformed") from error
    if len(rows) != expected_rows:
        raise ValueError("NYC CSV row count differs from frozen manifest")
    return rows


def _counter(rows: list[tuple[str, ...]]) -> tuple[Counter, Counter, int]:
    raw: Counter = Counter()
    dated: Counter = Counter()
    invalid = 0
    for row in rows:
        if len(row) != 21 or any(type(value) is not str for value in row):
            raise ValueError("NYC row differs from canonical schema")
        trimmed = tuple(value.strip() for value in row)
        raw[trimmed] += 1
        normalized = canonical_date(trimmed[20])
        if normalized is None:
            invalid += 1
        else:
            dated[(*trimmed[:20], normalized)] += 1
    return raw, dated, invalid


def _overlap(left: Counter, right: Counter) -> int:
    return sum(min(count, right.get(key, 0)) for key, count in left.items())


def compare_rows(
    archive_rows: list[tuple[str, ...]], current_rows: list[tuple[str, ...]]
) -> dict:
    """Count full-row multiset overlap without emitting any row-level value."""
    if len(archive_rows) > MAX_ROWS or len(current_rows) > MAX_ROWS:
        raise ValueError("NYC row count exceeds cap")
    archive_raw, archive_dated, archive_invalid = _counter(archive_rows)
    current_raw, current_dated, current_invalid = _counter(current_rows)
    raw_match = _overlap(archive_raw, current_raw)
    date_match = _overlap(archive_dated, current_dated)
    archive_eligible = len(archive_rows) - archive_invalid
    current_eligible = len(current_rows) - current_invalid
    return {
        "archive_rows": len(archive_rows),
        "current_rows": len(current_rows),
        "raw_full_row_multiset_matches": raw_match,
        "archive_raw_residual_rows": len(archive_rows) - raw_match,
        "current_raw_residual_rows": len(current_rows) - raw_match,
        "date_canonical_full_row_multiset_matches": date_match,
        "archive_invalid_date_rows": archive_invalid,
        "current_invalid_date_rows": current_invalid,
        "archive_date_eligible_rows": archive_eligible,
        "current_date_eligible_rows": current_eligible,
        "archive_date_residual_rows": archive_eligible - date_match,
        "current_date_residual_rows": current_eligible - date_match,
        "sale_labels_certified": 0,
        "historical_asof_eligible": False,
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
    """Expose only source denominators, broad buckets, and gate boundaries."""
    required = (
        "archive_rows",
        "current_rows",
        "raw_full_row_multiset_matches",
        "date_canonical_full_row_multiset_matches",
    )
    if any(type(private.get(key)) is not int or private[key] < 0 for key in required):
        raise ValueError("Private comparison counters are invalid")
    if any(
        private[name] > min(private["archive_rows"], private["current_rows"])
        for name in required[2:]
    ):
        raise ValueError("Private overlap exceeds source rows")
    return {
        "protocol": PROTOCOL,
        "archive_rows": private["archive_rows"],
        "current_rows": private["current_rows"],
        "raw_overlap_bucket": _bucket(private["raw_full_row_multiset_matches"]),
        "date_overlap_bucket": _bucket(
            private["date_canonical_full_row_multiset_matches"]
        ),
        "sale_labels_certified": 0,
        "historical_asof_eligible": False,
        "u0_status": "PENDING",
        "g_us_status": "PENDING",
    }


def _pinned_bytes(
    path: Path, *, limit: int, expected_sha: str, expected_bytes: int | None = None
) -> bytes:
    if path.is_symlink() or not path.is_file() or path.stat().st_nlink != 1:
        raise ValueError("Pinned comparison file is missing or linked")
    with path.open("rb") as handle:
        before = os.fstat(handle.fileno())
        if before.st_nlink != 1 or before.st_size > limit:
            raise ValueError("Pinned comparison file exceeds cap or is linked")
        body = handle.read(limit + 1)
        after = os.fstat(handle.fileno())
    if (
        len(body) != before.st_size
        or len(body) > limit
        or (before.st_dev, before.st_ino, before.st_size)
        != (after.st_dev, after.st_ino, after.st_size)
        or (
            path.stat().st_dev,
            path.stat().st_ino,
            path.stat().st_size,
            path.stat().st_nlink,
        )
        != (before.st_dev, before.st_ino, before.st_size, before.st_nlink)
        or path.is_symlink()
    ):
        raise ValueError("Pinned comparison file changed during read")
    if expected_bytes is not None and len(body) != expected_bytes:
        raise ValueError("Pinned comparison file byte count differs")
    if _sha(body) != expected_sha:
        raise ValueError("Pinned comparison file hash differs")
    return body


def _manifests() -> tuple[Path, dict, dict]:
    private_review_io.real_directory(PRIVATE_ROOT, PRIVATE_ROOT.parent)
    private_review_io.verify_acl(PRIVATE_ROOT)
    private_review_io.real_directory(ARCHIVE_RUN, PRIVATE_ROOT)
    private_review_io.verify_acl(ARCHIVE_RUN)
    archive_body = _pinned_bytes(
        ARCHIVE_MANIFEST, limit=64 * 1024, expected_sha=ARCHIVE_MANIFEST_SHA256
    )
    private_body = _pinned_bytes(
        ARCHIVE_RUN / "manifest.json",
        limit=64 * 1024,
        expected_sha=ARCHIVE_MANIFEST_SHA256,
    )
    if archive_body != private_body:
        raise ValueError("Archive private/public manifests differ")
    snapshot_body = _pinned_bytes(
        SNAPSHOT_MANIFEST, limit=64 * 1024, expected_sha=SNAPSHOT_MANIFEST_SHA256
    )
    archive = json.loads(archive_body)
    snapshot = json.loads(snapshot_body)
    csv_requests = [
        item for item in archive.get("requests", []) if item.get("stage") == "csv"
    ]
    if (
        archive.get("protocol") != "nyc-ready-rolling-archive-v2"
        or archive.get("version") != 62
        or len(csv_requests) != 1
        or csv_requests[0].get("file") != "archive.csv"
        or csv_requests[0].get("sha256") != ARCHIVE_SHA256
        or csv_requests[0].get("bytes") != ARCHIVE_BYTES
    ):
        raise ValueError("Archive manifest differs from frozen source")
    if (
        snapshot.get("source_id") != "nyc_dof_rolling_usep_8jbt"
        or snapshot.get("sha256") != CURRENT_SHA256
        or snapshot.get("bytes") != CURRENT_BYTES
        or snapshot.get("rows") != CURRENT_ROWS
    ):
        raise ValueError("Current snapshot manifest differs from frozen source")
    filename = snapshot.get("raw_filename")
    if (
        type(filename) is not str
        or not filename
        or Path(filename).name != filename
        or "/" in filename
        or "\\" in filename
    ):
        raise ValueError("Current snapshot filename is unsafe")
    return PRIVATE_ROOT / filename, archive, snapshot


def _code_hashes() -> dict[str, str]:
    return {name: _sha((ROOT / name).read_bytes()) for name in CODE_FILES}


def _configuration_sha() -> str:
    return _sha(
        _encoded(
            {
                "protocol": PROTOCOL,
                "archive_sha256": ARCHIVE_SHA256,
                "current_sha256": CURRENT_SHA256,
                "archive_header": ARCHIVE_HEADER,
                "current_header": CURRENT_HEADER,
                "archive_fields_in_current_order": ARCHIVE_FIELDS_IN_CURRENT_ORDER,
                "date_range": [str(_LOW_DATE), str(_HIGH_DATE)],
                "max_csv_bytes": MAX_CSV_BYTES,
                "max_rows": MAX_ROWS,
                "max_field_chars": MAX_FIELD_CHARS,
                "max_cell_chars": MAX_CELL_CHARS,
            }
        )
    )


def _git_state() -> tuple[str, bool]:
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    ).stdout.strip()
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    ).stdout
    return commit, bool(status.strip())


def _remote_tracking_commit() -> str:
    return subprocess.run(
        ["git", "rev-parse", "refs/remotes/origin/audit/u0"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    ).stdout.strip()


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


def _intent(output: Path) -> dict:
    commit, dirty = _git_state()
    if dirty:
        raise ValueError("Comparison requires a clean pushed code tree")
    if commit != _remote_tracking_commit():
        raise ValueError(
            "Comparison code commit differs from pushed branch tracking ref"
        )
    if sys.implementation.name != "cpython" or sys.version_info[:3] != (3, 11, 6):
        raise ValueError("Comparison Python runtime differs from environment lock")
    _pinned_bytes(
        ENVIRONMENT_LOCK,
        limit=64 * 1024,
        expected_sha=ENVIRONMENT_LOCK_SHA256,
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
        "archive_manifest_sha256": ARCHIVE_MANIFEST_SHA256,
        "snapshot_manifest_sha256": SNAPSHOT_MANIFEST_SHA256,
        "archive_csv_sha256": ARCHIVE_SHA256,
        "current_csv_sha256": CURRENT_SHA256,
        "started_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }


def _compute(snapshot_path: Path) -> dict:
    archive_body = _pinned_bytes(
        ARCHIVE_RUN / "archive.csv",
        limit=MAX_CSV_BYTES,
        expected_sha=ARCHIVE_SHA256,
        expected_bytes=ARCHIVE_BYTES,
    )
    current_body = _pinned_bytes(
        snapshot_path,
        limit=MAX_CSV_BYTES,
        expected_sha=CURRENT_SHA256,
        expected_bytes=CURRENT_BYTES,
    )
    archive_rows = scan_csv(archive_body, source="archive", expected_rows=ARCHIVE_ROWS)
    current_rows = scan_csv(current_body, source="current", expected_rows=CURRENT_ROWS)
    return {"protocol": PROTOCOL, **compare_rows(archive_rows, current_rows)}


def _write_new(output: Path, name: str, value: dict) -> bytes:
    body = _encoded(value)
    private_review_io.new_file(output / name, body)
    return body


def _checked_run_artifact(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file() or path.stat().st_nlink != 1:
        raise ValueError("Comparison run artifact is missing or linked")
    with path.open("rb") as handle:
        before = os.fstat(handle.fileno())
        if before.st_size > 64 * 1024 or before.st_nlink != 1:
            raise ValueError("Comparison run artifact exceeds cap or is linked")
        body = handle.read(64 * 1024 + 1)
        after = os.fstat(handle.fileno())
    if (
        len(body) != before.st_size
        or (before.st_dev, before.st_ino, before.st_size)
        != (after.st_dev, after.st_ino, after.st_size)
        or (path.stat().st_dev, path.stat().st_ino, path.stat().st_size)
        != (before.st_dev, before.st_ino, before.st_size)
        or path.is_symlink()
    ):
        raise ValueError("Comparison run artifact changed during read")
    return body


def compare(output: Path) -> dict:
    """Save a new protected run after intent; never overwrite an earlier run."""
    target = _run_dir(output, new=True)
    snapshot_path, _, _ = _manifests()
    intent = _intent(target)
    target.mkdir(mode=0o700)
    try:
        private_review_io.secure_directory(target)
        private_review_io.verify_acl(target)
        intent_body = _write_new(target, "intent.json", intent)
        private = _compute(snapshot_path)
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
    """Verify saved hashes and regenerate the exact aggregate offline."""
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
        or intent.get("archive_manifest_sha256") != ARCHIVE_MANIFEST_SHA256
        or intent.get("snapshot_manifest_sha256") != SNAPSHOT_MANIFEST_SHA256
        or intent.get("archive_csv_sha256") != ARCHIVE_SHA256
        or intent.get("current_csv_sha256") != CURRENT_SHA256
    ):
        raise ValueError("Comparison run intent differs from pinned code or inputs")
    snapshot_path, _, _ = _manifests()
    _pinned_bytes(
        ENVIRONMENT_LOCK,
        limit=64 * 1024,
        expected_sha=ENVIRONMENT_LOCK_SHA256,
    )
    private = _compute(snapshot_path)
    public = public_projection(private)
    if result_body != _encoded(private) or public_body != _encoded(public):
        raise ValueError("Comparison offline replay differs")
    return public


def plan() -> dict:
    return {
        "protocol": PROTOCOL,
        "archive_csv_sha256": ARCHIVE_SHA256,
        "current_csv_sha256": CURRENT_SHA256,
        "archive_rows": ARCHIVE_ROWS,
        "current_rows": CURRENT_ROWS,
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
        parser.exit(2, f"NYC archive comparison failed: {type(error).__name__}\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
