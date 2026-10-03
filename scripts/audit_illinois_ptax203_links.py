"""Offline, private Cook–PTAX review triage; never certifies sale labels."""

from __future__ import annotations

import argparse
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
from pathlib import Path
import re
import sys

from scripts import private_review_io as private_io
from scripts import probe_illinois_ptax203 as probe
from scripts import review_cook_sales_sample as cook


PROTOCOL = "illinois-ptax203-offline-link-v1"
RAW_ROOT = Path(__file__).resolve().parents[1] / "data" / "raw"
SOURCE_RUN_NAME = f"ptax-link-v1-{cook.CAPTURE_SHA256[:16]}"
RUN_NAME = f"ptax-offline-v1-{cook.CAPTURE_SHA256[:16]}"
PINNED_RESPONSE_SET_SHA256 = (
    "69d86b7fb9c221dee662d49ebc01b94ef26f5e2862a0c9d26afb887f997cd05a"
)
EXPECTED_COOK_ROWS = 100
EXPECTED_DOCUMENTS = 83
EXPECTED_DECLARATIONS = 80
EXPECTED_REQUESTS = 20
MAX_PAIRS = 500
MAX_WORKLIST_BYTES = 512 * 1024
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
MONEY = re.compile(r"-?[0-9]+(?:\.[0-9]+)?\Z")
PIN = re.compile(r"[0-9][0-9 -]{0,63}\Z")
COUNT = re.compile(r"[0-9]+\Z")
# The frozen v1 diagnostic recognizes only these explicit neighboring county names.
# Every other non-Cook token stays unknown until a sourced code list is registered.
KNOWN_NON_COOK_COUNTIES = frozenset({"dupage", "kane", "lake", "will"})


def _encoded(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, ensure_ascii=False) + "\n").encode(
        "utf-8"
    )


def _hash(content: bytes) -> str:
    return sha256(content).hexdigest()


def _value_state(value: object, *, pattern: re.Pattern[str] | None = None) -> str:
    if value is None or value == "":
        return "missing"
    if not isinstance(value, str) or len(value) > 256:
        return "malformed"
    if pattern is not None and not pattern.fullmatch(value):
        return "malformed"
    return "present"


def _money(value: object) -> tuple[str, Decimal | None]:
    state = _value_state(value, pattern=MONEY)
    if state != "present":
        return state, None
    try:
        amount = Decimal(value)
    except InvalidOperation:
        return "malformed", None
    return ("present", amount) if amount.is_finite() else ("malformed", None)


def _money_comparison(left: object, right: object) -> str:
    left_state, left_amount = _money(left)
    right_state, right_amount = _money(right)
    if "missing" in (left_state, right_state):
        return "missing"
    if "malformed" in (left_state, right_state):
        return "malformed"
    if left_amount <= 0 or right_amount <= 0:
        return "nonpositive"
    return "same" if left_amount == right_amount else "different"


def _personal_amount_state(value: object) -> str:
    state, amount = _money(value)
    if state != "present":
        return state
    return "nonpositive" if amount < 0 else "present"


def _day(value: object) -> tuple[str, date | None]:
    state = _value_state(value)
    if state != "present":
        return state, None
    try:
        parsed = (
            date.fromisoformat(value)
            if len(value) == 10
            else datetime.fromisoformat(value.replace("Z", "+00:00")).date()
        )
    except ValueError:
        return "malformed", None
    return "present", parsed


def _date_comparison(left: object, right: object) -> str:
    left_state, left_day = _day(left)
    right_state, right_day = _day(right)
    if "missing" in (left_state, right_state):
        return "missing"
    if "malformed" in (left_state, right_state):
        return "malformed"
    return "same" if left_day == right_day else "different"


def _instrument_month(value: object) -> str:
    state, _ = _day(value)
    return "present_coarse" if state == "present" else state


def _instrument_month_comparison(cook_date: object, instrument_date: object) -> str:
    """Compare two reported calendar months, without treating either as close date."""
    cook_state, cook_day = _day(cook_date)
    instrument_state, instrument_day = _day(instrument_date)
    if "missing" in (cook_state, instrument_state):
        return "missing"
    if "malformed" in (cook_state, instrument_state):
        return "malformed"
    return (
        "same_month"
        if (cook_day.year, cook_day.month)
        == (instrument_day.year, instrument_day.month)
        else "different_month"
    )


