"""Read-only aggregate DBF inventory; does not expose property or person rows."""

from __future__ import annotations

from collections import Counter
from datetime import date
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
from pathlib import Path
import sys
from zipfile import ZipFile


EXPECTED_ARCHIVE_SHA256 = "847854d9139fe3811506991d3c41d961581a92a648bb661c4bd9d166591366c7"
EXPECTED_MEMBER_BYTES = 679533377
MAX_ARCHIVE_BYTES = 100_000_000
MAX_RECORDS = 3_000_000
MAX_CATEGORY_KEYS = 500


def _archive_hash(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _fields(header: bytes) -> dict[str, tuple[int, int]]:
    if not header or header[-1] != 13 or (len(header) - 1) % 32 != 0:
        raise ValueError("Malformed DBF field terminator")
    fields: dict[str, tuple[int, int]] = {}
    offset = 1
    for position in range(0, len(header) - 1, 32):
        descriptor = header[position : position + 32]
        if descriptor[0] == 13:
            break
        name = descriptor[:11].split(b"\0", 1)[0].decode("ascii")
        width = descriptor[16]
        if not name or name in fields or width == 0:
            raise ValueError("Malformed or duplicate DBF field descriptor")
        fields[name] = (offset, width)
        offset += width
    return fields


def _count_code(counter: Counter[str], raw: str, width: int) -> None:
    code = raw or "<blank>"
    if raw and (
        len(raw) > width
        or not raw.isascii()
        or not all(char.isupper() or char.isdigit() for char in raw)
    ):
        code = "<invalid>"
    if code not in counter and len(counter) >= MAX_CATEGORY_KEYS:
        raise ValueError("Unexpectedly large DBF category vocabulary")
    counter[code] += 1


def _value(record: bytes, field: tuple[int, int]) -> str:
    offset, width = field
    return record[offset : offset + width].decode("ascii").strip()


def profile(archive: Path) -> dict[str, object]:
    if archive.stat().st_size > MAX_ARCHIVE_BYTES:
        raise ValueError("Archive exceeds the source-audit size cap")
    archive_hash = _archive_hash(archive)
    if archive_hash != EXPECTED_ARCHIVE_SHA256:
        raise ValueError("Archive checksum differs from the audited source")
    with ZipFile(archive) as zipped:
        info = zipped.getinfo("allsales.dbf")
        if (
            info.file_size != EXPECTED_MEMBER_BYTES
            or info.compress_size == 0
            or info.file_size / info.compress_size > 20
        ):
            raise ValueError("DBF member size or compression ratio is unexpected")
        with zipped.open(info) as stream:
            dbf_header = stream.read(32)
            if len(dbf_header) != 32 or dbf_header[0] != 3:
                raise ValueError("Expected an intact dBASE III header")
            row_count = int.from_bytes(dbf_header[4:8], "little")
            header_length = int.from_bytes(dbf_header[8:10], "little")
            row_length = int.from_bytes(dbf_header[10:12], "little")
            if not (0 < row_count <= MAX_RECORDS and 33 <= header_length <= 4096 and 1 < row_length <= 512):
                raise ValueError("DBF header dimensions exceed the audit contract")
            if header_length + row_count * row_length + 1 != info.file_size:
                raise ValueError("DBF header count disagrees with member size")
            descriptors = stream.read(header_length - 32)
            fields = _fields(descriptors)
            if 1 + sum(width for _, width in fields.values()) != row_length:
                raise ValueError("DBF field widths do not match record length")
            required = {"S_DATE", "S_AMT", "QU", "VI", "S_TYPE", "DOR_CODE", "PIN", "FOLIO", "DOC_NUM"}
            if not required <= fields.keys():
                raise ValueError("Required audit columns missing")

            counts: Counter[str] = Counter()
            years: Counter[str] = Counter()
            qualifications: Counter[str] = Counter()
            improvement: Counter[str] = Counter()
            sale_types: Counter[str] = Counter()
            dor_codes: Counter[str] = Counter()
            earliest: str | None = None
            latest: str | None = None
            for _ in range(row_count):
                record = stream.read(row_length)
                if len(record) != row_length:
                    raise ValueError("DBF ends before its header record count")
                counts["records"] += 1
                if record[0:1] == b"*":
                    counts["deleted"] += 1
                    continue
                if record[0:1] != b" ":
                    raise ValueError("Unexpected DBF record marker")
                counts["active"] += 1
                raw_date = _value(record, fields["S_DATE"])
                try:
                    if len(raw_date) != 8 or not raw_date.isascii() or not raw_date.isdigit():
                        raise ValueError("Invalid DBF date")
                    parsed = date(int(raw_date[:4]), int(raw_date[4:6]), int(raw_date[6:8]))
                except ValueError:
                    counts["invalid_sale_date"] += 1
                else:
                    years[str(parsed.year)] += 1
                    earliest = min(earliest, raw_date) if earliest else raw_date
                    latest = max(latest, raw_date) if latest else raw_date
                raw_amount = _value(record, fields["S_AMT"])
                try:
                    amount = Decimal(raw_amount)
                    if not amount.is_finite():
                        raise InvalidOperation
                except (InvalidOperation, ValueError):
                    counts["invalid_sale_amount"] += 1
                else:
                    if amount <= 0:
                        counts["nonpositive_sale_amount"] += 1
                for name in ("PIN", "FOLIO", "DOC_NUM"):
                    if not _value(record, fields[name]):
                        counts[f"missing_{name.lower()}"] += 1
                for field_name, counter in (
                    ("QU", qualifications),
                    ("VI", improvement),
                    ("S_TYPE", sale_types),
                    ("DOR_CODE", dor_codes),
                ):
                    _count_code(counter, _value(record, fields[field_name]), fields[field_name][1])
            if stream.read(2) != b"\x1a":
                raise ValueError("Expected DBF end-of-file marker")
    return {
        "source_archive_sha256": archive_hash,
        "member": "allsales.dbf",
        "member_crc32": f"{info.CRC:08x}",
        "member_uncompressed_bytes": info.file_size,
        "header_record_count": row_count,
        "header_date": f"{1900 + dbf_header[1]:04d}-{dbf_header[2]:02d}-{dbf_header[3]:02d}",
        "field_names": list(fields),
        "counts": dict(sorted(counts.items())),
        "earliest_sale_date": earliest,
        "latest_sale_date": latest,
        "sale_year_counts": dict(sorted(years.items())),
        "qualification_code_counts": dict(sorted(qualifications.items())),
        "vacant_improved_code_counts": dict(sorted(improvement.items())),
        "sale_type_counts": dict(sorted(sale_types.items())),
        "dor_code_counts": dict(sorted(dor_codes.items())),
        "interpretation": "Unqualified source profile; no row-level dates, prices, names or addresses retained",
    }


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("Usage: profile.py ARCHIVE.zip OUTPUT.json")
    result = profile(Path(sys.argv[1]))
    Path(sys.argv[2]).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
