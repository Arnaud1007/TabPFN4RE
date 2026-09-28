"""Explain frozen HCPA PIN crosswalk gaps without admitting any property join.

All row-level flags remain under ignored ``data/raw/hcpa``. The public report
contains counts, source hashes and descriptive DBF header metadata only.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from datetime import date
from hashlib import sha256
import json
import os
from pathlib import Path
import stat
import sys
from typing import TypedDict
from zipfile import BadZipFile, ZipFile

import audit_hcpa_pin_crosswalk as crosswalk


PRIVATE_ROOT = crosswalk.PRIVATE_ROOT
MAX_AGGREGATE_BYTES = 100_000
FROZEN_INTERSECTION = {
    "old_exact_current_nonblank": 983,
    "old_exact_current_blank": 1,
    "old_no_exact_current_nonblank": 11,
    "old_no_exact_current_blank": 5,
}


class ArchiveMetadata(TypedDict):
    archive_sha256: str
    member: str
    member_crc32: str
    schema_sha256: str
    header_rows: int
    active_rows: int
    deleted_rows: int


ParcelRow = tuple[int, str, str, str]
ParcelIndex = dict[str, list[ParcelRow]]


@dataclass(frozen=True)
class PinnedFile:
    path: Path
    sha256: str


@dataclass(frozen=True)
class GapInputs:
    archive_2025: PinnedFile
    archive_2026: PinnedFile
    sample: PinnedFile
    old_sample: PinnedFile
    prior_aggregate: PinnedFile
    private_flags: Path
    aggregate: Path
    expected_rows: int = 1000
    expected_old_rows: int = 200


@dataclass(frozen=True)
class ArchiveIndex:
    metadata: ArchiveMetadata
    by_pin: ParcelIndex
    by_folio: ParcelIndex

    def as_crosswalk(self) -> tuple[ArchiveMetadata, ParcelIndex, ParcelIndex]:
        return self.metadata, self.by_pin, self.by_folio


def _read_prior(path: Path, expected_hash: str) -> dict:
    if not crosswalk.SHA256_PATTERN.fullmatch(expected_hash):
        raise ValueError("Prior aggregate SHA-256 must contain 64 hex digits")
    if path.is_symlink():
        raise ValueError("Prior aggregate may not be a symlink")
    with path.open("rb") as source:
        metadata = os.fstat(source.fileno())
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_AGGREGATE_BYTES:
            raise ValueError("Prior aggregate exceeds size or file-type contract")
        content = source.read(MAX_AGGREGATE_BYTES + 1)
        if (metadata.st_dev, metadata.st_ino) != (
            path.stat().st_dev,
            path.stat().st_ino,
        ):
            raise ValueError("Prior aggregate changed while open")
    if sha256(content).hexdigest() != expected_hash.lower():
        raise ValueError("Prior aggregate SHA-256 mismatch")

    def unique_keys(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Prior aggregate has duplicate JSON keys")
            result[key] = value
        return result

    try:
        prior = json.loads(content, object_pairs_hook=unique_keys)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Prior aggregate is not valid JSON") from error
    if not isinstance(prior, dict):
        raise ValueError("Prior aggregate is not an object")
    return prior


def _verify_prior(prior: dict, expected: dict) -> None:
    for key, value in expected.items():
        if prior.get(key) != value:
            raise ValueError("Pinned prior aggregate mismatch")


def _read_selected_raw(
    path: Path,
    expected_hash: str,
    basename: str,
    required: dict[str, int],
    source_metadata: dict,
    ordinals: set[int],
) -> tuple[date, dict[int, dict[str, bytes]]]:
    """Re-open a pinned DBF, retaining raw C-field bytes for selected rows."""
    crosswalk._private_path(path)
    with path.open("rb") as source:
        crosswalk._revalidate_open_file(path, source)
        metadata = os.fstat(source.fileno())
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_size > crosswalk.MAX_ARCHIVE_BYTES
        ):
            raise ValueError("Archive exceeds size or file-type contract")
        digest = crosswalk._hash_stream(source)
        if digest != expected_hash.lower():
            raise ValueError("Archive SHA-256 mismatch")
        source.seek(0)
        with ZipFile(source) as zipped:
            info = crosswalk._member(zipped, basename)
            with zipped.open(info) as member:
                header = member.read(32)
            if len(header) != 32:
                raise ValueError("Parcel DBF header is truncated")
            try:
                header_date = date(1900 + header[1], header[2], header[3])
            except ValueError as error:
                raise ValueError("Parcel DBF header date is invalid") from error
            with zipped.open(info) as member:
                row_count, record_bytes, fields, schema_hash = crosswalk._header(
                    member, info.file_size, required
                )
                if (
                    schema_hash != source_metadata["schema_sha256"]
                    or row_count != source_metadata["header_rows"]
                    or f"{info.CRC:08x}" != source_metadata["member_crc32"]
                ):
                    raise ValueError("Parcel DBF schema or metadata mismatch")
                selected = {}
                for ordinal in range(1, row_count + 1):
                    record = member.read(record_bytes)
                    if len(record) != record_bytes:
                        raise ValueError(
                            "Parcel DBF ended before declared record count"
                        )
                    if ordinal not in ordinals:
                        continue
                    if record[:1] != b" ":
                        raise ValueError("Selected parcel row is not active")
                    selected[ordinal] = {
                        name: record[offset : offset + width]
                        for name in required
                        for offset, width, _ in (fields[name],)
                    }
                if member.read(2) != b"\x1a":
                    raise ValueError("Parcel DBF end marker is invalid")
        source.seek(0)
        if crosswalk._hash_stream(source) != digest:
            raise ValueError("Archive SHA-256 changed during diagnosis")
        crosswalk._revalidate_open_file(path, source)
    if selected.keys() != ordinals:
        raise ValueError("Selected parcel ordinals could not be reconciled")
    return header_date, selected


def _raw_ascii(value: bytes) -> str:
    try:
        decoded = value.decode("ascii")
    except UnicodeDecodeError as error:
        raise ValueError("Selected parcel identifier is not ASCII") from error
    if any(character not in (" ",) and ord(character) < 33 for character in decoded):
        raise ValueError("Selected parcel identifier contains non-space controls")
    return decoded.strip(" ")


def _sale_date(raw: str) -> date:
    crosswalk._band(raw)
    return date(int(raw[:4]), int(raw[4:6]), int(raw[6:8]))


def _date_relation(raw: str, header_date: date) -> str:
    sale = _sale_date(raw)
    if sale < header_date:
        return "before"
    if sale > header_date:
        return "after"
    return "on"


def _matches(
    sample: dict,
    old: ArchiveIndex,
    current: ArchiveIndex,
) -> tuple[str, str, str, dict, dict]:
    pin, folio = sample["PIN"].strip(), sample["FOLIO"].strip()
    candidate = crosswalk.transform_pin(pin)
    if candidate is None or not crosswalk._usable_folio(folio):
        raise ValueError("Frozen gap diagnostic requires valid PIN and FOLIO")
    old_match = crosswalk._match(pin, folio, old.by_pin, old.by_folio)
    current_match = crosswalk._match(candidate, folio, current.by_pin, current.by_folio)
    if old_match["status"] not in ("unique_exact", "folio_only_lead", "no_match"):
        raise ValueError("Conflicting or ambiguous 2025 candidate")
    if current_match["unique_folio"] is None or current_match["status"] not in (
        "unique_exact",
        "folio_only_lead",
    ):
        raise ValueError("Missing or ambiguous current FOLIO candidate")
    return pin, folio, candidate, old_match, current_match


def _current_blank_status(
    folio: str,
    candidate: str,
    old_match: dict,
    current_match: dict,
    current_raw: dict[int, dict[str, bytes]],
    counts: Counter,
) -> bool:
    ordinal, current_pin, _, _ = current_match["unique_folio"]
    raw = current_raw[ordinal]
    raw_pin = raw["PIN"]
    if _raw_ascii(raw_pin) != current_pin:
        raise ValueError("Current PIN raw and indexed values disagree")
    if _raw_ascii(raw["FOLIO"]) != folio:
        raise ValueError("Current FOLIO raw and indexed values disagree")
    if current_pin:
        if current_pin != candidate:
            raise ValueError("Current PIN conflicts with transformed sale PIN")
        return False
    counts["total"] += 1
    counts["unique_folio"] += 1
    if raw_pin != b" " * len(raw_pin):
        raise ValueError("Current PIN is blank after trimming but not raw spaces")
    counts["raw_all_spaces"] += 1
    old_exact = old_match["status"] == "unique_exact"
    counts["old_exact" if old_exact else "overlap_old_no_exact"] += 1
    if not old_exact:
        counts[
            "old_folio_only_lead"
            if old_match["status"] == "folio_only_lead"
            else "old_no_lead"
        ] += 1
    return True


def _classify_old_lead(
    pin: str,
    folio: str,
    candidate: str,
    old_match: dict,
    old_raw: dict[int, dict[str, bytes]],
    counts: Counter,
) -> None:
    lead = old_match["unique_folio"]
    if lead is None:
        raise ValueError("2025 FOLIO lead is not unique")
    raw = old_raw[lead[0]]
    lead_pin, lead_strap = _raw_ascii(raw["PIN"]), _raw_ascii(raw["STRAP"])
    if (
        lead_pin != lead[1]
        or lead_strap != lead[3]
        or _raw_ascii(raw["FOLIO"]) != folio
    ):
        raise ValueError("2025 lead raw and indexed values disagree")
    if not lead_pin:
        pin_status = "folio_lead_pin_blank"
    elif not crosswalk.FORMATTED_PIN.fullmatch(lead_pin):
        pin_status = "folio_lead_pin_malformed"
    else:
        pin_status = (
            "folio_lead_pin_nonblank_same"
            if lead_pin == pin
            else "folio_lead_pin_nonblank_different"
        )
    if not lead_strap:
        strap_status = "folio_lead_strap_blank"
    else:
        strap_status = (
            "folio_lead_strap_agree"
            if lead_strap == candidate
            else "folio_lead_strap_disagree"
        )
    counts[pin_status] += 1
    counts[strap_status] += 1


def _old_gap_status(
    sample: dict,
    pin: str,
    folio: str,
    candidate: str,
    old_match: dict,
    old_raw: dict[int, dict[str, bytes]],
    header_date: date,
    counts: Counter,
    date_counts: Counter,
) -> tuple[str, str]:
    if old_match["status"] == "unique_exact":
        return "exact", "not_in_gap"
    counts["total"] += 1
    relation = _date_relation(sample["S_DATE"], header_date)
    date_counts[relation] += 1
    status = (
        "folio_only_lead" if old_match["status"] == "folio_only_lead" else "no_lead"
    )
    counts[status] += 1
    if status == "folio_only_lead":
        _classify_old_lead(pin, folio, candidate, old_match, old_raw, counts)
    return status, relation


def _category_report(
    samples: list[dict],
    intersection: Counter,
    old_gaps: Counter,
    current_blank: Counter,
    date_gap: Counter,
) -> dict:
    old_report = {
        key: old_gaps[key]
        for key in (
            "total",
            "folio_only_lead",
            "no_lead",
            "folio_lead_pin_blank",
            "folio_lead_pin_malformed",
            "folio_lead_pin_nonblank_same",
            "folio_lead_pin_nonblank_different",
            "folio_lead_strap_blank",
            "folio_lead_strap_agree",
            "folio_lead_strap_disagree",
        )
    }
    old_report["sale_date_vs_old_dbf_header"] = {
        key: date_gap[key] for key in ("before", "on", "after")
    }
    categories = {
        "intersection": {key: intersection[key] for key in FROZEN_INTERSECTION},
        "old_no_exact": old_report,
        "current_blank": {
            key: current_blank[key]
            for key in (
                "total",
                "unique_folio",
                "raw_all_spaces",
                "overlap_old_no_exact",
                "old_exact",
                "old_folio_only_lead",
                "old_no_lead",
            )
        },
    }
    _validate_partitions(categories, len(samples))
    return categories


def _validate_partitions(categories: dict, row_count: int) -> None:
    old, blank, intersection = (
        categories["old_no_exact"],
        categories["current_blank"],
        categories["intersection"],
    )
    old_pin_states = (
        "folio_lead_pin_blank",
        "folio_lead_pin_malformed",
        "folio_lead_pin_nonblank_same",
        "folio_lead_pin_nonblank_different",
    )
    old_strap_states = (
        "folio_lead_strap_blank",
        "folio_lead_strap_agree",
        "folio_lead_strap_disagree",
    )
    if not all(
        (
            sum(intersection.values()) == row_count,
            old["total"] == old["folio_only_lead"] + old["no_lead"],
            old["total"] == sum(old["sale_date_vs_old_dbf_header"].values()),
            blank["total"] == blank["overlap_old_no_exact"] + blank["old_exact"],
            blank["overlap_old_no_exact"]
            == blank["old_folio_only_lead"] + blank["old_no_lead"],
            old["folio_only_lead"] == sum(old[key] for key in old_pin_states),
            old["folio_only_lead"] == sum(old[key] for key in old_strap_states),
        )
    ):
        raise ValueError("Gap categories do not reconcile")


def _classify(
    samples: list[dict],
    old_archive: ArchiveIndex,
    current_archive: ArchiveIndex,
    old_raw: dict[int, dict[str, bytes]],
    current_raw: dict[int, dict[str, bytes]],
    old_header_date: date,
) -> tuple[dict, list[dict]]:
    intersection, old_gaps, current_blank, date_gap = (
        Counter(),
        Counter(),
        Counter(),
        Counter(),
    )
    flags = []
    for sample in samples:
        pin, folio, candidate, old, current = _matches(
            sample, old_archive, current_archive
        )
        current_is_blank = _current_blank_status(
            folio, candidate, old, current, current_raw, current_blank
        )
        old_exact = old["status"] == "unique_exact"
        intersection[
            f"old_{'exact' if old_exact else 'no_exact'}_current_"
            f"{'blank' if current_is_blank else 'nonblank'}"
        ] += 1
        old_status, date_status = _old_gap_status(
            sample,
            pin,
            folio,
            candidate,
            old,
            old_raw,
            old_header_date,
            old_gaps,
            date_gap,
        )
        flags.append(
            {
                "record_ordinal": sample["record_ordinal"],
                "old_status": old_status,
                "current_pin_status": "blank" if current_is_blank else "agrees",
                "sale_date_vs_old_dbf_header": date_status,
            }
        )
    return _category_report(
        samples, intersection, old_gaps, current_blank, date_gap
    ), flags


def _validate_inputs(inputs: GapInputs) -> None:
    private_paths = (
        inputs.archive_2025.path,
        inputs.archive_2026.path,
        inputs.sample.path,
        inputs.old_sample.path,
        inputs.private_flags,
    )
    for path in private_paths:
        crosswalk._private_path(path)
    paths = (*private_paths, inputs.prior_aggregate.path, inputs.aggregate)
    if len({path.resolve() for path in paths}) != len(paths):
        raise ValueError("Source and output paths must be distinct")
    if inputs.private_flags.exists() or inputs.aggregate.exists():
        raise FileExistsError("Diagnostic output already exists")
    if not 0 < inputs.expected_rows <= 1000 or not 0 < inputs.expected_old_rows <= 200:
        raise ValueError("Expected sample counts exceed registered protocol")
    if (
        inputs.expected_rows == 1000
        and inputs.sample.sha256.lower() != crosswalk.FROZEN_VALIDATION_SAMPLE_SHA256
    ):
        raise ValueError("Input is not frozen validation sample SHA-256")
    if (
        inputs.expected_rows == 1000
        and inputs.expected_old_rows == 200
        and inputs.old_sample.sha256.lower() != crosswalk.FROZEN_OLD_SAMPLE_SHA256
    ):
        raise ValueError("Input is not frozen audit sample SHA-256")


def _load_archives(
    inputs: GapInputs,
) -> tuple[list[dict], dict[str, int], ArchiveIndex, ArchiveIndex]:
    samples, cells = crosswalk._load_samples(
        crosswalk._pinned_bytes(inputs.sample.path, inputs.sample.sha256),
        crosswalk._pinned_bytes(inputs.old_sample.path, inputs.old_sample.sha256),
        inputs.expected_rows,
        inputs.expected_old_rows,
    )
    pins = {row["PIN"].strip() for row in samples if row["PIN"].strip()}
    folios = {
        row["FOLIO"].strip()
        for row in samples
        if crosswalk._usable_folio(row["FOLIO"].strip())
    }
    transformed = {
        value
        for row in samples
        if (value := crosswalk.transform_pin(row["PIN"].strip()))
    }
    old = ArchiveIndex(
        *crosswalk._read_archive(
            inputs.archive_2025.path,
            inputs.archive_2025.sha256,
            "2025_10_parcel.dbf",
            {"PIN": 29, "FOLIO": 10, "STRAP": 22},
            pins,
            folios,
        )
    )
    current = ArchiveIndex(
        *crosswalk._read_archive(
            inputs.archive_2026.path,
            inputs.archive_2026.sha256,
            "parcel.dbf",
            {"PIN": 25, "FOLIO": 20},
            transformed,
            folios,
        )
    )
    return samples, cells, old, current


def _verify_frozen_prior(
    inputs: GapInputs,
    samples: list[dict],
    cells: dict[str, int],
    old: ArchiveIndex,
    current: ArchiveIndex,
) -> dict:
    prior = _read_prior(inputs.prior_aggregate.path, inputs.prior_aggregate.sha256)
    summary, _ = crosswalk._summarize(
        samples, old.as_crosswalk(), current.as_crosswalk()
    )
    _verify_prior(
        prior,
        {
            "source_2025": old.metadata,
            "source_2026": current.metadata,
            "validation_sample_sha256": inputs.sample.sha256.lower(),
            "frozen_audit_sample_sha256": inputs.old_sample.sha256.lower(),
            "cell_counts": cells,
            **summary,
        },
    )
    return prior


def _selected_ordinals(
    samples: list[dict],
    old: ArchiveIndex,
    current: ArchiveIndex,
) -> tuple[set[int], set[int]]:
    old_ordinals: set[int] = set()
    current_ordinals: set[int] = set()
    for sample in samples:
        pin, folio = sample["PIN"].strip(), sample["FOLIO"].strip()
        old_match = crosswalk._match(pin, folio, old.by_pin, old.by_folio)
        current_match = crosswalk._match(
            crosswalk.transform_pin(pin) or "",
            folio,
            current.by_pin,
            current.by_folio,
        )
        if old_match["status"] == "folio_only_lead" and old_match["unique_folio"]:
            old_ordinals.add(old_match["unique_folio"][0])
        if current_match["unique_folio"]:
            current_ordinals.add(current_match["unique_folio"][0])
    return old_ordinals, current_ordinals


def _load_raw_controls(
    inputs: GapInputs,
    samples: list[dict],
    old: ArchiveIndex,
    current: ArchiveIndex,
) -> tuple[date, dict[int, dict[str, bytes]], dict[int, dict[str, bytes]]]:
    old_ordinals, current_ordinals = _selected_ordinals(samples, old, current)
    header_date, old_raw = _read_selected_raw(
        inputs.archive_2025.path,
        inputs.archive_2025.sha256,
        "2025_10_parcel.dbf",
        {"PIN": 29, "FOLIO": 10, "STRAP": 22},
        old.metadata,
        old_ordinals,
    )
    _, current_raw = _read_selected_raw(
        inputs.archive_2026.path,
        inputs.archive_2026.sha256,
        "parcel.dbf",
        {"PIN": 25, "FOLIO": 20},
        current.metadata,
        current_ordinals,
    )
    return header_date, old_raw, current_raw


def _verify_gap_counts(inputs: GapInputs, categories: dict, prior: dict) -> None:
    old, blank = categories["old_no_exact"], categories["current_blank"]
    if (
        old["total"] != prior["vintage_2025"]["exact_two_key"]["zero"]
        or blank["total"] != prior["vintage_2026"]["unique_folio_blank_pin_rows"]
        or old["folio_only_lead"] != prior["vintage_2025"]["folio_only_lead_rows"]
    ):
        raise ValueError("Gap counts do not reconcile with prior aggregate")
    if inputs.expected_rows == 1000 and (
        categories["intersection"] != FROZEN_INTERSECTION
        or old["folio_only_lead"] != 6
        or old["no_lead"] != 10
        or blank["total"] != 6
    ):
        raise ValueError("Gap counts differ from ADR 0018 frozen controls")


def _make_report(
    inputs: GapInputs,
    samples: list[dict],
    old: ArchiveIndex,
    current: ArchiveIndex,
    prior: dict,
    categories: dict,
    header_date: date,
) -> dict:
    return {
        "validation_sample_sha256": inputs.sample.sha256.lower(),
        "frozen_audit_sample_sha256": inputs.old_sample.sha256.lower(),
        "prior_aggregate_sha256": inputs.prior_aggregate.sha256.lower(),
        "source_2025": old.metadata,
        "source_2026": current.metadata,
        "old_dbf_header_date": header_date.isoformat(),
        "old_dbf_header_date_semantics": (
            "DBF metadata only; not source publication or feature availability"
        ),
        "sample": {
            "rows": len(samples),
            "distinct_source_identities": prior["sample"]["distinct_source_identities"],
        },
        **categories,
        "automatic_join_status": "BLOCKED",
        "automatic_join_blockers": prior["automatic_join_blockers"],
        "interpretation": (
            "One-key leads and current blank PINs are diagnostic only; "
            "no eligibility or as-of rights inferred."
        ),
    }


def _write_outputs(inputs: GapInputs, report: dict, flags: list[dict]) -> None:
    private_content = "".join(
        json.dumps(row, sort_keys=True) + "\n" for row in flags
    ).encode("utf-8")
    public_content = (json.dumps(report, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )
    crosswalk._write_once(inputs.private_flags, private_content, private=True)
    try:
        crosswalk._write_once(inputs.aggregate, public_content, private=False)
    except (FileExistsError, OSError):
        inputs.private_flags.unlink(missing_ok=True)
        raise


def diagnose_gaps(inputs: GapInputs) -> dict:
    """Recompute the frozen crosswalk and classify only its unresolved gaps."""
    _validate_inputs(inputs)
    samples, cells, old, current = _load_archives(inputs)
    prior = _verify_frozen_prior(inputs, samples, cells, old, current)
    header_date, old_raw, current_raw = _load_raw_controls(
        inputs, samples, old, current
    )
    categories, flags = _classify(
        samples, old, current, old_raw, current_raw, header_date
    )
    _verify_gap_counts(inputs, categories, prior)
    report = _make_report(inputs, samples, old, current, prior, categories, header_date)
    _write_outputs(inputs, report, flags)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in (
        "archive-2025",
        "archive-2026",
        "sample",
        "old-sample",
        "prior-aggregate",
        "private-flags",
        "aggregate",
    ):
        parser.add_argument(f"--{name}", required=True, type=Path)
    for name in (
        "archive-2025-sha256",
        "archive-2026-sha256",
        "sample-sha256",
        "old-sample-sha256",
        "prior-aggregate-sha256",
    ):
        parser.add_argument(f"--{name}", required=True)
    options = parser.parse_args(argv)
    try:
        diagnose_gaps(
            GapInputs(
                archive_2025=PinnedFile(
                    options.archive_2025, options.archive_2025_sha256
                ),
                archive_2026=PinnedFile(
                    options.archive_2026, options.archive_2026_sha256
                ),
                sample=PinnedFile(options.sample, options.sample_sha256),
                old_sample=PinnedFile(options.old_sample, options.old_sample_sha256),
                prior_aggregate=PinnedFile(
                    options.prior_aggregate, options.prior_aggregate_sha256
                ),
                private_flags=options.private_flags,
                aggregate=options.aggregate,
            )
        )
    except (BadZipFile, FileExistsError, OSError, ValueError) as error:
        print(f"HCPA gap diagnosis failed: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
