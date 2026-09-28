"""Ames-only engineering checks; these are not release evaluations."""

from __future__ import annotations

import csv
from dataclasses import dataclass
import hashlib
import io
import math
from pathlib import Path
import random
import re
from statistics import median
from typing import Mapping, Sequence


_ATTRIBUTE = re.compile(r"@attribute\s+(?:'([^']+)'|\"([^\"]+)\"|(\S+))", re.I)
_MAX_AMES_BYTES = 10_000_000


def _positive_number(value: object, field: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a positive finite number")
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field} must be a positive finite number") from error
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{field} must be a positive finite number")
    return number


def _row_id(row: Mapping[str, object]) -> str:
    value = row.get("Id")
    identifier = str(value).strip() if value is not None else ""
    if not re.fullmatch(r"[1-9][0-9]*", identifier):
        raise ValueError("Id must be a positive integer")
    return identifier


def load_ames_arff(
    path: str | Path,
    *,
    expected_rows: int | None = None,
    expected_sha256: str | None = None,
    max_bytes: int = _MAX_AMES_BYTES,
) -> list[dict[str, str]]:
    """Load the original ARFF without inferring dates or a legacy split."""
    source_path = Path(path)
    if max_bytes <= 0 or max_bytes > _MAX_AMES_BYTES:
        raise ValueError(f"ARFF size limit must be within 1..{_MAX_AMES_BYTES} bytes")
    with source_path.open("rb") as source_file:
        source_bytes = source_file.read(max_bytes + 1)
    if len(source_bytes) > max_bytes:
        raise ValueError(f"ARFF size exceeds {max_bytes} bytes")
    source_sha256 = hashlib.sha256(source_bytes).hexdigest()
    if expected_sha256 is not None and source_sha256 != expected_sha256.lower():
        raise ValueError("ARFF SHA-256 checksum does not match")

    with io.StringIO(source_bytes.decode("utf-8-sig")) as source:
        attributes: list[str] = []
        for line in source:
            stripped = line.strip()
            if stripped.lower() == "@data":
                break
            if stripped.lower().startswith("@attribute"):
                match = _ATTRIBUTE.match(stripped)
                if match is None:
                    raise ValueError(f"Invalid ARFF attribute: {stripped}")
                attributes.append(next(part for part in match.groups() if part is not None))
        else:
            raise ValueError("ARFF @DATA section is missing")

        if len(attributes) != len(set(attributes)):
            raise ValueError("Duplicate ARFF attribute")
        if not {"Id", "SalePrice"}.issubset(attributes):
            raise ValueError("Ames schema requires Id and SalePrice")

        records = csv.reader(
            (line for line in source if line.strip() and not line.lstrip().startswith("%")),
            quotechar="'",
            escapechar="\\",
            strict=True,
        )
        rows: list[dict[str, str]] = []
        identifiers: set[str] = set()
        for index, record in enumerate(records, start=1):
            if len(record) != len(attributes):
                raise ValueError(f"ARFF row {index} has {len(record)} fields, expected {len(attributes)}")
            row = dict(zip(attributes, record, strict=True))
            identifier = _row_id(row)
            if identifier in identifiers:
                raise ValueError(f"Duplicate Id: {identifier}")
            _positive_number(row["SalePrice"], "SalePrice")
            identifiers.add(identifier)
            rows.append(row)
            if expected_rows is not None and len(rows) > expected_rows:
                raise ValueError(f"Expected {expected_rows} rows, found more")

    if expected_rows is not None and len(rows) != expected_rows:
        raise ValueError(f"Expected {expected_rows} rows, found {len(rows)}")
    return rows


@dataclass(frozen=True)
class Split:
    development_ids: tuple[str, ...]
    reserved_ids: tuple[str, ...]
    protocol_id: str = "ames_engineering_v1"


def engineering_split(rows: Sequence[Mapping[str, object]], *, seed: int = 42) -> Split:
    """Make a distinct deterministic smoke split, never the historical holdout."""
    identifiers = [_row_id(row) for row in rows]
    if len(identifiers) < 2 or len(set(identifiers)) != len(identifiers):
        raise ValueError("Engineering split needs at least two unique Id values")
    shuffled = random.Random(seed).sample(identifiers, k=len(identifiers))
    boundary = min(max(int(0.8 * len(shuffled)), 1), len(shuffled) - 1)
    return Split(tuple(shuffled[:boundary]), tuple(shuffled[boundary:]))


@dataclass(frozen=True)
class MedianBaseline:
    median_price: float

    def predict(self, rows: Sequence[Mapping[str, object]]) -> list[float]:
        return [self.median_price for _ in rows]


def fit_median_baseline(
    rows: Sequence[Mapping[str, object]], *, split: Split
) -> MedianBaseline:
    if not rows:
        raise ValueError("Median baseline needs training rows")
    development = set(split.development_ids)
    reserved = set(split.reserved_ids)
    if (
        split.protocol_id != "ames_engineering_v1"
        or not development
        or not reserved
        or development & reserved
        or len(development) != len(split.development_ids)
        or len(reserved) != len(split.reserved_ids)
    ):
        raise ValueError("Invalid engineering split")
    fit_ids = [_row_id(row) for row in rows]
    if len(set(fit_ids)) != len(fit_ids) or not set(fit_ids).issubset(development):
        raise ValueError("Fit includes a reserved or non-development Id")
    prices = [_positive_number(row.get("SalePrice"), "SalePrice") for row in rows]
    return MedianBaseline(float(median(prices)))


def signed_percentage_error(actual: object, predicted: object) -> float:
    actual_price = _positive_number(actual, "actual price")
    predicted_price = _positive_number(predicted, "predicted price")
    result = (predicted_price - actual_price) / actual_price
    if not math.isfinite(result):
        raise ValueError("Percentage error is not finite")
    return result


def median_absolute_percentage_error(
    actuals: Sequence[object], predictions: Sequence[object]
) -> float:
    if not actuals or len(actuals) != len(predictions):
        raise ValueError("Metrics require equal nonempty actual and prediction lengths")
    return float(median(abs(signed_percentage_error(actual, predicted))
                        for actual, predicted in zip(actuals, predictions, strict=True)))
