"""Date-precision publications stay typed through local OFF feature assembly."""

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
import sys
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


from tabpfn4realestate.data.local_date_facts import (  # noqa: E402
    DatePublishedAttribute,
    DatePublishedProperty,
    DateOnlyEvent,
    event_day_end_utc,
)
from tabpfn4realestate.data.local_date_sale import LocalDateSale  # noqa: E402
from tabpfn4realestate.data.schema import (  # noqa: E402
    Attribute,
    Property,
    SourceSnapshot,
    Transaction,
)
from tabpfn4realestate.evaluation.local_dates import (  # noqa: E402
    DateOnlyAvailability,
    derive_local_date_origin,
)
from tabpfn4realestate.features.asof import (  # noqa: E402
    NoAvailablePropertyVersionError,
    assemble_local_date_snapshot,
    assemble_snapshot,
    select_property_version,
)
from tabpfn4realestate.features.asof_local_date import (  # noqa: E402
    assemble_local_date_snapshot_from_versions_v2,
    assemble_local_date_snapshot_v2,
)


UTC = timezone.utc
NY = "America/New_York"
SPRING = derive_local_date_origin(date(2024, 6, 8), NY)
ORIGIN_DAY = date(2024, 3, 10)
SOURCE = "synthetic-county"


def source(as_of=None):
    return SourceSnapshot(
        "synthetic-v2", (SOURCE,), as_of or SPRING.cutoff_exclusive_utc
    )


def property_row(publication=None, **changes):
    return replace(
        DatePublishedProperty(
            property_id="home-1",
            country="US",
            property_type="single_family",
            source_id=SOURCE,
            observed_at=datetime(2023, 1, 1, tzinfo=UTC),
            available_at=publication or DateOnlyAvailability(ORIGIN_DAY, NY),
            living_area=Decimal("1500"),
            living_area_unit="sqft",
        ),
        **changes,
    )


def attribute_row(publication=None, **changes):
    return replace(
        DatePublishedAttribute(
            property_id="home-1",
            name="condition",
            value="good",
            observed_at=datetime(2024, 3, 10, 12, tzinfo=UTC),
            available_at=publication or DateOnlyAvailability(ORIGIN_DAY, NY),
            source_id=SOURCE,
        ),
        **changes,
    )


def prior_sale(publication=None, **changes):
    return replace(
        LocalDateSale(
            transaction_id="prior-deed",
            economic_transfer_id="prior-transfer",
            property_id="home-1",
            close_date=date(2024, 2, 1),
            close_zone_key=NY,
            available_at=publication or DateOnlyAvailability(ORIGIN_DAY, NY),
            price=Decimal("120000"),
            currency="USD",
            source_id=SOURCE,
            scope="single_property",
            consideration_type="gross_recorded_sale",
            arm_length_status="confirmed",
            adjustment_flags=(),
        ),
        **changes,
    )


