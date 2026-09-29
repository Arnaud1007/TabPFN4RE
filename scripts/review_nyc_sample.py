"""Validate a frozen NYC source sample and record private, revisioned reviews.

The source rows, evidence, entry JSON and ledger belong under ignored raw data.
Only suppressed aggregate counts leave the protected review directory. A stale
lock requires manual PID/host inspection; it is never removed by age alone.
"""

from __future__ import annotations

import argparse
import csv
from datetime import date, datetime, timezone
from decimal import Decimal
from hashlib import sha256
import io
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit
from uuid import uuid4

from scripts import private_review_io as private_io


RAW_ROOT = Path(__file__).resolve().parents[1] / "data" / "raw" / "nyc_dof"
SOURCE_SHA256 = "84c06057c52a2822f982cd98fb77ef7edf2c14134d00f46b073d2e4b762b2ef2"
SAMPLE_SHA256 = "e137de2cf73aa4a9fea6d024e4564ef6e907020e73fc8dbec3e4026786b189ca"
SOURCE_ROWS = 82_345
SAMPLE_COUNT = 200
PROTOCOL = "nyc-source-review-v1"
MAX_SOURCE_BYTES = 12_000_000
MAX_SAMPLE_BYTES = 100_000
MAX_LEDGER_BYTES = 5_000_000
MAX_ENTRY_BYTES = 40_000
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
CODE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,63}\Z")
NUMBER = re.compile(r"-?(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)(?:\.[0-9]+)?\Z")

DIMENSIONS = {
    "source_row_identity": {"match", "mismatch", "unknown"},
    "property_unit_identity": {"match", "mismatch", "not_applicable", "unknown"},
    "economic_transfer_scope": {
        "single_property",
        "multiple_properties",
        "partial_interest",
        "non_sale",
        "unknown",
    },
    "repeated_consideration": {"distinct_transfer", "repeated_amount", "unknown"},
    "price_semantics": {"reported_positive", "reported_zero", "invalid", "unknown"},
    "sale_date_vs_contract": {"before", "same", "after", "unknown"},
    "sale_date_vs_closing": {"before", "same", "after", "unknown"},
    "sale_date_vs_recording": {"before", "same", "after", "unknown"},
    "first_row_availability": {
        "upper_bound_only",
        "first_publication_verified",
        "unknown",
    },
    "attribute_vintage": {"historical_asof_supported", "later_or_current", "unknown"},
    "source_correction": {
        "documented_correction",
        "no_correction_in_checked_history",
        "unknown",
    },
    "property_class": {
        "single_family",
        "condominium",
        "small_multifamily",
        "other_residential",
        "nonresidential",
        "vacant_land",
        "unknown",
    },
    "evidence_quality": {"high", "medium", "low", "unknown"},
}
EVIDENCE_KINDS = {
    "source_record",
    "official_documentation",
    "independent_dof_export",
    "recorded_instrument",
    "recording_index",
    "closing_record",
    "archived_row_snapshot",
    "publication_log",
    "correction_record",
    "unavailable_attempt",
}
ENTRY_FIELDS = {
    "entry_id",
    "ledger_id",
    "protocol",
    "source_sha256",
    "sample_sha256",
    "ordinal",
    "revision",
    "supersedes_entry_id",
    "review_status",
    "reviewer_code",
    "reviewed_at",
    "attested",
    "evidence",
    "rubric",
}
IDENTITY_FIELDS = {
    "borough": "BOROUGH",
    "block": "BLOCK",
    "lot": "LOT",
    "apartment_number": "APARTMENT NUMBER",
    "sale_date": "SALE DATE",
    "sale_price": "SALE PRICE",
}
ATTEMPT_TARGETS = {
    "recorded_instrument",
    "independent_dof_export",
    "recording_index",
    "closing_record",
    "archived_row_snapshot",
    "publication_log",
    "correction_record",
}
ATTEMPT_OUTCOMES = {
    "access_unavailable",
    "access_denied",
    "lookup_failed",
    "not_found_in_checked_source",
}
ATTEMPT_DIMENSIONS = {
    "recorded_instrument": {
        "source_row_identity",
        "property_unit_identity",
        "economic_transfer_scope",
        "repeated_consideration",
        "sale_date_vs_recording",
    },
    "independent_dof_export": {"source_row_identity", "repeated_consideration"},
    "recording_index": {"sale_date_vs_recording", "source_row_identity"},
    "closing_record": {"sale_date_vs_contract", "sale_date_vs_closing"},
    "archived_row_snapshot": {"first_row_availability", "attribute_vintage"},
    "publication_log": {"first_row_availability"},
    "correction_record": {"source_correction"},
}


