"""Read only HCPA's public DOR code table and emit a small aggregate audit.

This tool never opens parcel records or emits individual property information.
The reported labels are source observations, not verified sale eligibility rules.
"""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys
import tempfile
from zipfile import BadZipFile, ZipFile


MEMBER_NAME = "parcel_dor_names.dbf"
SELECTED_CODES = ("0100", "0400", "0800")
SOURCE_SPECIAL_CODES = frozenset(("HH", "NN"))
MAX_ARCHIVE_BYTES = 500_000_000
MAX_MEMBER_BYTES = 1_000_000
MAX_ROWS = 10_000
SHA256_PATTERN = re.compile(r"[0-9a-fA-F]{64}\Z")


def _hash_stream(source) -> str:
    digest = sha256()
    for chunk in iter(lambda: source.read(1024 * 1024), b""):
        digest.update(chunk)
    return digest.hexdigest()


def _code_table_member(zipped: ZipFile):
    matches = [
        info
        for info in zipped.infolist()
        if PurePosixPath(info.filename).name.lower() == MEMBER_NAME
    ]
    if len(matches) != 1:
        raise ValueError("Expected exactly one parcel_dor_names.dbf member")
    info = matches[0]
    parts = PurePosixPath(info.filename).parts
    if (
        info.is_dir()
        or info.filename.startswith("/")
        or ".." in parts
        or "\\" in info.filename
        or not 0 < info.file_size <= MAX_MEMBER_BYTES
        or not 0 < info.compress_size <= MAX_MEMBER_BYTES
        or info.file_size / info.compress_size > 100
    ):
        raise ValueError("Code-table ZIP member violates the audit contract")
    return info


def _parse_fields(data: bytes, header_length: int, row_length: int) -> list[dict]:
    descriptors = data[32:header_length]
    if len(descriptors) != 65 or descriptors[-1] != 13:
        raise ValueError("DBF field descriptors or terminator are invalid")
    fields = []
    offset = 1
    for index in range(0, 64, 32):
        descriptor = descriptors[index : index + 32]
        try:
            name = descriptor[:11].split(b"\0", 1)[0].decode("ascii")
        except UnicodeDecodeError as error:
            raise ValueError("DBF field name is not ASCII") from error
        field_type = chr(descriptor[11])
        width = descriptor[16]
        if (
            field_type != "C"
            or width == 0
            or descriptor[17] != 0
            or name not in ("DORCODE", "DORDESCR")
        ):
            raise ValueError("DBF code-table field definition is invalid")
        fields.append({"name": name, "type": field_type, "width": width})
        offset += width
    if (
        [field["name"] for field in fields] != ["DORCODE", "DORDESCR"]
        or fields[0]["width"] != 4
        or fields[1]["width"] > 200
        or offset != row_length
    ):
        raise ValueError("DBF field order or record width is invalid")
    return fields


def _parse_dbf(data: bytes) -> dict:
    if len(data) < 98 or data[0] != 3:
        raise ValueError("DBF dBASE III header is invalid")
    row_count = int.from_bytes(data[4:8], "little")
    header_length = int.from_bytes(data[8:10], "little")
    row_length = int.from_bytes(data[10:12], "little")
    if not 0 < row_count <= MAX_ROWS or header_length != 97:
        raise ValueError("DBF header dimensions are invalid")
    if len(data) != header_length + row_count * row_length + 1:
        raise ValueError("DBF size disagrees with header record count")
    if data[-1:] != b"\x1a":
        raise ValueError("DBF end marker is invalid")
    fields = _parse_fields(data, header_length, row_length)
    labels: dict[str, str] = {}
    deleted = 0
    for ordinal in range(row_count):
        start = header_length + ordinal * row_length
        row = data[start : start + row_length]
        if row[:1] == b"*":
            deleted += 1
            continue
        if row[:1] != b" ":
            raise ValueError("DBF record marker is invalid")
        try:
            code = row[1:5].decode("ascii").strip()
            label = row[5:].decode("cp1252").strip()
        except UnicodeDecodeError as error:
            raise ValueError("DBF code-table text is undecodable") from error
        if not (
            (len(code) == 4 and code.isascii() and code.isdigit())
            or code in SOURCE_SPECIAL_CODES
        ):
            raise ValueError("DBF active code is not an expected source code")
        if not label or not label.isprintable():
            raise ValueError("DBF active label is blank or nonprintable")
        if code in labels:
            raise ValueError("Duplicate active code in DBF code table")
        labels[code] = label
    return {
        "dbf_version": "dBASE III",
        "header_record_count": row_count,
        "active_rows": row_count - deleted,
        "deleted_rows": deleted,
        "fields": fields,
        "selected_code_labels": {code: labels.get(code) for code in SELECTED_CODES},
    }


def audit_code_table(archive: Path, expected_archive_sha256: str) -> dict:
    """Validate a pinned ZIP and summarize only its DOR code-name DBF member."""
    if not SHA256_PATTERN.fullmatch(expected_archive_sha256):
        raise ValueError("Archive SHA-256 format must be 64 hex digits")
    with archive.open("rb") as source:
        if os.fstat(source.fileno()).st_size > MAX_ARCHIVE_BYTES:
            raise ValueError("Archive size violates the audit contract")
        actual_hash = _hash_stream(source)
        if actual_hash != expected_archive_sha256.lower():
            raise ValueError("Archive SHA-256 mismatch")
        source.seek(0)
        with ZipFile(source) as zipped:
            info = _code_table_member(zipped)
            with zipped.open(info) as member:
                data = member.read(MAX_MEMBER_BYTES + 1)
            if len(data) != info.file_size:
                raise ValueError("DBF size differs from ZIP member metadata")
        source.seek(0)
        if _hash_stream(source) != actual_hash:
            raise ValueError("Archive SHA-256 changed during the audit")
    return {
        "source_archive_sha256": actual_hash,
        "member": info.filename,
        "dbf_sha256": sha256(data).hexdigest(),
        "dbf_bytes": len(data),
        **_parse_dbf(data),
    }


def _write_json_once(output: Path, report: dict) -> None:
    if not output.parent.is_dir():
        raise ValueError("Output parent directory does not exist")
    content = (json.dumps(report, indent=2, sort_keys=True) + "\n").encode("utf-8")
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{output.name}-",
            suffix=".tmp",
            dir=output.parent,
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.link(temporary_path, output)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--archive-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    options = parser.parse_args(argv)
    try:
        report = audit_code_table(options.archive, options.archive_sha256)
        _write_json_once(options.output, report)
    except (BadZipFile, FileExistsError, OSError, ValueError) as error:
        print(f"Code-table audit failed: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
