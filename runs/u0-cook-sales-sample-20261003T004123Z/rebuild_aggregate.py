"""Rebuild the public Cook audit summary from the ignored private capture."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import sys
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from capture_cook_sales_audit import CELLS, PRIVATE_ROOT, verify_capture  # noqa: E402


RUN_ID = "u0-cook-sales-sample-20261003T004123Z"
CODE_COMMIT = "4851fb9dc86f38262a7a170a36f2332c514729b5"
PRIVATE_NAME = "cook-sales-v1-20261003T004123.032937Z-c08de13e9f1d"
RUN_DIR = Path(__file__).resolve().parent
OUTPUT = RUN_DIR / "aggregate.json"


def _hash(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def validate_capture_timestamp(value: object) -> str:
    if not isinstance(value, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z", value
    ):
        raise ValueError("Invalid capture timestamp")
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("Invalid capture timestamp") from error
    return value


def validated_capture_times(started: object, completed: object) -> tuple[str, str]:
    started_at = validate_capture_timestamp(started)
    completed_at = validate_capture_timestamp(completed)
    start_instant = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
    complete_instant = datetime.fromisoformat(completed_at.replace("Z", "+00:00"))
    if complete_instant < start_instant:
        raise ValueError("Capture timestamps are out of order")
    return started_at, completed_at


def summarize_sample_rows(rows: list[dict]) -> dict:
    """Publish fixed-category counts only; never copy source field values."""
    multisale = {"false": 0, "true": 0, "other": 0}
    sale_type = {"missing": 0, "land": 0, "land_and_building": 0, "other": 0}
    for row in rows:
        flag = row.get("is_multisale")
        multisale[
            "true" if flag is True else "false" if flag is False else "other"
        ] += 1
        value = row.get("sale_type")
        key = (
            "missing"
            if value is None
            else "land"
            if value == "LAND"
            else "land_and_building"
            if value == "LAND AND BUILDING"
            else "other"
        )
        sale_type[key] += 1
    documents = Counter(
        row["doc_no"]
        for row in rows
        if isinstance(row.get("doc_no"), str) and row["doc_no"]
    )
    return {
        "sample_multisale": multisale,
        "sample_sale_type": sale_type,
        "sample_class_nonblank": sum(
            isinstance(row.get("class"), str) and bool(row["class"]) for row in rows
        ),
        "sample_duplicate_document_groups": sum(n > 1 for n in documents.values()),
        "sample_duplicate_document_rows": sum(n for n in documents.values() if n > 1),
        "sample_missing_document_number": sum(not row.get("doc_no") for row in rows),
        "sample_pin_14_digits": sum(
            str(row.get("pin", "")).isdigit() and len(str(row.get("pin", ""))) == 14
            for row in rows
        ),
    }


def summarize() -> dict:
    private = PRIVATE_ROOT / PRIVATE_NAME
    replay = verify_capture(private)
    manifest = json.loads((private / "manifest.json").read_bytes())
    started_at, completed_at = validated_capture_times(
        manifest.get("started_at"), manifest.get("completed_at")
    )
    rows = []
    for cell in CELLS:
        for page in range(2):
            rows.extend(
                json.loads((private / f"rows-{cell.slug}-{page}.json").read_bytes())
            )
    if len(rows) != 200 or replay["sample_rows"] != 200:
        raise ValueError("Private replay row count differs")
    if any("buyer_name" in row or "seller_name" in row for row in rows):
        raise ValueError("Private sample contains a prohibited personal field")

    return {
        "run_id": RUN_ID,
        "code_commit": CODE_COMMIT,
        "environment_lock_sha256": _hash(RUN_DIR / "environment_lock.txt"),
        "configuration_sha256": _hash(
            ROOT / "decisions" / "0051-cook-sales-private-audit-sample.md"
        ),
        "data_snapshot_sha256": _hash(private / "manifest.json"),
        "source_metadata_sha256": _hash(private / "metadata-before.json"),
        "source_dataset_id": "wvhk-k5uv",
        "capture_started_at": started_at,
        "capture_completed_at": completed_at,
        "response_count": len(manifest["responses"]),
        "cell_counts": manifest["cell_counts"],
        "sample_rows": len(rows),
        "sample_cell_count": len(CELLS),
        **summarize_sample_rows(rows),
        "manual_rubrics_complete": 0,
        "certified_sale_labels": 0,
        "historical_asof_eligible": False,
        "primary_90_day_close_origin_eligible": False,
        "split_hash": None,
        "feature_policy_hash": None,
        "checkpoint_identity": None,
        "status": "private_source_audit_sample_only",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    actual = summarize()
    if args.check:
        expected = json.loads(OUTPUT.read_text(encoding="utf-8"))
        if actual != expected:
            raise ValueError("Saved aggregate differs from private replay")
    else:
        temporary = RUN_DIR / f".aggregate-{uuid4().hex}.tmp"
        try:
            with temporary.open("x", encoding="utf-8") as output:
                json.dump(actual, output, indent=2, sort_keys=True)
                output.write("\n")
                output.flush()
                os.fsync(output.fileno())
            os.link(temporary, OUTPUT)
        finally:
            temporary.unlink(missing_ok=True)
    print(json.dumps({"run_id": RUN_ID, "status": "verified", "sample_rows": 200}))


if __name__ == "__main__":
    main()