def _hash(data: bytes) -> str:
    return sha256(data).hexdigest()


def _utc(value: object) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("Review timestamps must be UTC with Z suffix")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise ValueError("Invalid UTC review timestamp") from error
    if parsed.utcoffset().total_seconds() != 0:
        raise ValueError("Invalid UTC review timestamp")
    return parsed


def _iso_date(value: object) -> None:
    if not isinstance(value, str):
        raise ValueError("Evidence date must be ISO local date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise ValueError("Evidence date must be ISO local date") from error
    if parsed.isoformat() != value:
        raise ValueError("Evidence date must be ISO local date")


def _private_path(path: Path, *, review: bool, must_exist: bool = False) -> Path:
    root = RAW_ROOT / "manual-review-v1" if review else RAW_ROOT
    private_io.real_directory(RAW_ROOT, RAW_ROOT.parent)
    return private_io.private_path(path, root, must_exist=must_exist)


def _read_bounded(path: Path, limit: int) -> bytes:
    if path.stat().st_size > limit:
        raise ValueError("Private audit file exceeds size limit")
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError("Private audit file exceeds size limit")
    return data


def _json_lines(data: bytes, description: str) -> list[dict]:
    if data and not data.endswith(b"\n"):
        raise ValueError(f"Malformed {description}: missing final newline")
    try:
        rows = [json.loads(line) for line in data.decode("utf-8").splitlines()]
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"Malformed {description}") from error
    if any(not isinstance(row, dict) for row in rows):
        raise ValueError(f"Malformed {description}: expected JSON objects")
    return rows


def _sample_ordinals(sample: Path) -> set[int]:
    data = _read_bounded(sample, MAX_SAMPLE_BYTES)
    if _hash(data) != SAMPLE_SHA256:
        raise ValueError("Frozen sample hash mismatch")
    rows = _json_lines(data, "sample")
    ordinals = [row.get("ordinal") for row in rows]
    if (
        len(ordinals) != SAMPLE_COUNT
        or any(type(n) is not int or n < 1 or n > SOURCE_ROWS for n in ordinals)
        or len(set(ordinals)) != SAMPLE_COUNT
    ):
        raise ValueError("Frozen sample must have unique, valid ordinals")
    return set(ordinals)


def _source_rows(source: Path, ordinals: set[int]) -> dict[int, dict[str, str]]:
    data = _read_bounded(source, MAX_SOURCE_BYTES)
    if _hash(data) != SOURCE_SHA256:
        raise ValueError("Frozen source hash mismatch")
    try:
        reader = csv.DictReader(
            io.StringIO(data.decode("utf-8-sig"), newline=""), strict=True
        )
        if not reader.fieldnames or not set(IDENTITY_FIELDS.values()).issubset(
            reader.fieldnames
        ):
            raise ValueError("Pinned source header lacks review identity fields")
        selected = {}
        count = 0
        for count, row in enumerate(reader, start=1):
            if None in row or any(value is None for value in row.values()):
                raise ValueError("Pinned source row has wrong field count")
            if count in ordinals:
                selected[count] = row
    except (UnicodeError, csv.Error) as error:
        raise ValueError("Pinned source CSV cannot be parsed") from error
    if count != SOURCE_ROWS or len(selected) != SAMPLE_COUNT:
        raise ValueError("Pinned source row count does not match review protocol")
    return selected


