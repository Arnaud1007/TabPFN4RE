"""Synthetic U2 comparable retrieval and price-per-area behavior."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
import sys
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tabpfn4realestate.data.schema import Property, SourceSnapshot, Transaction  # noqa: E402
from tabpfn4realestate.features.comparables import (  # noqa: E402
    ComparableConfig,
    comparable_price_per_area,
    retrieve_comparables,
    retrieve_comparables_from_versions,
)


ORIGIN = datetime(2024, 6, 30, 12, tzinfo=timezone.utc)


def property_record(property_id="home-1", **changes):
    fields = {
        "property_id": property_id,
        "country": "US",
        "property_type": "single_family",
        "source_id": "assessor",
        "observed_at": ORIGIN - timedelta(days=365),
        "available_at": ORIGIN - timedelta(days=364),
        "living_area": Decimal("1500"),
        "living_area_unit": "sqft",
        "latitude": Decimal("40.0000"),
        "longitude": Decimal("-75.0000"),
    }
    return Property(**(fields | changes))


def sale_record(property_id="home-2", **changes):
    fields = {
        "transaction_id": f"sale-{property_id}",
        "economic_transfer_id": f"transfer-{property_id}",
        "property_id": property_id,
        "close_at": ORIGIN - timedelta(days=30),
        "available_at": ORIGIN - timedelta(days=20),
        "price": Decimal("200000"),
        "currency": "USD",
        "source_id": "sales",
        "scope": "single_property",
        "consideration_type": "gross_recorded_sale",
        "arm_length_status": "confirmed",
        "adjustment_flags": (),
    }
    return Transaction(**(fields | changes))


def source_snapshot():
    return SourceSnapshot(
        snapshot_id="synthetic-comps",
        source_ids=("assessor", "sales"),
        as_of=ORIGIN,
    )


def config(**changes):
    fields = {
        "n_neighbors": 5,
        "sale_window_months": 12,
        "radii_km": (1, 3, 20),
        "min_comparables": 1,
        "distance_scale_km": 1,
        "recency_scale_days": 365,
        "area_scale_ratio": 0.25,
    }
    return ComparableConfig(**(fields | changes))


def retrieve(subject=None, candidates=(), sales=(), settings=None):
    return retrieve_comparables(
        subject or property_record(),
        ORIGIN,
        source_snapshot(),
        candidate_properties=candidates,
        transactions=sales,
        config=settings or config(),
    )


def price(subject, result, *, origin=ORIGIN, snapshot=None):
    return comparable_price_per_area(
        subject, origin, snapshot or source_snapshot(), result
    )


class ComparableRetrievalTests(unittest.TestCase):
    def test_property_coordinates_are_paired_and_geographically_valid(self):
        for coordinates in (
            {"latitude": None, "longitude": Decimal("-75")},
            {"latitude": Decimal("91"), "longitude": Decimal("-75")},
            {"latitude": Decimal("40"), "longitude": Decimal("-181")},
        ):
            with self.subTest(coordinates=coordinates):
                with self.assertRaises(ValueError):
                    property_record(**coordinates)

    def test_future_and_late_published_sales_cannot_change_result(self):
        candidate = property_record("home-2", latitude=Decimal("40.001"))
        past = sale_record()
        future = sale_record(
            transaction_id="future-sale",
            economic_transfer_id="future-transfer",
            close_at=ORIGIN + timedelta(seconds=1),
        )
        late = sale_record(
            transaction_id="late-sale",
            economic_transfer_id="late-transfer",
            available_at=ORIGIN + timedelta(seconds=1),
        )
        base = retrieve(candidates=(candidate,), sales=(past,))
        perturbed = retrieve(candidates=(candidate,), sales=(late, future, past))
        self.assertEqual(
            tuple(item.sale.economic_transfer_id for item in base.comparables),
            tuple(item.sale.economic_transfer_id for item in perturbed.comparables),
        )
        self.assertEqual(
            price(property_record(), base),
            price(property_record(), perturbed),
        )

    def test_similarity_ranking_is_independent_of_unknown_target_price(self):
        near_wrong_area = property_record(
            "home-2", latitude=Decimal("40.001"), living_area=Decimal("3000")
        )
        farther_matched_area = property_record("home-3", latitude=Decimal("40.002"))
        expensive = sale_record("home-2", price=Decimal("900000"))
        inexpensive = sale_record("home-3", price=Decimal("100000"))
        candidates = (near_wrong_area, farther_matched_area)
        first = retrieve(candidates=candidates, sales=(expensive, inexpensive))
        swapped = retrieve(
            candidates=candidates,
            sales=(
                sale_record("home-2", price=Decimal("100000")),
                sale_record("home-3", price=Decimal("900000")),
            ),
        )
        first_order = tuple(item.property.property_id for item in first.comparables)
        second_order = tuple(item.property.property_id for item in swapped.comparables)
        self.assertEqual(first_order, second_order)
        self.assertEqual(first_order[0], "home-3")
        self.assertTrue(
            all(item.distance_km >= 0 and item.weight > 0 for item in first.comparables)
        )

    def test_tie_order_is_deterministic_across_input_permutations(self):
        two = property_record("home-2", latitude=Decimal("40.001"))
        three = property_record("home-3", latitude=Decimal("40.001"))
        sale_two = sale_record("home-2")
        sale_three = sale_record("home-3")
        forward = retrieve(candidates=(two, three), sales=(sale_two, sale_three))
        reverse = retrieve(candidates=(three, two), sales=(sale_three, sale_two))
        self.assertEqual(
            tuple(item.sale.economic_transfer_id for item in forward.comparables),
            tuple(item.sale.economic_transfer_id for item in reverse.comparables),
        )

    def test_radius_expands_to_find_three_eligible_comparables(self):
        candidates = (
            property_record("home-2", latitude=Decimal("40.001")),
            property_record("home-3", latitude=Decimal("40.020")),
            property_record("home-4", latitude=Decimal("40.100")),
        )
        sales = tuple(sale_record(property.property_id) for property in candidates)
        result = retrieve(
            candidates=candidates,
            sales=sales,
            settings=config(min_comparables=3),
        )
        self.assertEqual(result.radius_km, 20)
        self.assertEqual(len(result.comparables), 3)
        self.assertEqual(result.support, "supported")

    def test_sparse_market_reports_low_support_after_last_radius(self):
        candidates = (
            property_record("home-2", latitude=Decimal("40.001")),
            property_record("home-3", latitude=Decimal("40.020")),
        )
        sales = tuple(sale_record(property.property_id) for property in candidates)
        result = retrieve(
            candidates=candidates,
            sales=sales,
            settings=config(min_comparables=3),
        )
        self.assertEqual(result.radius_km, 20)
        self.assertEqual(len(result.comparables), 2)
        self.assertEqual(result.support, "low")

    def test_registered_sale_window_excludes_older_sale(self):
        candidate = property_record("home-2", latitude=Decimal("40.001"))
        old_sale = sale_record(
            close_at=ORIGIN - timedelta(days=400),
            available_at=ORIGIN - timedelta(days=390),
        )
        result = retrieve(candidates=(candidate,), sales=(old_sale,))
        self.assertEqual(result.comparables, ())
        self.assertEqual(result.support, "low")

    def test_weighted_median_price_per_area_is_hand_checkable(self):
        candidates = (
            property_record(
                "home-2", latitude=Decimal("40.001"), living_area=Decimal("1000")
            ),
            property_record(
                "home-3", latitude=Decimal("40.002"), living_area=Decimal("2000")
            ),
            property_record(
                "home-4", latitude=Decimal("40.050"), living_area=Decimal("2000")
            ),
        )
        sales = (
            sale_record("home-2", price=Decimal("100000")),
            sale_record("home-3", price=Decimal("200000")),
            sale_record("home-4", price=Decimal("300000")),
        )
        result = retrieve(
            candidates=candidates,
            sales=sales,
            settings=config(min_comparables=3),
        )
        self.assertEqual(len(result.comparables), 3)
        self.assertEqual(price(property_record(), result), Decimal("150000"))

    def test_missing_coordinates_or_area_does_not_fabricate_estimate(self):
        no_location = property_record(latitude=None, longitude=None)
        with self.assertRaises(ValueError):
            retrieve(subject=no_location)
        candidate = property_record("home-2", latitude=Decimal("40.001"))
        no_area = property_record(
            living_area=None,
            living_area_unit=None,
            living_area_state="unknown",
        )
        no_subject_area_result = retrieve(
            subject=no_area, candidates=(candidate,), sales=(sale_record(),)
        )
        self.assertIsNone(price(no_area, no_subject_area_result))
        candidate_without_area = property_record(
            "home-2",
            latitude=Decimal("40.001"),
            living_area=None,
            living_area_unit=None,
            living_area_state="unknown",
        )
        no_area_result = retrieve(
            candidates=(candidate_without_area,), sales=(sale_record(),)
        )
        self.assertIsNone(price(property_record(), no_area_result))
        with self.assertRaises(ValueError):
            property_record(living_area=Decimal("0"))

    def test_missing_area_does_not_bypass_subject_availability_or_source(self):
        missing = {
            "living_area": None,
            "living_area_unit": None,
            "living_area_state": "unknown",
        }
        for change in (
            {"available_at": ORIGIN + timedelta(seconds=1)},
            {"source_id": "unlisted"},
        ):
            with self.subTest(change=change):
                with self.assertRaises(ValueError):
                    retrieve(subject=property_record(**(missing | change)))

    def test_price_rejects_a_later_subject_version_or_different_context(self):
        candidate = property_record("home-2", latitude=Decimal("40.001"))
        result = retrieve(candidates=(candidate,), sales=(sale_record(),))
        future_subject = property_record(
            living_area=Decimal("3000"),
            observed_at=ORIGIN + timedelta(seconds=1),
            available_at=ORIGIN + timedelta(seconds=1),
        )
        with self.assertRaises(ValueError):
            price(future_subject, result)
        with self.assertRaises(ValueError):
            price(property_record(), result, origin=ORIGIN - timedelta(seconds=1))
        changed_snapshot = SourceSnapshot(
            snapshot_id="another-snapshot",
            source_ids=("assessor", "sales"),
            as_of=ORIGIN,
        )
        with self.assertRaises(ValueError):
            price(property_record(), result, snapshot=changed_snapshot)

    def test_post_sale_property_version_is_not_a_comparable_area(self):
        sale = sale_record(close_at=ORIGIN - timedelta(days=30))
        later_area = property_record(
            "home-2",
            latitude=Decimal("40.001"),
            observed_at=ORIGIN - timedelta(days=10),
            available_at=ORIGIN - timedelta(days=9),
            living_area=Decimal("3000"),
        )
        result = retrieve(candidates=(later_area,), sales=(sale,))
        self.assertEqual(result.comparables, ())
        self.assertEqual(result.support, "low")

    def test_expired_subject_and_candidate_versions_are_not_used(self):
        expired_subject = property_record(
            valid_from=ORIGIN - timedelta(days=365),
            valid_to=ORIGIN - timedelta(days=1),
            valid_to_available_at=ORIGIN - timedelta(days=2),
        )
        with self.assertRaisesRegex(ValueError, "valid|expired"):
            retrieve(subject=expired_subject)

        sale = sale_record(close_at=ORIGIN - timedelta(days=30))
        expired_candidate = property_record(
            "home-2",
            latitude=Decimal("40.001"),
            valid_from=ORIGIN - timedelta(days=365),
            valid_to=ORIGIN - timedelta(days=31),
            valid_to_available_at=ORIGIN - timedelta(days=35),
        )
        result = retrieve(candidates=(expired_candidate,), sales=(sale,))
        self.assertEqual(result.comparables, ())

    def test_comparable_effective_start_must_precede_its_sale(self):
        sale = sale_record(close_at=ORIGIN - timedelta(days=30))
        later_effective = property_record(
            "home-2",
            latitude=Decimal("40.001"),
            observed_at=ORIGIN - timedelta(days=80),
            available_at=ORIGIN - timedelta(days=79),
            valid_from=ORIGIN - timedelta(days=10),
        )
        result = retrieve(candidates=(later_effective,), sales=(sale,))
        self.assertEqual(result.comparables, ())

    def test_post_sale_expiry_does_not_discard_valid_historical_comparable(self):
        sale = sale_record(close_at=ORIGIN - timedelta(days=30))
        later_expired = property_record(
            "home-2",
            latitude=Decimal("40.001"),
            valid_from=ORIGIN - timedelta(days=365),
            valid_to=ORIGIN - timedelta(days=10),
            valid_to_available_at=ORIGIN - timedelta(days=20),
        )
        result = retrieve(candidates=(later_expired,), sales=(sale,))
        self.assertEqual(len(result.comparables), 1)

    def test_candidate_history_uses_version_visible_at_comparable_sale(self):
        sale = sale_record(
            close_at=ORIGIN - timedelta(days=40), price=Decimal("200000")
        )
        old = property_record(
            "home-2",
            latitude=Decimal("40.001"),
            living_area=Decimal("1000"),
            valid_from=ORIGIN - timedelta(days=365),
            valid_to=ORIGIN - timedelta(days=20),
            valid_to_available_at=ORIGIN - timedelta(days=30),
        )
        new = property_record(
            "home-2",
            latitude=Decimal("40.001"),
            living_area=Decimal("2000"),
            observed_at=ORIGIN - timedelta(days=20),
            available_at=ORIGIN - timedelta(days=19),
            valid_from=ORIGIN - timedelta(days=20),
        )
        result = retrieve(candidates=(new, old), sales=(sale,))
        self.assertEqual(len(result.comparables), 1)
        self.assertEqual(result.comparables[0].property.living_area, Decimal("1000"))
        self.assertEqual(price(property_record(), result), Decimal("300000"))

    def test_late_published_correction_changes_sale_date_area_when_known_at_origin(
        self,
    ):
        sale = sale_record(close_at=ORIGIN - timedelta(days=30))
        old = property_record(
            "home-2",
            latitude=Decimal("40.001"),
            living_area=Decimal("1000"),
            valid_from=ORIGIN - timedelta(days=365),
            valid_to=ORIGIN - timedelta(days=40),
            valid_to_available_at=ORIGIN - timedelta(days=20),
        )
        corrected = property_record(
            "home-2",
            latitude=Decimal("40.001"),
            living_area=Decimal("2000"),
            available_at=ORIGIN - timedelta(days=20),
            valid_from=ORIGIN - timedelta(days=40),
        )
        result = retrieve(candidates=(old, corrected), sales=(sale,))
        self.assertEqual(len(result.comparables), 1)
        self.assertEqual(result.comparables[0].property.living_area, Decimal("2000"))
        self.assertEqual(price(property_record(), result), Decimal("150000"))

    def test_late_published_expiry_excludes_invalid_sale_date_area(self):
        sale = sale_record(close_at=ORIGIN - timedelta(days=30))
        invalid = property_record(
            "home-2",
            latitude=Decimal("40.001"),
            valid_from=ORIGIN - timedelta(days=365),
            valid_to=ORIGIN - timedelta(days=40),
            valid_to_available_at=ORIGIN - timedelta(days=20),
        )
        self.assertEqual(retrieve(candidates=(invalid,), sales=(sale,)).comparables, ())

    def test_post_sale_observation_cannot_backdate_comparable_area(self):
        sale = sale_record(close_at=ORIGIN - timedelta(days=30))
        later_observation = property_record(
            "home-2",
            latitude=Decimal("40.001"),
            observed_at=ORIGIN - timedelta(days=20),
            available_at=ORIGIN - timedelta(days=19),
            valid_from=ORIGIN - timedelta(days=40),
        )
        self.assertEqual(
            retrieve(candidates=(later_observation,), sales=(sale,)).comparables,
            (),
        )

    def test_visible_unlisted_candidate_source_fails_even_without_sale(self):
        unlisted = property_record("home-3", source_id="unlisted")
        with self.assertRaisesRegex(ValueError, "source"):
            retrieve(candidates=(unlisted,), sales=())
        future = property_record(
            "home-3",
            source_id="unlisted",
            observed_at=ORIGIN + timedelta(days=1),
            available_at=ORIGIN + timedelta(days=1),
        )
        self.assertEqual(retrieve(candidates=(future,), sales=()).comparables, ())

    def test_subject_history_selects_origin_version(self):
        old_subject = property_record(
            living_area=Decimal("1000"),
            valid_from=ORIGIN - timedelta(days=365),
            valid_to=ORIGIN - timedelta(days=20),
            valid_to_available_at=ORIGIN - timedelta(days=25),
        )
        new_subject = property_record(
            living_area=Decimal("1500"),
            observed_at=ORIGIN - timedelta(days=20),
            available_at=ORIGIN - timedelta(days=19),
            valid_from=ORIGIN - timedelta(days=20),
        )
        candidate = property_record("home-2", latitude=Decimal("40.001"))
        result = retrieve_comparables_from_versions(
            "home-1",
            (new_subject, old_subject),
            ORIGIN,
            source_snapshot(),
            candidate_properties=(candidate,),
            transactions=(sale_record(),),
            config=config(),
        )
        self.assertEqual(result.subject.living_area, Decimal("1500"))
        self.assertEqual(
            comparable_price_per_area(
                result.subject, ORIGIN, source_snapshot(), result
            ),
            Decimal("200000"),
        )

    def test_future_end_metadata_is_hidden_in_comparable_result(self):
        late_end = property_record(
            valid_from=ORIGIN - timedelta(days=365),
            valid_to=ORIGIN + timedelta(days=10),
            valid_to_available_at=ORIGIN + timedelta(days=20),
        )
        candidate = property_record("home-2", latitude=Decimal("40.001"))
        result = retrieve(
            subject=late_end, candidates=(candidate,), sales=(sale_record(),)
        )
        self.assertIsNone(result.subject.valid_to)
        self.assertIsNone(result.subject.valid_to_available_at)
        self.assertIsNotNone(price(late_end, result))

    def test_config_requires_immutable_radii_and_extreme_areas_do_not_crash(self):
        with self.assertRaises(ValueError):
            config(radii_km=[1, 3, 20])
        subject = property_record(living_area=Decimal("1e-1000"))
        candidate = property_record(
            "home-2", latitude=Decimal("40.001"), living_area=Decimal("1e1000")
        )
        result = retrieve(
            subject=subject, candidates=(candidate,), sales=(sale_record(),)
        )
        self.assertEqual(len(result.comparables), 1)
        self.assertGreater(result.comparables[0].score, 0)

    def test_repeat_sale_of_one_neighbor_is_one_comparable(self):
        candidate = property_record("home-2", latitude=Decimal("40.001"))
        older = sale_record(
            transaction_id="older-sale",
            economic_transfer_id="older-transfer",
            close_at=ORIGIN - timedelta(days=100),
            available_at=ORIGIN - timedelta(days=90),
        )
        newer = sale_record()
        result = retrieve(candidates=(candidate,), sales=(older, newer))
        self.assertEqual(len(result.comparables), 1)
        self.assertEqual(
            result.comparables[0].sale.economic_transfer_id, "transfer-home-2"
        )


if __name__ == "__main__":
    unittest.main()
