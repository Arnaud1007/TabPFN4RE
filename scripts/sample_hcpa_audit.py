"""Select a private, reproducible 200-record HCPA manual-review sample.

The JSONL contains property identifiers and must remain under ignored data/raw/hcpa.
Only the aggregate manifest is suitable for the tracked audit record.
"""

from __future__ import annotations

from collections import Counter
from datetime import date
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import heapq
import json
import os
from pathlib import Path
import sys
import tempfile
from zipfile import ZipFile


EXPECTED_ARCHIVE_SHA256 = "847854d9139fe3811506991d3c41d961581a92a648bb661c4bd9d166591366c7"
EXPECTED_MEMBER_BYTES = 679_533_377
PRIVATE_ROOT = Path(__file__).resolve().parents[1] / "data" / "raw" / "hcpa"
MAX_ARCHIVE_BYTES = 100_000_000
MAX_RECORDS = 3_000_000
RANKING_VERSION = "hcpa-audit-v1"
SEED = 42
ROWS_PER_CELL = 20
EDGE_PER_CELL = 10
OUTPUT_FIELDS = (
    "PIN", "FOLIO", "S_DATE", "S_AMT", "QU", "VI", "REA_CD",
    "S_TYPE", "DOR_CODE", "DOC_NUM", "OR_BK", "OR_PG",
)
REVIEW_FIELDS = (
    "source_evidence", "identity", "sale_date_semantics", "price_semantics",
    "eligibility", "notes",
)
BANDS = ("before_2000", "2000_2009", "2010_2019", "2020_2023", "2024_2026")