def _ensure_directory() -> Path:
    private_io.real_directory(RAW_ROOT, RAW_ROOT.parent)
    directory = RAW_ROOT / "manual-review-v1"
    if not directory.exists():
        directory.mkdir(mode=0o700)
        private_io.secure_directory(directory)
    private_io.real_directory(directory, RAW_ROOT)
    private_io.verify_acl(directory)
    return directory


def _manifest(path: Path) -> dict:
    try:
        value = json.loads(_read_bounded(path, 2048))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("Malformed private review manifest") from error
    if (
        not isinstance(value, dict)
        or set(value)
        != {"ledger_id", "protocol", "source_sha256", "sample_sha256", "created_at"}
        or not isinstance(value["ledger_id"], str)
        or not CODE.fullmatch(value["ledger_id"])
        or value["protocol"] != PROTOCOL
        or value["source_sha256"] != SOURCE_SHA256
        or value["sample_sha256"] != SAMPLE_SHA256
    ):
        raise ValueError("Private review manifest identity mismatch")
    _utc(value["created_at"])
    return value


def _inputs(
    source: Path, sample: Path, ledger: Path, manifest: Path, *, initialize: bool
) -> tuple[set[int], dict[int, dict[str, str]]]:
    if initialize:
        _ensure_directory()
    else:
        private_io.real_directory(RAW_ROOT / "manual-review-v1", RAW_ROOT)
        private_io.verify_acl(RAW_ROOT / "manual-review-v1")
    source = _private_path(source, review=False, must_exist=True)
    sample = _private_path(sample, review=False, must_exist=True)
    ledger = _private_path(ledger, review=True, must_exist=not initialize)
    manifest = _private_path(manifest, review=True, must_exist=not initialize)
    if len({source, sample, ledger, manifest}) != 4:
        raise ValueError("Private audit inputs must be distinct")
    ordinals = _sample_ordinals(sample)
    return ordinals, _source_rows(source, ordinals)