def _county(value: object) -> str:
    state = _value_state(value)
    if state != "present" or not isinstance(value, str):
        return "unknown"
    text = value.strip().casefold().removesuffix(" county")
    if text == "cook":
        return "same"
    return "conflict" if text in KNOWN_NON_COOK_COUNTIES else "unknown"


def _pin(left: object, right: object, additional: object) -> str:
    left_state = _value_state(left, pattern=PIN)
    right_state = _value_state(right, pattern=PIN)
    if "missing" in (left_state, right_state):
        return "missing"
    if "malformed" in (left_state, right_state):
        return "malformed"
    if left == right:
        return "same"
    if additional is True:
        return "possible_nonprimary"
    if additional is False:
        return "different"
    return "unequal_primary_unknown_secondary"


def _boolean_state(value: object) -> str:
    if value is None or value == "":
        return "missing"
    if type(value) is not bool:
        return "malformed"
    return "reported_true" if value else "reported_false"


def _parcel_scope(cook_row: dict, ptax_row: dict) -> str:
    states = (
        _value_state(cook_row.get("num_parcels_sale"), pattern=COUNT),
        _value_state(ptax_row.get("line_2_total_parcels"), pattern=COUNT),
        _boolean_state(cook_row.get("is_multisale")),
        _boolean_state(ptax_row.get("line_3_additional_pins")),
    )
    if "malformed" in states:
        return "malformed"
    values = (cook_row.get("num_parcels_sale"), ptax_row.get("line_2_total_parcels"))
    if any(
        state == "present" and int(value) < 1
        for state, value in zip(states[:2], values)
    ):
        return "malformed"
    if (
        any(
            state == "present" and int(value) > 1
            for state, value in zip(states[:2], values)
        )
        or states[2] == "reported_true"
        or states[3] == "reported_true"
    ):
        return "multi_parcel_indicator"
    return "unknown" if "missing" in states else "single_reported"


def _candidate(cook_row: dict, declaration: dict) -> dict:
    related = _boolean_state(declaration.get("line_10b_sale_between_related"))
    return {
        "declaration_id": declaration["declaration_id"],
        "ptax_row_sha256": cook.row_hash(declaration),
        "source_row": declaration,
        "county_state": _county(declaration.get("line_1_county")),
        "pin_state": _pin(
            cook_row.get("pin"),
            declaration.get("line_1_primary_pin"),
            declaration.get("line_3_additional_pins"),
        ),
        "parcel_scope_state": _parcel_scope(cook_row, declaration),
        "line_11_vs_cook_state": _money_comparison(
            cook_row.get("sale_price"), declaration.get("line_11_full_consideration")
        ),
        "line_12_state": _personal_amount_state(
            declaration.get("line_12a_total_personal")
        ),
        "line_13_vs_cook_state": _money_comparison(
            cook_row.get("sale_price"), declaration.get("line_13_net_consideration")
        ),
        "recorded_date_state": _date_comparison(
            cook_row.get("sale_date"), declaration.get("date_recorded")
        ),
        "instrument_month_state": _instrument_month(
            declaration.get("line_4_instrument_date")
        ),
        "instrument_month_vs_cook_state": _instrument_month_comparison(
            cook_row.get("sale_date"), declaration.get("line_4_instrument_date")
        ),
        "related_party_state": related,
        "status_code_state": _value_state(declaration.get("status")),
        "use_code_state": _value_state(declaration.get("line_8_current_use")),
        "instrument_code_state": _value_state(
            declaration.get("line_5_instrument_type")
        ),
    }


