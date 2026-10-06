"""Compare two exact HCPA parcel DBFs without emitting property-level data."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tempfile
from typing import BinaryIO
from zipfile import BadZipFile, ZipFile, ZipInfo


MEMBER_NAME = "dailyparcels.dbf"
HASH_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
MAX_ARCHIVE_BYTES = 256 * 1024 * 1024
MAX_DBF_BYTES = 1024 * 1024 * 1024
MAX_RECORDS = 2_000_000
MAX_FIELDS = 255
MAX_ZIP_ENTRIES = 32
MAX_CENTRAL_DIRECTORY_BYTES = 64 * 1024
KEY_FIELDS = ("FOLIO", "PIN")
GEOMETRY_MEMBERS = ("dailyparcels.shp", "dailyparcels.shx")
MAX_GEOMETRY_MEMBER_BYTES = 256 * 1024 * 1024
MAX_GEOMETRY_TOTAL_BYTES = 300 * 1024 * 1024


@dataclass(frozen=True)
class Field:
    name: str
    field_type: str
    width: int
    decimals: int
    start: int


@dataclass(frozen=True)
class Header:
    records: int
    header_length: int
    record_length: int
    fields: tuple[Field, ...]


def _stream_digest(source: BinaryIO, expected_bytes: int) -> str:
    digest = sha256()
    observed = 0
    for chunk in iter(lambda: source.read(1024 * 1024), b""):
        observed += len(chunk)
        if observed > expected_bytes:
            raise ValueError("ZIP member exceeded its declared size")
        digest.update(chunk)
    if observed != expected_bytes:
        raise ValueError("ZIP member ended before its declared size")
    return digest.hexdigest()


def _preflight_zip(source: BinaryIO, size: int) -> None:
    source.seek(max(0, size - 65_557))
    trailer = source.read()
    offset = trailer.rfind(b"PK\x05\x06")
    if offset < 0 or len(trailer) - offset < 22:
        raise ValueError("Archive central directory is invalid")
    eocd = trailer[offset : offset + 22]
    comment_length = int.from_bytes(eocd[20:22], "little")
    entries = int.from_bytes(eocd[10:12], "little")
    directory_size = int.from_bytes(eocd[12:16], "little")
    if (
        offset + 22 + comment_length != len(trailer)
        or eocd[4:8] != b"\0\0\0\0"
        or entries == 0xFFFF
        or directory_size == 0xFFFFFFFF
        or not 1 <= entries <= MAX_ZIP_ENTRIES
        or directory_size > MAX_CENTRAL_DIRECTORY_BYTES
    ):
        raise ValueError("Archive central directory exceeds the comparison contract")


def _validated_member(
    path: Path, expected_hash: str
) -> tuple[BytesIO, ZipFile, ZipInfo]:
    if not HASH_PATTERN.fullmatch(expected_hash):
        raise ValueError("Expected SHA-256 is invalid")
    try:
        if stat.S_ISLNK(path.lstat().st_mode):
            raise ValueError("Archive violates the comparison contract")
        source = path.open("rb")
    except (OSError, FileNotFoundError) as error:
        raise ValueError("Archive cannot be opened") from error
    with source:
        opened = os.fstat(source.fileno())
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
            or not 0 < opened.st_size <= MAX_ARCHIVE_BYTES
        ):
            raise ValueError("Archive violates the comparison contract")
        snapshot_bytes = source.read(MAX_ARCHIVE_BYTES + 1)
    if (
        len(snapshot_bytes) != opened.st_size
        or sha256(snapshot_bytes).hexdigest() != expected_hash
    ):
        raise ValueError("Archive hash mismatch")
    snapshot = BytesIO(snapshot_bytes)
    try:
        _preflight_zip(snapshot, opened.st_size)
    except ValueError:
        snapshot.close()
        raise
    snapshot.seek(0)
    try:
        zipped = ZipFile(snapshot)
    except BadZipFile as error:
        snapshot.close()
        raise ValueError("Archive is not a valid ZIP") from error
    infos = zipped.infolist()
    if len(infos) > MAX_ZIP_ENTRIES:
        zipped.close()
        snapshot.close()
        raise ValueError("Archive entry count exceeds the comparison contract")
    matches = [info for info in infos if info.filename == MEMBER_NAME]
    if len(matches) != 1:
        zipped.close()
        snapshot.close()
        raise ValueError("Expected exactly one dailyparcels.dbf member")
    info = matches[0]
    parts = PurePosixPath(info.filename).parts
    if (
        info.is_dir()
        or info.flag_bits & 1
        or info.filename.startswith("/")
        or ".." in parts
        or not 0 < info.file_size <= MAX_DBF_BYTES
        or info.compress_size <= 0
        or info.file_size / info.compress_size > 100
    ):
        zipped.close()
        snapshot.close()
        raise ValueError("DBF ZIP member violates the comparison contract")
    return snapshot, zipped, info


def _read_header(source: BinaryIO, member_size: int) -> Header:
    fixed = source.read(32)
    if len(fixed) != 32 or fixed[0] != 3:
        raise ValueError("DBF header is invalid")
    records = int.from_bytes(fixed[4:8], "little")
    header_length = int.from_bytes(fixed[8:10], "little")
    record_length = int.from_bytes(fixed[10:12], "little")
    if not 0 < records <= MAX_RECORDS or not 33 <= header_length <= 8193:
        raise ValueError("DBF dimensions are invalid")
    descriptor_bytes = source.read(header_length - 32)
    if len(descriptor_bytes) != header_length - 32 or descriptor_bytes[-1:] != b"\r":
        raise ValueError("DBF field descriptors are invalid")
    raw_descriptors = descriptor_bytes[:-1]
    if len(raw_descriptors) % 32 or len(raw_descriptors) // 32 > MAX_FIELDS:
        raise ValueError("DBF field descriptor count is invalid")
    fields: list[Field] = []
    field_names: set[str] = set()
    offset = 1
    for index in range(0, len(raw_descriptors), 32):
        descriptor = raw_descriptors[index : index + 32]
        try:
            name = descriptor[:11].split(b"\0", 1)[0].decode("ascii")
            field_type = chr(descriptor[11])
        except (UnicodeDecodeError, ValueError) as error:
            raise ValueError("DBF schema is invalid") from error
        width, decimals = descriptor[16], descriptor[17]
        normalized_name = name.upper()
        if not name or width == 0 or normalized_name in field_names:
            raise ValueError("DBF field definition is invalid")
        field_names.add(normalized_name)
        fields.append(Field(name, field_type, width, decimals, offset))
        offset += width
    if offset != record_length:
        raise ValueError("DBF record width disagrees with its schema")
    expected_size = header_length + records * record_length
    if member_size not in (expected_size, expected_size + 1):
        raise ValueError("DBF member size disagrees with its header")
    return Header(records, header_length, record_length, tuple(fields))


def _compare_streams(old: BinaryIO, new: BinaryIO, header: Header) -> dict:
    by_name = {field.name: field for field in header.fields}
    if any(
        name not in by_name or by_name[name].field_type != "C" for name in KEY_FIELDS
    ):
        raise ValueError("Required DBF identity fields are unavailable")
    changed = {field.name: 0 for field in header.fields}
    changed_records = deleted_marker_changes = 0
    for _ordinal in range(header.records):
        old_row = old.read(header.record_length)
        new_row = new.read(header.record_length)
        if len(old_row) != header.record_length or len(new_row) != header.record_length:
            raise ValueError("DBF record stream ended early")
        row_changed = old_row[0] != new_row[0]
        deleted_marker_changes += int(old_row[0] != new_row[0])
        for field in header.fields:
            start, end = field.start, field.start + field.width
            if old_row[start:end] != new_row[start:end]:
                changed[field.name] += 1
                row_changed = True
        changed_records += int(row_changed)
    return {
        "records": header.records,
        "changed_records": changed_records,
        "unchanged_records": header.records - changed_records,
        "deleted_marker_changes": deleted_marker_changes,
        "field_change_counts": {
            name: count for name, count in changed.items() if count
        },
    }


def _verify_geometry(old_zip: ZipFile, new_zip: ZipFile) -> dict[str, str]:
    digests: dict[str, str] = {}
    expanded_total = 0
    for name in GEOMETRY_MEMBERS:
        old_matches = [info for info in old_zip.infolist() if info.filename == name]
        new_matches = [info for info in new_zip.infolist() if info.filename == name]
        if len(old_matches) != 1 or len(new_matches) != 1:
            raise ValueError("Required parcel geometry member is missing or duplicated")
        old_info, new_info = old_matches[0], new_matches[0]
        infos = (old_info, new_info)
        if old_info.file_size != new_info.file_size:
            raise ValueError("Parcel geometry changed between releases")
        if any(
            info.is_dir()
            or info.flag_bits & 1
            or not 0 < info.file_size <= MAX_GEOMETRY_MEMBER_BYTES
            or info.compress_size <= 0
            or info.file_size / info.compress_size > 100
            for info in infos
        ):
            raise ValueError("Parcel geometry member violates the comparison contract")
        expanded_total += old_info.file_size + new_info.file_size
        if expanded_total > MAX_GEOMETRY_TOTAL_BYTES:
            raise ValueError("Parcel geometry exceeds the expanded-byte budget")
        with old_zip.open(old_info) as old, new_zip.open(new_info) as new:
            old_digest = _stream_digest(old, old_info.file_size)
            new_digest = _stream_digest(new, new_info.file_size)
        if old_digest != new_digest:
            raise ValueError("Parcel geometry changed between releases")
        digests[name] = old_digest
    return digests


def compare_releases(
    old_archive: Path,
    old_sha256: str,
    new_archive: Path,
    new_sha256: str,
) -> dict:
    """Return only aggregate differences for two hash-pinned parcel exports."""
    old_source, old_zip, old_info = _validated_member(old_archive, old_sha256)
    try:
        new_source, new_zip, new_info = _validated_member(new_archive, new_sha256)
        try:
            geometry_sha256 = _verify_geometry(old_zip, new_zip)
            with old_zip.open(old_info) as old, new_zip.open(new_info) as new:
                old_header = _read_header(old, old_info.file_size)
                new_header = _read_header(new, new_info.file_size)
                if old_header != new_header:
                    raise ValueError("DBF schema or dimensions changed")
                aggregate = _compare_streams(old, new, old_header)
                if old.read(2) not in (b"", b"\x1a") or new.read(2) not in (
                    b"",
                    b"\x1a",
                ):
                    raise ValueError("DBF end marker is invalid")
        finally:
            new_zip.close()
            new_source.close()
    finally:
        old_zip.close()
        old_source.close()
    return {
        "status": "verified",
        "old_archive_sha256": old_sha256,
        "new_archive_sha256": new_sha256,
        "schema_equal": True,
        "geometry_equal": True,
        "geometry_sha256": geometry_sha256,
        "key_fields": list(KEY_FIELDS),
        **aggregate,
    }


def _write_output(output: Path, rendered: str, inputs: tuple[Path, Path]) -> None:
    output_resolved = output.resolve(strict=False)
    input_resolved = {path.resolve(strict=True) for path in inputs}
    if output_resolved in input_resolved:
        raise ValueError("Output must not replace an input archive")
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists() and any(os.path.samefile(output, path) for path in inputs):
        raise ValueError("Output must not replace an input archive")
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=output.parent, delete=False
        ) as temporary:
            temporary.write(rendered)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_name = temporary.name
        os.replace(temporary_name, output)
        temporary_name = None
    finally:
        if temporary_name:
            Path(temporary_name).unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old", type=Path, required=True)
    parser.add_argument("--old-sha256", required=True)
    parser.add_argument("--new", type=Path, required=True)
    parser.add_argument("--new-sha256", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = compare_releases(args.old, args.old_sha256, args.new, args.new_sha256)
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        _write_output(args.output, rendered, (args.old, args.new))
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