def _evidence_item(
    raw: object, source_sha: str, source_row: dict[str, str], reviewed_at: datetime
) -> dict:
    required = {"evidence_id", "kind", "reference", "observed_at"}
    allowed = required | {
        "snapshot_sha256",
        "official_revision_date",
        "row_identity",
        "identity_checked",
        "names_row",
        "rules_out_earlier",
        "checked_history",
        "record_type",
        "attribute_observed_at",
        "whole_property",
        "attempted_at",
        "target",
        "outcome",
    }
    if (
        not isinstance(raw, dict)
        or not required.issubset(raw)
        or not set(raw) <= allowed
    ):
        raise ValueError("Invalid review evidence fields")
    identifier, kind, reference = raw["evidence_id"], raw["kind"], raw["reference"]
    if (
        not isinstance(identifier, str)
        or not CODE.fullmatch(identifier)
        or not isinstance(kind, str)
        or kind not in EVIDENCE_KINDS
    ):
        raise ValueError("Invalid review evidence identifier or kind")
    if _utc(raw["observed_at"]) > reviewed_at:
        raise ValueError("Review evidence observed after review")
    if (
        not isinstance(reference, str)
        or len(reference) > 2048
        or any(ord(char) < 32 for char in reference)
    ):
        raise ValueError("Invalid review evidence reference")
    if kind == "source_record":
        if reference != "sha256:" + source_sha:
            raise ValueError("Source evidence must cite pinned source hash")
    else:
        try:
            url = urlsplit(reference)
            hostname = url.hostname
        except ValueError as error:
            raise ValueError("Invalid review evidence HTTPS reference") from error
        if (
            url.scheme != "https"
            or not hostname
            or url.username
            or url.password
            or url.fragment
        ):
            raise ValueError("Invalid review evidence HTTPS reference")
    if kind in {"archived_row_snapshot", "independent_dof_export"}:
        identity = raw.get("row_identity")
        if not isinstance(identity, dict) or set(identity) != set(IDENTITY_FIELDS):
            raise ValueError("Independent row evidence needs checked identity fields")
        if raw.get("identity_checked") is not True or any(
            not isinstance(value, str) for value in identity.values()
        ):
            raise ValueError("Independent row evidence needs checked identity fields")
    if kind == "archived_row_snapshot":
        if not isinstance(raw.get("snapshot_sha256"), str) or not HEX64.fullmatch(
            raw["snapshot_sha256"]
        ):
            raise ValueError("Archived row needs verified snapshot checksum")
        _iso_date(raw.get("official_revision_date"))
        if any(
            identity[name] != source_row[field]
            for name, field in IDENTITY_FIELDS.items()
        ):
            raise ValueError("Archived row identity does not match pinned source")
        if raw["official_revision_date"] > raw["observed_at"][:10]:
            raise ValueError("Archived row revision cannot postdate observation")
    if kind == "publication_log" and (
        raw.get("names_row") is not True or raw.get("rules_out_earlier") is not True
    ):
        raise ValueError("Publication log must name row and rule out earlier release")
    if kind == "correction_record":
        history = raw.get("checked_history")
        if (
            not isinstance(history, dict)
            or set(history) != {"from", "through", "version_ids"}
            or not isinstance(history["version_ids"], list)
            or not history["version_ids"]
            or any(
                not isinstance(version, str) or not CODE.fullmatch(version)
                for version in history["version_ids"]
            )
        ):
            raise ValueError(
                "Correction evidence needs bounded history and version IDs"
            )
        _iso_date(history["from"])
        _iso_date(history["through"])
        if history["from"] > history["through"]:
            raise ValueError("Correction history bounds are inverted")
        if history["through"] > min(
            raw["observed_at"][:10], reviewed_at.date().isoformat()
        ):
            raise ValueError("Correction history cannot extend beyond observation")
    if kind == "unavailable_attempt":
        if (
            not isinstance(raw.get("target"), str)
            or raw["target"] not in ATTEMPT_TARGETS
            or not isinstance(raw.get("outcome"), str)
            or raw["outcome"] not in ATTEMPT_OUTCOMES
            or "attempted_at" not in raw
        ):
            raise ValueError(
                "Unavailable attempt needs target, outcome and attempted_at"
            )
        attempted = _utc(raw["attempted_at"])
        if attempted > _utc(raw["observed_at"]) or attempted > reviewed_at:
            raise ValueError("Unavailable attempt time exceeds observation or review")
    if "attribute_observed_at" in raw:
        _iso_date(raw["attribute_observed_at"])
    if "record_type" in raw and raw["record_type"] not in {"contract", "closing"}:
        raise ValueError("Invalid transaction record type")
    if "whole_property" in raw and type(raw["whole_property"]) is not bool:
        raise ValueError("Invalid whole-property evidence flag")
    return raw


def _reported_price(row: dict[str, str]) -> str:
    value = row["SALE PRICE"].strip()
    if not NUMBER.fullmatch(value):
        return "invalid"
    number = Decimal(value.replace(",", ""))
    if number > 0:
        return "reported_positive"
    if number == 0:
        return "reported_zero"
    return "invalid"


def _rubric(raw: object, evidence: dict[str, dict], source_row: dict[str, str]) -> None:
    if not isinstance(raw, dict) or not raw or not set(raw) <= set(DIMENSIONS):
        raise ValueError("Invalid review rubric dimensions")
    for dimension, detail in raw.items():
        if not isinstance(detail, dict) or set(detail) != {
            "value",
            "evidence_ids",
            "limitation",
        }:
            raise ValueError("Invalid review rubric finding")
        value, refs, limitation = (
            detail["value"],
            detail["evidence_ids"],
            detail["limitation"],
        )
        if not isinstance(value, str) or value not in DIMENSIONS[dimension]:
            raise ValueError("Invalid review rubric value")
        if (
            not isinstance(refs, list)
            or not refs
            or any(not isinstance(ref, str) or ref not in evidence for ref in refs)
            or len(refs) != len(set(refs))
        ):
            raise ValueError("Invalid review rubric evidence references")
        if value == "unknown" and (
            not isinstance(limitation, str) or not limitation.strip()
        ):
            raise ValueError("Unknown review finding needs a concrete limitation")
        if limitation is not None and (
            not isinstance(limitation, str) or len(limitation) > 2000
        ):
            raise ValueError("Invalid review rubric limitation")
        if value != "unknown":
            if dimension != "price_semantics":
                raise ValueError(
                    "Non-unknown v1 finding needs a verified local artifact protocol"
                )
            cited_kinds = {evidence[ref]["kind"] for ref in refs}
            if not {"source_record", "official_documentation"} <= cited_kinds:
                raise ValueError(
                    "Published price finding needs source and official definition"
                )
            if value != _reported_price(source_row):
                raise ValueError("Review price semantics contradict pinned source")


