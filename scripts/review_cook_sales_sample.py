"""Offline, private review ledger for the frozen Cook County audit sample.

The review records source investigation, not eligible sale labels. Only fixed
aggregate counts leave the protected raw-data directory.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit
from uuid import uuid4

from scripts import capture_cook_sales_audit as capture
from scripts import private_review_io as private_io


RAW_ROOT = Path(__file__).resolve().parents[1] / "data" / "raw" / "cook_county"
CAPTURE_NAME = "cook-sales-v1-20261003T004123.032937Z-c08de13e9f1d"
CAPTURE_SHA256 = "130b5169ff81ccbc0a729cba98400f2fb377ff9a25999316aaac1960e38a3cf7"
SOURCE_METADATA_SHA256 = (
    "c967e289fdd1a45319b1efdedf38276c670b1cdb0e11e5466e95e31731119dce"
)
CAPTURE_COMPLETED_AT = "2026-10-03T00:42:14.862412Z"
SAMPLE_COUNT = 200
PROTOCOL = "cook-source-review-v1"
REVIEW_NAME = "manual-review-v1"
MAX_MANIFEST_BYTES = 16_384
MAX_WORKLIST_BYTES = 512_000
MAX_LEDGER_BYTES = 8_000_000
MAX_ENTRY_BYTES = 40_000
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
CODE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,63}\Z")

DIMENSIONS = (
    "source_row_identity",
    "property_unit_identity",
    "economic_transfer_scope",
    "repeated_consideration",
    "published_price_state",
    "sale_date_vs_contract",
    "sale_date_vs_closing",
    "sale_date_vs_recording",
    "first_row_availability",
    "attribute_vintage",
    "source_correction",
    "property_class",
    "arm_length_status",
    "evidence_quality",
)
EVIDENCE_KINDS = {
    "source_record",
    "official_documentation",
    "recorded_instrument",
    "recording_index",
    "closing_record",
    "archived_row_snapshot",
    "publication_log",
    "correction_record",
    "unavailable_attempt",
}
ATTEMPT_TARGETS = EVIDENCE_KINDS - {
    "source_record",
    "official_documentation",
    "unavailable_attempt",
}
ATTEMPT_OUTCOMES = {
    "access_unavailable",
    "access_denied",
    "lookup_failed",
    "not_found_in_checked_source",
}
ENTRY_FIELDS = {
    "entry_id",
    "ledger_id",
    "protocol",
    "capture_sha256",
    "ordinal",
    "row_sha256",
    "revision",
    "supersedes_entry_id",
    "review_status",
    "reviewer_code",
    "reviewed_at",
    "attested",
    "evidence",
    "rubric",
}


def _hash(content: bytes) -> str:
    return sha256(content).hexdigest()


def row_hash(row: dict) -> str:
    """Hash a source row with stable UTF-8 JSON serialization."""
    if not isinstance(row, dict):
        raise ValueError("Review row must be a JSON object")
    return _hash(
        json.dumps(
            row, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")
    )


def _utc(value: object) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("Review timestamp must be UTC")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise ValueError("Invalid UTC review timestamp") from error
    if parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        raise ValueError("Invalid UTC review timestamp")
    return parsed


def _bounded(path: Path, limit: int) -> bytes:
    if path.stat().st_size > limit:
        raise ValueError("Private review file exceeds size cap")
    with path.open("rb") as source:
        content = source.read(limit + 1)
    if len(content) > limit:
        raise ValueError("Private review file exceeds size cap")
    return content


def _json_lines(content: bytes) -> list[dict]:
    if content and not content.endswith(b"\n"):
        raise ValueError("Private ledger is truncated")
    try:
        rows = [json.loads(line) for line in content.decode("utf-8").splitlines()]
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("Private ledger is malformed") from error
    if any(not isinstance(row, dict) for row in rows):
        raise ValueError("Private ledger contains a non-object entry")
    return rows


def _capture_rows() -> list[dict]:
    private_io.real_directory(RAW_ROOT, RAW_ROOT.parent)
    private_io.verify_acl(RAW_ROOT)
    directory = RAW_ROOT / CAPTURE_NAME
    private_io.real_directory(directory, RAW_ROOT)
    private_io.verify_acl(directory)
    manifest_path = private_io.private_path(
        directory / "manifest.json", directory, must_exist=True
    )
    raw_manifest = _bounded(manifest_path, capture.MAX_MANIFEST_BYTES)
    if _hash(raw_manifest) != CAPTURE_SHA256:
        raise ValueError("Frozen Cook capture manifest hash mismatch")
    metadata_path = private_io.private_path(
        directory / "metadata-before.json", directory, must_exist=True
    )
    if (
        _hash(_bounded(metadata_path, capture.MAX_METADATA_BYTES))
        != SOURCE_METADATA_SHA256
    ):
        raise ValueError("Frozen Cook source metadata hash mismatch")
    verified = capture.verify_capture(directory)
    if (
        verified.get("sample_rows") != SAMPLE_COUNT
        or verified.get("historical_asof_eligible") is not False
    ):
        raise ValueError("Frozen Cook capture verification differs")
    try:
        manifest = json.loads(raw_manifest)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("Frozen Cook capture manifest is malformed") from error
    if not isinstance(manifest, dict):
        raise ValueError("Frozen Cook capture manifest is malformed")
    _utc(manifest.get("completed_at"))
    if manifest["completed_at"] != CAPTURE_COMPLETED_AT:
        raise ValueError("Frozen Cook capture completion time differs")
    expected_ids = manifest.get("sample_row_ids")
    if (
        not isinstance(expected_ids, list)
        or len(expected_ids) != SAMPLE_COUNT
        or any(not isinstance(key, str) or not key for key in expected_ids)
        or len(set(expected_ids)) != SAMPLE_COUNT
    ):
        raise ValueError("Frozen Cook sample membership is invalid")
    rows = []
    for cell in capture.CELLS:
        for page_index in range(2):
            path = private_io.private_path(
                directory / f"rows-{cell.slug}-{page_index}.json",
                directory,
                must_exist=True,
            )
            try:
                page = json.loads(_bounded(path, capture.MAX_ROW_BYTES))
            except (UnicodeError, json.JSONDecodeError) as error:
                raise ValueError("Frozen Cook row page is malformed") from error
            if (
                not isinstance(page, list)
                or not page
                or any(not isinstance(row, dict) for row in page)
            ):
                raise ValueError("Frozen Cook row page is malformed")
            rows.extend(page)
    row_ids = [row.get("row_id") for row in rows]
    if row_ids != expected_ids or len(rows) != SAMPLE_COUNT:
        raise ValueError("Frozen Cook row order or membership differs")
    return rows


def _review_dir(*, initialize: bool) -> Path:
    private_io.real_directory(RAW_ROOT, RAW_ROOT.parent)
    directory = RAW_ROOT / REVIEW_NAME
    if initialize:
        directory.mkdir(mode=0o700, exist_ok=False)
        private_io.secure_directory(directory)
    private_io.real_directory(directory, RAW_ROOT)
    private_io.verify_acl(directory)
    return directory


def _file(directory: Path, name: str, *, must_exist: bool = True) -> Path:
    return private_io.private_path(directory / name, directory, must_exist=must_exist)


def _worklist(rows: list[dict]) -> bytes:
    doc_counts: dict[str, int] = {}
    for row in rows:
        document = row.get("doc_no")
        if isinstance(document, str) and document:
            doc_counts[document] = doc_counts.get(document, 0) + 1
    items = []
    for ordinal, row in enumerate(rows, start=1):
        document = row.get("doc_no")
        flags = []
        if row.get("is_multisale") is True:
            flags.append("multisale")
        if isinstance(document, str) and doc_counts.get(document, 0) > 1:
            flags.append("repeated_document")
        items.append(
            {
                "ordinal": ordinal,
                "capture_sha256": CAPTURE_SHA256,
                "row_sha256": row_hash(row),
                "priority_flags": flags,
                "source_row": row,
            }
        )
    return b"".join(
        (json.dumps(item, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
        for item in items
    )


def _manifest(directory: Path, rows: list[dict]) -> dict:
    path = _file(directory, "manifest.json")
    try:
        manifest = json.loads(_bounded(path, MAX_MANIFEST_BYTES))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("Private Cook review manifest is malformed") from error
    if (
        not isinstance(manifest, dict)
        or set(manifest)
        != {"ledger_id", "protocol", "capture_sha256", "worklist_sha256", "created_at"}
        or not isinstance(manifest["ledger_id"], str)
        or not CODE.fullmatch(manifest["ledger_id"])
        or manifest["protocol"] != PROTOCOL
        or manifest["capture_sha256"] != CAPTURE_SHA256
        or manifest["worklist_sha256"] != _hash(_worklist(rows))
    ):
        raise ValueError("Private Cook review manifest identity mismatch")
    created_at = _utc(manifest["created_at"])
    if created_at < _utc(CAPTURE_COMPLETED_AT) or created_at > datetime.now(
        timezone.utc
    ):
        raise ValueError("Private Cook review manifest creation time is invalid")
    worklist_path = _file(directory, "worklist.jsonl")
    if (
        _hash(_bounded(worklist_path, MAX_WORKLIST_BYTES))
        != manifest["worklist_sha256"]
    ):
        raise ValueError("Private Cook worklist hash mismatch")
    return manifest


def _price_state(row: dict) -> str:
    value = row.get("sale_price")
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", value):
        return "invalid"
    try:
        price = Decimal(value)
    except InvalidOperation:
        return "invalid"
    if not price.is_finite() or price < 0:
        return "invalid"
    return "reported_zero" if price == 0 else "reported_positive"


def _evidence(raw: object, row: dict, reviewed_at: datetime) -> dict[str, dict]:
    if not isinstance(raw, list) or not raw or len(raw) > 30:
        raise ValueError("Review needs bounded evidence items")
    items = {}
    for item in raw:
        required = {"evidence_id", "kind", "reference", "observed_at"}
        allowed = required | {"attempted_at", "target", "outcome"}
        if (
            not isinstance(item, dict)
            or not required <= set(item)
            or not set(item) <= allowed
        ):
            raise ValueError("Invalid Cook evidence fields")
        identifier, kind, reference = (
            item["evidence_id"],
            item["kind"],
            item["reference"],
        )
        if (
            not isinstance(identifier, str)
            or not CODE.fullmatch(identifier)
            or identifier in items
            or not isinstance(kind, str)
            or kind not in EVIDENCE_KINDS
        ):
            raise ValueError("Invalid Cook evidence identity or kind")
        observed_at = _utc(item["observed_at"])
        if observed_at > reviewed_at:
            raise ValueError("Cook evidence postdates review")
        if (
            not isinstance(reference, str)
            or len(reference) > 2048
            or any(ord(char) < 32 for char in reference)
        ):
            raise ValueError("Invalid Cook evidence reference")
        if kind == "source_record":
            if reference != "sha256:" + row_hash(row):
                raise ValueError("Source evidence must cite pinned row")
            if observed_at < _utc(CAPTURE_COMPLETED_AT):
                raise ValueError("Source row evidence predates frozen capture")
        elif kind == "official_documentation":
            if reference != "sha256:" + SOURCE_METADATA_SHA256:
                raise ValueError("Official definition must cite pinned metadata bytes")
            if observed_at < _utc(CAPTURE_COMPLETED_AT):
                raise ValueError("Official metadata evidence predates frozen capture")
        else:
            try:
                url = urlsplit(reference)
                valid_url = (
                    url.scheme == "https"
                    and bool(url.hostname)
                    and not url.username
                    and not url.password
                    and not url.fragment
                )
            except ValueError as error:
                raise ValueError("Invalid Cook evidence HTTPS reference") from error
            if not valid_url:
                raise ValueError("Invalid Cook evidence HTTPS reference")
        if kind == "unavailable_attempt":
            if (
                not isinstance(item.get("target"), str)
                or item["target"] not in ATTEMPT_TARGETS
                or not isinstance(item.get("outcome"), str)
                or item["outcome"] not in ATTEMPT_OUTCOMES
                or "attempted_at" not in item
            ):
                raise ValueError("Cook access attempt needs target, outcome and time")
            if _utc(item["attempted_at"]) > min(_utc(item["observed_at"]), reviewed_at):
                raise ValueError("Cook access attempt postdates observation or review")
        elif set(item) != required:
            raise ValueError("Unexpected Cook evidence fields")
        items[identifier] = item
    return items


def _rubric(raw: object, evidence: dict[str, dict], row: dict) -> None:
    if not isinstance(raw, dict) or not raw or not set(raw) <= set(DIMENSIONS):
        raise ValueError("Invalid Cook review rubric dimensions")
    for dimension, detail in raw.items():
        if not isinstance(detail, dict) or set(detail) != {
            "value",
            "evidence_ids",
            "limitation",
        }:
            raise ValueError("Invalid Cook review finding")
        value, references, limitation = (
            detail["value"],
            detail["evidence_ids"],
            detail["limitation"],
        )
        if (
            not isinstance(value, str)
            or not isinstance(references, list)
            or not references
            or any(not isinstance(ref, str) for ref in references)
            or len(references) != len(set(references))
            or any(ref not in evidence for ref in references)
        ):
            raise ValueError("Invalid Cook review finding references")
        if value == "unknown":
            if (
                not isinstance(limitation, str)
                or not limitation.strip()
                or len(limitation) > 2000
            ):
                raise ValueError("Unknown Cook finding needs bounded limitation")
            continue
        if limitation is not None:
            raise ValueError("Affirmative Cook finding has unexpected limitation")
        if dimension != "published_price_state" or value != _price_state(row):
            raise ValueError("Affirmative Cook v1 finding is unsupported")
        kinds = {evidence[ref]["kind"] for ref in references}
        if not {"source_record", "official_documentation"} <= kinds:
            raise ValueError("Published price state needs row and official definition")


def validate_entry(
    raw: object,
    row: dict,
    ledger_id: str,
    prior: list[dict],
    created_at: str | None = None,
) -> dict:
    """Validate an entry against the exact pinned row and its prior revisions."""
    if not isinstance(raw, dict) or set(raw) != ENTRY_FIELDS:
        raise ValueError("Invalid Cook review entry fields")
    if (
        raw["ledger_id"] != ledger_id
        or raw["protocol"] != PROTOCOL
        or raw["capture_sha256"] != CAPTURE_SHA256
        or raw["row_sha256"] != row_hash(row)
        or type(raw["ordinal"]) is not int
        or raw["ordinal"] < 1
    ):
        raise ValueError("Cook review entry identity mismatch")
    for field in ("entry_id", "reviewer_code"):
        if not isinstance(raw[field], str) or not CODE.fullmatch(raw[field]):
            raise ValueError("Invalid Cook review code")
    if not isinstance(raw["review_status"], str) or raw["review_status"] not in {
        "partial",
        "complete",
    }:
        raise ValueError("Invalid Cook review status")
    if type(raw["attested"]) is not bool or raw["attested"] != (
        raw["review_status"] == "complete"
    ):
        raise ValueError("Cook review attestation mismatch")
    reviewed_at = _utc(raw["reviewed_at"])
    if reviewed_at > datetime.now(timezone.utc):
        raise ValueError("Cook review time is in the future")
    if reviewed_at < _utc(CAPTURE_COMPLETED_AT):
        raise ValueError("Cook review predates frozen capture")
    if created_at is not None and reviewed_at < _utc(created_at):
        raise ValueError("Cook review predates private ledger initialization")
    evidence = _evidence(raw["evidence"], row, reviewed_at)
    _rubric(raw["rubric"], evidence, row)
    if raw["review_status"] == "complete":
        if set(raw["rubric"]) != set(DIMENSIONS):
            raise ValueError("Complete Cook review requires full rubric")
        price = raw["rubric"]["published_price_state"]
        price_kinds = {evidence[ref]["kind"] for ref in price["evidence_ids"]}
        if (
            price["value"] != _price_state(row)
            or not {"source_record", "official_documentation"} <= price_kinds
        ):
            raise ValueError("Complete Cook review needs source and field definition")
        relevant = {
            "economic_transfer_scope",
            "repeated_consideration",
            "sale_date_vs_recording",
        }
        attempts = {
            key
            for key, item in evidence.items()
            if item["kind"] == "unavailable_attempt"
            and item["target"] == "recorded_instrument"
        }
        if not attempts or not any(
            set(raw["rubric"][name]["evidence_ids"]) & attempts for name in relevant
        ):
            raise ValueError(
                "Complete Cook v1 review needs a relevant instrument attempt"
            )
    if (
        type(raw["revision"]) is not int
        or raw["revision"] != len(prior) + 1
        or raw["supersedes_entry_id"] != (prior[-1]["entry_id"] if prior else None)
    ):
        raise ValueError("Cook review revision does not continue history")
    if any(raw["entry_id"] == entry["entry_id"] for entry in prior):
        raise ValueError("Cook review entry ID already exists")
    if prior and reviewed_at < _utc(prior[-1]["reviewed_at"]):
        raise ValueError("Cook review revision predates prior revision")
    return raw


def _history(
    content: bytes, rows: list[dict], ledger_id: str, created_at: str
) -> tuple[list[dict], dict[int, dict]]:
    entries = _json_lines(content)
    latest: dict[int, dict] = {}
    by_ordinal: dict[int, list[dict]] = {}
    entry_ids = set()
    for entry in entries:
        ordinal = entry.get("ordinal")
        if type(ordinal) is not int or not 1 <= ordinal <= len(rows):
            raise ValueError("Cook review ordinal outside pinned sample")
        if not isinstance(entry.get("entry_id"), str) or entry["entry_id"] in entry_ids:
            raise ValueError("Duplicate Cook review entry ID")
        validate_entry(
            entry,
            rows[ordinal - 1],
            ledger_id,
            by_ordinal.get(ordinal, []),
            created_at,
        )
        by_ordinal.setdefault(ordinal, []).append(entry)
        latest[ordinal] = entry
        entry_ids.add(entry["entry_id"])
    return entries, latest


def _summary(content: bytes, latest: dict[int, dict]) -> dict:
    complete = sum(entry["review_status"] == "complete" for entry in latest.values())
    partial = sum(entry["review_status"] == "partial" for entry in latest.values())
    return {
        "protocol": PROTOCOL,
        "capture_sha256": CAPTURE_SHA256,
        "sample_count": SAMPLE_COUNT,
        "complete_records": complete,
        "partial_records": partial,
        "unreviewed_records": SAMPLE_COUNT - complete - partial,
        "certified_sale_labels": 0,
        "historical_asof_eligible": False,
        "ledger_sha256": _hash(content),
    }


def init_review() -> dict:
    """Create one private worklist and ledger; never reuse an orphan."""
    rows = _capture_rows()
    directory = _review_dir(initialize=True)
    ledger = _file(directory, "reviews.jsonl", must_exist=False)
    with private_io.exclusive_lock(ledger, directory):
        worklist = _worklist(rows)
        if len(worklist) > MAX_WORKLIST_BYTES:
            raise ValueError("Cook private worklist exceeds size cap")
        private_io.new_file(
            _file(directory, "worklist.jsonl", must_exist=False), worklist
        )
        manifest = {
            "ledger_id": "cook-" + uuid4().hex,
            "protocol": PROTOCOL,
            "capture_sha256": CAPTURE_SHA256,
            "worklist_sha256": _hash(worklist),
            "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        private_io.new_file(
            _file(directory, "manifest.json", must_exist=False),
            (json.dumps(manifest, sort_keys=True) + "\n").encode("utf-8"),
        )
        private_io.new_file(ledger, b"")
    return _summary(b"", {})


def _state() -> tuple[Path, list[dict], str, str]:
    rows = _capture_rows()
    directory = _review_dir(initialize=False)
    manifest = _manifest(directory, rows)
    ledger = _file(directory, "reviews.jsonl")
    return ledger, rows, manifest["ledger_id"], manifest["created_at"]


def summarize_reviews() -> dict:
    """Replay the ledger and produce a private-information-free count summary."""
    ledger, rows, ledger_id, created_at = _state()
    with private_io.exclusive_lock(ledger, ledger.parent):
        content = _bounded(ledger, MAX_LEDGER_BYTES)
        _, latest = _history(content, rows, ledger_id, created_at)
        return _summary(content, latest)


def append_review(entry: dict, *, expected_ledger_sha256: str) -> dict:
    """Compare-and-swap append with complete-history validation and atomic write."""
    ledger, rows, ledger_id, created_at = _state()
    with private_io.exclusive_lock(ledger, ledger.parent):
        content = _bounded(ledger, MAX_LEDGER_BYTES)
        entries, _ = _history(content, rows, ledger_id, created_at)
        if (
            not isinstance(expected_ledger_sha256, str)
            or not HEX64.fullmatch(expected_ledger_sha256)
            or expected_ledger_sha256 != _hash(content)
        ):
            raise ValueError("Cook review prior ledger hash mismatch")
        ordinal = entry.get("ordinal") if isinstance(entry, dict) else None
        if type(ordinal) is not int or not 1 <= ordinal <= len(rows):
            raise ValueError("Cook review ordinal outside pinned sample")
        if not isinstance(entry.get("entry_id"), str) or entry["entry_id"] in {
            prior["entry_id"] for prior in entries
        }:
            raise ValueError("Duplicate Cook review entry ID")
        prior = [old for old in entries if old["ordinal"] == ordinal]
        validate_entry(entry, rows[ordinal - 1], ledger_id, prior, created_at)
        line = (json.dumps(entry, sort_keys=True, ensure_ascii=False) + "\n").encode(
            "utf-8"
        )
        updated = content + line
        if len(updated) > MAX_LEDGER_BYTES:
            raise ValueError("Cook review ledger would exceed size cap")
        _, latest = _history(updated, rows, ledger_id, created_at)
        private_io.atomic_replace(ledger, updated)
        return _summary(updated, latest)


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline private Cook source review")
    parser.add_argument("action", choices=("init", "append", "summary"))
    parser.add_argument(
        "--entry", type=Path, help="Private review entry JSON for append"
    )
    parser.add_argument("--expected-ledger-sha256")
    parser.add_argument(
        "--output", type=Path, required=True, help="New aggregate-only JSON"
    )
    options = parser.parse_args(arguments)
    directory = RAW_ROOT / REVIEW_NAME
    inputs = (
        directory / "manifest.json",
        directory / "worklist.jsonl",
        directory / "reviews.jsonl",
    )
    if options.action == "append":
        if options.entry is None or options.expected_ledger_sha256 is None:
            parser.error("append needs --entry and --expected-ledger-sha256")
        inputs = (*inputs, options.entry)
    elif options.entry is not None or options.expected_ledger_sha256 is not None:
        parser.error("entry and expected ledger hash belong to append only")
    try:
        private_io.summary_target(options.output, inputs)
        if options.action == "init":
            result = init_review()
        elif options.action == "summary":
            result = summarize_reviews()
        else:
            _review_dir(initialize=False)
            entry_path = private_io.private_path(
                options.entry, directory, must_exist=True
            )
            try:
                entry = json.loads(_bounded(entry_path, MAX_ENTRY_BYTES))
            except (UnicodeError, json.JSONDecodeError) as error:
                raise ValueError("Private Cook review entry is malformed") from error
            result = append_review(
                entry, expected_ledger_sha256=options.expected_ledger_sha256
            )
        private_io.write_summary_new(options.output, result, inputs)
    except (OSError, ValueError):
        print("Cook review operation failed; inspect private state", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