class DatePublicationV2Tests(unittest.TestCase):
    def test_date_published_contract_rejects_false_precision_and_invalid_values(self):
        with self.assertRaisesRegex(ValueError, "date precision"):
            DateOnlyEvent(datetime(2024, 3, 10, tzinfo=UTC), NY)
        with self.assertRaisesRegex(ValueError, "date event"):
            event_day_end_utc(datetime(2024, 3, 10, tzinfo=UTC))
        with self.assertRaisesRegex(ValueError, "calendar range"):
            event_day_end_utc(DateOnlyEvent(date.max, NY))

        invalid_property = (
            {"country": "FR"},
            {"available_at": datetime(2024, 3, 10, tzinfo=UTC)},
            {"valid_to_available_at": DateOnlyAvailability(ORIGIN_DAY, NY)},
            {"valid_to": datetime(2024, 4, 1, tzinfo=UTC)},
            {
                "valid_to": datetime(2022, 1, 1, tzinfo=UTC),
                "valid_to_available_at": DateOnlyAvailability(ORIGIN_DAY, NY),
            },
            {
                "living_area": None,
                "living_area_state": "unknown",
                "living_area_unit": "sqft",
            },
            {"living_area_unit": "hectares"},
            {"latitude": Decimal("1")},
            {"latitude": Decimal("91"), "longitude": Decimal("1")},
        )
        for changes in invalid_property:
            with self.subTest(property_changes=changes), self.assertRaises(ValueError):
                property_row(**changes)
        invalid_attribute = (
            {"available_at": datetime(2024, 3, 10, tzinfo=UTC)},
            {"valid_to_available_at": DateOnlyAvailability(ORIGIN_DAY, NY)},
            {"valid_to": datetime(2024, 4, 1, tzinfo=UTC)},
            {"value": ["not", "scalar"]},
            {"value": Decimal("NaN")},
        )
        for changes in invalid_attribute:
            with self.subTest(attribute_changes=changes), self.assertRaises(ValueError):
                attribute_row(**changes)

    def test_v2_entrypoints_reject_incompatible_fact_types(self):
        for kwargs in (
            {"property": object()},
            {"origin": "2024-03-10"},
            {"attributes": (object(),)},
            {"transactions": (object(),)},
        ):
            request = {"property": property_row(), "origin": SPRING}
            request.update(kwargs)
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                assemble_local_date_snapshot_v2(
                    request["property"],
                    request["origin"],
                    "OFF",
                    source(),
                    attributes=request.get("attributes", ()),
                    transactions=request.get("transactions", ()),
                )
        with self.assertRaises(ValueError):
            assemble_local_date_snapshot_from_versions_v2(
                "home-1", (property_row(),), "2024-03-10", "OFF", source()
            )
        with self.assertRaises(ValueError):
            assemble_local_date_snapshot_from_versions_v2(
                "home-1", (object(),), SPRING, "OFF", source()
            )

    def test_origin_day_publications_are_visible_without_making_up_a_timestamp(self):
        exact_at_cutoff = Attribute(
            "home-1",
            "bedrooms",
            3,
            SPRING.cutoff_exclusive_utc,
            SPRING.cutoff_exclusive_utc,
            SOURCE,
        )
        snapshot = assemble_local_date_snapshot_v2(
            property_row(),
            SPRING,
            "OFF",
            source(),
            attributes=(attribute_row(), exact_at_cutoff),
            transactions=(prior_sale(),),
        )
        self.assertEqual(snapshot.values["living_area"], Decimal("1500"))
        self.assertEqual(snapshot.values["condition"], "good")
        self.assertEqual(snapshot.values["prior_sale_price"], Decimal("120000"))
        self.assertNotIn("bedrooms", snapshot.values)
        self.assertEqual(
            snapshot.lineage["condition"].available_at,
            DateOnlyAvailability(ORIGIN_DAY, NY),
        )
        self.assertEqual(
            snapshot.lineage["prior_sale_price"].observed_at,
            DateOnlyEvent(date(2024, 2, 1), NY),
        )

    def test_publication_zone_and_source_cap_both_control_visibility(self):
        london = property_row(DateOnlyAvailability(ORIGIN_DAY, "Europe/London"))
        los_angeles = property_row(
            DateOnlyAvailability(ORIGIN_DAY, "America/Los_Angeles")
        )
        self.assertEqual(
            assemble_local_date_snapshot_v2(london, SPRING, "OFF", source()).values[
                "living_area"
            ],
            Decimal("1500"),
        )
        with self.assertRaises(NoAvailablePropertyVersionError):
            assemble_local_date_snapshot_v2(los_angeles, SPRING, "OFF", source())
        with self.assertRaises(NoAvailablePropertyVersionError):
            assemble_local_date_snapshot_v2(
                property_row(),
                SPRING,
                "OFF",
                source(SPRING.cutoff_exclusive_utc - timedelta(microseconds=1)),
            )
        self.assertEqual(
            assemble_local_date_snapshot_v2(
                property_row(), SPRING, "OFF", source(SPRING.cutoff_exclusive_utc)
            ).values["living_area"],
            Decimal("1500"),
        )

    def test_date_published_version_end_must_be_known_before_it_closes_a_record(self):
        end = datetime(2024, 3, 10, 18, tzinfo=UTC)
        old = property_row(
            publication=DateOnlyAvailability(date(2023, 1, 2), NY),
            valid_to=end,
            valid_to_available_at=DateOnlyAvailability(ORIGIN_DAY, NY),
        )
        newer = property_row(
            observed_at=end,
            valid_from=end,
            living_area=Decimal("1700"),
        )
        snapshot = assemble_local_date_snapshot_from_versions_v2(
            "home-1", (old, newer), SPRING, "OFF", source()
        )
        self.assertEqual(snapshot.values["living_area"], Decimal("1700"))
        with self.assertRaises(ValueError):
            assemble_local_date_snapshot_from_versions_v2(
                "home-1",
                (
                    replace(
                        old,
                        valid_to_available_at=DateOnlyAvailability(
                            ORIGIN_DAY + timedelta(days=1), NY
                        ),
                    ),
                    newer,
                ),
                SPRING,
                "OFF",
                source(),
            )

    def test_date_published_correction_can_expire_exact_property_and_attribute(self):
        start = datetime(2023, 1, 1, tzinfo=UTC)
        end = datetime(2024, 3, 10, 18, tzinfo=UTC)
        exact_old = Property(
            "home-1",
            "US",
            "single_family",
            SOURCE,
            start,
            datetime(2023, 1, 2, tzinfo=UTC),
            Decimal("1500"),
            "sqft",
        )
        dated_old = property_row(
            publication=DateOnlyAvailability(date(2023, 1, 3), NY),
            valid_to=end,
            valid_to_available_at=DateOnlyAvailability(ORIGIN_DAY, NY),
        )
        new = property_row(observed_at=end, valid_from=end, living_area=Decimal("1700"))
        exact_attribute = Attribute(
            "home-1",
            "condition",
            "fair",
            start,
            datetime(2023, 1, 2, tzinfo=UTC),
            SOURCE,
        )
        dated_attribute = attribute_row(
            DateOnlyAvailability(date(2023, 1, 3), NY),
            value="fair",
            observed_at=start,
            valid_to=end,
            valid_to_available_at=DateOnlyAvailability(ORIGIN_DAY, NY),
        )
        new_attribute = attribute_row(
            value="good",
            observed_at=end,
            valid_from=end,
        )
        snapshot = assemble_local_date_snapshot_from_versions_v2(
            "home-1",
            (exact_old, dated_old, new),
            SPRING,
            "OFF",
            source(),
            attributes=(exact_attribute, dated_attribute, new_attribute),
        )
        self.assertEqual(snapshot.values["living_area"], Decimal("1700"))
        self.assertEqual(snapshot.values["condition"], "good")
        earlier_origin = derive_local_date_origin(date(2024, 6, 7), NY)
        earlier_disclosure = DateOnlyAvailability(date(2024, 3, 9), NY)
        old_snapshot = assemble_local_date_snapshot_from_versions_v2(
            "home-1",
            (
                exact_old,
                replace(dated_old, valid_to_available_at=earlier_disclosure),
                new,
            ),
            earlier_origin,
            "OFF",
            source(),
            attributes=(
                exact_attribute,
                replace(dated_attribute, valid_to_available_at=earlier_disclosure),
                new_attribute,
            ),
        )
        self.assertEqual(old_snapshot.values["living_area"], Decimal("1500"))
        self.assertEqual(old_snapshot.values["condition"], "fair")
        self.assertEqual(
            old_snapshot.lineage["condition"].valid_to_available_at,
            earlier_disclosure,
        )
        self.assertEqual(
            old_snapshot.lineage["living_area"].valid_to_available_at,
            earlier_disclosure,
        )

    def test_late_and_conflicting_prior_sale_records_do_not_become_comparables(self):
        late = prior_sale(DateOnlyAvailability(ORIGIN_DAY + timedelta(days=1), NY))
        snapshot = assemble_local_date_snapshot_v2(
            property_row(), SPRING, "OFF", source(), transactions=(late,)
        )
        self.assertNotIn("prior_sale_price", snapshot.values)
        with self.assertRaisesRegex(ValueError, "Conflicting"):
            assemble_local_date_snapshot_v2(
                property_row(),
                SPRING,
                "OFF",
                source(),
                transactions=(prior_sale(), prior_sale(price=Decimal("999999"))),
            )
        with self.assertRaisesRegex(ValueError, "transaction"):
            assemble_local_date_snapshot_v2(
                property_row(),
                SPRING,
                "OFF",
                source(),
                transactions=(
                    prior_sale(),
                    prior_sale(economic_transfer_id="another-transfer"),
                ),
            )

    def test_mixed_precision_sale_identities_require_reconciliation(self):
        exact = Transaction(
            "prior-deed",
            "other-transfer",
            "home-1",
            datetime(2024, 2, 1, 20, tzinfo=UTC),
            datetime(2024, 3, 1, tzinfo=UTC),
            Decimal("120000"),
            "USD",
            SOURCE,
            "single_property",
            "gross_recorded_sale",
            "confirmed",
            (),
        )
        with self.assertRaisesRegex(ValueError, "Mixed-precision"):
            assemble_local_date_snapshot_v2(
                property_row(),
                SPRING,
                "OFF",
                source(),
                transactions=(prior_sale(), exact),
            )
        with self.assertRaisesRegex(ValueError, "Mixed-precision"):
            assemble_local_date_snapshot_v2(
                property_row(),
                SPRING,
                "OFF",
                source(),
                transactions=(
                    prior_sale(),
                    replace(
                        exact,
                        transaction_id="distinct-deed",
                        economic_transfer_id="prior-transfer",
                    ),
                ),
            )

    def test_hash_retains_publication_precision_and_zone(self):
        dated = assemble_local_date_snapshot_v2(property_row(), SPRING, "OFF", source())
        dated_replay = assemble_local_date_snapshot_v2(
            property_row(), SPRING, "OFF", source()
        )
        toronto = assemble_local_date_snapshot_v2(
            property_row(DateOnlyAvailability(ORIGIN_DAY, "America/Toronto")),
            SPRING,
            "OFF",
            source(),
        )
        exact = Property(
            "home-1",
            "US",
            "single_family",
            SOURCE,
            datetime(2023, 1, 1, tzinfo=UTC),
            SPRING.cutoff_exclusive_utc - timedelta(microseconds=1),
            Decimal("1500"),
            "sqft",
        )
        exact_snapshot = assemble_local_date_snapshot_v2(exact, SPRING, "OFF", source())
        self.assertEqual(dated.snapshot_hash, dated_replay.snapshot_hash)
        self.assertNotEqual(dated.snapshot_hash, toronto.snapshot_hash)
        self.assertNotEqual(dated.snapshot_hash, exact_snapshot.snapshot_hash)
        self.assertNotEqual(
            dated.snapshot_hash,
            assemble_local_date_snapshot(exact, SPRING, "OFF", source()).snapshot_hash,
        )

    def test_exact_and_v1_paths_reject_date_precision(self):
        with self.assertRaisesRegex(ValueError, "date-only|exact"):
            assemble_snapshot(
                property_row(), SPRING.cutoff_exclusive_utc, "OFF", source()
            )
        with self.assertRaisesRegex(ValueError, "date-only|exact"):
            select_property_version(
                "home-1", (property_row(),), SPRING.cutoff_exclusive_utc, source()
            )
        with self.assertRaisesRegex(ValueError, "date-only|v2"):
            assemble_local_date_snapshot(property_row(), SPRING, "OFF", source())
        with self.assertRaisesRegex(ValueError, "date-only|v2"):
            assemble_local_date_snapshot(
                Property(
                    "home-1",
                    "US",
                    "single_family",
                    SOURCE,
                    datetime(2023, 1, 1, tzinfo=UTC),
                    datetime(2023, 1, 2, tzinfo=UTC),
                    Decimal("1500"),
                    "sqft",
                ),
                SPRING,
                "OFF",
                source(),
                attributes=(attribute_row(),),
            )
        with self.assertRaisesRegex(ValueError, "date-only|v2"):
            assemble_local_date_snapshot(
                Property(
                    "home-1",
                    "US",
                    "single_family",
                    SOURCE,
                    datetime(2023, 1, 1, tzinfo=UTC),
                    datetime(2023, 1, 2, tzinfo=UTC),
                    Decimal("1500"),
                    "sqft",
                ),
                SPRING,
                "OFF",
                source(),
                transactions=(prior_sale(),),
            )
        exact = Property(
            "home-1",
            "US",
            "single_family",
            SOURCE,
            datetime(2023, 1, 1, tzinfo=UTC),
            datetime(2023, 1, 2, tzinfo=UTC),
            Decimal("1500"),
            "sqft",
        )
        self.assertEqual(
            assemble_local_date_snapshot(exact, SPRING, "OFF", source()).snapshot_hash,
            "03b78d6bee6268e8be3f2901f1b918a1e3a329f7e7341a0ed1e95eec2c424839",
        )


if __name__ == "__main__":
    unittest.main()
