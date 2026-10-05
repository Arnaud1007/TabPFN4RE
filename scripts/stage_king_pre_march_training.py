"""Stage a canonical private King training artifact with no March-May rows."""

from __future__ import annotations

import argparse
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Mapping, Sequence

from scripts.king_historical_benchmark import (
    FEATURES,
    SOURCE_SHA256,
    Sale,
    select_eligible_sales,
)
from scripts.private_review_io import real_directory, secure_directory, verify_acl
from scripts.run_king_absolute_error_development import read_development_source
from scripts.run_king_historical_benchmark import PRIVATE_ROOT, _committed_code

PROTOCOL = "king_pre_march_training_stage_v1"
CUTOFF_EXCLUSIVE = date(2015, 3, 1)
SOURCE_ROWS = 16_861
TRAINING_ROWS = 16_849
ARTIFACT_NAME = "training.jsonl"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def membership_sha256(rows: Sequence[Sale]) -> str:
    return hashlib.sha256(
        ("\n".join(item.row_id for item in rows) + "\n").encode("utf-8")
    ).hexdigest()


def canonical_record(item: Sale) -> dict[str, object]:
    return {
        "row_id": item.row_id,
        "property_id": item.property_id,
        "sale_date": item.sale_date.isoformat(),
        "price_usd": str(item.price),
        "features": {name: item.attributes[name] for name in FEATURES},
    }


def stage(source: Path, output: Path) -> dict[str, object]:
    commit = _committed_code()
    created_root = not PRIVATE_ROOT.exists()
    PRIVATE_ROOT.mkdir(parents=True, exist_ok=True)
    real_directory(PRIVATE_ROOT, PRIVATE_ROOT.parent)
    if created_root:
        secure_directory(PRIVATE_ROOT)
    verify_acl(PRIVATE_ROOT)
    if (
        output.parent.resolve() != PRIVATE_ROOT.resolve()
        or output.exists()
        or output.is_symlink()
    ):
        raise ValueError("Output must be a new private King benchmark directory")

    source_rows = read_development_source(source)
    training, quarantine = select_eligible_sales(source_rows)
    if len(source_rows) != SOURCE_ROWS or len(training) != TRAINING_ROWS:
        raise ValueError("Stage requires exactly 16,849 eligible pre-March rows")
    if quarantine != {"future_year_built": 12}:
        raise ValueError("Stage quarantine membership is incompatible")
    if any(item.sale_date >= CUTOFF_EXCLUSIVE for item in training):
        raise ValueError("Stage contains a row at or after the training cutoff")

    summary = {
        "protocol": PROTOCOL,
        "source_rows_parsed": len(source_rows),
        "training_rows": len(training),
        "training_cutoff_exclusive": CUTOFF_EXCLUSIVE.isoformat(),
        "march_may_labels_parsed": 0,
    }
    _write_stage(output, training, quarantine, commit, summary)
    return summary


def _write_stage(
    output: Path,
    training: Sequence[Sale],
    quarantine: Mapping[str, int],
    commit: str,
    summary: Mapping[str, object],
) -> None:
    with tempfile.TemporaryDirectory(
        dir=PRIVATE_ROOT, prefix="pre-march-"
    ) as temporary:
        staging = Path(temporary)
        secure_directory(staging)
        artifact = staging / ARTIFACT_NAME
        with artifact.open("w", encoding="utf-8", newline="\n") as stream:
            for item in training:
                stream.write(
                    json.dumps(
                        canonical_record(item), sort_keys=True, separators=(",", ":")
                    )
                    + "\n"
                )
        manifest = {
            "run_id": output.name,
            "protocol": PROTOCOL,
            "scope": "private_historical_research_training_only",
            "status": "complete",
            "code_commit": commit,
            "source_sha256": SOURCE_SHA256,
            "source_rows_parsed": len(training) + sum(quarantine.values()),
            "training_rows": len(training),
            "training_cutoff_exclusive": CUTOFF_EXCLUSIVE.isoformat(),
            "training_membership_sha256": membership_sha256(training),
            "quarantine_counts": dict(quarantine),
            "schema": ["row_id", "property_id", "sale_date", "price_usd", "features"],
            "feature_names": list(FEATURES),
            "march_may_labels_parsed": 0,
            "outputs": {ARTIFACT_NAME: digest(artifact)},
            "summary": dict(summary),
        }
        (staging / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
        )
        real_directory(staging, PRIVATE_ROOT)
        verify_acl(staging)
        os.replace(staging, output)
        real_directory(output, PRIVATE_ROOT)
        verify_acl(output)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(stage(args.source, args.output), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
