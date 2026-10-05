"""RED contracts for bounded HCPA property-record review evidence."""

from __future__ import annotations

import unittest

from tests.test_hcpa_sample_review import HASH, WHEN, finding, review


PROPERTY_RECORD_URL = (
    "https://gis.hcpafl.org/PropertySearch/#/parcel/basic/9927330ZZ000005000130U"
)
VALID_TOKEN = "9927330ZZ000005000130U"


def property_record(reference: str = PROPERTY_RECORD_URL) -> dict[str, str]:
    return {
        "evidence_id": "hcpa_property",
        "kind": "hcpa_property_record",
        "reference": reference,
        "observed_at": WHEN,
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


if __name__ == "__main__":
    unittest.main()
