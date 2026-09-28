"""Ames-only engineering checks; these are not release evaluations."""

from __future__ import annotations

import csv
from dataclasses import dataclass
import math
from pathlib import Path
import random
import re
from statistics import median
from typing import Collection, Mapping, Sequence


_ATTRIBUTE = re.compile(r"@attribute\s+(?:'([^']+)'|\"([^\"]+)\"|(\S+))", re.I)


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
    if value is None or not str(value).strip() or str(value).strip() == "?":
        raise ValueError("Id is required")
    return str(value).strip()


def load_ames_arff(path: str | Path, *, expected_rows: int | None = None) -> list[dict[str, str]]:
    """Load the original ARFF without inferring dates or a legacy split."""
    with Path(path).open(encoding="utf-8-sig", newline="") as source:
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
            line for line in source if line.strip() and not line.lstrip().startswith("%")
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
    rows: Sequence[Mapping[str, object]], *, reserved_ids: Collection[str] = ()
) -> MedianBaseline:
    if not rows:
        raise ValueError("Median baseline needs training rows")
    reserved = set(reserved_ids)
    if any(_row_id(row) in reserved for row in rows):
        raise ValueError("Fit includes a reserved Id")
    prices = [_positive_number(row.get("SalePrice"), "SalePrice") for row in rows]
    return MedianBaseline(float(median(prices)))


def signed_percentage_error(actual: object, predicted: object) -> float:
    actual_price = _positive_number(actual, "actual price")
    predicted_price = _positive_number(predicted, "predicted price")
    return (predicted_price - actual_price) / actual_price


def median_absolute_percentage_error(
    actuals: Sequence[object], predictions: Sequence[object]
) -> float:
    if not actuals or len(actuals) != len(predictions):
        raise ValueError("Metrics require equal nonempty actual and prediction lengths")
    return float(median(abs(signed_percentage_error(actual, predicted))
                        for actual, predicted in zip(actuals, predictions, strict=True)))
