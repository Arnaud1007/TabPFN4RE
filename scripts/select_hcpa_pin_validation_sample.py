"""Freeze ADR 0017's disjoint HCPA PIN validation sample.

Row identifiers stay in ignored data/raw/hcpa; the manifest has counts and hashes.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import date
from hashlib import sha256
import heapq
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
from zipfile import BadZipFile, ZipFile


PRIVATE_ROOT = Path(__file__).resolve().parents[1] / "data" / "raw" / "hcpa"
EXPECTED_ARCHIVE_SHA256 = (
    "847854d9139fe3811506991d3c41d961581a92a648bb661c4bd9d166591366c7"
)
EXPECTED_EXCLUSION_SHA256 = (
    "2f26728c37f8218d1bb79ee75e4082fb918665eb2cb4cc287feba7f6250aaec9"
)
EXPECTED_MEMBER_BYTES = 679_533_377
MAX_ARCHIVE_BYTES = 100_000_000
MAX_EXCLUSION_BYTES = 10_000_000
MAX_RECORDS = 3_000_000
MAX_SAMPLE_ROWS = 10_000
SHA256_PATTERN = re.compile(r"[0-9a-fA-F]{64}\Z")
RANKING_VERSION = "hcpa-pin-validation-v1"
SEED = 43
BANDS = ("before_2000", "2000_2009", "2010_2019", "2020_2023", "2024_2026")
PRIVATE_FIELDS = ("PIN", "FOLIO", "S_DATE", "QU")


def _hash_stream(source) -> str:
    digest = sha256()
    for chunk in iter(lambda: source.read(1024 * 1024), b""):
        digest.update(chunk)
    return digest.hexdigest()


def _private_path(path: Path) -> None:
    root = PRIVATE_ROOT.resolve(strict=True)
    if PRIVATE_ROOT.is_symlink() or os.path.normcase(
        str(PRIVATE_ROOT.absolute())
    ) != os.path.normcase(str(root)):
        raise ValueError("Private HCPA root is a symlink or redirects")
    if not path.resolve().is_relative_to(root) or path.parent.resolve() != root:
        raise ValueError("Row-level input and output must be directly in private root")
    if path.exists() and (path.is_symlink() or path.stat().st_nlink != 1):
        raise ValueError("Private row-level input must not be linked")


def _pinned_exclusions(
    path: Path, expected_sha: str, expected_rows: int
) -> dict[int, dict]:
    if not SHA256_PATTERN.fullmatch(expected_sha):
        raise ValueError("Exclusion SHA-256 must be 64 hex digits")
    _private_path(path)
    with path.open("rb") as source:
        meta = os.fstat(source.fileno())
        if not stat.S_ISREG(meta.st_mode) or meta.st_size > MAX_EXCLUSION_BYTES:
            raise ValueError("Private exclusion sample exceeds the file contract")
        content = source.read(MAX_EXCLUSION_BYTES + 1)
    if sha256(content).hexdigest() != expected_sha.lower():
        raise ValueError("Exclusion sample SHA-256 mismatch")
    try:
        rows = [json.loads(line) for line in content.decode("utf-8").splitlines()]
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Malformed exclusion JSONL") from error
    if not 0 < expected_rows <= MAX_SAMPLE_ROWS or len(rows) != expected_rows:
        raise ValueError("Exclusion sample count differs from the frozen protocol")
    exclusions: dict[int, dict] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Malformed exclusion row")
        ordinal = row.get("record_ordinal")
        if (
            type(ordinal) is not int
            or ordinal < 1
            or any(not isinstance(row.get(field), str) for field in PRIVATE_FIELDS)
        ):
            raise ValueError("Malformed exclusion ordinal or identifier")
        if ordinal in exclusions:
            raise ValueError("duplicate exclusion ordinal")
        exclusions[ordinal] = row
    return exclusions


def _fields(descriptors: bytes, row_length: int) -> dict[str, tuple[int, int]]:
    if not descriptors or descriptors[-1:] != b"\x0d" or (len(descriptors) - 1) % 32:
        raise ValueError("Malformed DBF field terminator")
    fields: dict[str, tuple[int, int]] = {}
    offset = 1
    for position in range(0, len(descriptors) - 1, 32):
        item = descriptors[position : position + 32]
        try:
            name = item[:11].split(b"\0", 1)[0].decode("ascii")
        except UnicodeDecodeError as error:
            raise ValueError("Malformed DBF field descriptor") from error
        width = item[16]
        if not name or name in fields or width == 0:
            raise ValueError("Malformed or duplicate DBF field descriptor")
        expected_type = "D" if name == "S_DATE" else "C"
        if name in PRIVATE_FIELDS and chr(item[11]) != expected_type:
            raise ValueError("Required DBF field has unexpected type")
        fields[name] = (offset, width)
        offset += width
    if offset != row_length or not set(PRIVATE_FIELDS).issubset(fields):
        raise ValueError("DBF widths or required fields violate sample contract")
    return fields


def _header(source, member_bytes: int) -> tuple[int, int, dict[str, tuple[int, int]]]:
    header = source.read(32)
    if len(header) != 32 or header[0] != 3:
        raise ValueError("Expected an intact dBASE III header")
    rows = int.from_bytes(header[4:8], "little")
    header_length = int.from_bytes(header[8:10], "little")
    row_length = int.from_bytes(header[10:12], "little")
    if not (
        0 < rows <= MAX_RECORDS
        and 33 <= header_length <= 4096
        and 1 < row_length <= 512
        and header_length + rows * row_length + 1 == member_bytes
    ):
        raise ValueError("DBF header dimensions violate sample contract")
    descriptors = source.read(header_length - 32)
    if len(descriptors) != header_length - 32:
        raise ValueError("DBF header ends early")
    return rows, row_length, _fields(descriptors, row_length)


def _value(record: bytes, field: tuple[int, int]) -> str:
    offset, width = field
    try:
        return record[offset : offset + width].decode("ascii").strip()
    except UnicodeDecodeError as error:
        raise ValueError("DBF selected field is not ASCII") from error


def _band(raw_date: str) -> str | None:
    # Exact date-band and invalid-date rule from ADR 0013.
    if len(raw_date) != 8 or not raw_date.isascii() or not raw_date.isdigit():
        return None
    try:
        year = date(int(raw_date[:4]), int(raw_date[4:6]), int(raw_date[6:8])).year
    except ValueError:
        return None
    if year < 2000:
        return BANDS[0]
    if year < 2010:
        return BANDS[1]
    if year < 2020:
        return BANDS[2]
    if year < 2024:
        return BANDS[3]
    if year <= 2026:
        return BANDS[4]
    return None


def _rank(source_sha: str, ordinal: int) -> int:
    canonical = f"{RANKING_VERSION}|{source_sha}|{SEED}|{ordinal}".encode("ascii")
    return int.from_bytes(sha256(canonical).digest(), "big")


def _offer(
    heap: list[tuple], ordinal: int, row: dict, rank: int, capacity: int
) -> None:
    item = (-rank, -ordinal, ordinal, row)
    if len(heap) < capacity:
        heapq.heappush(heap, item)
    elif item > heap[0]:
        heapq.heapreplace(heap, item)


def _scan(
    zipped: ZipFile,
    source_sha: str,
    exclusions: dict[int, dict],
    expected_member_bytes: int,
    rows_per_cell: int,
) -> tuple[list[dict], dict, dict]:
    members = [info for info in zipped.infolist() if info.filename == "allsales.dbf"]
    if len(members) != 1 or len(zipped.infolist()) > 100:
        raise ValueError("Expected exactly one allsales.dbf ZIP member")
    info = members[0]
    if (
        info.is_dir()
        or info.file_size != expected_member_bytes
        or info.compress_size <= 0
        or info.file_size / info.compress_size > 20
    ):
        raise ValueError("DBF member size or compression violates source contract")
    heaps = {(band, qu): [] for band in BANDS for qu in ("Q", "U")}
    eligible = Counter()
    excluded_cells = Counter()
    excluded = Counter()
    reconciled: set[int] = set()
    with zipped.open(info) as source:
        total_rows, row_length, fields = _header(source, info.file_size)
        if max(exclusions) > total_rows:
            raise ValueError("Exclusion ordinal exceeds DBF record count")
        for ordinal in range(1, total_rows + 1):
            record = source.read(row_length)
            if len(record) != row_length:
                raise ValueError("DBF ends before header record count")
            if record[:1] == b"*":
                if ordinal in exclusions:
                    raise ValueError("Excluded record is deleted; cannot reconcile")
                excluded["deleted"] += 1
                continue
            if record[:1] != b" ":
                raise ValueError("Unexpected DBF record marker")
            sale_date = _value(record, fields["S_DATE"])
            band = _band(sale_date)
            if band is None:
                if ordinal in exclusions:
                    raise ValueError("Excluded record date cannot reconcile")
                excluded["date_outside_or_invalid"] += 1
                continue
            qu = _value(record, fields["QU"])
            if qu not in ("Q", "U"):
                if ordinal in exclusions:
                    raise ValueError("Excluded qualification cannot reconcile")
                excluded["qualification_other"] += 1
                continue
            key = band, qu
            if ordinal in exclusions:
                observed = {
                    name: _value(record, fields[name]) for name in PRIVATE_FIELDS
                }
                if any(
                    observed[name] != exclusions[ordinal][name]
                    for name in PRIVATE_FIELDS
                ):
                    raise ValueError("Excluded identifier does not reconcile with DBF")
                reconciled.add(ordinal)
                excluded_cells[key] += 1
                continue
            eligible[key] += 1
            row = {
                "record_ordinal": ordinal,
                "PIN": _value(record, fields["PIN"]),
                "FOLIO": _value(record, fields["FOLIO"]),
                "S_DATE": sale_date,
                "QU": qu,
            }
            _offer(heaps[key], ordinal, row, _rank(source_sha, ordinal), rows_per_cell)
        if source.read(2) != b"\x1a" or source.read(1):
            raise ValueError("Expected DBF end-of-file marker")
    if reconciled != exclusions.keys():
        raise ValueError("Exclusion set cannot reconcile with source DBF")
    selected = []
    cell_counts = {}
    for band in BANDS:
        for qu in ("Q", "U"):
            key = band, qu
            label = f"{band}_{qu}"
            if eligible[key] < rows_per_cell:
                raise ValueError(
                    f"Insufficient quota in {label}: {eligible[key]}/{rows_per_cell}"
                )
            picks = sorted(heaps[key], key=lambda item: (-item[0], -item[1]))
            selected.extend(item[3] for item in picks)
            cell_counts[label] = {
                "eligible_after_exclusion": eligible[key],
                "excluded_original_sample": excluded_cells[key],
                "selected": len(picks),
            }
    return (
        selected,
        cell_counts,
        {
            "member": info.filename,
            "member_crc32": f"{info.CRC:08x}",
            "member_uncompressed_bytes": info.file_size,
            "header_record_count": total_rows,
            "excluded_counts": dict(sorted(excluded.items())),
            "excluded_sample_rows_reconciled": len(reconciled),
        },
    )


def _write_atomic(
    output: Path, manifest: Path, sample_bytes: bytes, manifest_bytes: bytes
) -> None:
    staged: list[Path] = []
    installed: list[Path] = []
    try:
        for destination, content in (
            (output, sample_bytes),
            (manifest, manifest_bytes),
        ):
            with tempfile.NamedTemporaryFile(
                dir=destination.parent, prefix=".hcpa-pin-validation-", delete=False
            ) as stream:
                staged.append(Path(stream.name))
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
        for temporary, destination in zip(staged, (output, manifest)):
            os.link(temporary, destination)
            installed.append(destination)
    except BaseException:
        for destination in installed:
            destination.unlink(missing_ok=True)
        raise
    finally:
        for temporary in staged:
            temporary.unlink(missing_ok=True)


def select_sample(
    archive: Path,
    exclusion_sample: Path,
    output: Path,
    manifest: Path,
    *,
    expected_archive_sha256: str = EXPECTED_ARCHIVE_SHA256,
    expected_exclusion_sha256: str = EXPECTED_EXCLUSION_SHA256,
    expected_member_bytes: int = EXPECTED_MEMBER_BYTES,
    expected_exclusion_rows: int = 200,
    rows_per_cell: int = 100,
) -> dict:
    """Freeze a private disjoint sample and an identifier-free aggregate manifest."""
    archive, exclusion_sample, output, manifest = map(
        Path, (archive, exclusion_sample, output, manifest)
    )
    for path in (archive, exclusion_sample, output):
        _private_path(path)
    if (
        len({path.resolve() for path in (archive, exclusion_sample, output, manifest)})
        != 4
    ):
        raise ValueError("Source, exclusion, output and manifest paths must differ")
    if output.exists() or manifest.exists():
        raise FileExistsError("Sample or manifest already exists; refusing overwrite")
    if not output.parent.is_dir() or not manifest.parent.is_dir():
        raise ValueError("Output parent directory is absent")
    if not 0 < rows_per_cell <= MAX_SAMPLE_ROWS // 10:
        raise ValueError("Per-cell quota exceeds sample contract")
    exclusions = _pinned_exclusions(
        exclusion_sample, expected_exclusion_sha256, expected_exclusion_rows
    )
    if not SHA256_PATTERN.fullmatch(expected_archive_sha256):
        raise ValueError("Archive SHA-256 must be 64 hex digits")
    with archive.open("rb") as source:
        meta = os.fstat(source.fileno())
        if not stat.S_ISREG(meta.st_mode) or meta.st_size > MAX_ARCHIVE_BYTES:
            raise ValueError("Archive exceeds file-type or size contract")
        source_sha = _hash_stream(source)
        if source_sha != expected_archive_sha256.lower():
            raise ValueError("Archive SHA-256 mismatch")
        source.seek(0)
        with ZipFile(source) as zipped:
            rows, cells, source_info = _scan(
                zipped, source_sha, exclusions, expected_member_bytes, rows_per_cell
            )
        source.seek(0)
        if _hash_stream(source) != source_sha:
            raise ValueError("Archive changed during source scan")
    sample_bytes = b"".join(
        (json.dumps(row, sort_keys=True) + "\n").encode("utf-8") for row in rows
    )
    result = {
        "source_archive_sha256": source_sha,
        "excluded_sample_sha256": expected_exclusion_sha256.lower(),
        "ranking_version": RANKING_VERSION,
        "ranking_formula": (
            f"SHA256(ASCII('{RANKING_VERSION}|{{source_archive_sha256}}|{SEED}|"
            "{one-based DBF ordinal}')); ascending unsigned 256-bit integer, ordinal tie-break"
        ),
        "sample_seed": SEED,
        "rows_per_cell": rows_per_cell,
        "cell_counts": cells,
        "sample_rows": len(rows),
        "sample_sha256": sha256(sample_bytes).hexdigest(),
        "sample_status": "Selected for identity-format validation only; no sale eligibility or historical availability implied",
        **source_info,
    }
    manifest_bytes = (json.dumps(result, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )
    _write_atomic(output, manifest, sample_bytes, manifest_bytes)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("exclusion_sample", type=Path)
    parser.add_argument("private_output", type=Path)
    parser.add_argument("aggregate_manifest", type=Path)
    options = parser.parse_args(argv)
    try:
        select_sample(
            options.archive,
            options.exclusion_sample,
            options.private_output,
            options.aggregate_manifest,
        )
    except (BadZipFile, FileExistsError, OSError, ValueError) as error:
        print(f"HCPA PIN validation sample failed: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
