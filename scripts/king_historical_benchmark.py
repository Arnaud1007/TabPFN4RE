"""Research-only King County sale-date benchmark; never a certified AVM."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import hashlib
import io
import math
from pathlib import Path
import re
from types import MappingProxyType
from typing import Mapping, Sequence

COLUMNS = (
    "id",
    "date",
    "price",
    "bedrooms",
    "bathrooms",
    "sqft_living",
    "sqft_lot",
    "floors",
    "waterfront",
    "view",
    "condition",
    "grade",
    "sqft_above",
    "sqft_basement",
    "yr_built",
    "yr_renovated",
    "zipcode",
    "lat",
    "long",
    "sqft_living15",
    "sqft_lot15",
)
NUMERIC_FEATURES = (
    "bedrooms",
    "bathrooms",
    "sqft_living",
    "sqft_lot",
    "floors",
    "waterfront",
    "view",
    "condition",
    "grade",
    "sqft_above",
    "sqft_basement",
    "yr_built",
    "lat",
    "long",
)
FEATURES = (*NUMERIC_FEATURES, "zipcode")
SOURCE_SHA256 = "25817379c3f06c584ca61eb2413a8368af72fc5548848a0ceb9bb4a885e90401"
MAX_SOURCE_BYTES = 10_000_000
TRAIN_END = date(2015, 1, 1)
VALIDATION_END = date(2015, 3, 1)


@dataclass(frozen=True)
class Sale:
    row_id: str
    property_id: str
    sale_date: date
    price: Decimal
    attributes: Mapping[str, float | str]


def _decode_source(path: Path, expected_sha256: str) -> list[str]:
    if not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        raise ValueError("Source checksum must be a lowercase SHA-256")
    with path.open("rb") as stream:
        content = stream.read(MAX_SOURCE_BYTES + 1)
    if len(content) > MAX_SOURCE_BYTES:
        raise ValueError("Source exceeds size limit")
    if hashlib.sha256(content).hexdigest() != expected_sha256:
        raise ValueError("Source checksum mismatch")
    try:
        return content.decode("utf-8").splitlines()
    except UnicodeDecodeError as error:
        raise ValueError("Source is not UTF-8") from error


def _locate_data(lines: Sequence[str]) -> int:
    attributes: list[str] = []
    marker: int | None = None
    for index, line in enumerate(lines):
        stripped = line.strip()
        match = re.match(r"@ATTRIBUTE\s+(\S+)\s+", stripped, flags=re.IGNORECASE)
        if match:
            attributes.append(match.group(1))
        if stripped.upper() == "@DATA":
            marker = index
            break
    if tuple(attributes) != COLUMNS or marker is None:
        raise ValueError("OpenML King source schema is incompatible")
    return marker


def _parse_sale(values: Sequence[str], raw_line: str) -> Sale:
    if len(values) != len(COLUMNS):
        raise ValueError("Source row has an incompatible column count")
    fields = dict(zip(COLUMNS, values, strict=True))
    if not fields["id"] or fields["id"] == "?":
        raise ValueError("Source property ID is missing")
    if not re.fullmatch(r"\d{8}T000000", fields["date"]):
        raise ValueError("Source sale date is invalid")
    try:
        sale_date = datetime.strptime(fields["date"], "%Y%m%dT%H%M%S").date()
        price = Decimal(fields["price"])
    except (ValueError, InvalidOperation) as error:
        raise ValueError("Source sale date or price is invalid") from error
    if not price.is_finite() or price <= 0:
        raise ValueError("Source sale price must be positive and finite")
    attributes: dict[str, float | str] = {"zipcode": fields["zipcode"]}
    if not re.fullmatch(r"\d{5}", fields["zipcode"]):
        raise ValueError("Source zipcode is invalid")
    for name in NUMERIC_FEATURES:
        try:
            number = float(fields[name])
        except ValueError as error:
            raise ValueError(f"Source {name} is invalid") from error
        if not math.isfinite(number):
            raise ValueError(f"Source {name} is not finite")
        attributes[name] = number
    return Sale(
        row_id=hashlib.sha256(raw_line.encode("utf-8")).hexdigest(),
        property_id=fields["id"],
        sale_date=sale_date,
        price=price,
        attributes=MappingProxyType(attributes.copy()),
    )


def read_source(
    path: Path, expected_sha256: str, *, expected_rows: int
) -> tuple[Sale, ...]:
    """Read only the pinned schema without reinterpreting unknown ARFF fields."""
    lines = _decode_source(path, expected_sha256)
    marker = _locate_data(lines)
    data_lines = [
        line
        for line in lines[marker + 1 :]
        if line.strip() and not line.lstrip().startswith("%")
    ]
    sales = tuple(
        _parse_sale(next(csv.reader(io.StringIO(line))), line) for line in data_lines
    )
    if len(sales) != expected_rows:
        raise ValueError("Source row count does not match expected row count")
    if len({sale.row_id for sale in sales}) != len(sales):
        raise ValueError("Source contains duplicate exact rows")
    return sales


def read_pinned_source(path: Path) -> tuple[Sale, ...]:
    """The real benchmark always uses the exact archived OpenML bytes."""
    return read_source(path, SOURCE_SHA256, expected_rows=21_613)


def select_eligible_sales(
    sales: Sequence[Sale],
) -> tuple[tuple[Sale, ...], dict[str, int]]:
    """Quarantine physically inconsistent rows using target-blind rules."""
    eligible: list[Sale] = []
    reasons: dict[str, int] = {}
    for sale in sales:
        features = sale.attributes
        reason = None
        if features["sqft_living"] <= 0:
            reason = "nonpositive_living_area"
        elif features["sqft_lot"] <= 0:
            reason = "nonpositive_lot_area"
        elif features["sqft_above"] < 0 or features["sqft_basement"] < 0:
            reason = "negative_building_area"
        elif any(features[name] < 0 for name in ("bedrooms", "bathrooms", "floors")):
            reason = "negative_room_or_floor_count"
        elif features["yr_built"] < 1800:
            reason = "invalid_year_built"
        elif features["yr_built"] > sale.sale_date.year:
            reason = "future_year_built"
        if reason is None:
            eligible.append(sale)
        else:
            reasons[reason] = reasons.get(reason, 0) + 1
    return tuple(eligible), reasons


def split_sales(sales: Sequence[Sale]) -> dict[str, tuple[Sale, ...]]:
    """Freeze a sale-date split with deterministic membership and ordering."""
    if not sales or len({sale.row_id for sale in sales}) != len(sales):
        raise ValueError("Split requires distinct nonempty sale rows")
    ordered = sorted(sales, key=lambda sale: (sale.sale_date, sale.row_id))
    return {
        "train": tuple(sale for sale in ordered if sale.sale_date < TRAIN_END),
        "validation": tuple(
            sale for sale in ordered if TRAIN_END <= sale.sale_date < VALIDATION_END
        ),
        "test": tuple(sale for sale in ordered if sale.sale_date >= VALIDATION_END),
    }


def encode_features(
    training: Sequence[Sale], other: Sequence[Sale]
) -> tuple[
    tuple[str, ...], tuple[tuple[float, ...], ...], tuple[tuple[float, ...], ...]
]:
    """One-hot zipcode vocabulary comes only from the supplied training rows."""
    if not training:
        raise ValueError("Feature encoding requires training sales")
    zipcodes = tuple(sorted({str(sale.attributes["zipcode"]) for sale in training}))
    names = (*NUMERIC_FEATURES, *(f"zipcode={zipcode}" for zipcode in zipcodes))

    def row(sale: Sale) -> tuple[float, ...]:
        return (
            *(float(sale.attributes[name]) for name in NUMERIC_FEATURES),
            *(float(sale.attributes["zipcode"] == zipcode) for zipcode in zipcodes),
        )

    return (
        names,
        tuple(row(sale) for sale in training),
        tuple(row(sale) for sale in other),
    )