def _priority(candidates: list[dict]) -> list[str]:
    if not candidates:
        return ["missing_link"]
    flags = ["multiple_links"] if len(candidates) > 1 else []
    if any(candidate["county_state"] == "conflict" for candidate in candidates):
        flags.append("county_conflict")
    if any(
        candidate["pin_state"]
        in ("different", "possible_nonprimary", "unequal_primary_unknown_secondary")
        for candidate in candidates
    ):
        flags.append("pin_identity_review")
    if any(
        candidate["parcel_scope_state"] == "multi_parcel_indicator"
        for candidate in candidates
    ):
        flags.append("multi_parcel_scope")
    if any(
        candidate["line_11_vs_cook_state"] == "different" for candidate in candidates
    ):
        flags.append("price_disagreement")
    if any(candidate["recorded_date_state"] == "different" for candidate in candidates):
        flags.append("recorded_date_disagreement")
    unresolved_fields = (
        "county_state",
        "pin_state",
        "parcel_scope_state",
        "line_11_vs_cook_state",
        "line_12_state",
        "line_13_vs_cook_state",
        "recorded_date_state",
        "instrument_month_state",
        "related_party_state",
        "status_code_state",
        "use_code_state",
        "instrument_code_state",
    )
    if any(
        candidate[field] in ("missing", "malformed", "unknown", "nonpositive")
        for candidate in candidates
        for field in unresolved_fields
    ):
        flags.append("unresolved_evidence")
    if any(
        candidate["related_party_state"] == "reported_true"
        or candidate["status_code_state"] == "present"
        or candidate["use_code_state"] == "present"
        or candidate["instrument_code_state"] == "present"
        for candidate in candidates
    ):
        flags.append("unqualified_source_flags")
    return flags


def build_worklist(
    cook_rows: list[dict], ptax_rows: list[dict], *, max_pairs: int = MAX_PAIRS
) -> dict:
    """Build one review item per Cook row and preserve every exact candidate."""
    if (
        not isinstance(cook_rows, list)
        or not isinstance(ptax_rows, list)
        or type(max_pairs) is not int
        or max_pairs < 0
    ):
        raise ValueError("Invalid offline linkage inputs")
    docs: dict[str, list[dict]] = {}
    seen_ids: set[str] = set()
    for declaration in ptax_rows:
        if not isinstance(declaration, dict) or not set(declaration) <= set(
            probe.ROW_FIELDS
        ):
            raise ValueError("Unexpected PTAX source row field")
        identifier = declaration.get("declaration_id")
        document = declaration.get("document_number")
        if (
            not isinstance(identifier, str)
            or not identifier
            or not isinstance(document, str)
            or not document
        ):
            raise ValueError("PTAX source row lacks exact identity")
        if identifier in seen_ids:
            raise ValueError("duplicate PTAX declaration ID")
        seen_ids.add(identifier)
        docs.setdefault(document, []).append(declaration)
    counts: dict[str, int] = {}
    pins: dict[str, set[str]] = {}
    seen_rows: set[str] = set()
    for row in cook_rows:
        if not isinstance(row, dict):
            raise ValueError("Cook source row is malformed")
        document, identifier = row.get("doc_no"), row.get("row_id")
        if (
            not isinstance(document, str)
            or not document
            or not isinstance(identifier, str)
            or not identifier
            or identifier in seen_rows
        ):
            raise ValueError("Cook source row lacks unique exact identity")
        seen_rows.add(identifier)
        counts[document] = counts.get(document, 0) + 1
        pin = row.get("pin")
        if isinstance(pin, str) and pin:
            pins.setdefault(document, set()).add(pin)
    items = []
    links = 0
    for ordinal, row in enumerate(cook_rows, start=1):
        document = row["doc_no"]
        candidates = [
            _candidate(row, declaration) for declaration in docs.get(document, ())
        ]
        links += len(candidates)
        if links > max_pairs:
            raise ValueError("Offline candidate cap exceeded")
        items.append(
            {
                "ordinal": ordinal,
                "cook_row_id": row["row_id"],
                "cook_row_sha256": cook.row_hash(row),
                "source_row": row,
                "document_group_cook_rows": counts[document],
                "document_group_distinct_pins": len(pins.get(document, set())),
                "document_group_declarations": len(docs.get(document, ())),
                "candidates": candidates,
                "priority_flags": _priority(candidates),
            }
        )
    return {
        "items": items,
        "candidate_links": links,
        "selected_cook_rows": len(cook_rows),
        "unique_document_strings": len(counts),
        "returned_declarations": len(ptax_rows),
        "certified_sale_labels": 0,
    }


