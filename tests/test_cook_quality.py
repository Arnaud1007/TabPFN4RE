"""Test the audit-only Cook quality funnel before any real-source execution."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import unittest

from tabpfn4realestate.data.cook_parcel_sales import _sha256, parse_cook_row
from tabpfn4realestate.data.cook_quality import profile_quality


CAPTURE_HASH = "a" * 64
RESPONSE_HASH = "b" * 64
OBSERVED = datetime(2026, 10, 3, tzinfo=timezone.utc)


def observation(row_id: str, **changes: object):
    row = {
        "row_id": row_id,
        "pin": "00000000000001",
        "sale_date": "2024-01-01T00:00:00.000",
        "sale_price": "123456.78",
        "doc_no": f"doc-{row_id}",
        "is_multisale": False,
        "num_parcels_sale": "1",
    } | changes
    return parse_cook_row(
        row,
        capture_sha256=CAPTURE_HASH,
        response_sha256=RESPONSE_HASH,
        row_sha256=_sha256(row),
        observed_at=OBSERVED,
    )


class CookQualityTests(unittest.TestCase):
    def test_clean_source_row_is_still_audit_only(self) -> None:
        result = profile_quality(
            (observation("row-1"),),
            expected_capture_sha256=CAPTURE_HASH,
            expected_rows=1,
        )
        finding = result.findings[0]
        self.assertEqual(finding.price_state, "positive")
        self.assertEqual(finding.pin_state, "valid")
        self.assertEqual(finding.recorded_date_state, "valid")
        self.assertEqual(finding.multisale_state, "false")
        self.assertEqual(finding.parcel_count_state, "single")
        self.assertEqual(finding.document_state, "unique")
        self.assertEqual(finding.reason_codes, ())
        self.assertEqual(finding.status, "audit_only")
        self.assertEqual(result.certified_sale_labels, 0)
        self.assertEqual(result.sample_rows, 1)
        self.assertNotIn("close_at", finding.to_record())
        self.assertNotIn("available_at", finding.to_record())
        self.assertNotIn("price", finding.to_record())
        self.assertNotIn("pin", finding.to_record())

    def test_missing_null_malformed_and_nonpositive_partition_without_drop(
        self,
    ) -> None:
        rows = (
            observation("a", sale_price="0", pin=None, sale_date="bad"),
            observation("b", sale_price="bad", pin="bad", sale_date=None),
            observation("c", sale_price=None, pin="00000000000001"),
            observation("d", **{"sale_price": None, "pin": None}),
        )
        result = profile_quality(
            rows, expected_capture_sha256=CAPTURE_HASH, expected_rows=4
        )
        self.assertEqual(len(result.findings), 4)
        self.assertIn("price_nonpositive", result.findings[0].reason_codes)
        self.assertIn("price_malformed", result.findings[1].reason_codes)
        self.assertIn("price_null", result.findings[2].reason_codes)
        self.assertIn("pin_null", result.findings[0].reason_codes)
        self.assertIn("pin_malformed", result.findings[1].reason_codes)
        self.assertIn("recorded_date_malformed", result.findings[0].reason_codes)
        self.assertIn("recorded_date_null", result.findings[1].reason_codes)
        for _, states in result.counts:
            self.assertEqual(sum(count for _, count in states), 4)
        self.assertEqual(result.certified_sale_labels, 0)

    def test_omitted_fields_stay_distinct_from_null(self) -> None:
        missing = observation("missing")
        record = missing.to_record()
        for field in (
            "pin",
            "sale_date",
            "sale_price",
            "doc_no",
            "is_multisale",
            "num_parcels_sale",
        ):
            record["raw_fields"].pop(field)
        absent = parse_cook_row(
            record["raw_fields"],
            capture_sha256=CAPTURE_HASH,
            response_sha256=RESPONSE_HASH,
            row_sha256=_sha256(record["raw_fields"]),
            observed_at=OBSERVED,
        )
        null = observation(
            "null",
            pin=None,
            sale_date=None,
            sale_price=None,
            doc_no=None,
            is_multisale=None,
            num_parcels_sale=None,
        )
        result = profile_quality(
            (absent, null), expected_capture_sha256=CAPTURE_HASH, expected_rows=2
        )
        for field in (
            "pin_state",
            "price_state",
            "recorded_date_state",
            "multisale_state",
            "parcel_count_state",
            "document_state",
        ):
            self.assertEqual(getattr(result.findings[0], field), "missing")
            self.assertEqual(getattr(result.findings[1], field), "null")

    def test_repeated_document_and_multisale_keep_both_parcel_rows(self) -> None:
        rows = (
            observation(
                "row-a", doc_no="same", is_multisale=True, num_parcels_sale="2"
            ),
            observation(
                "row-b",
                pin="00000000000002",
                doc_no="same",
                is_multisale=False,
                num_parcels_sale=1,
            ),
        )
        result = profile_quality(
            rows, expected_capture_sha256=CAPTURE_HASH, expected_rows=2
        )
        self.assertEqual(len(result.findings), 2)
        self.assertEqual(
            [row.document_state for row in result.findings], ["repeated"] * 2
        )
        self.assertEqual(
            [row.parcel_count_state for row in result.findings], ["multiple", "single"]
        )
        self.assertIn("document_repeated", result.findings[0].reason_codes)
        self.assertIn("document_repeated", result.findings[1].reason_codes)
        self.assertIn("multisale_true", result.findings[0].reason_codes)
        self.assertEqual(result.certified_sale_labels, 0)

    def test_malformed_flags_are_not_coerced_to_false_or_one(self) -> None:
        rows = (
            observation("a", is_multisale="false", num_parcels_sale="0"),
            observation("b", is_multisale=0, num_parcels_sale="1.0"),
            observation("c", is_multisale=None, num_parcels_sale=None),
            observation("d", is_multisale=False, num_parcels_sale="000000001"),
        )
        result = profile_quality(
            rows, expected_capture_sha256=CAPTURE_HASH, expected_rows=4
        )
        self.assertEqual(
            [row.multisale_state for row in result.findings],
            ["malformed", "malformed", "null", "false"],
        )
        self.assertEqual(
            [row.parcel_count_state for row in result.findings],
            ["malformed", "malformed", "null", "malformed"],
        )

    def test_wrong_capture_duplicate_id_and_count_fail_closed(self) -> None:
        row = observation("row-1")
        cases = (
            ((row,), "c" * 64, 1),
            ((row, row), CAPTURE_HASH, 2),
            ((row,), CAPTURE_HASH, 2),
        )
        for rows, digest, count in cases:
            with self.subTest(digest=digest, count=count):
                with self.assertRaises(ValueError):
                    profile_quality(
                        rows,
                        expected_capture_sha256=digest,
                        expected_rows=count,
                    )

    def test_decimal_price_is_not_exported_in_finding(self) -> None:
        row = observation("secret-row", sale_price="987654321.23")
        self.assertEqual(row.price, Decimal("987654321.23"))
        result = profile_quality(
            (row,), expected_capture_sha256=CAPTURE_HASH, expected_rows=1
        )
        encoded = str(result.findings[0].to_record())
        self.assertNotIn("987654321.23", encoded)
        self.assertNotIn("00000000000001", encoded)
        self.assertNotIn("doc-secret-row", encoded)


if __name__ == "__main__":
    unittest.main()
