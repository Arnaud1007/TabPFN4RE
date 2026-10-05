"""RED contracts for bounded HCPA property-record review evidence."""

from __future__ import annotations

import unittest

from tests.test_hcpa_sample_review import HASH, WHEN, finding, review


PROPERTY_RECORD_URL = (
    "https://gis.hcpafl.org/PropertySearch/#/parcel/basic/9927330ZZ000005000130U"
)
VALID_TOKEN = "9927330ZZ000005000130U"
PROPERTY_RECORD_PDF_URL = (
    f"https://gis.hcpafl.org/CommonServices/property/parcelpdf/?pin={VALID_TOKEN}"
)


def property_record(reference: str = PROPERTY_RECORD_URL) -> dict[str, str]:
    return {
        "evidence_id": "hcpa_property",
        "kind": "hcpa_property_record",
        "reference": reference,
        "observed_at": WHEN,
    }


def property_record_pdf(reference: str = PROPERTY_RECORD_PDF_URL) -> dict[str, str]:
    return {
        "evidence_id": "hcpa_property_pdf",
        "kind": "hcpa_property_record_pdf",
        "reference": reference,
        "observed_at": WHEN,
        "artifact_sha256": HASH,
    }


class HcpaPropertyRecordEvidenceTests(unittest.TestCase):
    def validated_evidence(self, reference: str = PROPERTY_RECORD_URL) -> dict:
        item = property_record(reference)
        self.assertEqual(review._validate_evidence(item, HASH), item)
        return {item["evidence_id"]: item}

    def test_official_property_record_supports_only_its_source_specific_facts(
        self,
    ) -> None:
        evidence_by_id = self.validated_evidence()
        supported = {
            "document_identity": "match",
            "parcel_unit_identity": "match",
            "property_class": "single_family",
            "qualification_code": "corroborated",
        }

        for dimension, value in supported.items():
            with self.subTest(dimension=dimension):
                review._validate_rubric(
                    {
                        dimension: finding(
                            value,
                            identifier="hcpa_property",
                        )
                    },
                    evidence_by_id,
                )

    def test_property_record_cannot_establish_transaction_or_rights_facts(self) -> None:
        evidence_by_id = self.validated_evidence()
        unsupported = {
            "date_vs_closing": "same",
            "price_scope": "single_property",
            "multi_parcel_consideration": "single_parcel_confirmed",
            "reuse_rights": "permitted",
            "missing_fields": "none_in_checked_sources",
            "duplicate_status": "no_duplicate_in_checked_sources",
            "evidence_quality": "high",
            "reason_code": "corroborated",
        }

        for dimension, value in unsupported.items():
            with self.subTest(dimension=dimension):
                with self.assertRaisesRegex(ValueError, "source-specific evidence"):
                    review._validate_rubric(
                        {
                            dimension: finding(
                                value,
                                identifier="hcpa_property",
                            )
                        },
                        evidence_by_id,
                    )

    def test_property_record_kind_rejects_unsafe_or_non_property_urls(self) -> None:
        invalid_references = (
            f"http://gis.hcpafl.org/PropertySearch/#/parcel/basic/{VALID_TOKEN}",
            f"https://example.org/PropertySearch/#/parcel/basic/{VALID_TOKEN}",
            "https://gis.hcpafl.org.evil.example/PropertySearch/"
            f"#/parcel/basic/{VALID_TOKEN}",
            "https://user:secret@gis.hcpafl.org/PropertySearch/"
            f"#/parcel/basic/{VALID_TOKEN}",
            f"https://@gis.hcpafl.org/PropertySearch/#/parcel/basic/{VALID_TOKEN}",
            f"https://:@gis.hcpafl.org/PropertySearch/#/parcel/basic/{VALID_TOKEN}",
            "https://gis.hcpafl.org:bad/PropertySearch/#/parcel/basic/AAAAAAAAAA",
            f"https://gis.hcpafl.org:443/PropertySearch/#/parcel/basic/{VALID_TOKEN}",
            "https://gis.hcpafl.org/PropertySearch/?source=test"
            f"#/parcel/basic/{VALID_TOKEN}",
            "https://www.hcpafl.org/Terms",
            "https://gis.hcpafl.org/PropertySearch/",
            f"https://gis.hcpafl.org/PropertySearch/#/search/basic/{VALID_TOKEN}",
            "https://gis.hcpafl.org/PropertySearch/#/parcel/basic/..........",
            "https://gis.hcpafl.org/PropertySearch/#/parcel/basic/9927330ZZ00000500013-U",
            "https://gis.hcpafl.org/PropertySearch/#/parcel/basic/9927330ZZ00000500013U",
            "https://gis.hcpafl.org/PropertySearch/#/parcel/basic/9927330ZZ0000050001300U",
        )

        for reference in invalid_references:
            with self.subTest(reference=reference):
                with self.assertRaisesRegex(ValueError, "evidence") as caught:
                    review._validate_evidence(property_record(reference), HASH)
                self.assertNotIn(reference, str(caught.exception))

    def test_property_record_pdf_supports_only_its_source_specific_facts(self) -> None:
        item = property_record_pdf()
        self.assertEqual(review._validate_evidence(item, HASH), item)
        evidence_by_id = {item["evidence_id"]: item}
        supported = {
            "document_identity": "match",
            "parcel_unit_identity": "match",
            "property_class": "single_family",
            "qualification_code": "corroborated",
        }

        for dimension, value in supported.items():
            with self.subTest(dimension=dimension):
                review._validate_rubric(
                    {
                        dimension: finding(
                            value,
                            identifier="hcpa_property_pdf",
                        )
                    },
                    evidence_by_id,
                )

    def test_property_record_pdf_cannot_establish_transaction_or_rights_facts(
        self,
    ) -> None:
        item = property_record_pdf()
        self.assertEqual(review._validate_evidence(item, HASH), item)
        evidence_by_id = {item["evidence_id"]: item}
        unsupported = {
            "date_vs_deed_execution": "same",
            "date_vs_recording": "same",
            "date_vs_closing": "same",
            "price_scope": "single_property",
            "multi_parcel_consideration": "single_parcel_confirmed",
            "reason_code": "corroborated",
            "reuse_rights": "permitted",
            "missing_fields": "none_in_checked_sources",
            "duplicate_status": "no_duplicate_in_checked_sources",
            "evidence_quality": "high",
        }

        for dimension, value in unsupported.items():
            with self.subTest(dimension=dimension):
                with self.assertRaisesRegex(ValueError, "source-specific evidence"):
                    review._validate_rubric(
                        {
                            dimension: finding(
                                value,
                                identifier="hcpa_property_pdf",
                            )
                        },
                        evidence_by_id,
                    )

    def test_property_record_pdf_requires_the_exact_official_url_shape(self) -> None:
        encoded_token = "%39" + VALID_TOKEN[1:]
        invalid_references = (
            f"http://gis.hcpafl.org/CommonServices/property/parcelpdf/?pin={VALID_TOKEN}",
            f"https://example.org/CommonServices/property/parcelpdf/?pin={VALID_TOKEN}",
            "https://gis.hcpafl.org.evil.example/CommonServices/property/parcelpdf/"
            f"?pin={VALID_TOKEN}",
            "https://user:secret@gis.hcpafl.org/CommonServices/property/parcelpdf/"
            f"?pin={VALID_TOKEN}",
            "https://gis.hcpafl.org:443/CommonServices/property/parcelpdf/"
            f"?pin={VALID_TOKEN}",
            "https://GIS.HCPAFL.ORG/CommonServices/property/parcelpdf/"
            f"?pin={VALID_TOKEN}",
            f"https://gis.hcpafl.org/CommonServices/property/parcelpdf?pin={VALID_TOKEN}",
            "https://gis.hcpafl.org/commonservices/property/parcelpdf/"
            f"?pin={VALID_TOKEN}",
            "https://gis.hcpafl.org/CommonServices/property/parcelpdf/",
            "https://gis.hcpafl.org/CommonServices/property/parcelpdf/?PIN="
            f"{VALID_TOKEN}",
            "https://gis.hcpafl.org/CommonServices/property/parcelpdf/?pin=",
            "https://gis.hcpafl.org/CommonServices/property/parcelpdf/?pin="
            f"{VALID_TOKEN}&extra=1",
            "https://gis.hcpafl.org/CommonServices/property/parcelpdf/?pin="
            f"{VALID_TOKEN}&pin={VALID_TOKEN}",
            "https://gis.hcpafl.org/CommonServices/property/parcelpdf/?%70in="
            f"{VALID_TOKEN}",
            "https://gis.hcpafl.org/CommonServices/property/parcelpdf/?pin="
            f"{encoded_token}",
            "https://gis.hcpafl.org/CommonServices/property/parcelpdf/?pin="
            f"{VALID_TOKEN}%20",
            "https://gis.hcpafl.org/CommonServices/property/parcelpdf/?pin="
            f"{VALID_TOKEN}X",
            "https://gis.hcpafl.org/CommonServices/property/parcelpdf/?pin="
            f"{VALID_TOKEN[:-1]}",
            "https://gis.hcpafl.org/CommonServices/property/parcelpdf/?pin="
            f"{VALID_TOKEN.lower()}",
            "https://gis.hcpafl.org/CommonServices/property/parcelpdf/?pin="
            f"{VALID_TOKEN}#fragment",
            " https://gis.hcpafl.org/CommonServices/property/parcelpdf/"
            f"?pin={VALID_TOKEN}",
            "https://gis.hcpafl.org/CommonServices/property/parcelpdf/"
            f"?pin={VALID_TOKEN} ",
            "https://gis.hcpafl.org/\nCommonServices/property/parcelpdf/"
            f"?pin={VALID_TOKEN}",
            "https://gis.hcpafl.org/CommonServices/property/parcelpdf/"
            f"?pi\tn={VALID_TOKEN}",
            "https://gis.hcpafl.org/CommonServices/property/parcelpdf/"
            f"?pin={VALID_TOKEN}\r",
            "https://gis.hcpafl.org/CommonServices/property/parcelpdf/"
            f"?pin={VALID_TOKEN}\x00",
        )

        for reference in invalid_references:
            with self.subTest(reference=reference):
                with self.assertRaisesRegex(ValueError, "evidence") as caught:
                    review._validate_evidence(property_record_pdf(reference), HASH)
                self.assertNotIn(reference, str(caught.exception))


if __name__ == "__main__":
    unittest.main()
