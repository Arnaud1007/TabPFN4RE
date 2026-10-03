"""Synthetic geographic holdout fixtures for US11."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal, localcontext
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tabpfn4realestate.evaluation.splits import LabelMaturity, OriginRef  # noqa: E402
from tabpfn4realestate.evaluation.spatial_splits import (  # noqa: E402
    ProjectedGrid,
    ProjectedRow,
    build_spatial_fold,
)


BASE = datetime(2024, 1, 1, tzinfo=timezone.utc)
D = Decimal
GRID = ProjectedGrid("EPSG:26916", "a" * 64, D("0"), D("0"), D("100"))


def origin(row_id: str, day: int, property_id: str | None = None) -> OriginRef:
    return OriginRef(
        row_id, property_id or f"property-{row_id}", BASE + timedelta(days=day)
    )


def maturity(row: OriginRef) -> LabelMaturity:
    close = row.origin + timedelta(days=90)
    return LabelMaturity(row.row_id, close, close + timedelta(days=7))


def location(row: OriginRef, x: str, y: str = "0") -> ProjectedRow:
    return ProjectedRow(row.row_id, row.property_id, D(x), D(y))


def build(origins, labels, locations, **changes):
    options = {
        "training_cutoff": BASE + timedelta(days=120),
        "validation_start": BASE + timedelta(days=130),
        "validation_end": BASE + timedelta(days=160),
        "grid": GRID,
        "heldout_cells": ((2, 0),),
        "buffer_m": D("10"),
    }
    return build_spatial_fold(origins, labels, locations, **(options | changes))


class SpatialFoldTests(unittest.TestCase):
    def setUp(self):
        self.safe = origin("safe", 0)
        self.buffered = origin("buffered", 0)
        self.blocked = origin("blocked", 0)
        self.immature = origin("immature", 50)
        self.validation = origin("validation", 130)
        self.other = origin("other", 131)
        self.origins = (
            self.safe,
            self.buffered,
            self.blocked,
            self.immature,
            self.validation,
            self.other,
        )
        self.labels = tuple(maturity(row) for row in self.origins[:4])
        self.locations = (
            location(self.safe, "0"),
            location(self.buffered, "195"),
            location(self.blocked, "250"),
            location(self.immature, "0"),
            location(self.validation, "250"),
            location(self.other, "0"),
        )

    def test_matured_membership_and_exclusions(self):
        result = build(self.origins, self.labels, self.locations)
        self.assertEqual(result.train_row_ids, ("safe",))
        self.assertEqual(result.validation_row_ids, ("validation",))
        self.assertEqual(result.immature_row_ids, ("immature",))
        self.assertEqual(result.purged_heldout_row_ids, ("blocked",))
        self.assertEqual(result.purged_buffer_row_ids, ("buffered",))
        self.assertEqual(result.out_of_area_validation_row_ids, ("other",))
        self.assertEqual(result.parent_train_count, 3)
        self.assertEqual(result.parent_validation_count, 2)
        self.assertEqual(len(result.parent_temporal_hash), 64)

    def test_reserved_label_and_real_protocol_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "reserved"):
            build(
                self.origins, self.labels + (maturity(self.validation),), self.locations
            )
        with self.assertRaisesRegex(ValueError, "synthetic"):
            build(self.origins, self.labels, self.locations, protocol_id="us_real_v1")

    def test_half_open_negative_cells_and_exact_buffer_distance(self):
        safe = origin("safe", 0)
        axis = origin("axis", 0)
        corner = origin("corner", 0)
        outside = origin("outside", 0)
        negative = origin("negative", 0)
        inside = origin("inside", 0)
        validation = origin("validation", 130)
        rows = (safe, axis, corner, outside, negative, inside, validation)
        points = (
            location(safe, "0"),
            location(axis, "190"),
            location(corner, "197", "-4"),
            location(outside, "189.999"),
            location(negative, "-0.001"),
            location(inside, "200"),
            location(validation, "200"),
        )
        result = build(
            rows,
            tuple(maturity(row) for row in rows[:-1]),
            points,
            heldout_cells=((2, 0),),
            buffer_m=D("10"),
        )
        self.assertEqual(result.train_row_ids, ("negative", "outside", "safe"))
        self.assertEqual(result.purged_buffer_row_ids, ("axis", "corner"))
        self.assertEqual(result.purged_heldout_row_ids, ("inside",))

    def test_negative_cell_uses_floor_and_zero_buffer_purges_boundary(self):
        safe = origin("safe", 0)
        blocked = origin("blocked", 0)
        boundary = origin("boundary", 0)
        validation = origin("validation", 130)
        rows = (safe, blocked, boundary, validation)
        points = (
            location(safe, "250"),
            location(blocked, "-0.001"),
            location(boundary, "0"),
            location(validation, "-0.002"),
        )
        result = build(
            rows,
            tuple(maturity(row) for row in rows[:-1]),
            points,
            heldout_cells=((-1, 0),),
            buffer_m=D("0"),
        )
        self.assertEqual(result.train_row_ids, ("safe",))
        self.assertEqual(result.purged_heldout_row_ids, ("blocked",))
        self.assertEqual(result.purged_buffer_row_ids, ("boundary",))

    def test_diagonal_exact_buffer_boundary(self):
        safe = origin("safe", 0)
        exact = origin("exact", 0)
        beyond = origin("beyond", 0)
        validation = origin("validation", 130)
        rows = (safe, exact, beyond, validation)
        points = (
            location(safe, "0"),
            location(exact, "197", "-4"),
            location(beyond, "196.999", "-4"),
            location(validation, "200"),
        )
        result = build(
            rows, tuple(maturity(row) for row in rows[:-1]), points, buffer_m=D("5")
        )
        self.assertEqual(result.purged_buffer_row_ids, ("exact",))
        self.assertEqual(result.train_row_ids, ("beyond", "safe"))

    def test_decimal_context_cannot_change_membership_or_hash(self):
        points = (location(self.safe, "199.999"),) + self.locations[1:]
        normal = build(self.origins, self.labels, points, buffer_m=D("0"))
        with localcontext() as context:
            context.prec = 3
            low_precision = build(self.origins, self.labels, points, buffer_m=D("0"))
        self.assertEqual(normal.train_row_ids, low_precision.train_row_ids)
        self.assertEqual(normal.validation_row_ids, low_precision.validation_row_ids)
        self.assertEqual(normal.split_hash, low_precision.split_hash)

    def test_repeated_property_is_purged_even_with_conflicting_far_coordinate(self):
        earlier = replace(self.safe, property_id="same-home")
        validation = replace(self.validation, property_id="same-home")
        rows = (
            earlier,
            self.buffered,
            self.blocked,
            self.immature,
            validation,
            self.other,
        )
        points = (
            location(earlier, "0"),
            *self.locations[1:4],
            location(validation, "250"),
            self.locations[-1],
        )
        with self.assertRaisesRegex(ValueError, "no training"):
            build(rows, self.labels, points)
        extra = origin("extra", 0)
        result = build(
            rows + (extra,),
            self.labels + (maturity(extra),),
            points + (location(extra, "0"),),
        )
        self.assertEqual(result.purged_repeat_property_row_ids, ("safe",))
        self.assertEqual(result.train_row_ids, ("extra",))

    def test_locations_require_one_to_one_identity(self):
        with self.assertRaisesRegex(ValueError, "location"):
            build(self.origins, self.labels, self.locations[:-1])
        with self.assertRaisesRegex(ValueError, "location"):
            build(self.origins, self.labels, self.locations + (self.locations[0],))
        wrong = replace(self.locations[0], property_id="wrong")
        with self.assertRaisesRegex(ValueError, "property"):
            build(self.origins, self.labels, (wrong,) + self.locations[1:])
        unknown = ProjectedRow("unknown", "unknown-property", D("0"), D("0"))
        with self.assertRaisesRegex(ValueError, "location"):
            build(self.origins, self.labels, self.locations + (unknown,))

    def test_invalid_grid_coordinates_and_selection_fail(self):
        for value in (D("NaN"), D("Infinity"), 1.5, "1"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                ProjectedRow("r", "p", value, D("0"))
        for size in (D("0"), D("-1"), D("NaN")):
            with self.subTest(size=size), self.assertRaises(ValueError):
                ProjectedGrid("EPSG:26916", "a" * 64, D("0"), D("0"), size)
        for crs in ("EPSG:4326", "EPSG:4267", "EPSG:4609", "EPSG:2227"):
            with self.subTest(crs=crs), self.assertRaises(ValueError):
                ProjectedGrid(crs, "a" * 64, D("0"), D("0"), D("100"))
        with self.assertRaises(ValueError):
            ProjectedGrid("EPSG:26916", "short", D("0"), D("0"), D("100"))
        for cells in ((), ((2, 0), (2, 0)), ((True, 0),)):
            with self.subTest(cells=cells), self.assertRaises(ValueError):
                build(self.origins, self.labels, self.locations, heldout_cells=cells)
        with self.assertRaises(ValueError):
            build(self.origins, self.labels, self.locations, buffer_m=D("-1"))
        with self.assertRaises(ValueError):
            build(
                self.origins,
                self.labels,
                self.locations,
                heldout_cells=tuple((x, 0) for x in range(257)),
            )

    def test_hash_is_canonical_and_binds_inputs(self):
        first = build(
            self.origins, self.labels, self.locations, heldout_cells=((2, 0), (3, 0))
        )
        reordered = build(
            tuple(reversed(self.origins)),
            tuple(reversed(self.labels)),
            tuple(reversed(self.locations)),
            heldout_cells=((3, 0), (2, 0)),
            buffer_m=D("10.0"),
        )
        self.assertEqual(first.split_hash, reordered.split_hash)
        self.assertEqual(len(first.split_hash), 64)
        variants = (
            {"grid": replace(GRID, projection_version="b" * 64)},
            {"grid": replace(GRID, cell_size_m=D("101"))},
            {"buffer_m": D("11")},
            {"heldout_cells": ((2, 0),)},
        )
        for variant in variants:
            with self.subTest(variant=variant):
                self.assertNotEqual(
                    first.split_hash,
                    build(
                        self.origins, self.labels, self.locations, **variant
                    ).split_hash,
                )
        moved = self.locations[:-1] + (location(self.other, "1"),)
        self.assertNotEqual(
            first.split_hash,
            build(
                self.origins, self.labels, moved, heldout_cells=((2, 0), (3, 0))
            ).split_hash,
        )

    def test_empty_spatial_validation_fails(self):
        with self.assertRaisesRegex(ValueError, "validation"):
            build(self.origins, self.labels, self.locations, heldout_cells=((9, 9),))


if __name__ == "__main__":
    unittest.main()