def _archive_hash(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _fields(descriptors: bytes, row_length: int) -> dict[str, tuple[int, int]]:
    if not descriptors or descriptors[-1] != 13 or (len(descriptors) - 1) % 32:
        raise ValueError("Malformed DBF field terminator")
    fields: dict[str, tuple[int, int]] = {}
    offset = 1
    for position in range(0, len(descriptors) - 1, 32):
        item = descriptors[position : position + 32]
        name = item[:11].split(b"\0", 1)[0].decode("ascii")
        width = item[16]
        if not name or name in fields or width == 0:
            raise ValueError("Malformed or duplicate DBF field descriptor")
        fields[name] = (offset, width)
        offset += width
    if offset != row_length or not set(OUTPUT_FIELDS).issubset(fields):
        raise ValueError("DBF field widths or required columns violate the audit contract")
    return fields


def _value(record: bytes, field: tuple[int, int]) -> str:
    offset, width = field
    return record[offset : offset + width].decode("ascii").strip()


def _band(raw_date: str) -> str | None:
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


def _is_edge(row: dict[str, str]) -> bool:
    try:
        amount = Decimal(row["S_AMT"])
        low_amount = amount.is_finite() and amount < 1000
    except InvalidOperation:
        low_amount = False
    return (
        row["VI"] != "I"
        or not row["DOC_NUM"]
        or row["S_TYPE"] != "WD"
        or low_amount
        or row["DOR_CODE"] != "0100"
    )


def _rank(source_sha: str, ordinal: int) -> int:
    canonical = f"{RANKING_VERSION}|{source_sha}|{SEED}|{ordinal}".encode("ascii")
    return int.from_bytes(sha256(canonical).digest(), "big")


def _offer(heap: list[tuple[int, int, dict[str, str]]], row: dict[str, str],
           ordinal: int, rank: int, capacity: int) -> None:
    item = (-rank, ordinal, row)
    if len(heap) < capacity:
        heapq.heappush(heap, item)
    elif item > heap[0]:
        heapq.heapreplace(heap, item)


def _read_candidates(archive: Path, source_sha: str, expected_member_bytes: int):
    heaps = {(band, qu): {"all": [], "edge": []} for band in BANDS for qu in ("Q", "U")}
    eligible = Counter()
    excluded = Counter()
    with ZipFile(archive) as zipped:
        info = zipped.getinfo("allsales.dbf")
        if (info.file_size != expected_member_bytes or info.compress_size <= 0
                or info.file_size / info.compress_size > 20):
            raise ValueError("DBF member size or compression ratio is unexpected")
        with zipped.open(info) as source:
            header = source.read(32)
            if len(header) != 32 or header[0] != 3:
                raise ValueError("Expected an intact dBASE III header")
            row_count = int.from_bytes(header[4:8], "little")
            header_length = int.from_bytes(header[8:10], "little")
            row_length = int.from_bytes(header[10:12], "little")
            if not (0 < row_count <= MAX_RECORDS and 33 <= header_length <= 4096
                    and 1 < row_length <= 512):
                raise ValueError("DBF header dimensions exceed the audit contract")
            if header_length + row_count * row_length + 1 != info.file_size:
                raise ValueError("DBF header count disagrees with member size")
            fields = _fields(source.read(header_length - 32), row_length)
            for ordinal in range(1, row_count + 1):
                record = source.read(row_length)
                if len(record) != row_length:
                    raise ValueError("DBF ends before its header record count")
                if record[:1] == b"*":
                    excluded["deleted"] += 1
                    continue
                if record[:1] != b" ":
                    raise ValueError("Unexpected DBF record marker")
                raw_date = _value(record, fields["S_DATE"])
                band = _band(raw_date)
                if band is None:
                    excluded["date_outside_or_invalid"] += 1
                    continue
                qu = _value(record, fields["QU"])
                if qu not in ("Q", "U"):
                    excluded["qualification_other"] += 1
                    continue
                row = {name: _value(record, fields[name]) for name in OUTPUT_FIELDS}
                key = (band, qu)
                eligible[key] += 1
                rank = _rank(source_sha, ordinal)
                _offer(heaps[key]["all"], row, ordinal, rank, ROWS_PER_CELL + EDGE_PER_CELL)
                if _is_edge(row):
                    _offer(heaps[key]["edge"], row, ordinal, rank, EDGE_PER_CELL)
            if source.read(2) != b"\x1a":
                raise ValueError("Expected DBF end-of-file marker")
    return heaps, eligible, excluded, row_count, info


def _selected(heaps, eligible: Counter) -> tuple[list[dict[str, object]], dict[str, dict[str, int]]]:
    selected: list[dict[str, object]] = []
    cell_counts: dict[str, dict[str, int]] = {}
    for band in BANDS:
        for qu in ("Q", "U"):
            key = (band, qu)
            label = f"{band}_{qu}"
            if eligible[key] < ROWS_PER_CELL:
                raise ValueError(f"Insufficient HCPA sample quota in {label}: {eligible[key]}/{ROWS_PER_CELL}")
            edges = sorted(heaps[key]["edge"], reverse=True)
            edge_ordinals = {item[1] for item in edges}
            remaining = sorted(
                (item for item in heaps[key]["all"] if item[1] not in edge_ordinals),
                reverse=True,
            )[:ROWS_PER_CELL - len(edges)]
            picks = sorted(edges + remaining, reverse=True)
            if len(picks) != ROWS_PER_CELL:
                raise ValueError(f"Insufficient HCPA sample quota in {label} after selection")
            cell_counts[label] = {
                "eligible": eligible[key],
                "selected": len(picks),
                "selected_edge": sum(_is_edge(row) for _, _, row in picks),
                "edge_reserved": len(edges),
            }
            for _, ordinal, row in picks:
                selected.append({
                    "record_ordinal": ordinal,
                    **row,
                    "manual_review": dict.fromkeys(REVIEW_FIELDS),
                })
    return selected, cell_counts


def _write_atomic(output: Path, manifest: Path, sample_bytes: bytes, manifest_bytes: bytes) -> None:
    staged: list[Path] = []
    installed: list[Path] = []
    try:
        for destination, content in ((output, sample_bytes), (manifest, manifest_bytes)):
            with tempfile.NamedTemporaryFile(dir=destination.parent, prefix=".hcpa-audit-",
                                             delete=False) as stream:
                staged.append(Path(stream.name))
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
        for temporary, destination in zip(staged, (output, manifest)):
            os.link(temporary, destination)  # Atomic and refuses an existing destination.
            installed.append(destination)
    except BaseException:
        for destination in installed:
            destination.unlink(missing_ok=True)
        raise
    finally:
        for temporary in staged:
            temporary.unlink(missing_ok=True)


def sample_archive(
    archive: Path,
    output: Path,
    manifest: Path,
    *,
    expected_sha256: str = EXPECTED_ARCHIVE_SHA256,
    expected_member_bytes: int = EXPECTED_MEMBER_BYTES,
) -> dict[str, object]:
    """Return an aggregate manifest after writing a private sample and manifest."""
    archive, output, manifest = Path(archive), Path(output), Path(manifest)
    if not output.resolve().is_relative_to(PRIVATE_ROOT.resolve()):
        raise ValueError("Row-level sample must be inside the private HCPA directory")
    if output.resolve() == manifest.resolve():
        raise ValueError("Sample and manifest paths must differ")
    if not output.parent.is_dir() or not manifest.parent.is_dir():
        raise ValueError("Sample and manifest parent directories must exist")
    if output.exists() or manifest.exists():
        raise FileExistsError("Sample or manifest already exists; refusing overwrite")
    if archive.stat().st_size > MAX_ARCHIVE_BYTES:
        raise ValueError("Archive exceeds the source-audit size cap")
    source_sha = _archive_hash(archive)
    if source_sha != expected_sha256:
        raise ValueError("Archive checksum differs from the audited source")
    heaps, eligible, excluded, row_count, info = _read_candidates(
        archive, source_sha, expected_member_bytes,
    )
    rows, cells = _selected(heaps, eligible)
    sample_bytes = "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows).encode("utf-8")
    result: dict[str, object] = {
        "source_archive_sha256": source_sha,
        "member": "allsales.dbf",
        "member_crc32": f"{info.CRC:08x}",
        "member_uncompressed_bytes": info.file_size,
        "header_record_count": row_count,
        "ranking_version": RANKING_VERSION,
        "ranking_formula": "SHA256(ASCII('hcpa-audit-v1|{source_archive_sha256}|42|{1-based DBF record ordinal}')); ascending unsigned 256-bit integer",
        "sample_seed": SEED,
        "rows_per_cell": ROWS_PER_CELL,
        "edge_reserved_per_cell": EDGE_PER_CELL,
        "edge_rule": "VI != I OR missing DOC_NUM OR S_TYPE != WD OR finite S_AMT < 1000 OR DOR_CODE != 0100",
        "excluded_counts": dict(sorted(excluded.items())),
        "cell_counts": cells,
        "sample_rows": len(rows),
        "sample_sha256": sha256(sample_bytes).hexdigest(),
        "sample_status": "selected_for_manual_review; no manual review or eligibility decision implied",
    }
    manifest_bytes = (json.dumps(result, indent=2, sort_keys=True) + "\n").encode("utf-8")
    _write_atomic(output, manifest, sample_bytes, manifest_bytes)
    return result


if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit("Usage: sample_hcpa_audit.py ARCHIVE.zip PRIVATE_SAMPLE.jsonl AGGREGATE_MANIFEST.json")
    print(json.dumps(sample_archive(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])), sort_keys=True))
