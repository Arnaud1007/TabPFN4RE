"""Validate a frozen HCPA PIN-format hypothesis on a disjoint private sample.

This is an identity-format experiment, not a historical feature or eligibility join.
Only aggregate counts may leave ``data/raw/hcpa``.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import date
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
SHA256_PATTERN = re.compile(r"[0-9a-fA-F]{64}\Z")
FORMATTED_PIN = re.compile(
    r"[A-Z0-9]-[A-Z0-9]{2}-[A-Z0-9]{2}-[A-Z0-9]{2}-"
    r"[A-Z0-9]{3}-[A-Z0-9]{6}-[A-Z0-9]{5}\.[A-Z0-9]\Z",
    re.ASCII,
)
REDACTED_FOLIOS = frozenset(("CONFID", "[FOLIO = CONFID]"))
MAX_ARCHIVE_BYTES = 500_000_000
MAX_MEMBER_BYTES = 1_100_000_000
MAX_SAMPLE_BYTES = 10_000_000
MAX_PARCEL_ROWS = 1_000_000
SAMPLE_FIELDS = ("PIN", "FOLIO", "S_DATE", "QU")
FROZEN_OLD_SAMPLE_SHA256 = (
    "2f26728c37f8218d1bb79ee75e4082fb918665eb2cb4cc287feba7f6250aaec9"
)
FROZEN_VALIDATION_SAMPLE_SHA256 = (
    "35c52bc969980cb0e1cabb698a70754825774f0ddc09e6b1417cdc21dc1ad3f9"
)


def transform_pin(formatted: str) -> str | None:
    """Return the frozen 22-character candidate only for the exact ASCII form."""
    if not isinstance(formatted, str) or not FORMATTED_PIN.fullmatch(formatted):
        return None
    alnum = formatted.replace("-", "").replace(".", "")
    return alnum[5:7] + alnum[3:5] + alnum[1:3] + alnum[7:] + alnum[0]


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
    _private_path(path)
    opened, named = os.fstat(source.fileno()), path.stat()
    if (opened.st_dev, opened.st_ino) != (named.st_dev, named.st_ino):
        raise ValueError("Private input path changed while open")


def _hash_stream(source) -> str:
    digest = sha256()
    for chunk in iter(lambda: source.read(1024 * 1024), b""):
        digest.update(chunk)
    return digest.hexdigest()


def _pinned_bytes(path: Path, expected_hash: str) -> bytes:
    if not SHA256_PATTERN.fullmatch(expected_hash):
        raise ValueError("SHA-256 must contain 64 hex digits")
    _private_path(path)
    with path.open("rb") as source:
        _revalidate_open_file(path, source)
        metadata = os.fstat(source.fileno())
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_SAMPLE_BYTES:
            raise ValueError("Private sample exceeds size or file-type contract")
        data = source.read(MAX_SAMPLE_BYTES + 1)
        _revalidate_open_file(path, source)
    if sha256(data).hexdigest() != expected_hash.lower():
        raise ValueError("Private sample SHA-256 mismatch")
    return data


def _jsonl(data: bytes, label: str) -> list[dict]:
    def unique_keys(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Private JSONL has a duplicate JSON key")
            result[key] = value
        return result

    try:
        rows = [
            json.loads(line, object_pairs_hook=unique_keys)
            for line in data.decode("utf-8").splitlines()
        ]
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"Malformed {label} JSONL") from error
    if not rows or any(not isinstance(row, dict) for row in rows):
        raise ValueError(f"Malformed {label} JSONL row")
    return rows


def _band(raw: str) -> str:
    try:
        parsed = date.fromisoformat(f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}")
    except ValueError as error:
        raise ValueError("Validation sample has an invalid sale date") from error
    if len(raw) != 8 or not raw.isascii() or not raw.isdigit() or parsed.year > 2026:
        raise ValueError("Validation sample has an invalid sale date")
    if parsed.year < 2000:
        return "before_2000"
    if parsed.year <= 2009:
        return "2000_2009"
    if parsed.year <= 2019:
        return "2010_2019"
    if parsed.year <= 2023:
        return "2020_2023"
    return "2024_2026"


def _load_samples(
    data: bytes, old_data: bytes, expected_rows: int, expected_old_rows: int
) -> tuple[list[dict], dict[str, int]]:
    rows = _jsonl(data, "validation sample")
    old_rows = _jsonl(old_data, "frozen audit sample")
    if len(rows) != expected_rows or len(old_rows) != expected_old_rows:
        raise ValueError("Private sample row count differs from frozen contract")
    ordinals, old_ordinals = set(), set()
    cells = Counter()
    for row in old_rows:
        ordinal = row.get("record_ordinal")
        if type(ordinal) is not int or ordinal < 1 or ordinal in old_ordinals:
            raise ValueError("Frozen audit sample has duplicate or invalid ordinals")
        old_ordinals.add(ordinal)
    for row in rows:
        ordinal = row.get("record_ordinal")
        if type(ordinal) is not int or ordinal < 1 or ordinal in ordinals:
            raise ValueError("Validation sample has duplicate or invalid ordinals")
        ordinals.add(ordinal)
        if any(not isinstance(row.get(field), str) for field in SAMPLE_FIELDS):
            raise ValueError("Validation sample lacks required identifier/date fields")
        if set(row) != {"record_ordinal", *SAMPLE_FIELDS}:
            raise ValueError("Validation sample contains unexpected fields")
        if any(
            not value.isascii() or any(ord(char) < 32 for char in value)
            for value in (row["PIN"], row["FOLIO"])
        ):
            raise ValueError("Validation sample identifiers must be printable ASCII")
        if len(row["PIN"]) > 29 or len(row["FOLIO"]) > 32:
            raise ValueError("Validation sample identifier exceeds field contract")
        if row["QU"] not in ("Q", "U"):
            raise ValueError("Validation sample QU is outside the frozen cells")
        cells[f"{_band(row['S_DATE'])}_{row['QU']}"] += 1
    if ordinals & old_ordinals:
        raise ValueError("Validation sample overlaps frozen 200-row audit sample")
    if expected_rows == 1000 and (
        len(cells) != 10 or any(count != 100 for count in cells.values())
    ):
        raise ValueError("Validation sample does not contain 100 rows per frozen cell")
    return rows, dict(sorted(cells.items()))


def _member(zipped: ZipFile, expected_basename: str):
    infos = zipped.infolist()
    if len(infos) > 100 or sum(len(info.filename) for info in infos) > 10_000:
        raise ValueError("ZIP entry count or names exceed audit limits")
    matches = [
        info
        for info in infos
        if PurePosixPath(info.filename).name.lower() == expected_basename.lower()
    ]
    if len(matches) != 1:
        raise ValueError("ZIP lacks one expected parcel DBF member")
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
        raise ValueError("Parcel DBF member violates ZIP path or size contract")
    return info


def _header(source, member_bytes: int, required: dict[str, int]):
    header = source.read(32)
    if len(header) != 32 or header[0] != 3:
        raise ValueError("Parcel DBF must be dBASE III")
    rows = int.from_bytes(header[4:8], "little")
    header_bytes = int.from_bytes(header[8:10], "little")
    record_bytes = int.from_bytes(header[10:12], "little")
    if (
        rows > MAX_PARCEL_ROWS
        or not 33 <= header_bytes <= 4096
        or not 1 < record_bytes <= 4096
        or header_bytes + rows * record_bytes + 1 != member_bytes
    ):
        raise ValueError("Parcel DBF schema size or record count is invalid")
    descriptors = source.read(header_bytes - 32)
    if (
        len(descriptors) != header_bytes - 32
        or descriptors[-1:] != b"\x0d"
        or (len(descriptors) - 1) % 32
    ):
        raise ValueError("Parcel DBF schema descriptors are malformed")
    fields = {}
    offset = 1
    for index in range(0, len(descriptors) - 1, 32):
        descriptor = descriptors[index : index + 32]
        try:
            name = descriptor[:11].split(b"\0", 1)[0].decode("ascii")
        except UnicodeDecodeError as error:
            raise ValueError("Parcel DBF schema has a non-ASCII field name") from error
        width = descriptor[16]
        field_type = chr(descriptor[11])
        if not name or name in fields or not width:
            raise ValueError("Parcel DBF schema has duplicate or empty fields")
        fields[name] = (offset, width, field_type)
        offset += width
    if offset != record_bytes or any(
        fields.get(name, (None, None, None))[1:] != (width, "C")
        for name, width in required.items()
    ):
        raise ValueError(
            "Parcel DBF schema differs from selected PIN/FOLIO/STRAP contract"
        )
    schema_sha256 = sha256(
        json.dumps(
            {"record_bytes": record_bytes, "fields": fields}, sort_keys=True
        ).encode("ascii")
    ).hexdigest()
    return rows, record_bytes, fields, schema_sha256


def _value(record: bytes, fields: dict, name: str) -> str:
    offset, width, _ = fields[name]
    try:
        return record[offset : offset + width].decode("ascii").strip()
    except UnicodeDecodeError as error:
        raise ValueError("Parcel identifier is not ASCII") from error


def _usable_folio(value: str) -> bool:
    return bool(value) and value.upper() not in REDACTED_FOLIOS


def _read_archive(
    path: Path,
    expected_hash: str,
    basename: str,
    required: dict[str, int],
    query_pins: set[str],
    query_folios: set[str],
):
    if not SHA256_PATTERN.fullmatch(expected_hash):
        raise ValueError("SHA-256 must contain 64 hex digits")
    _private_path(path)
    with path.open("rb") as source:
        _revalidate_open_file(path, source)
        metadata = os.fstat(source.fileno())
        if (
            not stat.S_ISREG(metadata.st_mode)
            or not 0 < metadata.st_size <= MAX_ARCHIVE_BYTES
        ):
            raise ValueError("Archive exceeds size or file-type contract")
        digest = _hash_stream(source)
        _revalidate_open_file(path, source)
        if digest != expected_hash.lower():
            raise ValueError("Archive SHA-256 mismatch")
        source.seek(0)
        with ZipFile(source) as zipped:
            info = _member(zipped, basename)
            by_pin, by_folio = defaultdict(list), defaultdict(list)
            with zipped.open(info) as member:
                row_count, record_bytes, fields, schema_sha256 = _header(
                    member, info.file_size, required
                )
                active = deleted = 0
                for ordinal in range(1, row_count + 1):
                    record = member.read(record_bytes)
                    if len(record) != record_bytes:
                        raise ValueError(
                            "Parcel DBF ended before declared record count"
                        )
                    if record[:1] == b"*":
                        deleted += 1
                        continue
                    if record[:1] != b" ":
                        raise ValueError("Parcel DBF record marker is invalid")
                    active += 1
                    pin, folio = (
                        _value(record, fields, "PIN"),
                        _value(record, fields, "FOLIO"),
                    )
                    if pin in query_pins or folio in query_folios:
                        row = (
                            ordinal,
                            pin,
                            folio,
                            _value(record, fields, "STRAP")
                            if "STRAP" in required
                            else "",
                        )
                        if pin in query_pins:
                            by_pin[pin].append(row)
                        if folio in query_folios:
                            by_folio[folio].append(row)
                if member.read(2) != b"\x1a":
                    raise ValueError("Parcel DBF end marker is invalid")
        source.seek(0)
        if _hash_stream(source) != digest:
            raise ValueError("Archive SHA-256 changed during audit")
        _revalidate_open_file(path, source)
    return (
        {
            "archive_sha256": digest,
            "member": basename,
            "member_crc32": f"{info.CRC:08x}",
            "schema_sha256": schema_sha256,
            "header_rows": row_count,
            "active_rows": active,
            "deleted_rows": deleted,
        },
        by_pin,
        by_folio,
    )


def _match(pin: str, folio: str, by_pin: dict, by_folio: dict) -> dict:
    pins = {row[0]: row for row in by_pin.get(pin, ())} if pin else {}
    folios = (
        {row[0]: row for row in by_folio.get(folio, ())} if _usable_folio(folio) else {}
    )
    both = pins.keys() & folios.keys()
    pin_only = pins.keys() - folios.keys()
    folio_only = folios.keys() - pins.keys()
    if len(both) > 1:
        status = "ambiguous_multiple"
    elif (pin_only and folio_only) or (both and (pin_only or folio_only)):
        status = "identifier_conflict"
    elif len(both) == 1:
        status = "unique_exact"
    elif pin_only:
        status = "pin_only_lead"
    elif folio_only:
        status = "folio_only_lead"
    else:
        status = "no_match"
    return {
        "status": status,
        "both": len(both),
        "pin_only": len(pin_only),
        "folio_only": len(folio_only),
        "exact": pins[next(iter(both))] if len(both) == 1 else None,
        "unique_folio": next(iter(folios.values())) if len(folios) == 1 else None,
    }


def _cardinality(matches: list[dict], field: str) -> dict[str, int]:
    counts = Counter(
        "zero" if match[field] == 0 else "one" if match[field] == 1 else "many"
        for match in matches
    )
    return {label: counts[label] for label in ("zero", "one", "many")}


def _vintage_report(matches: list[dict]) -> dict:
    return {
        "exact_two_key": _cardinality(matches, "both"),
        "pin_only_candidates": _cardinality(matches, "pin_only"),
        "folio_only_candidates": _cardinality(matches, "folio_only"),
        "conflicting_rows": sum(
            match["status"] == "identifier_conflict" for match in matches
        ),
        "ambiguous_multiple_rows": sum(
            match["status"] == "ambiguous_multiple" for match in matches
        ),
        "pin_only_lead_rows": sum(
            match["status"] == "pin_only_lead" for match in matches
        ),
        "folio_only_lead_rows": sum(
            match["status"] == "folio_only_lead" for match in matches
        ),
        "duplicate_exact_key_rows": sum(match["both"] > 1 for match in matches),
    }


def _summarize(
    samples: list[dict], by_2025: tuple, by_2026: tuple
) -> tuple[dict, list[dict]]:
    _, old_pins, old_folios = by_2025
    _, current_pins, current_folios = by_2026
    old_matches, current_matches, flags = [], [], []
    controls: dict[tuple[str, str], bool] = {}
    mapped_identities = defaultdict(set)
    unique_exact = nonblank_strap = agree_rows = malformed_controls = 0
    unique_folio_nonblank = unique_folio_blank = current_agree = 0
    for sample in samples:
        pin, folio = sample["PIN"].strip(), sample["FOLIO"].strip()
        candidate = transform_pin(pin)
        old = _match(pin, folio, old_pins, old_folios)
        current = _match(candidate or "", folio, current_pins, current_folios)
        old_matches.append(old)
        current_matches.append(current)
        if candidate:
            mapped_identities[candidate].add((pin, folio))
        strap_status = "no_unique_exact_control"
        if old["both"] == 1:
            unique_exact += 1
            strap = old["exact"][3]
            if not strap:
                strap_status = "blank_strap"
            else:
                nonblank_strap += 1
                agrees = candidate == strap
                agree_rows += agrees
                malformed_controls += candidate is None
                controls[(pin, folio)] = agrees
                strap_status = "agree" if agrees else "disagree"
        current_status = "no_unique_folio"
        if current["unique_folio"] is not None:
            current_pin = current["unique_folio"][1]
            if not current_pin:
                unique_folio_blank += 1
                current_status = "blank_current_pin"
            else:
                unique_folio_nonblank += 1
                agrees = candidate == current_pin
                current_agree += agrees
                current_status = "agree" if agrees else "disagree"
        flags.append(
            {
                "record_ordinal": sample["record_ordinal"],
                "transform_status": "valid" if candidate else "malformed",
                "vintage_2025_status": old["status"],
                "vintage_2025_exact_candidates": old["both"],
                "vintage_2025_pin_only_candidates": old["pin_only"],
                "vintage_2025_folio_only_candidates": old["folio_only"],
                "strap_control_status": strap_status,
                "vintage_2026_status": current["status"],
                "vintage_2026_exact_candidates": current["both"],
                "vintage_2026_pin_only_candidates": current["pin_only"],
                "vintage_2026_folio_only_candidates": current["folio_only"],
                "current_unique_folio_pin_status": current_status,
            }
        )
    report = {
        "sample": {
            "rows": len(samples),
            "missing_pin_rows": sum(not row["PIN"].strip() for row in samples),
            "missing_folio_rows": sum(not row["FOLIO"].strip() for row in samples),
            "redacted_folio_rows": sum(
                row["FOLIO"].strip().upper() in REDACTED_FOLIOS for row in samples
            ),
            "malformed_pin_rows": sum(
                transform_pin(row["PIN"].strip()) is None for row in samples
            ),
            "distinct_source_identities": len(
                {(row["PIN"].strip(), row["FOLIO"].strip()) for row in samples}
            ),
        },
        "vintage_2025": _vintage_report(old_matches),
        "strap_control": {
            "unique_exact_sale_rows": unique_exact,
            "nonblank_strap_sale_rows": nonblank_strap,
            "agree_sale_rows": agree_rows,
            "nonblank_distinct_controls": len(controls),
            "agree_distinct_controls": sum(controls.values()),
            "malformed_sale_rows": malformed_controls,
        },
        "vintage_2026": {
            **_vintage_report(current_matches),
            "unique_folio_nonblank_pin_rows": unique_folio_nonblank,
            "unique_folio_blank_pin_rows": unique_folio_blank,
            "pin_agrees_on_unique_folio_rows": current_agree,
            "pin_disagrees_on_unique_folio_rows": unique_folio_nonblank - current_agree,
        },
        "transformed_collisions": sum(
            len(identities) > 1 for identities in mapped_identities.values()
        ),
    }
    has_conflict = bool(
        report["transformed_collisions"]
        or report["vintage_2025"]["conflicting_rows"]
        or report["vintage_2026"]["conflicting_rows"]
        or report["vintage_2025"]["ambiguous_multiple_rows"]
        or report["vintage_2026"]["ambiguous_multiple_rows"]
        or report["vintage_2025"]["duplicate_exact_key_rows"]
        or report["vintage_2026"]["duplicate_exact_key_rows"]
    )
    if has_conflict:
        report["format_rule_numeric_status"] = "fails_numeric_criteria"
    elif len(controls) < 200:
        report["format_rule_numeric_status"] = (
            "inconclusive_insufficient_distinct_controls"
        )
    elif (
        agree_rows * 100 < nonblank_strap * 99
        or sum(controls.values()) * 100 < len(controls) * 99
    ):
        report["format_rule_numeric_status"] = "fails_numeric_criteria"
    else:
        report["format_rule_numeric_status"] = (
            "meets_numeric_criteria_pending_custodian"
        )
    blockers = [
        "source_contract_unconfirmed",
        "historical_availability_unverified",
        "rights_unresolved",
        "sale_identity_and_eligibility_unverified",
    ]
    if report["vintage_2026"]["pin_disagrees_on_unique_folio_rows"]:
        blockers.append("current_pin_disagreement")
    if has_conflict:
        blockers.append("ambiguous_or_conflicting_identity")
    if report["sample"]["malformed_pin_rows"]:
        blockers.append("malformed_sale_pin")
    report["automatic_join_status"] = "BLOCKED"
    report["automatic_join_blockers"] = blockers
    return report, flags


def _write_once(path: Path, content: bytes, *, private: bool) -> None:
    if not path.parent.is_dir() or path.exists():
        raise FileExistsError("Audit output exists or parent directory is absent")
    if private:
        _private_path(path)
        if path.parent.resolve() != PRIVATE_ROOT.resolve(strict=True):
            raise ValueError("Private output must be directly in private root")
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
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def audit_crosswalk(
    archive_2025: Path,
    archive_2026: Path,
    sample: Path,
    old_sample: Path,
    private_flags: Path,
    aggregate: Path,
    archive_2025_sha256: str,
    archive_2026_sha256: str,
    sample_sha256: str,
    old_sample_sha256: str,
    *,
    expected_rows: int = 1000,
    expected_old_rows: int = 200,
) -> dict:
    """Read only pinned sources; write private flags and a safe aggregate once."""
    for path in (archive_2025, archive_2026, sample, old_sample, private_flags):
        _private_path(path)
    if (
        len(
            {
                path.resolve()
                for path in (
                    archive_2025,
                    archive_2026,
                    sample,
                    old_sample,
                    private_flags,
                    aggregate,
                )
            }
        )
        != 6
    ):
        raise ValueError("Source and output paths must be distinct")
    if private_flags.exists() or aggregate.exists():
        raise FileExistsError("Audit output already exists")
    if not 0 < expected_rows <= 1000 or not 0 < expected_old_rows <= 200:
        raise ValueError("Expected sample counts exceed the registered protocol")
    if (
        expected_rows == 1000
        and expected_old_rows == 200
        and old_sample_sha256.lower() != FROZEN_OLD_SAMPLE_SHA256
    ):
        raise ValueError("Input is not the frozen audit sample SHA-256")
    if (
        expected_rows == 1000
        and sample_sha256.lower() != FROZEN_VALIDATION_SAMPLE_SHA256
    ):
        raise ValueError("Input is not the frozen validation sample SHA-256")
    samples, cell_counts = _load_samples(
        _pinned_bytes(sample, sample_sha256),
        _pinned_bytes(old_sample, old_sample_sha256),
        expected_rows,
        expected_old_rows,
    )
    old_pins = {row["PIN"].strip() for row in samples if row["PIN"].strip()}
    folios = {
        row["FOLIO"].strip() for row in samples if _usable_folio(row["FOLIO"].strip())
    }
    transformed = {
        candidate for row in samples if (candidate := transform_pin(row["PIN"].strip()))
    }
    old_archive = _read_archive(
        archive_2025,
        archive_2025_sha256,
        "2025_10_parcel.dbf",
        {"PIN": 29, "FOLIO": 10, "STRAP": 22},
        old_pins,
        folios,
    )
    current_archive = _read_archive(
        archive_2026,
        archive_2026_sha256,
        "parcel.dbf",
        {"PIN": 25, "FOLIO": 20},
        transformed,
        folios,
    )
    summary, flags = _summarize(samples, old_archive, current_archive)
    report = {
        "source_2025": old_archive[0],
        "source_2026": current_archive[0],
        "validation_sample_sha256": sample_sha256.lower(),
        "frozen_audit_sample_sha256": old_sample_sha256.lower(),
        "cell_counts": cell_counts,
        **summary,
        "interpretation": "PIN format validation only; no sale eligibility, historical availability, label semantics, reuse-rights or production source contract inferred.",
    }
    private_content = "".join(
        json.dumps(flag, sort_keys=True) + "\n" for flag in flags
    ).encode("utf-8")
    public_content = (json.dumps(report, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )
    _write_once(private_flags, private_content, private=True)
    try:
        _write_once(aggregate, public_content, private=False)
    except (FileExistsError, OSError):
        private_flags.unlink(missing_ok=True)
        raise
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in (
        "archive-2025",
        "archive-2026",
        "sample",
        "old-sample",
        "private-flags",
        "aggregate",
    ):
        parser.add_argument(f"--{name}", type=Path, required=True)
    for name in (
        "archive-2025-sha256",
        "archive-2026-sha256",
        "sample-sha256",
        "old-sample-sha256",
    ):
        parser.add_argument(f"--{name}", required=True)
    options = parser.parse_args(argv)
    try:
        audit_crosswalk(
            options.archive_2025,
            options.archive_2026,
            options.sample,
            options.old_sample,
            options.private_flags,
            options.aggregate,
            options.archive_2025_sha256,
            options.archive_2026_sha256,
            options.sample_sha256,
            options.old_sample_sha256,
        )
    except (BadZipFile, FileExistsError, OSError, ValueError) as error:
        print(f"PIN crosswalk audit failed: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