def _entry(
    raw: object, ledger_id: str, ordinals: set[int], rows: dict[int, dict[str, str]]
) -> dict:
    if not isinstance(raw, dict) or set(raw) != ENTRY_FIELDS:
        raise ValueError("Invalid private review entry fields")
    if (
        raw["ledger_id"] != ledger_id
        or raw["protocol"] != PROTOCOL
        or raw["source_sha256"] != SOURCE_SHA256
        or raw["sample_sha256"] != SAMPLE_SHA256
    ):
        raise ValueError("Review entry source, sample, protocol or ledger ID mismatch")
    ordinal = raw["ordinal"]
    if type(ordinal) is not int or ordinal not in ordinals:
        raise ValueError("Review references an unsampled ordinal")
    if (
        not isinstance(raw["entry_id"], str)
        or not CODE.fullmatch(raw["entry_id"])
        or not isinstance(raw["reviewer_code"], str)
        or not CODE.fullmatch(raw["reviewer_code"])
    ):
        raise ValueError("Invalid review or reviewer identifier")
    if type(raw["revision"]) is not int or raw["revision"] < 1:
        raise ValueError("Invalid review revision")
    supersedes = raw["supersedes_entry_id"]
    if supersedes is not None and (
        not isinstance(supersedes, str) or not CODE.fullmatch(supersedes)
    ):
        raise ValueError("Invalid review supersession identifier")
    if (
        not isinstance(raw["review_status"], str)
        or raw["review_status"] not in {"partial", "complete"}
        or type(raw["attested"]) is not bool
    ):
        raise ValueError("Invalid review status or attestation")
    reviewed_at = _utc(raw["reviewed_at"])
    if reviewed_at > datetime.now(timezone.utc):
        raise ValueError("Review time cannot be in the future")
    sources = raw["evidence"]
    if not isinstance(sources, list) or not sources:
        raise ValueError("Review needs evidence")
    validated = [
        _evidence_item(source, SOURCE_SHA256, rows[ordinal], reviewed_at)
        for source in sources
    ]
    evidence = {item["evidence_id"]: item for item in validated}
    if len(evidence) != len(validated):
        raise ValueError("Duplicate review evidence IDs")
    _rubric(raw["rubric"], evidence, rows[ordinal])
    if raw["review_status"] == "complete":
        kinds = {item["kind"] for item in validated}
        if (
            set(raw["rubric"]) != set(DIMENSIONS)
            or not raw["attested"]
            or not {"source_record", "official_documentation"} <= kinds
            or not kinds & {"recorded_instrument", "unavailable_attempt"}
        ):
            raise ValueError(
                "Complete review needs full rubric, source definitions, instrument or unavailable attempt, and attestation"
            )
        attempts = [item for item in validated if item["kind"] == "unavailable_attempt"]
        for attempt in attempts:
            if not any(
                dimension in ATTEMPT_DIMENSIONS[attempt["target"]]
                and finding["value"] == "unknown"
                and attempt["evidence_id"] in finding["evidence_ids"]
                for dimension, finding in raw["rubric"].items()
            ):
                raise ValueError(
                    "Complete review needs attempt cited in a relevant unknown finding"
                )
        if "recorded_instrument" not in kinds and not any(
            attempt["target"] in {"recorded_instrument", "independent_dof_export"}
            for attempt in attempts
        ):
            raise ValueError(
                "Complete review needs instrument or qualified-source attempt"
            )
    return raw


