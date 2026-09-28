"""T03/T04 canaries for comparable timing and predictive-feature policy."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
import sys
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tabpfn4realestate.data.schema import (  # noqa: E402
    Property,
    SourceSnapshot,
    Transaction,
)
from tabpfn4realestate.features.comparables import (  # noqa: E402
    eligible_comparable_sales,
)
from tabpfn4realestate.models.guards import (  # noqa: E402
    FeatureDefinition,
    validate_feature_columns,
)


ORIGIN = datetime(2024, 6, 30, 12, tzinfo=timezone.utc)


def property_record(**changes):
    fields = {
        "property_id": "home-2",
        "country": "US",
        "property_type": "single_family",
        "source_id": "assessor",
        "observed_at": ORIGIN - timedelta(days=365),
        "available_at": ORIGIN - timedelta(days=364),
        "living_area": Decimal("1400"),
        "living_area_unit": "sqft",
    }
    return Property(**(fields | changes))


def transaction_record(**changes):
    fields = {
        "transaction_id": "sale-2",
        "economic_transfer_id": "transfer-2",
        "property_id": "home-2",
        "close_at": ORIGIN - timedelta(days=30),
        "available_at": ORIGIN - timedelta(days=20),
        "price": Decimal("350000"),
        "currency": "USD",
        "source_id": "sales",
        "scope": "single_property",
        "consideration_type": "gross_recorded_sale",
        "arm_length_status": "confirmed",
        "adjustment_flags": (),
    }
    return Transaction(**(fields | changes))


def source_snapshot(**changes):
    fields = {
        "snapshot_id": "source-snapshot",
        "source_ids": ("assessor", "sales"),
        "as_of": ORIGIN,
    }
    return SourceSnapshot(**(fields | changes))


class ComparableEligibilityTests(unittest.TestCase):
    def candidates(
        self,
        *,
        properties=None,
        transactions=None,
        origin=ORIGIN,
        manifest=None,
        subject_economic_transfer_id=None,
    ):
        subject = property_record(property_id="home-1")
        return eligible_comparable_sales(
            subject,
            origin,
            manifest or source_snapshot(),
            candidate_properties=properties
            if properties is not None
            else (property_record(),),
            transactions=transactions
            if transactions is not None
            else (transaction_record(),),
            subject_economic_transfer_id=subject_economic_transfer_id,
        )

    def test_available_single_property_sale_is_returned(self):
        sale = transaction_record()
        self.assertEqual(self.candidates(transactions=(sale,)), (sale,))

    def test_future_and_late_published_sales_are_not_comparables(self):
        future = transaction_record(close_at=ORIGIN + timedelta(seconds=1))
        late = transaction_record(available_at=ORIGIN + timedelta(seconds=1))
        self.assertEqual(self.candidates(transactions=(future, late)), ())

    def test_source_snapshot_cutoff_is_inclusive_for_property_and_sale(self):
        cutoff = ORIGIN - timedelta(days=1)
        manifest = source_snapshot(as_of=cutoff)
        at_cutoff_property = property_record(observed_at=cutoff, available_at=cutoff)
        at_cutoff_sale = transaction_record(close_at=cutoff, available_at=cutoff)
        self.assertEqual(
            self.candidates(
                properties=(at_cutoff_property,),
                transactions=(at_cutoff_sale,),
                manifest=manifest,
            ),
            (at_cutoff_sale,),
        )
        later_sale = transaction_record(close_at=cutoff + timedelta(microseconds=1))
        self.assertEqual(
            self.candidates(
                properties=(at_cutoff_property,),
                transactions=(later_sale,),
                manifest=manifest,
            ),
            (),
        )
        later_publication = transaction_record(
            close_at=cutoff, available_at=cutoff + timedelta(microseconds=1)
        )
        self.assertEqual(
            self.candidates(
                properties=(at_cutoff_property,),
                transactions=(later_publication,),
                manifest=manifest,
            ),
            (),
        )
        later_property = property_record(
            observed_at=cutoff + timedelta(microseconds=1),
            available_at=cutoff + timedelta(microseconds=1),
        )
        self.assertEqual(
            self.candidates(
                properties=(later_property,),
                transactions=(at_cutoff_sale,),
                manifest=manifest,
            ),
            (),
        )

    def test_candidate_property_version_must_be_available_and_observed(self):
        future_available = property_record(available_at=ORIGIN + timedelta(seconds=1))
        future_observed = property_record(observed_at=ORIGIN + timedelta(seconds=1))
        for candidate in (future_available, future_observed):
            with self.subTest(candidate=candidate):
                self.assertEqual(self.candidates(properties=(candidate,)), ())

    def test_wrong_property_class_and_subject_property_are_excluded(self):
        condo = property_record(property_type="condo")
        subject_history = transaction_record(property_id="home-1")
        self.assertEqual(self.candidates(properties=(condo,)), ())
        self.assertEqual(
            self.candidates(
                properties=(property_record(property_id="home-1"),),
                transactions=(subject_history,),
            ),
            (),
        )

    def test_explicit_subject_transfer_is_not_a_comparable(self):
        sale = transaction_record()
        self.assertEqual(
            self.candidates(
                transactions=(sale,),
                subject_economic_transfer_id=sale.economic_transfer_id,
            ),
            (),
        )

    def test_visible_subject_transfer_conflicting_with_candidate_is_quarantined(self):
        subject_sale = transaction_record(property_id="home-1")
        candidate_sale = transaction_record(
            transaction_id="sale-2-copy", source_id="assessor"
        )
        with self.assertRaises(ValueError):
            self.candidates(
                properties=(property_record(),),
                transactions=(subject_sale, candidate_sale),
            )

    def test_visible_transfer_conflict_outside_candidate_class_or_list_is_quarantined(
        self,
    ):
        candidate_sale = transaction_record()
        wrong_class = property_record(property_id="home-3", property_type="condo")
        cases = (
            (
                (property_record(), wrong_class),
                transaction_record(
                    transaction_id="sale-3", property_id="home-3", source_id="assessor"
                ),
            ),
            (
                (property_record(),),
                transaction_record(
                    transaction_id="sale-4", property_id="home-4", source_id="assessor"
                ),
            ),
        )
        for properties, conflicting in cases:
            with self.subTest(conflicting_property=conflicting.property_id):
                with self.assertRaises(ValueError):
                    self.candidates(
                        properties=properties,
                        transactions=(candidate_sale, conflicting),
                    )

    def test_noneligible_sales_do_not_enter_comparable_candidates(self):
        variants = (
            {"scope": "partial_interest"},
            {"scope": "multi_property"},
            {"consideration_type": "nominal"},
            {"arm_length_status": "unknown"},
            {"adjustment_flags": ("foreclosure",)},
        )
        for change in variants:
            with self.subTest(change=change):
                self.assertEqual(
                    self.candidates(transactions=(transaction_record(**change),)),
                    (),
                )

    def test_identical_cross_feed_duplicate_is_one_comparable(self):
        sale = transaction_record()
        duplicate = transaction_record(
            transaction_id="sale-2-copy", source_id="assessor"
        )
        result = self.candidates(transactions=(duplicate, sale))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].economic_transfer_id, "transfer-2")

    def test_conflicting_duplicate_eligibility_is_quarantined_before_filter(self):
        sale = transaction_record()
        flagged = transaction_record(
            transaction_id="sale-2-copy",
            source_id="assessor",
            adjustment_flags=("foreclosure",),
        )
        with self.assertRaises(ValueError):
            self.candidates(transactions=(sale, flagged))

    def test_future_sale_perturbation_cannot_change_candidate_result(self):
        past = transaction_record()
        future = transaction_record(
            transaction_id="future-sale",
            economic_transfer_id="future-transfer",
            close_at=ORIGIN + timedelta(days=1),
            available_at=ORIGIN + timedelta(days=2),
            price=Decimal("999999"),
        )
        self.assertEqual(
            self.candidates(transactions=(past,)),
            self.candidates(transactions=(future, past)),
        )

    def test_result_order_is_deterministic_across_input_order(self):
        first = transaction_record()
        second = transaction_record(
            transaction_id="sale-3",
            economic_transfer_id="transfer-3",
            property_id="home-3",
            close_at=ORIGIN - timedelta(days=10),
        )
        properties = (property_record(), property_record(property_id="home-3"))
        forward = self.candidates(properties=properties, transactions=(first, second))
        reverse = self.candidates(
            properties=tuple(reversed(properties)),
            transactions=(second, first),
        )
        self.assertEqual(forward, reverse)
        self.assertEqual(
            {row.economic_transfer_id for row in forward}, {"transfer-2", "transfer-3"}
        )


class FeaturePolicyCanaryTests(unittest.TestCase):
    def definitions(self):
        return {
            "living_area": FeatureDefinition("living_area"),
            "condition": FeatureDefinition("condition"),
            "asking_price": FeatureDefinition("asking_price", modes=("ON",)),
            "intermediate": FeatureDefinition(
                "intermediate", dependencies=("SalePrice",)
            ),
            "derived": FeatureDefinition("derived", dependencies=("intermediate",)),
            "a": FeatureDefinition("a", dependencies=("b",)),
            "b": FeatureDefinition("b", dependencies=("a",)),
        }

    def test_registered_off_features_are_accepted(self):
        validate_feature_columns(
            ("living_area", "condition"), self.definitions(), mode="OFF"
        )

    def test_target_aliases_and_inherited_forbidden_ids_are_rejected(self):
        for name in ("SalePrice", "sale_price", "target", "F172", "F349", "F350"):
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    validate_feature_columns((name,), self.definitions(), mode="OFF")

    def test_named_investment_aliases_are_forbidden_even_when_registered(self):
        aliases = (
            "rendement_locatif",
            "note_attractivite_marche",
            "note_potentiel_d_investissement",
            "f172_rendement_locatif",
            "f349_note_attractivite_marche",
            "f350_note_potentiel_d_investissement",
        )
        for name in aliases:
            with self.subTest(name=name):
                definitions = self.definitions() | {name: FeatureDefinition(name)}
                with self.assertRaises(ValueError):
                    validate_feature_columns((name,), definitions, mode="OFF")

    def test_unknown_feature_fails_closed(self):
        with self.assertRaises(ValueError):
            validate_feature_columns(("unregistered_rating",), self.definitions())

    def test_on_only_feature_is_rejected_from_off(self):
        with self.assertRaises(ValueError):
            validate_feature_columns(("asking_price",), self.definitions(), mode="OFF")

    def test_transitive_target_dependency_is_rejected(self):
        with self.assertRaises(ValueError):
            validate_feature_columns(("derived",), self.definitions(), mode="OFF")

    def test_dependency_cycle_is_rejected(self):
        with self.assertRaises(ValueError):
            validate_feature_columns(("a",), self.definitions(), mode="OFF")


if __name__ == "__main__":
    unittest.main()
