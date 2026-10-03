"""Synthetic property-history selection canaries for US06 and US08."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
import sys
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tabpfn4realestate.data.schema import Property, SourceSnapshot  # noqa: E402
from tabpfn4realestate.features.asof import (  # noqa: E402
    assemble_snapshot_from_versions,
    select_property_version,
)


def at(month: int, day: int = 1) -> datetime:
    return datetime(2024, month, day, tzinfo=timezone.utc)


def version(**changes: object) -> Property:
    fields = {
        "property_id": "synthetic-home",
        "country": "US",
        "property_type": "single_family",
        "source_id": "assessor",
        "observed_at": at(1),
        "available_at": at(1),
        "living_area": Decimal("1500"),
        "living_area_unit": "sqft",
    }
    return Property(**(fields | changes))


def source(as_of: datetime) -> SourceSnapshot:
    return SourceSnapshot("assessor-vintage", ("assessor",), as_of)


def select(origin: datetime, versions: tuple[Property, ...], *, as_of=None):
    return select_property_version(
        "synthetic-home", versions, origin, source(as_of or origin)
    )


def assemble(origin: datetime, versions: tuple[Property, ...], *, as_of=None):
    return assemble_snapshot_from_versions(
        "synthetic-home", versions, origin, "OFF", source(as_of or origin)
    )


class PropertyVersionSelectionTests(unittest.TestCase):
    def test_boundary_selects_correct_structural_version_independent_of_order(self):
        old = version(valid_from=at(1), valid_to=at(6), valid_to_available_at=at(5))
        new = version(
            property_type="single_family",
            living_area=Decimal("1700"),
            observed_at=at(6),
            available_at=at(6),
            valid_from=at(6),
        )
        before = assemble(at(6) - timedelta(microseconds=1), (old, new))
        after = assemble(at(6), (old, new))
        reversed_after = assemble(at(6), (new, old))
        self.assertEqual(before.values["living_area"], Decimal("1500"))
        self.assertEqual(after.values["living_area"], Decimal("1700"))
        self.assertEqual(after.lineage["living_area"].observed_at, at(6))
        self.assertEqual(after.snapshot_hash, reversed_after.snapshot_hash)

    def test_known_end_closes_earlier_open_copy(self):
        open_old = version(valid_from=at(1))
        revised_old = version(
            valid_from=at(1),
            available_at=at(5),
            valid_to=at(6),
            valid_to_available_at=at(5),
        )
        new = version(
            living_area=Decimal("1700"),
            observed_at=at(6),
            available_at=at(6),
            valid_from=at(6),
        )
        selected = select(at(7), (open_old, revised_old, new))
        self.assertEqual(selected.living_area, Decimal("1700"))

    def test_equivalent_copies_have_order_independent_snapshot_and_lineage(self):
        implicit = version()
        explicit = version(valid_from=at(1), living_area=Decimal("1500.0"))
        first = assemble(at(7), (implicit, explicit))
        reversed_result = assemble(at(7), (explicit, implicit))
        self.assertEqual(first.snapshot_hash, reversed_result.snapshot_hash)
        self.assertEqual(first.values, reversed_result.values)
        self.assertEqual(first.lineage, reversed_result.lineage)

    def test_equivalent_end_instants_return_one_canonical_timezone(self):
        utc_copy = version(valid_to=at(6), valid_to_available_at=at(5))
        offset_copy = version(
            valid_to=at(6).astimezone(timezone(timedelta(hours=1))),
            valid_to_available_at=at(5).astimezone(timezone(timedelta(hours=1))),
        )
        forward = select(at(5), (utc_copy, offset_copy))
        reverse = select(at(5), (offset_copy, utc_copy))
        self.assertEqual(forward.valid_to.isoformat(), reverse.valid_to.isoformat())
        self.assertEqual(
            forward.valid_to_available_at.isoformat(),
            reverse.valid_to_available_at.isoformat(),
        )

    def test_later_information_cutoff_selects_correct_prior_effective_version(self):
        old = version(valid_from=at(1), valid_to=at(5), valid_to_available_at=at(6))
        corrected = version(
            living_area=Decimal("1700"),
            observed_at=at(1),
            available_at=at(6),
            valid_from=at(5),
        )
        self.assertEqual(
            select_property_version(
                "synthetic-home",
                (old, corrected),
                at(5),
                source(at(7)),
                known_at=at(7),
            ).living_area,
            Decimal("1700"),
        )

    def test_late_publication_preserves_earlier_snapshot_hash(self):
        old = version(valid_from=at(1))
        published_end = version(
            valid_from=at(1),
            available_at=at(8),
            valid_to=at(6),
            valid_to_available_at=at(8),
        )
        new = version(
            living_area=Decimal("1700"),
            observed_at=at(6),
            available_at=at(8),
            valid_from=at(6),
        )
        baseline = assemble(at(7), (old,))
        with_future = assemble(at(7), (old, published_end, new))
        self.assertEqual(with_future.snapshot_hash, baseline.snapshot_hash)
        self.assertEqual(
            assemble(at(9), (old, published_end, new)).values["living_area"],
            Decimal("1700"),
        )

    def test_source_snapshot_cutoff_limits_end_and_new_version(self):
        old = version(valid_from=at(1))
        published_end = version(
            valid_from=at(1),
            available_at=at(8),
            valid_to=at(6),
            valid_to_available_at=at(8),
        )
        new = version(
            living_area=Decimal("1700"),
            observed_at=at(6),
            available_at=at(8),
            valid_from=at(6),
        )
        result = assemble(at(9), (old, published_end, new), as_of=at(7))
        self.assertEqual(result.values["living_area"], Decimal("1500"))

    def test_selector_does_not_return_unpublished_end_metadata(self):
        old = version(
            valid_from=at(1),
            valid_to=at(5),
            valid_to_available_at=at(8),
        )
        selected = select(at(7), (old,))
        self.assertIsNone(selected.valid_to)
        self.assertIsNone(selected.valid_to_available_at)

    def test_future_unlisted_source_cannot_change_earlier_snapshot(self):
        old = version(valid_from=at(1))
        future = version(
            source_id="new-source",
            observed_at=at(8),
            available_at=at(8),
            valid_from=at(8),
        )
        earlier = assemble(at(7), (old,))
        with_future = assemble(at(7), (old, future))
        self.assertEqual(earlier.snapshot_hash, with_future.snapshot_hash)
        with self.assertRaisesRegex(ValueError, "source"):
            assemble(at(9), (old, future))

    def test_overlapping_versions_fail_closed(self):
        old = version(valid_from=at(1), valid_to=at(9), valid_to_available_at=at(5))
        new = version(
            living_area=Decimal("1700"),
            observed_at=at(6),
            available_at=at(6),
            valid_from=at(6),
        )
        with self.assertRaisesRegex(ValueError, "overlap|[Aa]mbiguous"):
            select(at(7), (old, new))

    def test_conflicting_ends_and_later_retraction_fail_closed(self):
        first = version(valid_from=at(1), valid_to=at(5), valid_to_available_at=at(3))
        conflicting = version(
            valid_from=at(1), valid_to=at(6), valid_to_available_at=at(3)
        )
        later_open = version(valid_from=at(1), available_at=at(7))
        for history in ((first, conflicting), (first, later_open)):
            with self.subTest(history=history):
                with self.assertRaisesRegex(ValueError, "[Aa]mbiguous|retraction"):
                    select(at(8), history)

    def test_empty_invalid_source_and_wrong_identity_fail_closed(self):
        for history in (
            (),
            (version(property_id="different-home"),),
            (version(source_id="unlisted"),),
            (version(observed_at=at(8), available_at=at(8)),),
        ):
            with self.subTest(history=history):
                with self.assertRaises(ValueError):
                    select(at(7), history)


if __name__ == "__main__":
    unittest.main()