def _load_sources(source_dir: Path) -> tuple[list[dict], list[dict], dict]:
    """Replay the pinned private captures and read the same verified bytes."""
    source_dir = Path(source_dir)
    if source_dir.name != SOURCE_RUN_NAME:
        raise ValueError("PTAX source capture identity differs")
    info = probe.verify(source_dir)
    if (
        info.get("response_set_sha256") != PINNED_RESPONSE_SET_SHA256
        or info.get("cook_capture_sha256") != cook.CAPTURE_SHA256
        or info.get("selected_cook_rows") != EXPECTED_COOK_ROWS
        or info.get("unique_document_strings") != EXPECTED_DOCUMENTS
        or info.get("returned_declarations") != EXPECTED_DECLARATIONS
        or info.get("request_count") != EXPECTED_REQUESTS
    ):
        raise ValueError("PTAX pinned capture counts or hashes differ")
    cook_rows = cook._capture_rows()
    documents = probe.select_documents(cook_rows)
    selected_pairs = {
        (document, identifier)
        for document, identifiers in documents.items()
        for identifier in identifiers
    }
    selected_ids = {identifier for _, identifier in selected_pairs}
    if (
        len(cook_rows) != cook.SAMPLE_COUNT
        or len(documents) != EXPECTED_DOCUMENTS
        or len(selected_pairs) != EXPECTED_COOK_ROWS
        or len(selected_ids) != EXPECTED_COOK_ROWS
    ):
        raise ValueError("Cook selected document membership differs")
    selected_rows = [
        row
        for row in cook_rows
        if (row.get("doc_no"), row.get("row_id")) in selected_pairs
    ]
    if (
        len(selected_rows) != EXPECTED_COOK_ROWS
        or {(row["doc_no"], row["row_id"]) for row in selected_rows} != selected_pairs
    ):
        raise ValueError("Cook selected row membership differs")
    bodies = []
    for index in range(EXPECTED_REQUESTS):
        cap = (
            probe.MAX_METADATA
            if index in (0, EXPECTED_REQUESTS - 1)
            else (probe.MAX_COUNT if index % 2 else probe.MAX_ROWS)
        )
        bodies.append(
            probe._read_bounded(
                private_io.private_path(
                    source_dir / f"response-{index:02d}.json",
                    source_dir,
                    must_exist=True,
                ),
                cap,
            )
        )
    if (
        _hash(probe._encoded([probe._hash(body) for body in bodies]))
        != PINNED_RESPONSE_SET_SHA256
    ):
        raise ValueError("PTAX response bytes changed after verification")
    ptax_rows = []
    for number, batch in enumerate(probe._batches(documents)):
        count = probe.parse_count(bodies[number * 2 + 1])
        ptax_rows.extend(
            probe.parse_rows(bodies[number * 2 + 2], batch, expected_count=count)
        )
    if len(ptax_rows) != EXPECTED_DECLARATIONS:
        raise ValueError("PTAX declaration count differs")
    return selected_rows, ptax_rows, info


def public_summary(
    cook_sha256: str, response_sha256: str, worklist_sha256: str, queue_size: int
) -> dict:
    if (
        any(
            not isinstance(value, str) or not HEX64.fullmatch(value)
            for value in (cook_sha256, response_sha256, worklist_sha256)
        )
        or type(queue_size) is not int
        or queue_size != EXPECTED_COOK_ROWS
    ):
        raise ValueError("Public aggregate identity differs")
    return {
        "protocol": PROTOCOL,
        "cook_capture_sha256": cook_sha256,
        "response_set_sha256": response_sha256,
        "private_worklist_sha256": worklist_sha256,
        "selected_cook_rows": EXPECTED_COOK_ROWS,
        "unique_document_strings": EXPECTED_DOCUMENTS,
        "returned_declarations": EXPECTED_DECLARATIONS,
        "review_queue_size": queue_size,
        "certified_sale_labels": 0,
        "historical_asof_eligible": False,
        "u0_gate": "PENDING",
        "g_us_gate": "PENDING",
    }


def _private_root() -> Path:
    return probe._private_root()


def _new_run() -> Path:
    root = _private_root()
    directory = root / RUN_NAME
    directory.mkdir(mode=0o700, exist_ok=False)
    private_io.secure_directory(directory)
    private_io.real_directory(directory, root)
    private_io.verify_acl(directory)
    return directory


def _worklist_bytes(result: dict) -> bytes:
    content = b"".join(_encoded(item) for item in result["items"])
    if len(content) > MAX_WORKLIST_BYTES:
        raise ValueError("Private worklist cap exceeded")
    return content


