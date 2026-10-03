"""Bounded, data-free cost probe for the synthetic paired bootstrap."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
import platform
import sys
import tempfile
from time import perf_counter


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from tabpfn4realestate.evaluation.metrics import PredictionRow  # noqa: E402
from tabpfn4realestate.evaluation.paired_bootstrap import (  # noqa: E402
    ComparisonMeta,
    compare_paired_blocks,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rows", type=int, default=10_000)
    parser.add_argument("--draws", type=int, default=100)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 20 <= args.rows <= 20_000 or not 100 <= args.draws <= 5000:
        parser.error("rows or draws outside the registered probe range")
    output_path = args.output.resolve(strict=False)
    if output_path.parent != Path(__file__).resolve().parent:
        parser.error("output must be inside this run directory")
    if output_path.exists():
        parser.error("output already exists; choose a new immutable result path")

    base_time = datetime(2024, 1, 1, tzinfo=timezone.utc)
    metadata = tuple(
        ComparisonMeta(
            f"row-{index:05d}",
            f"property-{index:05d}",
            f"market-{index // 5000}",
            f"geo-{index:05d}",
            "quarter-1",
            base_time + timedelta(days=index % 90),
        )
        for index in range(args.rows)
    )

    def predictions(offset: int, modulus: int) -> tuple[PredictionRow, ...]:
        return tuple(
            PredictionRow(
                row.row_id,
                Decimal("100"),
                Decimal(offset + index % modulus),
                "USD",
                "USD",
                "estimated",
            )
            for index, row in enumerate(metadata)
        )

    baseline = predictions(110, 5)
    challenger = predictions(102, 7)
    start = perf_counter()
    result = compare_paired_blocks(
        metadata,
        baseline,
        challenger,
        split_hash="a" * 64,
        block_plan_hash="b" * 64,
        draws=args.draws,
    )
    elapsed = perf_counter() - start
    payload = {
        "schema_version": 1,
        "kind": "synthetic_cost_probe",
        "python_version": platform.python_version(),
        "rows": args.rows,
        "draws": args.draws,
        "markets": result.market_count,
        "independent_components": result.component_count,
        "status": result.status,
        "comparison_hash": result.comparison_hash,
        "elapsed_seconds": round(elapsed, 3),
        "certification_eligible": False,
    }
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=output_path.parent,
        prefix=f".{output_path.name}-",
        suffix=".tmp",
        delete=False,
    ) as output:
        temporary_path = Path(output.name)
        json.dump(payload, output, indent=2)
        output.write("\n")
        output.flush()
        os.fsync(output.fileno())
    try:
        os.link(temporary_path, output_path)
    finally:
        temporary_path.unlink(missing_ok=True)
    print(json.dumps(payload, sort_keys=True))


if __name__ == "__main__":
    main()
