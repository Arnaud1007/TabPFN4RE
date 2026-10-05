"""RED contracts for bounded offline HCPA property-record PDF evidence."""

from __future__ import annotations

import zlib
from hashlib import sha256
import unittest

try:
    from scripts import hcpa_property_record_pdf as property_pdf
except ImportError:
    property_pdf = None


PINS_AND_STRAPS = (
    ("U-12-34-56-ABC-DEF123-GHIJK.L", "563412ABCDEF123GHIJKLU"),
    ("T-AA-BB-CC-DDD-EEEEEE-FFFFF.G", "CCBBAADDDEEEEEEFFFFFGT"),
    ("A-01-02-03-XYZ-ABCDEF-12345.6", "030201XYZABCDEF123456A"),
)


def flate_pdf(content: bytes, *, filter_name: bytes = b"FlateDecode") -> bytes:
    compressed = zlib.compress(content)
    return (
        b"%PDF-1.4\n"
        b"1 0 obj\n"
        b"<< /Length "
        + str(len(compressed)).encode("ascii")
        + b" /Filter /"
        + filter_name
        + b" >>\nstream\n"
        + compressed
        + b"\nendstream\nendobj\n%%EOF\n"
    )


def extract(pdf: bytes, *, max_pdf_bytes: int, max_decoded_bytes: int):
    return property_pdf.extract_ordered_fields(
        pdf,
        expected_sha256=sha256(pdf).hexdigest(),
        max_pdf_bytes=max_pdf_bytes,
        max_decoded_bytes=max_decoded_bytes,
    )


