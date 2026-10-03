"""Stage the pinned Cook parcel rows as private source observations only."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import sys

from scripts import capture_cook_sales_audit as capture
from scripts import private_review_io as private_io
from scripts import review_cook_sales_sample as review
from tabpfn4realestate.data.cook_parcel_sales import (
    CookParcelSaleObservation,
    SELECT_FIELDS as CORE_SELECT_FIELDS,
    parse_cook_row,
)


PROTOCOL = "cook-parcel-source-staging-v1"
RUN_NAME = f"parcel-staging-v1-{review.CAPTURE_SHA256[:16]}"
RAW_ROOT = review.RAW_ROOT
CAPTURE_SHA256 = review.CAPTURE_SHA256
SOURCE_METADATA_SHA256 = review.SOURCE_METADATA_SHA256
SAMPLE_ROWS = review.SAMPLE_COUNT
MAX_OBSERVATIONS_BYTES = 1024 * 1024
MAX_COMPLETE_BYTES = 4096
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
PUBLIC_FIELDS = frozenset(
    {
        "protocol",
        "capture_manifest_sha256",
        "source_metadata_sha256",
        "private_observations_sha256",
        "sample_rows",
        "certified_sale_labels",
        "historical_asof_eligible",
        "u0_gate",
        "g_us_gate",
    }
)


def _encoded(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n"
    ).encode("utf-8")


def _hash(content: bytes) -> str:
    return sha256(content).hexdigest()


def _page_filename(index: int) -> str:
    cell = capture.CELLS[index // 2]
    return f"rows-{cell.slug}-{index % 2}.json"


def _source_rows() -> tuple[list[dict], list[dict]]:
    """Replay the frozen capture and map each row to its verified page entry."""
    if CORE_SELECT_FIELDS != capture.SELECT_FIELDS:
        raise ValueError("Cook adapter fields differ from frozen source selection")
    rows = review._capture_rows()
    capture_dir = RAW_ROOT / review.CAPTURE_NAME
    manifest_path = private_io.private_path(
        capture_dir / "manifest.json", capture_dir, must_exist=True
    )
    raw = review._bounded(manifest_path, capture.MAX_MANIFEST_BYTES)
    if _hash(raw) != CAPTURE_SHA256:
        raise ValueError("Frozen Cook manifest differs")
    try:
        manifest = json.loads(raw)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("Frozen Cook manifest is malformed") from error
    if not isinstance(manifest, dict):
        raise ValueError("Frozen Cook manifest is malformed")
    response_entries = manifest.get("responses")
    sample_ids = manifest.get("sample_row_ids")
    if not isinstance(response_entries, list) or not isinstance(sample_ids, list):
        raise ValueError("Frozen Cook manifest lacks source lineage")
    by_name = {
        entry.get("file"): entry
        for entry in response_entries
        if isinstance(entry, dict)
    }
    if len(by_name) != len(response_entries):
        raise ValueError("Frozen Cook response inventory differs")
    pages = []
    for index in range(len(capture.CELLS) * 2):
        filename = _page_filename(index)
        entry = by_name.get(filename)
        if not isinstance(entry, dict):
            raise ValueError("Frozen Cook row page is missing")
        pages.append(
            {
                "file": filename,
                "sha256": entry.get("sha256"),
                "retrieved_at": entry.get("retrieved_at"),
                "row_ids": sample_ids[index * 10 : (index + 1) * 10],
            }
        )
    return rows, pages


def build_observations(rows: list[dict], pages: list[dict]) -> bytes:
    """Encode 200 distinct parcel observations in verified captured order."""
    if (
        not isinstance(rows, list)
        or len(rows) != SAMPLE_ROWS
        or not isinstance(pages, list)
        or len(pages) != len(capture.CELLS) * 2
    ):
        raise ValueError("Cook source staging denominator differs")
    content = bytearray()
    seen_ids: set[str] = set()
    for index, page in enumerate(pages):
        expected_fields = {"file", "sha256", "retrieved_at", "row_ids"}
        if (
            not isinstance(page, dict)
            or set(page) != expected_fields
            or page["file"] != _page_filename(index)
            or not isinstance(page["sha256"], str)
            or not HEX64.fullmatch(page["sha256"])
            or not isinstance(page["row_ids"], list)
            or len(page["row_ids"]) != 10
        ):
            raise ValueError("Cook page lineage differs")
        observed_at = review._utc(page["retrieved_at"])
        for offset, row_id in enumerate(page["row_ids"]):
            ordinal = index * 10 + offset + 1
            row = rows[ordinal - 1]
            if (
                not isinstance(row_id, str)
                or not row_id
                or row_id in seen_ids
                or not isinstance(row, dict)
                or row.get("row_id") != row_id
            ):
                raise ValueError("Cook row identity or order differs")
            seen_ids.add(row_id)
            observation = parse_cook_row(
                row,
                capture_sha256=CAPTURE_SHA256,
                response_sha256=page["sha256"],
                row_sha256=review.row_hash(row),
                observed_at=observed_at,
            )
            record = observation.to_record()
            if CookParcelSaleObservation.from_record(record) != observation:
                raise ValueError("Cook observation round trip differs")
            content.extend(_encoded({"ordinal": ordinal, "observation": record}))
            if len(content) > MAX_OBSERVATIONS_BYTES:
                raise ValueError("Cook observations exceed private byte cap")
    return bytes(content)


def _private_root() -> Path:
    private_io.real_directory(RAW_ROOT, RAW_ROOT.parent)
    private_io.verify_acl(RAW_ROOT)
    return RAW_ROOT


def _new_run() -> Path:
    root = _private_root()
    directory = root / RUN_NAME
    directory.mkdir(mode=0o700, exist_ok=False)
    private_io.secure_directory(directory)
    private_io.real_directory(directory, root)
    private_io.verify_acl(directory)
    return directory


def _complete(content: bytes) -> dict:
    return {
        "protocol": PROTOCOL,
        "capture_manifest_sha256": CAPTURE_SHA256,
        "source_metadata_sha256": SOURCE_METADATA_SHA256,
        "observations_sha256": _hash(content),
        "sample_rows": SAMPLE_ROWS,
        "certified_sale_labels": 0,
    }


def public_summary(content: bytes) -> dict:
    result = {
        "protocol": PROTOCOL,
        "capture_manifest_sha256": CAPTURE_SHA256,
        "source_metadata_sha256": SOURCE_METADATA_SHA256,
        "private_observations_sha256": _hash(content),
        "sample_rows": SAMPLE_ROWS,
        "certified_sale_labels": 0,
        "historical_asof_eligible": False,
        "u0_gate": "PENDING",
        "g_us_gate": "PENDING",
    }
    if set(result) != PUBLIC_FIELDS:
        raise ValueError("Cook public allowlist differs")
    return result


def _public_destination(output: Path) -> Path:
    output = Path(output)
    if output.parent.resolve().is_relative_to(RAW_ROOT.resolve()):
        raise ValueError("Public output must be outside private raw data")
    return private_io.summary_target(
        output, (RAW_ROOT / review.CAPTURE_NAME / "manifest.json",)
    )


def run(output: Path) -> dict:
    """Create private staged rows once, then publish an allowlisted aggregate."""
    _public_destination(output)
    rows, pages = _source_rows()
    content = build_observations(rows, pages)
    directory = _new_run()
    private_io.new_file(
        private_io.private_path(directory / "observations.jsonl", directory), content
    )
    private_io.new_file(
        private_io.private_path(directory / "complete.json", directory),
        _encoded(_complete(content)),
    )
    summary = verify(directory)
    private_io.write_summary_new(
        output, summary, (RAW_ROOT / review.CAPTURE_NAME / "manifest.json",)
    )
    return summary


def verify(directory: Path) -> dict:
    """Replay the source and require exact private observation and manifest bytes."""
    root = _private_root()
    directory = Path(directory)
    private_io.real_directory(directory, root)
    private_io.verify_acl(directory)
    if not private_io.same_path(directory, root / RUN_NAME):
        raise ValueError("Cook staging directory identity differs")
    if {path.name for path in directory.iterdir()} != {
        "observations.jsonl",
        "complete.json",
    }:
        raise ValueError("Cook staging file set differs")
    rows, pages = _source_rows()
    expected = build_observations(rows, pages)
    actual = review._bounded(
        private_io.private_path(
            directory / "observations.jsonl", directory, must_exist=True
        ),
        MAX_OBSERVATIONS_BYTES,
    )
    if actual != expected:
        raise ValueError("Cook staged observations differ from frozen source")
    complete = review._bounded(
        private_io.private_path(
            directory / "complete.json", directory, must_exist=True
        ),
        MAX_COMPLETE_BYTES,
    )
    if complete != _encoded(_complete(expected)):
        raise ValueError("Cook staging completion manifest differs")
    return public_summary(expected)


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("run", "verify"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--run-dir", type=Path)
    options = parser.parse_args(arguments)
    try:
        if options.action == "run":
            if options.run_dir is not None or options.output is None:
                parser.error("run needs --output and takes no --run-dir")
            result = run(options.output)
        else:
            if options.run_dir is None:
                parser.error("verify needs --run-dir")
            result = verify(options.run_dir)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (OSError, ValueError, UnicodeError):
        print("Cook parcel staging failed; inspect private state", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
