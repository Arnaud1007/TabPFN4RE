"""Synthetic checks for Cook parcel observations, never sale labels."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from hashlib import sha256
import json
import unittest

from tabpfn4realestate.data.cook_parcel_sales import (
    CookParcelSaleObservation,
    parse_cook_row,
)


CAPTURE = "a" * 64
RESPONSE = "b" * 64
OBSERVED = datetime(2026, 10, 3, 0, 42, 14, tzinfo=timezone.utc)


def row_hash(row: dict) -> str:
    return sha256(
        json.dumps(
            row, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()


def parse(row: dict, **overrides: object) -> CookParcelSaleObservation:
    options = {
        "capture_sha256": CAPTURE,
        "response_sha256": RESPONSE,
        "row_sha256": row_hash(row),
        "observed_at": OBSERVED,
        **overrides,
    }
    return parse_cook_row(row, **options)


class CookParcelSaleObservationTest(unittest.TestCase):
    def test_full_field_round_trip_preserves_raw_values(self) -> None:
        row = {
            "row_id": "source-1",
            "pin": "00000000000001",
            "year": "2025",
            "township_code": "01",
            "nbhd": "004",
            "class": "203",
            "sale_date": "2025-07-09T00:00:00",
            "is_mydec_date": False,
            "sale_price": "100000.0100",
            "doc_no": "doc-1",
            "deed_type": "W",
            "mydec_deed_type": None,
            "is_multisale": True,
            "num_parcels_sale": "2",
            "sale_type": "X",
            "sale_filter_same_sale_within_365": False,
            "sale_filter_less_than_10k": False,
            "sale_filter_deed_type": True,
        }
        result = parse(row)
        self.assertEqual(result.row_id, "source-1")
        self.assertEqual(result.pin_state, "valid")
        self.assertEqual(result.pin, "00000000000001")
        self.assertEqual(result.price_state, "positive")
        self.assertEqual(result.price, Decimal("100000.0100"))
        self.assertEqual(result.recorded_date, date(2025, 7, 9))
        self.assertEqual(result.recorded_date_state, "valid")
        self.assertEqual(result.to_record()["raw_fields"], row)
        self.assertEqual(result.currency, "USD")
        self.assertEqual(result.to_record()["currency"], "USD")
        self.assertTrue(result.source_audit_only)
        self.assertIs(result.to_record()["source_audit_only"], True)
        serialized = json.loads(json.dumps(result.to_record()))
        self.assertEqual(CookParcelSaleObservation.from_record(serialized), result)
        self.assertEqual(result.observed_at, OBSERVED)
        self.assertFalse(hasattr(result, "available_at"))
        self.assertFalse(hasattr(result, "close_at"))
        self.assertFalse(hasattr(result, "eligible_prior_sale"))
        with self.assertRaises(FrozenInstanceError):
            result.row_id = "changed"  # type: ignore[misc]
        with self.assertRaises(ValueError):
            replace(result, currency="EUR")
        with self.assertRaises(ValueError):
            replace(result, source_audit_only=False)

    def test_missing_null_false_and_zero_are_distinct(self) -> None:
        missing = parse({"row_id": "a"})
        null = parse(
            {
                "row_id": "b",
                "pin": None,
                "sale_price": None,
                "sale_date": None,
                "is_multisale": False,
                "num_parcels_sale": "0",
            }
        )
        zero = parse({"row_id": "c", "sale_price": "0"})
        self.assertEqual(
            (missing.pin_state, missing.price_state, missing.recorded_date_state),
            ("missing", "missing", "missing"),
        )
        self.assertEqual(
            (null.pin_state, null.price_state, null.recorded_date_state),
            ("null", "null", "null"),
        )
        self.assertEqual(null.to_record()["raw_fields"]["is_multisale"], False)
        self.assertEqual(null.to_record()["raw_fields"]["num_parcels_sale"], "0")
        self.assertEqual(zero.price_state, "nonpositive")
        self.assertEqual(zero.price, Decimal("0"))

    def test_invalid_optional_values_are_states_not_invented_facts(self) -> None:
        result = parse(
            {
                "row_id": "a",
                "pin": 123,
                "sale_price": "NaN",
                "sale_date": "2025-99-99",
            }
        )
        self.assertEqual(result.pin_state, "malformed")
        self.assertIsNone(result.pin)
        self.assertEqual(result.price_state, "malformed")
        self.assertIsNone(result.price)
        self.assertEqual(result.recorded_date_state, "malformed")
        self.assertIsNone(result.recorded_date)
        self.assertEqual(result.to_record()["raw_fields"]["pin"], 123)

    def test_repeated_document_stays_separate_observations(self) -> None:
        first = parse({"row_id": "first", "doc_no": "shared", "is_multisale": True})
        second = parse({"row_id": "second", "doc_no": "shared", "is_multisale": True})
        self.assertNotEqual(first.row_id, second.row_id)
        self.assertEqual(first.to_record()["raw_fields"]["doc_no"], "shared")
        self.assertEqual(second.to_record()["raw_fields"]["doc_no"], "shared")

    def test_unrequested_personal_or_nested_fields_fail(self) -> None:
        for row in (
            {"row_id": "a", "buyer_name": "private"},
            {"row_id": "a", "doc_no": {"nested": "bad"}},
            {"row_id": "a", "doc_no": ["nested"]},
            {"row_id": "a", "year": float("nan")},
        ):
            with self.subTest(row=row), self.assertRaises(ValueError):
                parse(row)

    def test_bad_identity_or_provenance_fails(self) -> None:
        for row in ({}, {"row_id": None}, {"row_id": 123}, {"row_id": " "}):
            with self.subTest(row=row), self.assertRaises(ValueError):
                parse(row)
        base = {"row_id": "a"}
        for changes in (
            {"capture_sha256": "A" * 64},
            {"response_sha256": "not-a-hash"},
            {"row_sha256": "f" * 64},
            {"observed_at": datetime(2026, 10, 3)},
            {"observed_at": datetime(2026, 10, 3, tzinfo=timezone(timedelta(hours=1)))},
            {"observed_at": "2026-10-03T00:00:00Z"},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                parse(base, **changes)

    def test_round_trip_rejects_raw_or_derived_tampering(self) -> None:
        original = parse({"row_id": "a", "pin": "00000000000001", "sale_price": "1.00"})
        for key, replacement in (
            (
                "raw_fields",
                {"row_id": "a", "pin": "00000000000002", "sale_price": "1.00"},
            ),
            ("pin", "00000000000002"),
            ("price", "2.00"),
            ("recorded_date", "2025-01-01"),
            ("currency", "EUR"),
            ("source_audit_only", False),
            ("available_at", "2020-01-01T00:00:00Z"),
        ):
            with self.subTest(key=key):
                changed = {**original.to_record(), key: replacement}
                with self.assertRaises(ValueError):
                    CookParcelSaleObservation.from_record(changed)


if __name__ == "__main__":
    unittest.main()