def _manifest(result: dict, info: dict, content: bytes) -> dict:
    return {
        "protocol": PROTOCOL,
        "cook_capture_sha256": info["cook_capture_sha256"],
        "response_set_sha256": info["response_set_sha256"],
        "worklist_sha256": _hash(content),
        "candidate_links": result["candidate_links"],
        "review_queue_size": len(result["items"]),
        "certified_sale_labels": 0,
    }


def _public_destination(output: Path, source_dir: Path) -> Path:
    target = Path(output)
    parent = target.parent.resolve()
    for forbidden in (RAW_ROOT, probe.PRIVATE_ROOT):
        if parent.is_relative_to(forbidden.resolve()):
            raise ValueError("Public output cannot be inside private raw data")
    return private_io.summary_target(target, (Path(source_dir) / "selection.json",))


def run(source_dir: Path, output: Path) -> dict:
    """Create a private diagnostic once, then publish only the allowed summary."""
    _public_destination(output, source_dir)
    cook_rows, ptax_rows, info = _load_sources(source_dir)
    result = build_worklist(cook_rows, ptax_rows)
    if (
        result["selected_cook_rows"] != EXPECTED_COOK_ROWS
        or result["unique_document_strings"] != EXPECTED_DOCUMENTS
        or result["returned_declarations"] != EXPECTED_DECLARATIONS
    ):
        raise ValueError("Frozen offline input denominators differ")
    content = _worklist_bytes(result)
    manifest = _manifest(result, info, content)
    directory = _new_run()
    private_io.new_file(
        private_io.private_path(directory / "worklist.jsonl", directory), content
    )
    private_io.new_file(
        private_io.private_path(directory / "complete.json", directory),
        _encoded(manifest),
    )
    summary = verify(directory, source_dir)
    private_io.write_summary_new(
        output, summary, (Path(source_dir) / "selection.json",)
    )
    return summary


def verify(directory: Path, source_dir: Path) -> dict:
    """Recompute the worklist from the frozen captures and compare exact bytes."""
    root = _private_root()
    directory = Path(directory)
    private_io.real_directory(directory, root)
    private_io.verify_acl(directory)
    if not private_io.same_path(directory, root / RUN_NAME):
        raise ValueError("Offline diagnostic directory identity differs")
    if {path.name for path in directory.iterdir()} != {
        "worklist.jsonl",
        "complete.json",
    }:
        raise ValueError("Offline diagnostic files differ")
    cook_rows, ptax_rows, info = _load_sources(source_dir)
    result = build_worklist(cook_rows, ptax_rows)
    expected = _worklist_bytes(result)
    actual = probe._read_bounded(
        private_io.private_path(
            directory / "worklist.jsonl", directory, must_exist=True
        ),
        MAX_WORKLIST_BYTES,
    )
    if actual != expected:
        raise ValueError("Offline worklist differs from pinned captures")
    manifest = json.loads(
        probe._read_bounded(
            private_io.private_path(
                directory / "complete.json", directory, must_exist=True
            ),
            4096,
        )
    )
    if manifest != _manifest(result, info, expected):
        raise ValueError("Offline completion manifest differs")
    return public_summary(
        info["cook_capture_sha256"],
        info["response_set_sha256"],
        _hash(expected),
        len(result["items"]),
    )


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Offline, private Cook–PTAX review triage"
    )
    parser.add_argument("action", choices=("run", "verify"))
    parser.add_argument("--source-run-dir", required=True, type=Path)
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--output", type=Path)
    options = parser.parse_args(arguments)
    try:
        if options.action == "run":
            if options.run_dir or not options.output:
                parser.error("run needs --output and takes no --run-dir")
            summary = run(options.source_run_dir, options.output)
        else:
            if not options.run_dir or not options.output:
                parser.error("verify needs --run-dir and --output")
            _public_destination(options.output, options.source_run_dir)
            summary = verify(options.run_dir, options.source_run_dir)
            private_io.write_summary_new(
                options.output, summary, (options.source_run_dir / "selection.json",)
            )
        print(json.dumps(summary, sort_keys=True))
        return 0
    except (OSError, ValueError):
        print("Offline PTAX diagnostic failed; inspect private state", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
