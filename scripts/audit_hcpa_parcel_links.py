"""Audit links between frozen HCPA sale sample and a *current* parcel DBF.

Only aggregate counts may leave the private raw-data directory. A current
parcel record is never a certified historical feature or sale eligibility rule.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import tempfile
from zipfile import BadZipFile, ZipFile


PRIVATE_ROOT = Path(__file__).resolve().parents[1] / "data" / "raw" / "hcpa"
MAX_ARCHIVE_BYTES = 500_000_000
MAX_MEMBER_BYTES = 1_100_000_000
MAX_SAMPLE_BYTES = 10_000_000
MAX_PARCEL_ROWS = 1_000_000
MAX_SAMPLE_ROWS = 10_000
SHA256_PATTERN = re.compile(r"[0-9a-fA-F]{64}\Z")
SELECTED_FIELDS = (
    "PIN",
    "FOLIO",
    "DOR_C",
    "tUNITS",
    "tBLDGS",
    "HEAT_AR",
    "SALE1_DOC",
    "SALE2_DOC",
    "SALE3_DOC",
)
REQUIRED_FIELDS = frozenset(SELECTED_FIELDS[:6])
SAMPLE_FIELDS = ("PIN", "FOLIO", "DOR_CODE", "DOC_NUM")
REDACTED_FOLIOS = frozenset(("CONFID", "[FOLIO = CONFID]"))


def _hash_stream(stream) -> str:
    digest = sha256()
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        digest.update(chunk)
    return digest.hexdigest()


def _private_path(path: Path) -> None:
    root = PRIVATE_ROOT.resolve(strict=True)
    if PRIVATE_ROOT.is_symlink() or os.path.normcase(
        str(PRIVATE_ROOT.absolute())
    ) != os.path.normcase(str(root)):
        raise ValueError("Private source root redirects to another path")
    if not path.resolve().is_relative_to(root):
        raise ValueError("Row-level input or output must remain private")
    if path.exists() and (path.is_symlink() or path.stat().st_nlink != 1):
        raise ValueError("Private row-level file may not be linked")


def _revalidate_open_file(path: Path, source) -> None:
    """Detect path replacement around reads on the trusted local workspace.

    Windows path APIs cannot eliminate a malicious concurrent directory-swap
    race. The audit assumes no adversarial local process can rename PRIVATE_ROOT.
    """
    _private_path(path)
    opened, named = os.fstat(source.fileno()), path.stat()
    if (opened.st_dev, opened.st_ino) != (named.st_dev, named.st_ino):
        raise ValueError("Private input path changed while open")


def _pinned_bytes(path: Path, expected_sha: str, limit: int) -> bytes:
    if not SHA256_PATTERN.fullmatch(expected_sha):
        raise ValueError("Expected SHA-256 must be 64 hex digits")
    _private_path(path)
    with path.open("rb") as source:
        _revalidate_open_file(path, source)
        if (
            not stat.S_ISREG(os.fstat(source.fileno()).st_mode)
            or os.fstat(source.fileno()).st_size > limit
        ):
            raise ValueError(
                "Private input exceeds the audit size or file-type contract"
            )
        data = source.read(limit + 1)
        _revalidate_open_file(path, source)
    if sha256(data).hexdigest() != expected_sha.lower():
        raise ValueError("Private input SHA-256 mismatch")
    return data


def _jsonl_rows(data: bytes, label: str) -> list[dict]:
    try:
        rows = [json.loads(line) for line in data.decode("utf-8").splitlines()]
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"Malformed private {label} JSONL") from error
    if (
        not rows
        or len(rows) > MAX_SAMPLE_ROWS
        or any(not isinstance(row, dict) for row in rows)
    ):
        raise ValueError(f"Private {label} row count or shape is invalid")
    return rows


def _load_sample(data: bytes, expected_rows: int) -> list[dict]:
    rows = _jsonl_rows(data, "sample")
    ordinals = set()
    for row in rows:
        ordinal = row.get("record_ordinal")
        if (
            type(ordinal) is not int
            or ordinal < 1
            or ordinal in ordinals
            or any(not isinstance(row.get(field), str) for field in SAMPLE_FIELDS)
        ):
            raise ValueError("Malformed or duplicate private sample row")
        ordinals.add(ordinal)
    if len(rows) != expected_rows:
        raise ValueError("Private sample row count differs from the audit contract")
    return rows


def _repeated_ordinals(data: bytes, sample_ordinals: set[int]) -> set[int]:
    rows = _jsonl_rows(data, "document flags")
    flags = {}
    for row in rows:
        ordinal, size = row.get("record_ordinal"), row.get("group_size")
        if (
            type(ordinal) is not int
            or ordinal not in sample_ordinals
            or ordinal in flags
            or type(size) is not int
            or size < 0
        ):
            raise ValueError("Document flags do not match the private sample")
        flags[ordinal] = size
    if flags.keys() != sample_ordinals:
        raise ValueError("Document flags omit a sample row")
    return {ordinal for ordinal, size in flags.items() if size > 1}


def _member(zipped: ZipFile):
    if (
        len(zipped.infolist()) > 100
        or sum(len(info.filename) for info in zipped.infolist()) > 10_000
    ):
        raise ValueError("ZIP has too many entries or excessive entry names")
    matches = [
        info
        for info in zipped.infolist()
        if PurePosixPath(info.filename).name.lower() == "parcel.dbf"
    ]
    if len(matches) != 1:
        raise ValueError("Expected exactly one parcel.dbf ZIP member")
    info = matches[0]
    if (
        info.is_dir()
        or info.filename.startswith("/")
        or ".." in PurePosixPath(info.filename).parts
        or "\\" in info.filename
        or not 0 < info.file_size <= MAX_MEMBER_BYTES
        or not 0 < info.compress_size <= MAX_ARCHIVE_BYTES
        or info.file_size / info.compress_size > 100
    ):
        raise ValueError("Parcel DBF member violates size or path contract")
    return info


def _header(
    source, member_bytes: int
) -> tuple[int, int, dict[str, tuple[int, int, str]]]:
    header = source.read(32)
    if len(header) != 32 or header[0] != 3:
        raise ValueError("Parcel DBF must be dBASE III")
    rows = int.from_bytes(header[4:8], "little")
    header_bytes = int.from_bytes(header[8:10], "little")
    row_bytes = int.from_bytes(header[10:12], "little")
    if (
        not 0 < rows <= MAX_PARCEL_ROWS
        or not 33 <= header_bytes <= 4096
        or not 1 < row_bytes <= 4096
        or header_bytes + rows * row_bytes + 1 != member_bytes
    ):
        raise ValueError("Parcel DBF row count or size is inconsistent")
    descriptors = source.read(header_bytes - 32)
    if (
        len(descriptors) != header_bytes - 32
        or descriptors[-1:] != b"\x0d"
        or (len(descriptors) - 1) % 32
    ):
        raise ValueError("Parcel DBF field terminator is invalid")
    fields: dict[str, tuple[int, int, str]] = {}
    offset = 1
    for index in range(0, len(descriptors) - 1, 32):
        descriptor = descriptors[index : index + 32]
        try:
            name = descriptor[:11].split(b"\0", 1)[0].decode("ascii")
            field_type = chr(descriptor[11])
        except UnicodeDecodeError as error:
            raise ValueError("Parcel DBF field descriptor is invalid") from error
        width = descriptor[16]
        if not name or name in fields or width == 0:
            raise ValueError("Parcel DBF field descriptor is invalid")
        fields[name] = (offset, width, field_type)
        offset += width
    if offset != row_bytes or not REQUIRED_FIELDS.issubset(fields):
        raise ValueError("Parcel DBF lacks required fields or has invalid row width")
    for name in SELECTED_FIELDS:
        if name in fields and fields[name][2] not in (
            {"C"}
            if name in ("PIN", "FOLIO", "DOR_C") or name.endswith("_DOC")
            else {"F", "N"}
        ):
            raise ValueError("Parcel DBF selected field has unexpected type")
    return rows, row_bytes, fields


def _value(record: bytes, fields: dict, name: str) -> str:
    if name not in fields:
        return ""
    offset, width, _ = fields[name]
    try:
        return record[offset : offset + width].decode("ascii").strip()
    except UnicodeDecodeError as error:
        raise ValueError("Parcel DBF selected field is not ASCII") from error


def _usable_folio(raw: str) -> bool:
    return bool(raw) and raw.upper() not in REDACTED_FOLIOS


def _clue(raw: str) -> str:
    if not raw:
        return "unknown"
    try:
        value = Decimal(raw)
    except InvalidOperation:
        return "invalid"
    if not value.is_finite() or value < 0 or value != value.to_integral_value():
        return "invalid"
    return "zero" if value == 0 else "one" if value == 1 else "multiple"


def _area_clue(raw: str) -> str:
    if not raw:
        return "unknown"
    try:
        value = Decimal(raw)
    except InvalidOperation:
        return "invalid"
    if not value.is_finite() or value < 0:
        return "invalid"
    return "zero" if value == 0 else "positive"


def _scan(
    source, member_bytes: int, samples: list[dict]
) -> tuple[dict, dict[int, dict]]:
    rows, row_bytes, fields = _header(source, member_bytes)
    by_pin = defaultdict(set)
    by_folio = defaultdict(set)
    for sample in samples:
        ordinal = sample["record_ordinal"]
        if sample["PIN"]:
            by_pin[sample["PIN"]].add(ordinal)
        if _usable_folio(sample["FOLIO"]):
            by_folio[sample["FOLIO"]].add(ordinal)
    matches = {
        sample["record_ordinal"]: {
            "both": 0,
            "pin_only": 0,
            "folio_only": 0,
            "candidate": None,
        }
        for sample in samples
    }
    seen_keys = set()
    counts = Counter()
    for _ in range(rows):
        record = source.read(row_bytes)
        if len(record) != row_bytes:
            raise ValueError("Parcel DBF ended before declared row count")
        if record[:1] == b"*":
            counts["deleted_rows"] += 1
            continue
        if record[:1] != b" ":
            raise ValueError("Parcel DBF record marker is invalid")
        counts["active_rows"] += 1
        pin, folio = _value(record, fields, "PIN"), _value(record, fields, "FOLIO")
        if not pin or not _usable_folio(folio):
            counts["incomplete_key_rows"] += 1
        else:
            key = (pin, folio)
            if key in seen_keys:
                counts["duplicate_two_key_rows"] += 1
            else:
                seen_keys.add(key)
        pin_ordinals = by_pin.get(pin, set()) if pin else set()
        folio_ordinals = by_folio.get(folio, set()) if _usable_folio(folio) else set()
        for ordinal in pin_ordinals | folio_ordinals:
            match = matches[ordinal]
            if ordinal in pin_ordinals and ordinal in folio_ordinals:
                match["both"] += 1
                if match["both"] == 1:
                    match["candidate"] = {
                        "dor": _value(record, fields, "DOR_C"),
                        "units": _clue(_value(record, fields, "tUNITS")),
                        "buildings": _clue(_value(record, fields, "tBLDGS")),
                        "heated_area": _area_clue(_value(record, fields, "HEAT_AR")),
                        "docs": tuple(
                            _value(record, fields, f"SALE{slot}_DOC")
                            for slot in (1, 2, 3)
                        ),
                    }
                else:
                    match["candidate"] = None
            elif ordinal in pin_ordinals:
                match["pin_only"] += 1
            else:
                match["folio_only"] += 1
    if (
        source.read(2) != b"\x1a"
        or counts["active_rows"] + counts["deleted_rows"] != rows
    ):
        raise ValueError("Parcel DBF end marker or row count is inconsistent")
    return {
        "header_record_count": rows,
        "active_rows": counts["active_rows"],
        "deleted_rows": counts["deleted_rows"],
        "incomplete_key_rows": counts["incomplete_key_rows"],
        "duplicate_two_key_rows": counts["duplicate_two_key_rows"],
    }, matches


def _summarize(
    samples: list[dict], repeated: set[int], matches: dict[int, dict]
) -> tuple[dict, list[dict]]:
    all_flags = []
    for sample in samples:
        ordinal = sample["record_ordinal"]
        match = matches[ordinal]
        complete = bool(sample["PIN"]) and _usable_folio(sample["FOLIO"])
        has_pin_lead = match["pin_only"] > 0
        has_folio_lead = match["folio_only"] > 0
        if not complete:
            status = "incomplete_key"
        elif match["both"] > 1:
            status = "ambiguous_multiple"
        elif (has_pin_lead and has_folio_lead) or (
            match["both"] == 1 and (has_pin_lead or has_folio_lead)
        ):
            status = "identifier_conflict"
        elif match["both"] == 1:
            status = "unique_current_candidate"
        elif has_pin_lead:
            status = "pin_only_lead"
        elif has_folio_lead:
            status = "folio_only_lead"
        else:
            status = "no_match"
        flag = {
            "record_ordinal": ordinal,
            "status": status,
            "two_key_candidates": match["both"],
            "pin_only_candidates": match["pin_only"],
            "folio_only_candidates": match["folio_only"],
            "repeated_instrument": ordinal in repeated,
        }
        if status == "unique_current_candidate":
            candidate = match["candidate"]
            flag["dor_status"] = (
                "missing"
                if not sample["DOR_CODE"] or not candidate["dor"]
                else "agree"
                if sample["DOR_CODE"] == candidate["dor"]
                else "disagree"
            )
            flag["unit_clue"] = candidate["units"]
            flag["building_clue"] = candidate["buildings"]
            flag["heated_area_clue"] = candidate["heated_area"]
            flag["sale_document_match"] = (
                "unknown"
                if not sample["DOC_NUM"] or not any(candidate["docs"])
                else "yes"
                if sample["DOC_NUM"] in candidate["docs"]
                else "no"
            )
        all_flags.append(flag)

    def cohort(flags: list[dict]) -> dict:
        def cardinality(field: str) -> dict[str, int]:
            bins = Counter(
                "zero" if flag[field] == 0 else "one" if flag[field] == 1 else "many"
                for flag in flags
            )
            return {key: bins[key] for key in ("zero", "one", "many")}

        result = {
            "rows": len(flags),
            "two_key_matches": cardinality("two_key_candidates"),
            "pin_only_candidates": cardinality("pin_only_candidates"),
            "folio_only_candidates": cardinality("folio_only_candidates"),
            "incomplete_key_rows": sum(
                flag["status"] == "incomplete_key" for flag in flags
            ),
            "identifier_conflict_rows": sum(
                flag["status"] == "identifier_conflict" for flag in flags
            ),
            "pin_only_status_rows": sum(
                flag["status"] == "pin_only_lead" for flag in flags
            ),
            "folio_only_status_rows": sum(
                flag["status"] == "folio_only_lead" for flag in flags
            ),
            "ambiguous_multiple_rows": sum(
                flag["status"] == "ambiguous_multiple" for flag in flags
            ),
            "unique_current_candidates": sum(
                flag["status"] == "unique_current_candidate" for flag in flags
            ),
            "pin_only_lead_rows": sum(
                flag["pin_only_candidates"] > 0 for flag in flags
            ),
            "folio_only_lead_rows": sum(
                flag["folio_only_candidates"] > 0 for flag in flags
            ),
        }
        for key, output, labels in (
            ("dor_status", "dor_code", ("agree", "disagree", "missing")),
            (
                "unit_clue",
                "unit_clues",
                ("zero", "one", "multiple", "unknown", "invalid"),
            ),
            (
                "building_clue",
                "building_clues",
                ("zero", "one", "multiple", "unknown", "invalid"),
            ),
            (
                "heated_area_clue",
                "heated_area_clues",
                ("zero", "positive", "unknown", "invalid"),
            ),
            ("sale_document_match", "sale_document_match", ("yes", "no", "unknown")),
        ):
            counts = Counter(flag[key] for flag in flags if key in flag)
            result[output] = {label: counts[label] for label in labels}
        return result

    return {
        "sample": cohort(all_flags),
        "repeated_instrument_sample": cohort(
            [flag for flag in all_flags if flag["repeated_instrument"]]
        ),
    }, all_flags


def _write_once(path: Path, content: bytes, *, private: bool = False) -> None:
    if not path.parent.is_dir() or path.exists():
        raise FileExistsError("Audit output exists or parent directory is absent")
    if private:
        _private_path(path)
        if path.parent.resolve() != PRIVATE_ROOT.resolve(strict=True):
            raise ValueError("Private output must be directly in the private root")
        parent_identity = path.parent.stat()
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            "wb", dir=path.parent, prefix=f".{path.name}-", suffix=".tmp", delete=False
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.link(temporary_path, path)
        if private:
            temporary_path.unlink()
            temporary_path = None
            _private_path(path)
            after = path.parent.stat()
            if (parent_identity.st_dev, parent_identity.st_ino) != (
                after.st_dev,
                after.st_ino,
            ):
                raise ValueError("Private output parent changed while writing")
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def audit_parcel_links(
    archive: Path,
    sample: Path,
    document_flags: Path,
    private_flags: Path,
    aggregate: Path,
    expected_archive_sha256: str,
    expected_sample_sha256: str,
    expected_document_flags_sha256: str,
    *,
    expected_sample_rows: int = 200,
) -> dict:
    """Validate pinned sources and emit private flags plus safe aggregate counts."""
    for path in (archive, sample, document_flags, private_flags):
        _private_path(path)
    if (
        len(
            {
                path.resolve()
                for path in (archive, sample, document_flags, private_flags, aggregate)
            }
        )
        != 5
    ):
        raise ValueError("Source and output paths must differ")
    if private_flags.exists() or aggregate.exists():
        raise FileExistsError("Audit output exists; refusing overwrite")
    if not SHA256_PATTERN.fullmatch(expected_archive_sha256):
        raise ValueError("Archive SHA-256 format must be 64 hex digits")
    samples = _load_sample(
        _pinned_bytes(sample, expected_sample_sha256, MAX_SAMPLE_BYTES),
        expected_sample_rows,
    )
    repeated = _repeated_ordinals(
        _pinned_bytes(document_flags, expected_document_flags_sha256, MAX_SAMPLE_BYTES),
        {row["record_ordinal"] for row in samples},
    )
    with archive.open("rb") as source:
        _revalidate_open_file(archive, source)
        meta = os.fstat(source.fileno())
        if not stat.S_ISREG(meta.st_mode) or meta.st_size > MAX_ARCHIVE_BYTES:
            raise ValueError("Archive exceeds size or file-type contract")
        archive_hash = _hash_stream(source)
        _revalidate_open_file(archive, source)
        if archive_hash != expected_archive_sha256.lower():
            raise ValueError("Archive SHA-256 mismatch")
        source.seek(0)
        with ZipFile(source) as zipped:
            info = _member(zipped)
            with zipped.open(info) as member:
                parcel, matches = _scan(member, info.file_size, samples)
        source.seek(0)
        if _hash_stream(source) != archive_hash:
            raise ValueError("Archive SHA-256 changed during audit")
        _revalidate_open_file(archive, source)
    cohorts, flags = _summarize(samples, repeated, matches)
    report = {
        "source_archive_sha256": archive_hash,
        "sample_sha256": expected_sample_sha256.lower(),
        "document_flags_sha256": expected_document_flags_sha256.lower(),
        "member": info.filename,
        "member_crc32": f"{info.CRC:08x}",
        "member_uncompressed_bytes": info.file_size,
        "parcel": parcel,
        **cohorts,
        "interpretation": "Current parcel linkage leads only. No historical as-of, transaction-scope, sale eligibility, price, rights or population-prevalence inference.",
    }
    private_bytes = "".join(
        json.dumps(flag, sort_keys=True) + "\n" for flag in flags
    ).encode("utf-8")
    public_bytes = (json.dumps(report, indent=2, sort_keys=True) + "\n").encode("utf-8")
    _write_once(private_flags, private_bytes, private=True)
    try:
        _write_once(aggregate, public_bytes)
    except (FileExistsError, OSError):
        private_flags.unlink(missing_ok=True)
        raise
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("archive", "sample", "document-flags", "private-flags", "aggregate"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    for name in ("archive-sha256", "sample-sha256", "document-flags-sha256"):
        parser.add_argument(f"--{name}", required=True)
    options = parser.parse_args(argv)
    try:
        audit_parcel_links(
            options.archive,
            options.sample,
            options.document_flags,
            options.private_flags,
            options.aggregate,
            options.archive_sha256,
            options.sample_sha256,
            options.document_flags_sha256,
        )
    except (BadZipFile, FileExistsError, OSError, ValueError) as error:
        print(f"Parcel-link audit failed: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
