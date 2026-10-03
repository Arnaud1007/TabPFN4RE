"""Synthetic effective-version and publication-time canaries for US06/US08."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
import sys
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tabpfn4realestate.data.schema import Attribute, Property, SourceSnapshot  # noqa: E402
from tabpfn4realestate.features.asof import assemble_snapshot  # noqa: E402


def at(month: int, day: int = 1) -> datetime:
    return datetime(2024, month, day, tzinfo=timezone.utc)


def property_version(**changes: object) -> Property:
    fields = {
        "property_id": "synthetic-home",
        "country": "US",
        "property_type": "single_family",
        "source_id": "synthetic-assessor",
        "observed_at": at(1),
        "available_at": at(1),
        "living_area": Decimal("1500"),
        "living_area_unit": "sqft",
    }
    return Property(**(fields | changes))


def condition(value: str = "fair", **changes: object) -> Attribute:
    fields = {
        "property_id": "synthetic-home",
        "name": "condition",
        "value": value,
        "observed_at": at(1),
        "available_at": at(1),
        "source_id": "synthetic-assessor",
    }
    return Attribute(**(fields | changes))


def snapshot(
    origin: datetime, *, as_of: datetime | None = None, attributes=(), property=None
):
    return assemble_snapshot(
        property or property_version(),
        origin,
        "OFF",
        SourceSnapshot(
            snapshot_id="synthetic-vintage",
            source_ids=("synthetic-assessor",),
            as_of=as_of or origin,
        ),
        attributes=attributes,
    )


class EffectiveVersionTests(unittest.TestCase):
    def test_known_expired_property_version_is_rejected(self):
        old = property_version(
            valid_from=at(1), valid_to=at(6), valid_to_available_at=at(5)
        )
        with self.assertRaisesRegex(ValueError, "valid|expired"):
            snapshot(at(7), property=old)

    def test_later_published_property_expiry_cannot_rewrite_earlier_origin(self):
        old = property_version(
            valid_from=at(1), valid_to=at(5), valid_to_available_at=at(7)
        )
        self.assertEqual(
            snapshot(at(6), property=old).values["property_type"], "single_family"
        )
        with self.assertRaisesRegex(ValueError, "valid|expired"):
            snapshot(at(8), property=old)

    def test_known_expired_attribute_is_absent(self):
        old = condition(valid_from=at(1), valid_to=at(5), valid_to_available_at=at(4))
        self.assertNotIn("condition", snapshot(at(6), attributes=(old,)).values)

    def test_later_published_correction_preserves_earlier_snapshot(self):
        old = condition(valid_from=at(1), valid_to=at(5), valid_to_available_at=at(7))
        corrected = condition(
            "renovated", observed_at=at(5), available_at=at(7), valid_from=at(5)
        )
        earlier = snapshot(at(6), attributes=(old,))
        with_unavailable_correction = snapshot(at(6), attributes=(old, corrected))
        self.assertEqual(dict(with_unavailable_correction.values), dict(earlier.values))
        self.assertEqual(
            with_unavailable_correction.snapshot_hash, earlier.snapshot_hash
        )
        self.assertEqual(
            snapshot(at(8), attributes=(old, corrected)).values["condition"],
            "renovated",
        )

    def test_simultaneously_effective_competing_versions_are_rejected(self):
        first = condition(
            valid_from=at(1), valid_to=at(12), valid_to_available_at=at(1)
        )
        second = condition(
            "poor", observed_at=at(6), available_at=at(6), valid_from=at(6)
        )
        with self.assertRaisesRegex(ValueError, "[Aa]mbiguous|overlap|competing"):
            snapshot(at(7), attributes=(first, second))

    def test_valid_to_is_exclusive_at_exact_instant(self):
        old = condition(valid_from=at(1), valid_to=at(6), valid_to_available_at=at(5))
        before = snapshot(at(6) - timedelta(microseconds=1), attributes=(old,))
        at_boundary = snapshot(at(6), attributes=(old,))
        self.assertEqual(before.values["condition"], "fair")
        self.assertNotIn("condition", at_boundary.values)

    def test_source_snapshot_cutoff_limits_version_end_knowledge(self):
        old = condition(valid_from=at(1), valid_to=at(5), valid_to_available_at=at(7))
        corrected = condition(
            "renovated", observed_at=at(5), available_at=at(7), valid_from=at(5)
        )
        result = snapshot(at(8), as_of=at(6), attributes=(old, corrected))
        self.assertEqual(result.values["condition"], "fair")

    def test_version_end_requires_publication_time(self):
        with self.assertRaisesRegex(ValueError, "valid_to_available_at|availability"):
            condition(valid_from=at(1), valid_to=at(5))

    def test_future_effective_start_is_excluded_even_when_record_is_available(self):
        future_property = property_version(valid_from=at(7))
        with self.assertRaisesRegex(ValueError, "valid"):
            snapshot(at(6), property=future_property)
        future_attribute = condition(valid_from=at(7))
        self.assertNotIn(
            "condition", snapshot(at(6), attributes=(future_attribute,)).values
        )

    def test_later_disclosed_end_does_not_change_historical_lineage(self):
        original = condition(valid_from=at(1))
        later_end = condition(
            valid_from=at(1), valid_to=at(5), valid_to_available_at=at(7)
        )
        original_snapshot = snapshot(at(6), attributes=(original,))
        revised_snapshot = snapshot(at(6), attributes=(original, later_end))
        self.assertEqual(revised_snapshot.lineage, original_snapshot.lineage)
        self.assertEqual(
            revised_snapshot.snapshot_hash, original_snapshot.snapshot_hash
        )

    def test_known_revision_closes_an_earlier_open_attribute_copy(self):
        original = condition(valid_from=at(1))
        revised = condition(
            available_at=at(7),
            valid_from=at(1),
            valid_to=at(5),
            valid_to_available_at=at(7),
        )
        self.assertEqual(
            snapshot(at(6), attributes=(original, revised)).values["condition"],
            "fair",
        )
        self.assertNotIn(
            "condition", snapshot(at(8), attributes=(original, revised)).values
        )

    def test_published_end_reconciles_open_copy_before_expiry(self):
        original = condition(valid_from=at(1))
        revised = condition(
            available_at=at(3),
            valid_from=at(1),
            valid_to=at(5),
            valid_to_available_at=at(3),
        )
        result = snapshot(at(4), attributes=(original, revised))
        self.assertEqual(result.values["condition"], "fair")
        self.assertEqual(result.lineage["condition"].valid_to, at(5))
        self.assertNotIn(
            "condition", snapshot(at(6), attributes=(original, revised)).values
        )

    def test_conflicting_published_ends_are_rejected(self):
        first = condition(valid_from=at(1), valid_to=at(5), valid_to_available_at=at(3))
        second = condition(
            valid_from=at(1), valid_to=at(6), valid_to_available_at=at(3)
        )
        with self.assertRaisesRegex(ValueError, "Ambiguous attribute version end"):
            snapshot(at(4), attributes=(first, second))

    def test_changed_value_or_observation_cannot_leave_stale_open_copy(self):
        original = condition(valid_from=at(1))
        corrections = (
            condition(
                "poor",
                available_at=at(7),
                valid_from=at(1),
                valid_to=at(5),
                valid_to_available_at=at(7),
            ),
            condition(
                observed_at=at(7),
                available_at=at(7),
                valid_from=at(1),
                valid_to=at(5),
                valid_to_available_at=at(7),
            ),
        )
        for correction in corrections:
            with self.subTest(correction=correction):
                with self.assertRaisesRegex(ValueError, "overlap|Ambiguous"):
                    snapshot(at(8), attributes=(original, correction))

    def test_later_open_copy_cannot_silently_retract_a_known_end(self):
        finite = condition(
            valid_from=at(1), valid_to=at(5), valid_to_available_at=at(3)
        )
        later_open = condition(available_at=at(7), valid_from=at(1))
        with self.assertRaisesRegex(ValueError, "retraction|Ambiguous"):
            snapshot(at(8), attributes=(finite, later_open))

    def test_invalid_effective_interval_and_timestamp_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "valid_to"):
            condition(valid_from=at(5), valid_to=at(5), valid_to_available_at=at(4))
        with self.assertRaisesRegex(ValueError, "valid_from"):
            property_version(valid_from=at(5).replace(tzinfo=None))
        with self.assertRaisesRegex(ValueError, "valid_to_available_at"):
            condition(valid_to_available_at=at(5))


if __name__ == "__main__":
    unittest.main()
