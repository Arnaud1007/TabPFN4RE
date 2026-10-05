"""Build retrospective King split-conformal intervals from saved predictions."""

from __future__ import annotations

import argparse
import csv
from datetime import date
from decimal import Decimal, localcontext
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile

from scripts.run_king_historical_benchmark import _committed_code
from tabpfn4realestate.evaluation.conformal import split_conformal_radius
from tabpfn4realestate.evaluation.metrics import _quantile

PROTOCOL = "king_historical_intervals_v1"
CALIBRATION_START = date(2015, 3, 1)
EVALUATION_START = date(2015, 4, 1)
EVALUATION_END = date(2015, 6, 1)
EXPECTED_MANIFEST_SHA256 = (
    "700eb921c3a715f3df8fce10b3214cccb1b1b92b661ae0463377ebaa9fd597c0"
)
EXPECTED_PREDICTIONS_SHA256 = (
    "25e64ecca3c83e017124428bc3b37baf0c44d17094b37fa43f0ae667f4151923"
)
EXPECTED_TOTAL_ROWS = 4752
EXPECTED_CALIBRATION_ROWS = 1875
EXPECTED_EVALUATION_ROWS = 2877
EXPECTED_COLUMNS = (
    "row_id",
    "sale_date",
    "actual_usd",
    "xgboost_usd",
    "zipcode_median_usd",
)


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _manifest(directory: Path) -> dict[str, object]:
    value = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not isinstance(value.get("outputs"), dict):
        raise ValueError("Saved run manifest is invalid")
    return value


def _read_predictions(
    directory: Path, filename: str, manifest: dict[str, object]
) -> list[dict[str, str]]:
    path = directory / filename
    expected = manifest["outputs"].get(filename)
    if not isinstance(expected, str) or _digest(path) != expected:
        raise ValueError("Saved prediction hash mismatch")
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or ()) != EXPECTED_COLUMNS:
            raise ValueError("Saved prediction schema is invalid")
        rows = list(reader)
    if len({row["row_id"] for row in rows}) != len(rows):
        raise ValueError("Saved predictions contain duplicate row IDs")
    return rows


def _price(row: dict[str, str], field: str) -> Decimal:
    value = Decimal(row[field])
    if not value.is_finite() or value <= 0:
        raise ValueError("Saved prediction contains an invalid price")
    return value


def _wilson(successes: int, total: int) -> tuple[float, float]:
    z = 1.959963984540054
    proportion = successes / total
    denominator = 1 + z * z / total
    center = (proportion + z * z / (2 * total)) / denominator
    margin = (
        z
        * math.sqrt(proportion * (1 - proportion) / total + z * z / (4 * total * total))
        / denominator
    )
    return center - margin, center + margin


