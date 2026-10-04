"""Select a fixed private source-audit sample from the Indiana 2025 cohort.

The sample is selected without model residuals or later human eligibility edits.
It is an audit worklist, not a new score or a certified as-of evaluation.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import unicodedata
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from zipfile import ZipFile

from scripts.indiana_assessment_diagnostic import OLD_SPLIT_MEMBERSHIP
from scripts.indiana_historical_benchmark import Sale, _rows, read_archive
from scripts.private_review_io import (
    new_file,
    private_path,
    real_directory,
    secure_directory,
    summary_target,
    verify_acl,
    write_summary_new,
)
from scripts.run_indiana_historical_benchmark import (
    ROOT,
    SOURCE_SHA256,
    _clean_commit,
    _digest,
    _membership_hash,
)

PROTOCOL = "indiana_2025_low_price_trending_source_audit_v1"
SEED = 42
PRICE_CUT = Decimal("117000")
CELL_ORDER = ((True, "Y"), (True, "N"), (False, "Y"), (False, "N"))
PRIVATE_DIR = ROOT / "data/raw/indiana_sdf/audit_sample_v1"
PUBLIC_OUTPUT = (
    ROOT / "runs/indiana-assessment-diagnostic-v1/audit_sample_manifest.json"
)
DIAGNOSTIC_DIR = (
    ROOT / "data/raw/indiana_sdf/benchmarks/indiana-assessment-diagnostic-v1"
)
DIAGNOSTIC_PUBLIC = ROOT / "runs/indiana-assessment-diagnostic-v1"
PRIVATE_FIELDS = (
    "selection_cell",
    "selection_role",
    "hashed_row_id",
    "SDF_ID",
    "A1_Parcel_Number",
    "sale_date",
    "sale_price_usd",
    "P2_16_Valid_Trending",
)


@dataclass(frozen=True)
class AuditRecord:
    sale: Sale
    sdf_id: str
    parcel_number: str
    valid_trending: str


def join_source_rows(path: Path, sales: Sequence[Sale]) -> tuple[AuditRecord, ...]:
    """Join source lookup and trend fields exactly to every eligible sale."""
    by_id = {sale.row_id: sale for sale in sales}
    if len(by_id) != len(sales):
        raise ValueError("Eligible economic sale IDs are duplicate")
    disclosures: dict[str, tuple[str, str]] = {}
    form_ids: set[str] = set()
    with ZipFile(path) as archive:
        for row in _rows(
            archive,
            "SALEDISC.txt",
            ("SDF_ID", "Unique_Sales_ID", "P2_16_Valid_Trending"),
        ):
            economic_id = (row.get("Unique_Sales_ID") or "").strip()
            row_id = hashlib.sha256(economic_id.encode("utf-8")).hexdigest()
            if row_id not in by_id:
                continue
            form_id = (row.get("SDF_ID") or "").strip()
            flag = (row.get("P2_16_Valid_Trending") or "").strip()
            if row_id in disclosures or form_id in form_ids:
                raise ValueError("duplicate disclosure join for eligible sale")
            if not form_id or flag not in ("Y", "N"):
                raise ValueError(
                    "Eligible disclosure join has missing identity or trend"
                )
            disclosures[row_id] = (form_id, flag)
            form_ids.add(form_id)
        if len(disclosures) != len(sales):
            raise ValueError("Eligible sale has missing disclosure join")
        parcels: dict[str, str] = {}
        for row in _rows(archive, "SALEPARCEL.txt", ("SDF_ID", "A1_Parcel_Number")):
            form_id = (row.get("SDF_ID") or "").strip()
            if form_id not in form_ids:
                continue
            if form_id in parcels:
                raise ValueError("duplicate parcel join for eligible sale")
            parcel_number = (row.get("A1_Parcel_Number") or "").strip()
            if not parcel_number:
                raise ValueError("blank parcel lookup for eligible sale")
            parcels[form_id] = parcel_number
    if len(parcels) != len(sales):
        raise ValueError("Eligible sale has missing parcel join")
    return tuple(
        AuditRecord(
            sale=sale,
            sdf_id=disclosures[sale.row_id][0],
            parcel_number=parcels[disclosures[sale.row_id][0]],
            valid_trending=disclosures[sale.row_id][1],
        )
        for sale in sales
    )


def load_candidates(path: Path, expected_sha256: str) -> tuple[AuditRecord, ...]:
    """Pin the official ZIP before reading the unchanged benchmark cohort."""
    sales, _ = read_archive(path, expected_sha256, year=2025)
    return join_source_rows(path, sales)


def _cell(record: AuditRecord) -> tuple[bool, str]:
    return record.sale.price <= PRICE_CUT, record.valid_trending


def _hash_rank(record: AuditRecord) -> tuple[str, str]:
    row_id = record.sale.row_id
    return hashlib.sha256(f"{SEED}:{row_id}".encode("utf-8")).hexdigest(), row_id


def select_audit_sample(
    records: Sequence[AuditRecord],
) -> tuple[AuditRecord, ...]:
    """Take 10 low, 10 high, then 30 hash-ranked remainder per cell."""
    if len({record.sale.row_id for record in records}) != len(records):
        raise ValueError("Audit cohort contains duplicate row IDs")
    groups: dict[tuple[bool, str], list[AuditRecord]] = {
        cell: [] for cell in CELL_ORDER
    }
    for record in records:
        if record.sale.price <= 0 or record.sale.sale_date.year != 2025:
            raise ValueError("Audit sale is outside the fixed 2025 cohort")
        cell = _cell(record)
        if cell not in groups:
            raise ValueError("Audit sale has an unsupported trending flag")
        groups[cell].append(record)
    chosen: list[AuditRecord] = []
    for cell in CELL_ORDER:
        group = groups[cell]
        if len(group) < 50:
            raise ValueError("Every audit cell requires at least 50 sales")
        ascending = sorted(group, key=lambda item: (item.sale.price, item.sale.row_id))
        low = ascending[:10]
        remaining = ascending[10:]
        high = sorted(remaining, key=lambda item: (-item.sale.price, item.sale.row_id))[
            :10
        ]
        reserved = {item.sale.row_id for item in (*low, *high)}
        middle = sorted(
            (item for item in group if item.sale.row_id not in reserved),
            key=_hash_rank,
        )[:30]
        chosen.extend((*low, *high, *middle))
    if len(chosen) != 200 or len({item.sale.row_id for item in chosen}) != 200:
        raise ValueError("Audit sample does not contain 200 distinct sales")
    return tuple(chosen)


def _private_csv(rows: Sequence[AuditRecord]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(PRIVATE_FIELDS)
    for index, row in enumerate(rows):
        for lookup in (row.sdf_id, row.parcel_number):
            if (
                not lookup
                or lookup[0] in "=+-@"
                or lookup[0].isspace()
                or any(
                    unicodedata.category(character).startswith("C")
                    for character in lookup
                )
            ):
                raise ValueError("unsafe lookup field for private CSV")
        cell = "low" if row.sale.price <= PRICE_CUT else "high"
        cell = f"{cell}_{row.valid_trending}"
        position = index % 50
        role = "lowest" if position < 10 else "highest" if position < 20 else "hash"
        writer.writerow(
            (
                cell,
                role,
                row.sale.row_id,
                row.sdf_id,
                row.parcel_number,
                row.sale.sale_date.isoformat(),
                row.sale.price,
                row.valid_trending,
            )
        )
    return stream.getvalue().encode("utf-8")


def _verify_diagnostic() -> tuple[str, dict[str, str]]:
    real_directory(DIAGNOSTIC_DIR, DIAGNOSTIC_DIR.parent)
    verify_acl(DIAGNOSTIC_DIR)
    prediction = private_path(
        DIAGNOSTIC_DIR / "predictions.csv", DIAGNOSTIC_DIR, must_exist=True
    )
    summary = json.loads((DIAGNOSTIC_PUBLIC / "summary.json").read_text())
    artifact = json.loads(
        (DIAGNOSTIC_PUBLIC / "private_artifact_manifest.json").read_text()
    )
    prediction_sha = artifact["files"]["predictions.csv"]
    memberships = summary["split_membership_sha256"]
    if (
        summary["source_sha256"]["2025"] != SOURCE_SHA256[2025]
        or memberships != OLD_SPLIT_MEMBERSHIP
        or _digest(prediction) != prediction_sha
    ):
        raise ValueError("Frozen Indiana diagnostic provenance differs")
    return prediction_sha, memberships


def _configuration_hash() -> str:
    configuration = {
        "protocol": PROTOCOL,
        "seed": SEED,
        "price_cut_usd": str(PRICE_CUT),
        "cell_order": CELL_ORDER,
        "lowest_per_cell": 10,
        "highest_remaining_per_cell": 10,
        "hash_ranked_remaining_per_cell": 30,
        "hash_input": "42:{hashed_row_id}",
        "private_fields": PRIVATE_FIELDS,
    }
    encoded = json.dumps(configuration, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _intent_bytes(public: dict[str, object], sample_bytes: bytes) -> bytes:
    public_bytes = (json.dumps(public, indent=2, sort_keys=True) + "\n").encode()
    intent = {
        "protocol": PROTOCOL,
        "code_commit": public["code_commit"],
        "configuration_sha256": public["configuration_sha256"],
        "source_sha256": public["source_sha256"],
        "prediction_sha256": public["prediction_sha256"],
        "split_membership_sha256": public["split_membership_sha256"],
        "sample_sha256": hashlib.sha256(sample_bytes).hexdigest(),
        "sample_bytes": len(sample_bytes),
        "public_manifest_sha256": hashlib.sha256(public_bytes).hexdigest(),
    }
    return (json.dumps(intent, indent=2, sort_keys=True) + "\n").encode()


def _exact_private_file(path: Path, expected: bytes, kind: str) -> None:
    if path.stat().st_size != len(expected) or path.read_bytes() != expected:
        raise ValueError(f"Private audit {kind} differs from frozen run")


def _prepare_private_files(intent: bytes, sample: bytes) -> Path:
    """Resume only an empty or byte-identical secured private directory."""
    if PRIVATE_DIR.exists() or PRIVATE_DIR.is_symlink():
        real_directory(PRIVATE_DIR, PRIVATE_DIR.parent)
        verify_acl(PRIVATE_DIR)
    else:
        PRIVATE_DIR.mkdir(mode=0o700)
        secure_directory(PRIVATE_DIR)
        verify_acl(PRIVATE_DIR)
    names = {entry.name for entry in PRIVATE_DIR.iterdir()}
    if names - {"intent.json", "sample.csv"}:
        raise ValueError("Private audit directory has conflicting files")
    intent_path = private_path(PRIVATE_DIR / "intent.json", PRIVATE_DIR)
    sample_path = private_path(PRIVATE_DIR / "sample.csv", PRIVATE_DIR)
    if sample_path.exists() and not intent_path.exists():
        raise ValueError("Private audit sample exists without frozen intent")
    if intent_path.exists():
        _exact_private_file(intent_path, intent, "intent")
    else:
        new_file(intent_path, intent)
    if sample_path.exists():
        _exact_private_file(sample_path, sample, "sample")
    else:
        new_file(sample_path, sample)
    if {entry.name for entry in PRIVATE_DIR.iterdir()} != {"intent.json", "sample.csv"}:
        raise ValueError("Private audit directory changed during publication")
    _exact_private_file(intent_path, intent, "intent")
    _exact_private_file(sample_path, sample, "sample")
    return sample_path


def run_sample(source_2025: Path) -> dict[str, object]:
    """Publish a create-only private worklist and aggregate public manifest."""
    commit = _clean_commit()
    real_directory(PRIVATE_DIR.parent, PRIVATE_DIR.parent.parent)
    real_directory(PUBLIC_OUTPUT.parent, PUBLIC_OUTPUT.parent.parent)
    summary_target(PUBLIC_OUTPUT, (source_2025,))
    prediction_sha, memberships = _verify_diagnostic()
    records = load_candidates(source_2025, SOURCE_SHA256[2025])
    if (
        _membership_hash(tuple(record.sale for record in records))
        != memberships["validation"]
    ):
        raise ValueError("Audit source membership differs from frozen diagnostic")
    selected = select_audit_sample(records)
    counts = Counter(_cell(record) for record in records)
    sample_bytes = _private_csv(selected)
    sample_sha = hashlib.sha256(sample_bytes).hexdigest()
    public = {
        "protocol": PROTOCOL,
        "status": "selected_for_manual_source_review",
        "code_commit": commit,
        "configuration_sha256": _configuration_hash(),
        "source_sha256": SOURCE_SHA256[2025],
        "prediction_sha256": prediction_sha,
        "split_membership_sha256": memberships,
        "ranking_formula": "SHA256(UTF8('42:{hashed_row_id}')); ascending digest, row_id tie-break",
        "price_boundary_usd": str(PRICE_CUT),
        "cells": {
            f"{'low' if low else 'high'}_{flag}": {
                "eligible": counts[(low, flag)],
                "selected": 50,
                "lowest": 10,
                "highest": 10,
                "hashed_middle": 30,
            }
            for low, flag in CELL_ORDER
        },
        "sample_rows": len(selected),
        "private_sample_sha256": sample_sha,
        "manual_review_status": "not_started",
        "reviewed_rows": 0,
        "pending_rows": len(selected),
        "certified_90_day_origin": False,
        "g_us_gate": "PENDING",
    }
    sample_path = _prepare_private_files(
        _intent_bytes(public, sample_bytes), sample_bytes
    )
    write_summary_new(PUBLIC_OUTPUT, public, (source_2025, sample_path))
    return public


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-2025", type=Path, required=True)
    args = parser.parse_args()
    result = run_sample(args.source_2025)
    print(
        json.dumps({"sample_rows": result["sample_rows"], "status": result["status"]})
    )


if __name__ == "__main__":
    main()
