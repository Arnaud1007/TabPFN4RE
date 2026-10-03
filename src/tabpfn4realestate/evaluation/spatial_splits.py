"""Synthetic projected-grid holdout layered on a validated temporal fold."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from fractions import Fraction
from hashlib import sha256
from itertools import islice
import json
import re
from typing import Sequence

from tabpfn4realestate.data.schema import _identifier
from tabpfn4realestate.evaluation.splits import (
    LabelMaturity,
    OriginRef,
    TemporalFold,
    build_temporal_fold,
)


_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_METRE_EPSG = (
    {"EPSG:3338", "EPSG:5070"}
    | {f"EPSG:{code}" for code in range(26901, 26924)}
    | {f"EPSG:{prefix}{zone:02d}" for prefix in (326, 327) for zone in range(1, 61)}
)


def _metres(value: Decimal, name: str, *, positive: bool = False) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError(f"{name} must be finite Decimal metres")
    if (
        value.adjusted() > 12
        or value.as_tuple().exponent < -9
        or len(value.as_tuple().digits) > 18
    ):
        raise ValueError(f"{name} exceeds the supported metre precision or range")
    if positive and value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def _decimal_text(value: Decimal) -> str:
    if value == 0:
        return "0"
    rendered = format(value, "f")
    return rendered.rstrip("0").rstrip(".") if "." in rendered else rendered


@dataclass(frozen=True)
class ProjectedRow:
    """A row's synthetic point in the grid's declared metre-based CRS."""

    row_id: str
    property_id: str
    x_m: Decimal
    y_m: Decimal

    def __post_init__(self) -> None:
        _identifier(self.row_id, "row_id")
        _identifier(self.property_id, "property_id")
        _metres(self.x_m, "x_m")
        _metres(self.y_m, "y_m")


@dataclass(frozen=True)
class ProjectedGrid:
    """Frozen metric grid; a real CRS requires an independently audited projection."""

    crs_id: str
    projection_version: str
    origin_x_m: Decimal
    origin_y_m: Decimal
    cell_size_m: Decimal

    def __post_init__(self) -> None:
        if not isinstance(self.crs_id, str) or self.crs_id not in _METRE_EPSG:
            raise ValueError("crs_id must be a supported metre-based EPSG CRS")
        if not isinstance(self.projection_version, str) or not _SHA256.fullmatch(
            self.projection_version
        ):
            raise ValueError("projection_version must be a SHA-256 digest")
        _metres(self.origin_x_m, "origin_x_m")
        _metres(self.origin_y_m, "origin_y_m")
        _metres(self.cell_size_m, "cell_size_m", positive=True)


@dataclass(frozen=True)
class SpatialFold:
    protocol_id: str
    parent_temporal_hash: str
    grid: ProjectedGrid
    heldout_cells: tuple[tuple[int, int], ...]
    buffer_m: Decimal
    train_row_ids: tuple[str, ...]
    validation_row_ids: tuple[str, ...]
    immature_row_ids: tuple[str, ...]
    purged_heldout_row_ids: tuple[str, ...]
    purged_buffer_row_ids: tuple[str, ...]
    purged_repeat_property_row_ids: tuple[str, ...]
    out_of_area_validation_row_ids: tuple[str, ...]
    parent_train_count: int
    parent_validation_count: int
    split_hash: str


def _cell(point: ProjectedRow, grid: ProjectedGrid) -> tuple[int, int]:
    return (
        (Fraction(point.x_m) - Fraction(grid.origin_x_m)) // Fraction(grid.cell_size_m),
        (Fraction(point.y_m) - Fraction(grid.origin_y_m)) // Fraction(grid.cell_size_m),
    )


def _distance_sq_to_cell(
    point: ProjectedRow, cell: tuple[int, int], grid: ProjectedGrid
) -> Fraction:
    size = Fraction(grid.cell_size_m)
    left = Fraction(grid.origin_x_m) + size * cell[0]
    bottom = Fraction(grid.origin_y_m) + size * cell[1]
    right = left + size
    top = bottom + size
    x = Fraction(point.x_m)
    y = Fraction(point.y_m)
    dx = max(left - x, x - right, Fraction(0))
    dy = max(bottom - y, y - top, Fraction(0))
    return dx * dx + dy * dy


def _locations_by_id(
    origins: Sequence[OriginRef], locations: Sequence[ProjectedRow]
) -> dict[str, ProjectedRow]:
    indexed: dict[str, ProjectedRow] = {}
    for point in locations:
        if not isinstance(point, ProjectedRow) or point.row_id in indexed:
            raise ValueError("Each origin needs exactly one unique location")
        indexed[point.row_id] = point
    origin_properties = {row.row_id: row.property_id for row in origins}
    if set(indexed) != set(origin_properties):
        raise ValueError("location rows must exactly match origin row IDs")
    if any(
        point.property_id != origin_properties[row_id]
        for row_id, point in indexed.items()
    ):
        raise ValueError("Location property identity differs from origin")
    return indexed


def _heldout_cells(cells: Sequence[tuple[int, int]]) -> tuple[tuple[int, int], ...]:
    try:
        values = tuple(islice(cells, 257))
    except TypeError as exc:
        raise ValueError("heldout_cells must be a sequence") from exc
    if (
        not values
        or any(
            not isinstance(cell, tuple)
            or len(cell) != 2
            or any(type(index) is not int or abs(index) > 10**9 for index in cell)
            for cell in values
        )
        or len(values) > 256
        or len(set(values)) != len(values)
    ):
        raise ValueError("heldout_cells must be nonempty unique integer grid cells")
    return tuple(sorted(values))


def _split_hash(
    fold: SpatialFold,
    temporal: TemporalFold,
    locations: dict[str, ProjectedRow],
) -> str:
    grid = fold.grid
    payload = {
        "protocol_id": fold.protocol_id,
        "parent_temporal_hash": temporal.split_hash,
        "grid": {
            "crs_id": grid.crs_id,
            "projection_version": grid.projection_version,
            "origin_x_m": _decimal_text(grid.origin_x_m),
            "origin_y_m": _decimal_text(grid.origin_y_m),
            "cell_size_m": _decimal_text(grid.cell_size_m),
        },
        "heldout_cells": fold.heldout_cells,
        "buffer_m": _decimal_text(fold.buffer_m),
        "locations": [
            (
                point.row_id,
                point.property_id,
                _decimal_text(point.x_m),
                _decimal_text(point.y_m),
            )
            for point in sorted(locations.values(), key=lambda item: item.row_id)
        ],
        "train_row_ids": fold.train_row_ids,
        "validation_row_ids": fold.validation_row_ids,
        "immature_row_ids": fold.immature_row_ids,
        "purged_heldout_row_ids": fold.purged_heldout_row_ids,
        "purged_buffer_row_ids": fold.purged_buffer_row_ids,
        "purged_repeat_property_row_ids": fold.purged_repeat_property_row_ids,
        "out_of_area_validation_row_ids": fold.out_of_area_validation_row_ids,
    }
    return sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def build_spatial_fold(
    origins: Sequence[OriginRef],
    training_maturity: Sequence[LabelMaturity],
    locations: Sequence[ProjectedRow],
    *,
    training_cutoff: datetime,
    validation_start: datetime,
    validation_end: datetime,
    grid: ProjectedGrid,
    heldout_cells: Sequence[tuple[int, int]],
    buffer_m: Decimal,
    horizon_days: int = 90,
    protocol_id: str = "us_synthetic_rolling_v2",
) -> SpatialFold:
    """Purge heldout blocks, boundaries and repeats after temporal validation."""
    if not isinstance(grid, ProjectedGrid):
        raise ValueError("grid must be a ProjectedGrid")
    cells = _heldout_cells(heldout_cells)
    _metres(buffer_m, "buffer_m")
    if buffer_m < 0:
        raise ValueError("buffer_m cannot be negative")
    temporal = build_temporal_fold(
        origins,
        training_maturity,
        training_cutoff=training_cutoff,
        validation_start=validation_start,
        validation_end=validation_end,
        horizon_days=horizon_days,
        protocol_id=protocol_id,
    )
    points = _locations_by_id(origins, locations)
    validation = tuple(
        row_id
        for row_id in temporal.validation_row_ids
        if _cell(points[row_id], grid) in cells
    )
    if not validation:
        raise ValueError("Spatial fold has no validation origins in heldout cells")
    selected_properties = {points[row_id].property_id for row_id in validation}
    validation_set = set(validation)
    cell_set = set(cells)
    buffer_squared = Fraction(buffer_m) ** 2
    in_cell: list[str] = []
    buffered: list[str] = []
    repeated: list[str] = []
    train: list[str] = []
    for row_id in temporal.train_row_ids:
        point = points[row_id]
        if _cell(point, grid) in cell_set:
            in_cell.append(row_id)
        elif any(
            _distance_sq_to_cell(point, cell, grid) <= buffer_squared for cell in cells
        ):
            buffered.append(row_id)
        elif point.property_id in selected_properties:
            repeated.append(row_id)
        else:
            train.append(row_id)
    if not train:
        raise ValueError("Spatial fold has no training rows after purging")
    fold = SpatialFold(
        protocol_id=temporal.protocol_id,
        parent_temporal_hash=temporal.split_hash,
        grid=grid,
        heldout_cells=cells,
        buffer_m=buffer_m,
        train_row_ids=tuple(train),
        validation_row_ids=validation,
        immature_row_ids=temporal.immature_row_ids,
        purged_heldout_row_ids=tuple(in_cell),
        purged_buffer_row_ids=tuple(buffered),
        purged_repeat_property_row_ids=tuple(repeated),
        out_of_area_validation_row_ids=tuple(
            row_id
            for row_id in temporal.validation_row_ids
            if row_id not in validation_set
        ),
        parent_train_count=len(temporal.train_row_ids),
        parent_validation_count=len(temporal.validation_row_ids),
        split_hash="",
    )
    return replace(fold, split_hash=_split_hash(fold, temporal, points))