def _history(
    entries: list[dict],
    ledger_id: str,
    ordinals: set[int],
    rows: dict[int, dict[str, str]],
) -> dict[int, dict]:
    latest: dict[int, dict] = {}
    used: set[str] = set()
    for raw in entries:
        entry = _entry(raw, ledger_id, ordinals, rows)
        if entry["entry_id"] in used:
            raise ValueError("Duplicate review entry ID")
        previous = latest.get(entry["ordinal"])
        if previous is None:
            valid = entry["revision"] == 1 and entry["supersedes_entry_id"] is None
        else:
            valid = (
                entry["revision"] == previous["revision"] + 1
                and entry["supersedes_entry_id"] == previous["entry_id"]
            )
        if not valid:
            raise ValueError("Invalid review revision or supersession")
        used.add(entry["entry_id"])
        latest[entry["ordinal"]] = entry
    return latest


def _summary(
    entries: list[dict],
    content: bytes,
    ledger_id: str,
    ordinals: set[int],
    rows: dict[int, dict[str, str]],
) -> dict:
    latest = _history(entries, ledger_id, ordinals, rows)
    complete = sum(entry["review_status"] == "complete" for entry in latest.values())
    return {
        "review_protocol_version": PROTOCOL,
        "source_sha256": SOURCE_SHA256,
        "sample_sha256": SAMPLE_SHA256,
        "ledger_sha256": _hash(content),
        "sampled_records": SAMPLE_COUNT,
        "review_entries": len(entries),
        "reviewed_records": len(latest),
        "superseded_entries": len(entries) - len(latest),
        "complete_records": complete,
        "partial_records": len(latest) - complete,
        "unreviewed_records": SAMPLE_COUNT - len(latest),
        "completion_basis": "attested review effort; unknown facts remain unknown",
    }


def _ledger_content(ledger: Path) -> tuple[list[dict], bytes]:
    content = _read_bounded(ledger, MAX_LEDGER_BYTES)
    return _json_lines(content, "review ledger"), content


def init_review(source: Path, sample: Path, ledger: Path, manifest: Path) -> dict:
    """Create a new private history after verifying frozen source and sample."""
    ordinals, rows = _inputs(source, sample, ledger, manifest, initialize=True)
    ledger = _private_path(ledger, review=True)
    manifest = _private_path(manifest, review=True)
    if ledger.exists() or manifest.exists():
        raise FileExistsError("Private review history already exists")
    with private_io.exclusive_lock(ledger, RAW_ROOT / "manual-review-v1"):
        if ledger.exists() or manifest.exists():
            raise FileExistsError("Private review history already exists")
        identity = "ledger-" + uuid4().hex
        value = {
            "ledger_id": identity,
            "protocol": PROTOCOL,
            "source_sha256": SOURCE_SHA256,
            "sample_sha256": SAMPLE_SHA256,
            "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        private_io.new_file(
            manifest, (json.dumps(value, sort_keys=True) + "\n").encode()
        )
        private_io.new_file(ledger, b"")
        return {**_summary([], b"", identity, ordinals, rows), "ledger_id": identity}


def inspect_orphan(source: Path, sample: Path, ledger: Path, manifest: Path) -> dict:
    """Record a manifest-only interrupted init without repairing its history."""
    ordinals, _ = _inputs(source, sample, ledger, manifest, initialize=True)
    ledger = _private_path(ledger, review=True)
    if not Path(manifest).exists():
        raise ValueError("Orphan manifest is missing")
    manifest = _private_path(manifest, review=True, must_exist=True)
    with private_io.exclusive_lock(ledger, RAW_ROOT / "manual-review-v1"):
        if ledger.exists():
            raise ValueError("History is not an orphan manifest")
        _manifest(manifest)
        return {
            "review_protocol_version": PROTOCOL,
            "status": "abandoned_manifest_only",
            "source_sha256": SOURCE_SHA256,
            "sample_sha256": SAMPLE_SHA256,
            "manifest_sha256": _hash(_read_bounded(manifest, 2048)),
            "sampled_records": len(ordinals),
            "review_entries": 0,
        }


