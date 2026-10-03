"""Private, offline Cook / Additional PIN triage; no sale-label certification."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import sys

from scripts import audit_illinois_ptax203_links as prior
from scripts import private_review_io as private_io
from scripts import probe_illinois_additional_pins as source


PROTOCOL = "illinois-additional-pin-offline-v3"
RUN_NAME = f"ptax-additional-offline-v3-{source.COOK_SHA256[:16]}"
PRIOR_WORKLIST_SHA256 = (
    "7981f32fe1970afcb2c20768271c5c0c58dc05ff9a3905fe94981aeef9f8ac8e"
)
ADDITIONAL_RESPONSE_SET_SHA256 = (
    "5b9d230f76f66d33b024009ee1c81aec18d5318b0cd5c748752ddf4300fba013"
)
PRIOR_AGGREGATE = (
    Path(__file__).resolve().parents[1]
    / "runs"
    / "u0-illinois-ptax203-offline-v1-20261003T035947Z"
    / "aggregate.json"
)
MAX_PAIRS = 500
MAX_REFERENCES = 5000
MAX_WORKLIST_BYTES = 1024 * 1024
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
BARE_PIN = re.compile(r"[0-9]{14}\Z")
DISPLAY_PIN = re.compile(r"[0-9]{2}-[0-9]{2}-[0-9]{3}-[0-9]{3}-[0-9]{4}\Z")


def _encoded(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n").encode()


def _hash(content: bytes) -> str:
    return sha256(content).hexdigest()


def _pin(value: object) -> tuple[str, str | None]:
    if value is None or value == "":
        return "missing", None
    if not isinstance(value, str):
        return "unknown", None
    if value.isascii() and value.lower() == "row only":
        return "right_of_way", None
    prefix = ""
    if value.startswith("PT "):
        prefix, value = "part_parcel", value[3:]
    elif value.startswith("PT"):
        prefix, value = "part_parcel", value[2:]
    if BARE_PIN.fullmatch(value):
        return prefix or "bare", value
    if DISPLAY_PIN.fullmatch(value):
        return prefix or "display", value.replace("-", "")
    return "unknown", None


def pin_relation(cook_pin: object, other_pin: object) -> str:
    """Compare only the frozen ASCII PIN shapes, without repairing source text."""
    left, left_key = _pin(cook_pin)
    right, right_key = _pin(other_pin)
    if "missing" in (left, right):
        return "missing"
    if "right_of_way" in (left, right):
        return "right_of_way"
    if left_key is None or right_key is None:
        return "unknown"
    if "part_parcel" in (left, right):
        return "part_parcel_lead" if left_key == right_key else "unknown"
    if left_key != right_key:
        return "valid_unequal"
    return "raw_exact" if cook_pin == other_pin else "display_equivalent"


def _observations(rows: list[dict], declaration_ids: set[str]) -> dict[str, list[dict]]:
    if not isinstance(rows, list) or len(rows) > source.MAX_TOTAL_ROWS:
        raise ValueError("Additional observation cap exceeded")
    grouped: dict[str, list[dict]] = {identifier: [] for identifier in declaration_ids}
    for ordinal, row in enumerate(rows, start=1):
        if not isinstance(row, dict) or not set(row) <= set(source.ROW_FIELDS):
            raise ValueError("Additional observation fields differ")
        identifier = row.get("declaration_id")
        if not isinstance(identifier, str) or identifier not in grouped:
            raise ValueError("Additional observation outside frozen declarations")
        grouped[identifier].append(
            {
                "ordinal": ordinal,
                "row_sha256": _hash(_encoded(row)),
                "pin": row.get("pin"),
            }
        )
    return grouped


def _candidate(cook_pin: object, declaration: dict, rows: list[dict]) -> dict:
    primary = declaration.get("line_1_primary_pin")
    pin_values = [_encoded(row["pin"]) for row in rows]
    hashes = [row["row_sha256"] for row in rows]
    per_pin_hashes: dict[bytes, set[str]] = {}
    for row, encoded_pin in zip(rows, pin_values):
        per_pin_hashes.setdefault(encoded_pin, set()).add(row["row_sha256"])
    references = [
        {
            "ordinal": row["ordinal"],
            "row_sha256": row["row_sha256"],
            "relation": pin_relation(cook_pin, row["pin"]),
        }
        for row in rows
    ]
    flags = []
    if any(
        pin_relation(primary, row["pin"]) in ("raw_exact", "display_equivalent")
        for row in rows
    ):
        flags.append("primary_and_additional_equality")
    if len(hashes) != len(set(hashes)):
        flags.append("duplicate_observation")
    if any(len(values) > 1 for values in per_pin_hashes.values()):
        flags.append("repeated_pin_distinct_rows")
    if len(set(pin_values)) > 1:
        flags.append("multiple_distinct_additional_pins")
    line3 = declaration.get("line_3_additional_pins")
    if line3 is True and not rows:
        flags.append("line3_true_zero_rows")
    if line3 is False and rows:
        flags.append("line3_false_with_rows")
    line2 = declaration.get("line_2_total_parcels")
    if line2 == "1" and rows:
        flags.append("line2_single_with_rows")
    return {
        "declaration_id": declaration["declaration_id"],
        "primary_relation": pin_relation(cook_pin, primary),
        "additional_observation_count": len(rows),
        "additional_distinct_raw_pin_count": len(set(pin_values)),
        "additional_duplicate_observation_count": len(hashes) - len(set(hashes)),
        "additional_observations": references,
        "review_flags": flags,
    }


def build_worklist(
    previous_items: list[dict],
    declarations: list[dict],
    additional_rows: list[dict],
    *,
    max_pairs: int = MAX_PAIRS,
    max_references: int = MAX_REFERENCES,
) -> dict:
    """Retain one item per Cook row and every Additional source observation."""
    if (
        not isinstance(previous_items, list)
        or not isinstance(declarations, list)
        or type(max_pairs) is not int
        or type(max_references) is not int
        or min(max_pairs, max_references) < 0
    ):
        raise ValueError("Invalid offline diagnostic inputs")
    by_id: dict[str, dict] = {}
    for row in declarations:
        if not isinstance(row, dict) or not set(row) <= set(prior.probe.ROW_FIELDS):
            raise ValueError("PTAX declaration fields differ")
        identifier = row.get("declaration_id")
        if not isinstance(identifier, str) or not identifier or identifier in by_id:
            raise ValueError("PTAX declaration identity differs")
        by_id[identifier] = row
    grouped = _observations(additional_rows, set(by_id))
    seen_cook: set[str] = set()
    items = []
    pairs = references = 0
    for ordinal, item in enumerate(previous_items, start=1):
        if not isinstance(item, dict) or item.get("ordinal") != ordinal:
            raise ValueError("Prior Cook worklist ordinal differs")
        cook_id = item.get("cook_row_id")
        cook_row = item.get("source_row")
        candidates = item.get("candidates")
        if (
            not isinstance(cook_id, str)
            or not cook_id
            or cook_id in seen_cook
            or not isinstance(cook_row, dict)
            or cook_row.get("row_id") != cook_id
            or not isinstance(candidates, list)
        ):
            raise ValueError("Prior Cook worklist identity differs")
        seen_cook.add(cook_id)
        candidate_ids = [
            row.get("declaration_id") for row in candidates if isinstance(row, dict)
        ]
        if (
            len(candidate_ids) != len(candidates)
            or not all(isinstance(identifier, str) for identifier in candidate_ids)
            or len(set(candidate_ids)) != len(candidate_ids)
        ):
            raise ValueError("Prior candidate identity differs")
        if any(identifier not in by_id for identifier in candidate_ids):
            raise ValueError("Prior candidate outside frozen declarations")
        if any(
            by_id[identifier]["document_number"] != cook_row.get("doc_no")
            for identifier in candidate_ids
        ):
            raise ValueError("Prior exact document relation differs")
        pairs += len(candidate_ids)
        references += sum(len(grouped[identifier]) for identifier in candidate_ids)
        if pairs > max_pairs or references > max_references:
            raise ValueError("Offline candidate or observation reference cap exceeded")
        flags = []
        if item.get("document_group_cook_rows", 0) > 1:
            flags.append("repeated_cook_document")
        if len(candidate_ids) > 1:
            flags.append("multiple_declarations")
        items.append(
            {
                "ordinal": ordinal,
                "cook_row_id": cook_id,
                "prior_worklist_item_sha256": _hash(_encoded(item)),
                "candidates": [
                    _candidate(
                        cook_row.get("pin"), by_id[identifier], grouped[identifier]
                    )
                    for identifier in candidate_ids
                ],
                "review_flags": flags,
            }
        )
    return {
        "items": items,
        "candidate_pairs": pairs,
        "observation_references": references,
        "certified_sale_labels": 0,
    }


def public_summary(
    cook_hash: str,
    ptax_hash: str,
    additional_hash: str,
    prior_hash: str,
    worklist_hash: str,
) -> dict:
    if any(
        not isinstance(value, str) or not HEX64.fullmatch(value)
        for value in (cook_hash, ptax_hash, additional_hash, prior_hash, worklist_hash)
    ):
        raise ValueError("Public summary input hash differs")
    return {
        "protocol": PROTOCOL,
        "cook_capture_sha256": cook_hash,
        "ptax_response_set_sha256": ptax_hash,
        "additional_response_set_sha256": additional_hash,
        "prior_worklist_sha256": prior_hash,
        "private_worklist_sha256": worklist_hash,
        "selected_cook_rows": prior.EXPECTED_COOK_ROWS,
        "unique_document_strings": prior.EXPECTED_DOCUMENTS,
        "returned_declarations": prior.EXPECTED_DECLARATIONS,
        "certified_sale_labels": 0,
        "historical_asof_eligible": False,
        "u0_gate": "PENDING",
        "g_us_gate": "PENDING",
    }


def _load_sources(
    additional_dir: Path,
) -> tuple[list[dict], list[dict], list[dict], tuple[str, str, str, str]]:
    ptax_dir = prior._private_root() / prior.SOURCE_RUN_NAME
    prior_dir = prior._private_root() / prior.RUN_NAME
    prior_summary = prior.verify(prior_dir, ptax_dir)
    cook_rows, declarations, ptax_info = prior._load_sources(ptax_dir)
    expected_prior = prior._worklist_bytes(
        prior.build_worklist(cook_rows, declarations)
    )
    actual_prior = prior.probe._read_bounded(
        private_io.private_path(
            prior_dir / "worklist.jsonl", prior_dir, must_exist=True
        ),
        prior.MAX_WORKLIST_BYTES,
    )
    registered = source._json(prior.probe._read_bounded(PRIOR_AGGREGATE, 4096))
    if (
        actual_prior != expected_prior
        or _hash(actual_prior) != PRIOR_WORKLIST_SHA256
        or prior_summary.get("private_worklist_sha256") != PRIOR_WORKLIST_SHA256
        or not isinstance(registered, dict)
        or registered.get("private_worklist_sha256") != PRIOR_WORKLIST_SHA256
    ):
        raise ValueError("Prior private worklist differs from frozen hash")
    replay = source._replay(additional_dir)
    replay_hash = _hash(_encoded([_hash(body) for body in replay["responses"]]))
    additional_summary = source.verify(additional_dir)
    if (
        replay_hash != ADDITIONAL_RESPONSE_SET_SHA256
        or additional_summary.get("additional_response_set_sha256") != replay_hash
        or additional_summary.get("cook_capture_sha256") != source.COOK_SHA256
        or additional_summary.get("ptax_response_set_sha256") != source.PTAX_SHA256
        or ptax_info.get("response_set_sha256") != source.PTAX_SHA256
    ):
        raise ValueError("Additional capture differs from frozen hash")
    return (
        prior.build_worklist(cook_rows, declarations)["items"],
        declarations,
        replay["rows"],
        (
            source.COOK_SHA256,
            source.PTAX_SHA256,
            ADDITIONAL_RESPONSE_SET_SHA256,
            PRIOR_WORKLIST_SHA256,
        ),
    )


def _private_root() -> Path:
    return source._private_root()


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


def _manifest(result: dict, hashes: tuple[str, str, str, str], content: bytes) -> dict:
    return {
        "protocol": PROTOCOL,
        "cook_capture_sha256": hashes[0],
        "ptax_response_set_sha256": hashes[1],
        "additional_response_set_sha256": hashes[2],
        "prior_worklist_sha256": hashes[3],
        "worklist_sha256": _hash(content),
        "candidate_pairs": result["candidate_pairs"],
        "observation_references": result["observation_references"],
        "review_queue_size": len(result["items"]),
        "certified_sale_labels": 0,
    }


def _public_destination(output: Path, additional_dir: Path) -> Path:
    parent = Path(output).parent.resolve()
    for forbidden in (prior.RAW_ROOT, source.PRIVATE_ROOT):
        if parent.is_relative_to(forbidden.resolve()):
            raise ValueError("Public output cannot be inside private raw data")
    return private_io.summary_target(
        Path(output), (Path(additional_dir) / "selection.json",)
    )


def run(additional_dir: Path, output: Path) -> dict:
    """Write a create-only private review queue and one aggregate allowlist."""
    _public_destination(output, additional_dir)
    previous, declarations, observations, hashes = _load_sources(additional_dir)
    if (
        len(previous) != prior.EXPECTED_COOK_ROWS
        or len(declarations) != prior.EXPECTED_DECLARATIONS
    ):
        raise ValueError("Frozen source denominators differ")
    result = build_worklist(previous, declarations, observations)
    content = _worklist_bytes(result)
    directory = _new_run()
    private_io.new_file(
        private_io.private_path(directory / "worklist.jsonl", directory), content
    )
    private_io.new_file(
        private_io.private_path(directory / "complete.json", directory),
        _encoded(_manifest(result, hashes, content)),
    )
    summary = verify(directory, additional_dir)
    private_io.write_summary_new(
        output, summary, (Path(additional_dir) / "selection.json",)
    )
    return summary


def verify(directory: Path, additional_dir: Path) -> dict:
    """Replay all frozen source bytes and compare the private worklist exactly."""
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
        raise ValueError("Offline diagnostic file set differs")
    previous, declarations, observations, hashes = _load_sources(additional_dir)
    result = build_worklist(previous, declarations, observations)
    expected = _worklist_bytes(result)
    actual = prior.probe._read_bounded(
        private_io.private_path(
            directory / "worklist.jsonl", directory, must_exist=True
        ),
        MAX_WORKLIST_BYTES,
    )
    if actual != expected:
        raise ValueError("Offline worklist differs from pinned captures")
    manifest = source._json(
        prior.probe._read_bounded(
            private_io.private_path(
                directory / "complete.json", directory, must_exist=True
            ),
            4096,
        )
    )
    if manifest != _manifest(result, hashes, expected):
        raise ValueError("Offline completion manifest differs")
    return public_summary(*hashes, _hash(expected))


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Private offline Additional PIN review triage"
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
    except (OSError, ValueError, UnicodeError):
        print(
            "Offline Additional PIN triage failed; inspect private state",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
