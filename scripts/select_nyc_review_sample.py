"""Draw the frozen NYC manual-audit sample from a verified private snapshot.

This selects records for human review. It makes no sale-eligibility or as-of claim.
Only aggregate counts are printed; the ordinal ledger stays under ignored raw data.
"""

from __future__ import annotations

import argparse
from collections import Counter
import csv
from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256
from io import BytesIO, TextIOWrapper
import json
import os
from pathlib import Path
from uuid import uuid4

import profile_nyc_rolling_snapshot as profile


SNAPSHOT_SHA256 = "84c06057c52a2822f982cd98fb77ef7edf2c14134d00f46b073d2e4b762b2ef2"
SNAPSHOT_BYTES = 10_397_977
SNAPSHOT_ROWS = 82_345
PROFILE_SHA256 = "6a5a7c57f21ae5a213a00545034fd2cd3c1bb4128d17b56cb1b26f8bedf692ef"
PROTOCOL = "nyc-review-v1"
SEED = 42
EDGE_QUOTAS = {
    "price": 10,
    "identity": 10,
    "repeated_source_key": 10,
    "gross_area": 10,
    "oldest_month": 5,
    "newest_month": 5,
}
STRUCTURAL_QUOTA = 15
MAX_PROFILE_BYTES = 128 * 1024


@dataclass(frozen=True)
class Candidate:
    ordinal: int
    rank: str
    structural_cell: str
    edge_flags: tuple[bool, ...]


def _rank(ordinal: int) -> str:
    material = f"{PROTOCOL}|{SNAPSHOT_SHA256}|{SEED}|{ordinal}"
    return sha256(material.encode("utf-8")).hexdigest()


def _source_key(values: dict[str, str]) -> tuple[str, ...]:
    return tuple(
        values[field].strip()
        for field in ("BOROUGH", "BLOCK", "LOT", "SALE DATE", "SALE PRICE")
    )


def _rows(body: bytes, expected_rows: int):
    """Parse one pass over the immutable, verified source bytes."""
    try:
        with TextIOWrapper(
            BytesIO(body), encoding="utf-8-sig", newline=""
        ) as text_source:
            reader = csv.reader(text_source, strict=True)
            if tuple(next(reader, ())) != profile.HEADER:
                raise ValueError("NYC CSV header differs from pinned 21-column schema")
            count = 0
            for record in reader:
                if len(record) != len(profile.HEADER):
                    raise ValueError("NYC CSV row has wrong field count")
                count += 1
                if count > profile.MAX_ROWS:
                    raise ValueError("NYC CSV exceeds row limit")
                yield count, dict(zip(profile.HEADER, record, strict=True))
    except (csv.Error, UnicodeError) as error:
        raise ValueError("NYC CSV cannot be parsed") from error
    if count != expected_rows:
        raise ValueError("Snapshot row count differs from manifest")


def _verify_source(snapshot_path: Path, root: Path) -> tuple[dict, Path, bytes]:
    snapshot_path = Path(snapshot_path)
    if snapshot_path.is_symlink() or not snapshot_path.is_file():
        raise ValueError("Snapshot manifest must be a regular file")
    manifest = profile._manifest(snapshot_path)
    if manifest["sha256"] != SNAPSHOT_SHA256:
        raise ValueError("Snapshot SHA-256 differs from frozen sample protocol")
    if manifest["bytes"] != SNAPSHOT_BYTES:
        raise ValueError("Snapshot byte count differs from frozen sample protocol")
    if manifest["rows"] != SNAPSHOT_ROWS:
        raise ValueError("Snapshot row count differs from frozen sample protocol")
    raw = root / profile._basename(manifest["raw_filename"])
    if raw.is_symlink() or not raw.is_file():
        raise ValueError("Snapshot raw file must be a private regular file")
    with raw.open("rb") as source:
        body = source.read(SNAPSHOT_BYTES + 1)
    if len(body) > SNAPSHOT_BYTES or len(body) > profile.MAX_CSV_BYTES:
        raise ValueError("Snapshot CSV exceeds byte limit")
    if len(body) != manifest["bytes"]:
        raise ValueError("Snapshot byte count differs from manifest")
    if sha256(body).hexdigest() != SNAPSHOT_SHA256:
        raise ValueError("Snapshot SHA-256 differs from manifest")
    return manifest, raw, body