class HcpaPropertyRecordPdfTests(unittest.TestCase):
    def setUp(self) -> None:
        if property_pdf is None:
            self.fail(
                "scripts.hcpa_property_record_pdf must implement the bounded "
                "offline property-record evidence contract"
            )

    def test_pin_to_strap_accepts_exact_u_t_and_a_formats(self) -> None:
        for pin, expected in PINS_AND_STRAPS:
            with self.subTest(pin=pin):
                self.assertEqual(property_pdf.pin_to_strap(pin), expected)
                self.assertEqual(len(property_pdf.pin_to_strap(pin)), 22)

    def test_pin_to_strap_rejects_malformed_or_non_ascii_values(self) -> None:
        malformed = (
            None,
            123,
            "",
            "u-12-34-56-ABC-DEF123-GHIJK.L",
            "U-12-34-56-ABC-DEF123-GHIJK.L ",
            "U123-34-56-ABC-DEF123-GHIJK.L",
            "U-12-34-56-ABC-DEF123-GHIJK",
            "U-12-34-56-ABC-DEF123-GHIJK.LX",
            "U-1２-34-56-ABC-DEF123-GHIJK.L",
            "B-12-34-56-ABC-DEF123-GHIJK.L",
        )
        for value in malformed:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    property_pdf.pin_to_strap(value)

    def test_extracts_ordered_literal_strings_from_one_bounded_flate_stream(
        self,
    ) -> None:
        content = (
            b"BT (Parcel ID) Tj (563412ABCDEF123GHIJKLU) Tj "
            b"(Document Number) Tj (DOC \\(SYN\\)\\\\A) Tj "
            b"(DOR Code) Tj (0100) Tj (Qualification) Tj (U) Tj ET"
        )
        pdf = flate_pdf(content)

        extracted = extract(
            pdf,
            max_pdf_bytes=len(pdf),
            max_decoded_bytes=len(content),
        )

        self.assertEqual(
            extracted,
            (
                "Parcel ID",
                "563412ABCDEF123GHIJKLU",
                "Document Number",
                "DOC (SYN)\\A",
                "DOR Code",
                "0100",
                "Qualification",
                "U",
            ),
        )

    def test_decodes_supported_literal_escape_forms_and_nested_parentheses(self) -> None:
        pdf = flate_pdf(
            b"BT (A\\nB\\rC\\tD\\bE\\fF\\101\\q(nested)) Tj ET"
        )

        self.assertEqual(
            extract(pdf, max_pdf_bytes=len(pdf), max_decoded_bytes=200),
            ("A\nB\rC\tD\bE\fFAq(nested)",),
        )

    def test_text_operator_scan_skips_et_inside_literal_string(self) -> None:
        pdf = flate_pdf(
            b"BT (OWNER ET AL) Tj (Parcel ID) Tj (SYNTHETIC) Tj ET"
        )

        self.assertEqual(
            extract(pdf, max_pdf_bytes=len(pdf), max_decoded_bytes=200),
            ("OWNER ET AL", "Parcel ID", "SYNTHETIC"),
        )

    def test_field_scan_ignores_comments_and_rejects_non_operator_suffix(self) -> None:
        pdf = flate_pdf(
            b"BT % (Document Number) Tj\n"
            b"(forged) Tj-evil (Parcel ID) Tj (SYNTHETIC) Tj ET"
        )

        self.assertEqual(
            extract(pdf, max_pdf_bytes=len(pdf), max_decoded_bytes=300),
            ("Parcel ID", "SYNTHETIC"),
        )

    def test_rejects_oversized_non_pdf_corrupt_and_unsupported_streams(self) -> None:
        valid = flate_pdf(b"BT (safe) Tj ET")
        corrupt = valid.replace(zlib.compress(b"BT (safe) Tj ET"), b"not-zlib")
        unsupported = flate_pdf(
            b"BT (safe) Tj ET", filter_name=b"ASCII85Decode"
        )
        expansion = flate_pdf(b"(" + b"A" * 4096 + b")")
        cases = (
            (valid, len(valid) - 1, 4096),
            (b"not a PDF", 4096, 4096),
            (corrupt, 4096, 4096),
            (unsupported, 4096, 4096),
            (expansion, 4096, 4096),
        )
        for pdf, max_pdf_bytes, max_decoded_bytes in cases:
            with self.subTest(prefix=pdf[:20]):
                with self.assertRaises(ValueError):
                    extract(
                        pdf,
                        max_pdf_bytes=max_pdf_bytes,
                        max_decoded_bytes=max_decoded_bytes,
                    )

    def test_skips_image_stream_when_a_supported_text_stream_exists(self) -> None:
        image = flate_pdf(b"image", filter_name=b"DCTDecode")
        text = flate_pdf(b"BT (safe) Tj ET")
        combined = image.removesuffix(b"%%EOF\n") + text.removeprefix(b"%PDF-1.4\n")

        self.assertEqual(
            extract(
                combined,
                max_pdf_bytes=len(combined),
                max_decoded_bytes=1024,
            ),
            ("safe",),
        )

    def test_skips_non_page_flate_stream_with_unbalanced_binary_bytes(self) -> None:
        binary = flate_pdf(b"font-or-binary (")
        text = flate_pdf(b"BT (safe) Tj ET")
        combined = binary.removesuffix(b"%%EOF\n") + text.removeprefix(b"%PDF-1.4\n")

        self.assertEqual(
            extract(
                combined,
                max_pdf_bytes=len(combined),
                max_decoded_bytes=1024,
            ),
            ("safe",),
        )

    def test_discards_all_fields_from_stream_with_malformed_suffix(self) -> None:
        malformed = flate_pdf(
            b"BT (Document Number) Tj (FORGED) Tj ET ("
        )
        text = flate_pdf(b"BT (safe) Tj ET")
        combined = malformed.removesuffix(b"%%EOF\n") + text.removeprefix(
            b"%PDF-1.4\n"
        )

        self.assertEqual(
            extract(
                combined,
                max_pdf_bytes=len(combined),
                max_decoded_bytes=1024,
            ),
            ("safe",),
        )

    def test_rejects_invalid_limits_encryption_and_missing_text(self) -> None:
        valid = flate_pdf(b"BT (safe) Tj ET")
        encrypted = valid.replace(b"1 0 obj", b"/Encrypt 1 0 obj")
        missing_text = flate_pdf(b"BT /F1 10 Tf ET")
        for pdf, pdf_limit, decoded_limit in (
            (valid, 0, 100),
            (valid, len(valid), 0),
            (encrypted, len(encrypted), 100),
            (missing_text, len(missing_text), 100),
        ):
            with self.subTest(prefix=pdf[:30], limits=(pdf_limit, decoded_limit)):
                with self.assertRaises(ValueError):
                    extract(
                        pdf,
                        max_pdf_bytes=pdf_limit,
                        max_decoded_bytes=decoded_limit,
                    )

    def test_rejects_indirect_stream_length_without_prefix_backtracking(self) -> None:
        valid = flate_pdf(b"BT (safe) Tj ET")
        direct_length = str(len(zlib.compress(b"BT (safe) Tj ET"))).encode("ascii")
        indirect = valid.replace(
            b"/Length " + direct_length,
            b"/Length " + direct_length + b" 0 R",
        )

        with self.assertRaises(ValueError):
            extract(
                indirect,
                max_pdf_bytes=len(indirect),
                max_decoded_bytes=100,
            )

    def test_rejects_hash_mismatch_appended_content_and_pseudo_pdf(self) -> None:
        valid = flate_pdf(b"BT (safe) Tj ET")
        with self.assertRaises(ValueError):
            property_pdf.extract_ordered_fields(
                valid,
                expected_sha256="0" * 64,
                max_pdf_bytes=len(valid),
                max_decoded_bytes=100,
            )
        for invalid in (
            valid + b"attacker",
            valid + flate_pdf(b"BT (attacker) Tj ET"),
            valid.replace(b"endobj\n%%EOF\n", b"endobj\n"),
        ):
            with self.subTest(suffix=invalid[-30:]):
                with self.assertRaises(ValueError):
                    extract(
                        invalid,
                        max_pdf_bytes=len(invalid),
                        max_decoded_bytes=100,
                    )

    def test_rejects_requested_limits_above_hard_safety_ceilings(self) -> None:
        pdf = flate_pdf(b"BT (safe) Tj ET")
        for pdf_limit, decoded_limit in (
            (10_000_001, 100),
            (len(pdf), 10_000_001),
        ):
            with self.assertRaises(ValueError):
                extract(
                    pdf,
                    max_pdf_bytes=pdf_limit,
                    max_decoded_bytes=decoded_limit,
                )

    def test_rejects_field_overflow_during_linear_text_scan(self) -> None:
        pdf = flate_pdf(b"BT " + b"() Tj " * 10_001 + b"ET")

        with self.assertRaises(ValueError):
            extract(
                pdf,
                max_pdf_bytes=len(pdf),
                max_decoded_bytes=100_000,
            )

    def test_compare_marks_duplicate_or_invalid_expected_values_unknown(self) -> None:
        result = property_pdf.compare_sample_row(
            {"PIN": "bad", "DOC_NUM": "D", "DOR_CODE": "", "QU": "Q"},
            ("Document Number", "D", "Document Number", "D", "Qualification", "Q"),
        )

        self.assertEqual(result["document_identity"], "unknown")
        self.assertEqual(result["parcel_unit_identity"], "unknown")
        self.assertEqual(result["property_class"], "unknown")
        self.assertEqual(result["qualification_code"], "match")
        with self.assertRaises(ValueError):
            property_pdf.compare_sample_row([], ())
        with self.assertRaises(ValueError):
            property_pdf.compare_sample_row({}, ("label", 1))

    def test_compare_returns_private_exact_states_without_transaction_claims(
        self,
    ) -> None:
        fields = (
            "Parcel ID",
            "563412ABCDEF123GHIJKLU",
            "Document Number",
            "DOC (SYN)\\A",
            "DOR Code",
            "0100",
            "Qualification",
            "U",
        )
        row = {
            "PIN": "U-12-34-56-ABC-DEF123-GHIJK.L",
            "DOC_NUM": "DOC (SYN)\\A",
            "DOR_CODE": "0100",
            "QU": "U",
        }

        result = property_pdf.compare_sample_row(row, fields)

        self.assertEqual(
            result,
            {
                "privacy_sensitive": True,
                "document_identity": "match",
                "parcel_unit_identity": "match",
                "property_class": "match",
                "qualification_code": "match",
            },
        )
        serialized_keys = set(result)
        for forbidden in (
            "date_vs_closing",
            "closing_date",
            "price_scope",
            "consideration_scope",
            "multi_parcel_consideration",
            "sale_price",
        ):
            self.assertNotIn(forbidden, serialized_keys)

        mismatch = property_pdf.compare_sample_row(
            {**row, "DOC_NUM": "OTHER", "DOR_CODE": "0200"}, fields
        )
        self.assertEqual(mismatch["document_identity"], "mismatch")
        self.assertEqual(mismatch["property_class"], "mismatch")
        self.assertEqual(mismatch["parcel_unit_identity"], "match")

        unknown = property_pdf.compare_sample_row(
            {**row, "DOC_NUM": "", "QU": ""},
            ("Parcel ID", "563412ABCDEF123GHIJKLU", "DOR Code", "0100"),
        )
        self.assertEqual(unknown["document_identity"], "unknown")
        self.assertEqual(unknown["qualification_code"], "unknown")
        self.assertEqual(unknown["parcel_unit_identity"], "match")


if __name__ == "__main__":
    unittest.main()