def summarize_reviews(source: Path, sample: Path, ledger: Path, manifest: Path) -> dict:
    """Revalidate full private history after a crash; return safe aggregate only."""
    ordinals, rows = _inputs(source, sample, ledger, manifest, initialize=False)
    ledger = _private_path(ledger, review=True, must_exist=True)
    manifest = _private_path(manifest, review=True, must_exist=True)
    with private_io.exclusive_lock(ledger, RAW_ROOT / "manual-review-v1"):
        identity = _manifest(manifest)["ledger_id"]
        entries, content = _ledger_content(ledger)
        return _summary(entries, content, identity, ordinals, rows)


def append_review(
    source: Path,
    sample: Path,
    ledger: Path,
    manifest: Path,
    entry: dict,
    ledger_id: str,
    prior_sha256: str,
) -> dict:
    """Append one revision if the whole prior ledger matches the caller's hash."""
    ordinals, rows = _inputs(source, sample, ledger, manifest, initialize=False)
    ledger = _private_path(ledger, review=True, must_exist=True)
    manifest = _private_path(manifest, review=True, must_exist=True)
    with private_io.exclusive_lock(ledger, RAW_ROOT / "manual-review-v1"):
        identity = _manifest(manifest)["ledger_id"]
        if identity != ledger_id:
            raise ValueError("Private review ledger ID mismatch")
        entries, content = _ledger_content(ledger)
        _history(entries, identity, ordinals, rows)
        if (
            not isinstance(prior_sha256, str)
            or not HEX64.fullmatch(prior_sha256)
            or prior_sha256 != _hash(content)
        ):
            raise ValueError("Private review prior ledger hash mismatch")
        _entry(entry, identity, ordinals, rows)
        combined = [*entries, entry]
        _history(combined, identity, ordinals, rows)
        line = (json.dumps(entry, sort_keys=True, ensure_ascii=False) + "\n").encode(
            "utf-8"
        )
        new_content = content + line
        if len(new_content) > MAX_LEDGER_BYTES:
            raise ValueError("Private review ledger would exceed size limit")
        private_io.atomic_replace(ledger, new_content)
        return _summary(combined, new_content, identity, ordinals, rows)


def main(arguments: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Offline NYC private source-review ledger"
    )
    parser.add_argument(
        "action", choices=("init", "append", "summary", "inspect-orphan")
    )
    parser.add_argument("source", type=Path)
    parser.add_argument("sample", type=Path)
    parser.add_argument("ledger", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument(
        "entry", type=Path, help="Private entry JSON, or '-' for init/summary"
    )
    parser.add_argument("summary", type=Path, help="New aggregate-only JSON output")
    parser.add_argument("--ledger-id")
    parser.add_argument("--prior-ledger-sha256")
    options = parser.parse_args(arguments)
    inputs = (options.source, options.sample, options.ledger, options.manifest)
    private_io.summary_target(options.summary, inputs)
    if options.action == "init":
        if str(options.entry) != "-":
            parser.error("init requires '-' in the entry slot")
        initialized = init_review(*inputs)
        # Identity is kept in the private manifest; public summaries omit it.
        result = {
            key: value for key, value in initialized.items() if key != "ledger_id"
        }
    elif options.action in {"summary", "inspect-orphan"}:
        if str(options.entry) != "-":
            parser.error("summary or inspect-orphan requires '-' in the entry slot")
        result = (
            summarize_reviews(*inputs)
            if options.action == "summary"
            else inspect_orphan(*inputs)
        )
    else:
        if not options.ledger_id or not options.prior_ledger_sha256:
            parser.error("append requires ledger ID and exact prior ledger SHA-256")
        private_entry = _private_path(options.entry, review=True, must_exist=True)
        inputs = (*inputs, private_entry)
        try:
            entry = json.loads(_read_bounded(private_entry, MAX_ENTRY_BYTES))
        except (UnicodeError, json.JSONDecodeError) as error:
            raise ValueError("Malformed private review entry") from error
        result = append_review(
            options.source,
            options.sample,
            options.ledger,
            options.manifest,
            entry,
            options.ledger_id,
            options.prior_ledger_sha256,
        )
    private_io.write_summary_new(options.summary, result, inputs)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