def _verify_profile(path: Path, source_body: bytes, expected_rows: int) -> dict:
    if path.is_symlink() or not path.is_file():
        raise ValueError("Aggregate profile must be a regular file")
    with path.open("rb") as source:
        body = source.read(MAX_PROFILE_BYTES + 1)
    if len(body) > MAX_PROFILE_BYTES:
        raise ValueError("Aggregate profile exceeds byte limit")
    if sha256(body).hexdigest() != PROFILE_SHA256:
        raise ValueError("Aggregate profile SHA-256 differs from frozen protocol")
    try:
        aggregate = json.loads(body)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("Aggregate profile is invalid JSON") from error
    if not isinstance(aggregate, dict) or any(
        aggregate.get(key) != expected
        for key, expected in (
            ("source_id", "nyc_dof_rolling_usep_8jbt"),
            ("snapshot_sha256", SNAPSHOT_SHA256),
            ("status", "source_inventory_only_not_sale_eligibility"),
        )
    ):
        raise ValueError("Aggregate profile identifies an incompatible source")
    computed = profile._profile_csv(BytesIO(source_body), expected_rows)
    for key, value in computed.items():
        if aggregate.get(key) != value:
            raise ValueError(f"Aggregate profile does not reconcile: {key}")
    return aggregate


def _screen(body: bytes, expected_rows: int) -> tuple[list[Candidate], int]:
    key_counts: Counter[tuple[str, ...]] = Counter()
    for _, values in _rows(body, expected_rows):
        key = _source_key(values)
        if all(key):
            key_counts[key] += 1
    candidates = []
    duplicate_rows = 0
    for ordinal, values in _rows(body, expected_rows):
        key = _source_key(values)
        repeated = all(key) and key_counts[key] > 1
        duplicate_rows += repeated
        price_state, amount = profile._number(values["SALE PRICE"])
        gross_state, _ = profile._number(values["GROSS SQUARE FEET"])
        class_at_sale = profile._class_at_sale(values["BUILDING CLASS AT TIME OF SALE"])
        borough = values["BOROUGH"].strip()
        category_one_family = (
            values["BUILDING CLASS CATEGORY"]
            .strip()
            .upper()
            .startswith("01 ONE FAMILY")
        )
        structural = (
            "candidate"
            if category_one_family and class_at_sale == "A"
            else "other_or_ambiguous"
        )
        month = profile._month(values["SALE DATE"])
        candidates.append(
            Candidate(
                ordinal,
                _rank(ordinal),
                f"{borough}:{structural}",
                (
                    price_state != "positive" or amount <= Decimal("1000"),
                    not values["BLOCK"].strip()
                    or not values["LOT"].strip()
                    or (
                        class_at_sale == "R" and not values["APARTMENT NUMBER"].strip()
                    ),
                    repeated,
                    gross_state != "positive",
                    month == "2025-09",
                    month == "2026-08",
                ),
            )
        )
    return candidates, duplicate_rows


def _choose(candidates: list[Candidate]) -> dict[int, tuple[Candidate, str]]:
    chosen: dict[int, tuple[Candidate, str]] = {}
    ranked = sorted(candidates, key=lambda item: (item.rank, item.ordinal))
    for index, (bucket, quota) in enumerate(EDGE_QUOTAS.items()):
        eligible = [
            item
            for item in ranked
            if item.edge_flags[index] and item.ordinal not in chosen
        ]
        if len(eligible) < quota:
            raise ValueError(f"Insufficient disjoint quota for {bucket}")
        chosen.update((item.ordinal, (item, bucket)) for item in eligible[:quota])
    for borough in "12345":
        for group in ("candidate", "other_or_ambiguous"):
            cell = f"{borough}:{group}"
            eligible = [
                item
                for item in ranked
                if item.structural_cell == cell and item.ordinal not in chosen
            ]
            if len(eligible) < STRUCTURAL_QUOTA:
                raise ValueError(f"Insufficient structural quota for {cell}")
            chosen.update(
                (item.ordinal, (item, "structural"))
                for item in eligible[:STRUCTURAL_QUOTA]
            )
    if len(chosen) != 200:
        raise ValueError("Selected sample does not contain 200 distinct rows")
    return chosen