def build_intervals(later_dir: Path, output: Path) -> dict[str, object]:
    """Calibrate on March and evaluate once on consumed April-May predictions."""
    code_commit = _committed_code()
    if output.parent.resolve() != later_dir.parent.resolve():
        raise ValueError(
            "Interval input and output must share the private benchmark root"
        )
    repository = Path.cwd().resolve()
    if output.resolve().is_relative_to(
        repository
    ) and not output.resolve().is_relative_to(repository / "data" / "raw"):
        raise ValueError("Row-level interval output must remain under data/raw")
    if output.exists() or output.is_symlink():
        raise ValueError("Interval output must be new")
    if _digest(later_dir / "manifest.json") != EXPECTED_MANIFEST_SHA256:
        raise ValueError("Saved run manifest is not the frozen interval input")
    later_manifest = _manifest(later_dir)
    source = later_manifest.get("source_sha256")
    split = later_manifest.get("split_sha256")
    model = later_manifest.get("model_sha256")
    if not all(
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
        for value in (source, split, model)
    ):
        raise ValueError("Saved prediction provenance is invalid")
    rows = _read_predictions(later_dir, "later_predictions.csv", later_manifest)
    if (
        later_manifest["outputs"].get("later_predictions.csv")
        != EXPECTED_PREDICTIONS_SHA256
        or len(rows) != EXPECTED_TOTAL_ROWS
    ):
        raise ValueError("Saved predictions are not the frozen interval cohort")
    calibration = [
        row
        for row in rows
        if CALIBRATION_START <= date.fromisoformat(row["sale_date"]) < EVALUATION_START
    ]
    evaluation = [
        row
        for row in rows
        if EVALUATION_START <= date.fromisoformat(row["sale_date"]) < EVALUATION_END
    ]
    if len(calibration) != EXPECTED_CALIBRATION_ROWS:
        raise ValueError("Interval calibration cohort is incomplete")
    if len(evaluation) != EXPECTED_EVALUATION_ROWS:
        raise ValueError("Interval evaluation cohort is incomplete")
    calibration_ids = {row["row_id"] for row in calibration}
    evaluation_ids = {row["row_id"] for row in evaluation}
    if calibration_ids & evaluation_ids:
        raise ValueError("Calibration and evaluation rows overlap")
    if len(calibration) + len(evaluation) != len(rows):
        raise ValueError("Saved predictions contain dates outside March-May 2015")
    with localcontext() as context:
        context.prec = 50
        residuals = tuple(
            abs(_price(row, "actual_usd").ln() - _price(row, "xgboost_usd").ln())
            for row in calibration
        )
        radius80 = split_conformal_radius(residuals, Decimal("0.20"))
        radius90 = split_conformal_radius(residuals, Decimal("0.10"))
        factor80, factor90 = radius80.exp(), radius90.exp()
    records = []
    covered80 = covered90 = nested = failures = 0
    widths90: list[Decimal] = []
    for row in evaluation:
        actual, predicted = _price(row, "actual_usd"), _price(row, "xgboost_usd")
        lower80, upper80 = predicted / factor80, predicted * factor80
        lower90, upper90 = predicted / factor90, predicted * factor90
        is_nested = lower90 <= lower80 <= upper80 <= upper90
        nested += int(is_nested)
        failures += int(not is_nested)
        covered80 += int(lower80 <= actual <= upper80)
        covered90 += int(lower90 <= actual <= upper90)
        widths90.append((upper90 - lower90) / actual)
        records.append(
            (
                row["row_id"],
                row["sale_date"],
                actual,
                predicted,
                lower80,
                upper80,
                lower90,
                upper90,
            )
        )
    coverage80, coverage90 = covered80 / len(records), covered90 / len(records)
    aggregate = {
        "protocol": PROTOCOL,
        "calibration_rows": len(calibration),
        "evaluation_rows": len(records),
        "radius80": str(radius80),
        "radius90": str(radius90),
        "coverage80": coverage80,
        "coverage80_wilson95": list(_wilson(covered80, len(records))),
        "coverage90": coverage90,
        "coverage90_wilson95": list(_wilson(covered90, len(records))),
        "mean_relative_width90_actual": float(sum(widths90) / len(widths90)),
        "p90_relative_width90_actual": float(_quantile(widths90, Decimal("0.90"))),
        "nested_intervals": nested,
        "interval_failures": failures,
        "model_sha256": model,
        "source_predictions_sha256": EXPECTED_PREDICTIONS_SHA256,
        "evaluation_previously_consumed": True,
        "certified_90_day_origin": False,
        "g_us_gate": "PENDING",
    }
    sidecar = {
        "protocol": PROTOCOL,
        "model_sha256": model,
        "split_sha256": split,
        "radius80": str(radius80),
        "radius90": str(radius90),
        "source_predictions_sha256": EXPECTED_PREDICTIONS_SHA256,
        "scope": "historical_research_only",
    }
    sidecar["calibration_id"] = hashlib.sha256(
        json.dumps(sidecar, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    with tempfile.TemporaryDirectory(
        dir=output.parent, prefix="intervals-"
    ) as temporary:
        staging = Path(temporary)
        with (staging / "evaluation_intervals.csv").open(
            "w", newline="", encoding="utf-8"
        ) as stream:
            writer = csv.writer(stream)
            writer.writerow(
                (
                    "row_id",
                    "sale_date",
                    "actual_usd",
                    "predicted_usd",
                    "lower80",
                    "upper80",
                    "lower90",
                    "upper90",
                )
            )
            writer.writerows(records)
        (staging / "calibration.json").write_text(
            json.dumps(sidecar, indent=2, sort_keys=True), encoding="utf-8"
        )
        (staging / "aggregate.json").write_text(
            json.dumps(aggregate, indent=2, sort_keys=True), encoding="utf-8"
        )
        manifest = {
            "protocol": PROTOCOL,
            "status": "complete",
            "code_commit": code_commit,
            "model_sha256": model,
            "calibration_id": sidecar["calibration_id"],
            "outputs": {
                path.name: _digest(path) for path in staging.iterdir() if path.is_file()
            },
        }
        (staging / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
        )
        os.replace(staging, output)
    return aggregate


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--later-run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    options = parser.parse_args()
    print(
        json.dumps(
            build_intervals(options.later_run, options.output),
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