def _write_private(
    output: Path, chosen: dict[int, tuple[Candidate, str]], root: Path
) -> str:
    if output.parent.resolve(strict=True) != root or output.suffix != ".jsonl":
        raise ValueError("Sample output must be a JSONL file inside private raw data")
    if output.exists() or output.is_symlink():
        raise FileExistsError("Sample output already exists")
    temp = root / f".nyc-review-{uuid4().hex}.part"
    try:
        with temp.open("x", encoding="utf-8", newline="\n") as sink:
            for ordinal in sorted(chosen):
                item, bucket = chosen[ordinal]
                flags = dict(zip(EDGE_QUOTAS, item.edge_flags, strict=True))
                sink.write(
                    json.dumps(
                        {
                            "ordinal": item.ordinal,
                            "rank": item.rank,
                            "primary_bucket": bucket,
                            "structural_cell": item.structural_cell,
                            "edge_flags": flags,
                        },
                        sort_keys=True,
                    )
                    + "\n"
                )
            sink.flush()
            os.fsync(sink.fileno())
        os.link(temp, output)
    finally:
        temp.unlink(missing_ok=True)
    return sha256(output.read_bytes()).hexdigest()


def select_sample(snapshot_path: Path, aggregate_path: Path, output_path: Path) -> dict:
    """Validate pinned files, choose disjoint quotas, and write a private ledger."""
    root = profile._private_root()
    output = Path(output_path).absolute()
    if output.parent.resolve(strict=True) != root:
        raise ValueError("Sample output must remain inside private raw data")
    if output.exists() or output.is_symlink():
        raise FileExistsError("Sample output already exists")
    manifest, raw, body = _verify_source(Path(snapshot_path), root)
    _verify_profile(Path(aggregate_path), body, manifest["rows"])
    candidates, duplicate_rows = _screen(body, manifest["rows"])
    chosen = _choose(candidates)
    final_manifest, final_raw, final_body = _verify_source(Path(snapshot_path), root)
    if final_manifest != manifest or final_raw != raw or final_body != body:
        raise ValueError("Snapshot changed during sample selection")
    ledger_sha = _write_private(output, chosen, root)
    primary_counts = dict.fromkeys((*EDGE_QUOTAS, "structural"), 0)
    structural_counts = {
        borough: {"candidate": 0, "other_or_ambiguous": 0} for borough in "12345"
    }
    flag_counts = dict.fromkeys(EDGE_QUOTAS, 0)
    for item, bucket in chosen.values():
        primary_counts[bucket] += 1
        if bucket == "structural":
            borough, group = item.structural_cell.split(":", maxsplit=1)
            structural_counts[borough][group] += 1
        for flag, present in zip(EDGE_QUOTAS, item.edge_flags, strict=True):
            flag_counts[flag] += present
    return {
        "status": "selected_for_private_manual_review_not_audited",
        "protocol": PROTOCOL,
        "snapshot_sha256": SNAPSHOT_SHA256,
        "profile_sha256": PROFILE_SHA256,
        "source_profile_reconciled": True,
        "source_rows": manifest["rows"],
        "selected_rows": len(chosen),
        "primary_bucket_counts": primary_counts,
        "structural_counts": structural_counts,
        "edge_flag_counts_in_sample": flag_counts,
        "duplicate_candidate_rows": duplicate_rows,
        "ledger_sha256": ledger_sha,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            select_sample(args.snapshot, args.profile, args.output), sort_keys=True
        )
    )


if __name__ == "__main__":
    main()
