"""Small adversarial fixtures for the Indiana research cohort."""

from __future__ import annotations

import csv
import tempfile
import unittest
from datetime import date
from decimal import Decimal
from hashlib import sha256
from io import StringIO
from pathlib import Path
from zipfile import ZipFile

from scripts.indiana_historical_benchmark import (
    DISCLOSURE_FIELDS,
    MODEL_FEATURES,
    PARCEL_FIELDS,
    encode_features,
    read_archive,
    split_sales,
)
from scripts.run_indiana_historical_benchmark import (
    baseline_predictions,
    replay_predictions,
    write_predictions,
)


def _disclosure(**changes: str) -> dict[str, str]:
    row = {name: "" for name in DISCLOSURE_FIELDS}
    row.update(
        {
            "SDF_ID": "form-1",
            "Unique_Sales_ID": "sale-1",
            "County_ID": "49",
            "P2_13_Date_Sale": "2024-06-15",
            "E1_Sales_Price": "30000000",
            "E2_PersProp": "0",
            "E4_Relationship_Discount": "0",
            "C9_Num_Parcels": "1",
            "C10_Residential_Property": "Y",
            "B1_Valuable_Consider": "Y",
        }
    )
    for name in (
        "B3_Vacant_Land",
        "B4_Trade",
        "B5_Land_Contract",
        "B6_Partial_Interest",
        "B7_Easement",
        "B8_Court_Order",
        "B9_Partition",
        "B10_Charity",
        "C1_Sheriff_Sale",
        "C2_Short_Sale",
        "C3_Quitclaim",
        "C4_Auction",
        "C6_Multiple_Forms",
        "G11_Special_Relationship",
        "G11_Special_Foreclosure",
        "G11_Special_Auction",
        "G11_Special_Trade",
        "G11_Special_Partial",
    ):
        row[name] = "N"
    return {**row, **changes}


def _parcel(**changes: str) -> dict[str, str]:
    return {
        **{name: "" for name in PARCEL_FIELDS},
        "SDF_ID": "form-1",
        "A4_Improvement": "Y",
        "A5_ZipCode": "46204",
        "P2_6_Prop_Class_Code": "510",
        "P2_9_Acreage": "2500",
        **changes,
    }


def _table(fields: tuple[str, ...], rows: list[dict[str, str]]) -> bytes:
    stream = StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, delimiter="\t")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-16")


def _archive(
    path: Path,
    disclosures: list[dict[str, str]],
    parcels: list[dict[str, str]],
) -> str:
    with ZipFile(path, "w") as source:
        source.writestr("SALEDISC.txt", _table(DISCLOSURE_FIELDS, disclosures))
        source.writestr("SALEPARCEL.txt", _table(PARCEL_FIELDS, parcels))
    return sha256(path.read_bytes()).hexdigest()


class IndianaHistoricalBenchmarkTests(unittest.TestCase):
    def test_utf16_quoted_fields_hash_and_schema(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.zip"
            digest = _archive(path, [_disclosure()], [_parcel(P2_9_Acreage="2500\t")])
            sales, funnel = read_archive(path, digest, year=2024)
            self.assertEqual(len(sales), 1)
            self.assertEqual(sales[0].county_id, "49")
            self.assertEqual(sales[0].acreage, 0.25)
            self.assertEqual(sales[0].price, Decimal("300000.00"))
            self.assertEqual(funnel["eligible"], 1)
            with self.assertRaisesRegex(ValueError, "checksum"):
                read_archive(path, "0" * 64, year=2024)
            with ZipFile(path, "w") as source:
                source.writestr("SALEDISC.txt", "wrong\n".encode("utf-16"))
                source.writestr("SALEPARCEL.txt", _table(PARCEL_FIELDS, [_parcel()]))
            with self.assertRaisesRegex(ValueError, "schema"):
                read_archive(path, sha256(path.read_bytes()).hexdigest(), year=2024)

    def test_economic_and_parcel_duplicates_do_not_create_labels(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.zip"
            disclosures = [
                _disclosure(),
                _disclosure(SDF_ID="form-2", Unique_Sales_ID="sale-1"),
                _disclosure(SDF_ID="form-3", Unique_Sales_ID="sale-3"),
            ]
            parcels = [
                _parcel(),
                _parcel(SDF_ID="form-2"),
                _parcel(SDF_ID="form-3"),
                _parcel(SDF_ID="form-3", A5_ZipCode="46205"),
            ]
            digest = _archive(path, disclosures, parcels)
            sales, funnel = read_archive(path, digest, year=2024)
            self.assertEqual(sales, ())
            self.assertEqual(funnel["duplicate_economic_sale"], 2)
            self.assertEqual(funnel["parcel_count_mismatch"], 1)

    def test_malformed_duplicate_still_blocks_its_economic_sale(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.zip"
            valid = _table(DISCLOSURE_FIELDS, [_disclosure()]).decode("utf-16")
            duplicated_row = valid.splitlines()[1] + "\tEXTRA\n"
            with ZipFile(path, "w") as source:
                source.writestr(
                    "SALEDISC.txt", (valid + duplicated_row).encode("utf-16")
                )
                source.writestr("SALEPARCEL.txt", _table(PARCEL_FIELDS, [_parcel()]))
            sales, funnel = read_archive(
                path, sha256(path.read_bytes()).hexdigest(), year=2024
            )
            self.assertEqual(sales, ())
            self.assertEqual(funnel["malformed_disclosure"], 1)
            self.assertEqual(funnel["duplicate_economic_sale"], 1)
            valid_parcel = _table(PARCEL_FIELDS, [_parcel()]).decode("utf-16")
            duplicate_parcel = valid_parcel.splitlines()[1] + "\tEXTRA\n"
            with ZipFile(path, "w") as source:
                source.writestr(
                    "SALEDISC.txt", _table(DISCLOSURE_FIELDS, [_disclosure()])
                )
                source.writestr(
                    "SALEPARCEL.txt", (valid_parcel + duplicate_parcel).encode("utf-16")
                )
            sales, funnel = read_archive(
                path, sha256(path.read_bytes()).hexdigest(), year=2024
            )
            self.assertEqual(sales, ())
            self.assertEqual(funnel["malformed_parcel"], 1)
            self.assertEqual(funnel["parcel_count_mismatch"], 1)

    def test_target_and_special_transfer_eligibility(self) -> None:
        cases = (
            (_disclosure(E1_Sales_Price="0"), _parcel(), "invalid_price"),
            (_disclosure(E1_Sales_Price="300000.00"), _parcel(), "invalid_price"),
            (_disclosure(P2_13_Date_Sale="2025-01-01"), _parcel(), "outside_year"),
            (_disclosure(County_ID="4\t9"), _parcel(), "invalid_county"),
            (_disclosure(B6_Partial_Interest="Y"), _parcel(), "special_transfer"),
            (_disclosure(E2_PersProp="100"), _parcel(), "personal_property"),
            (_disclosure(), _parcel(P2_6_Prop_Class_Code="550"), "property_class"),
            (_disclosure(), _parcel(A4_Improvement="N"), "no_improvement"),
        )
        with tempfile.TemporaryDirectory() as directory:
            for index, (disclosure, parcel, reason) in enumerate(cases):
                path = Path(directory) / f"fixture-{index}.zip"
                digest = _archive(path, [disclosure], [parcel])
                sales, funnel = read_archive(path, digest, year=2024)
                self.assertEqual(sales, (), reason)
                self.assertEqual(funnel[reason], 1)

    def test_model_features_are_an_explicit_small_allowlist(self) -> None:
        self.assertEqual(MODEL_FEATURES, ("County_ID", "A5_ZipCode", "P2_9_Acreage"))
        self.assertFalse(
            {"E1_Sales_Price", "P2_5_Total_AV", "C8_Market_Days", "SDF_ID"}
            & set(MODEL_FEATURES)
        )

    def test_split_and_encoding_fit_only_training_categories(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.zip"
            first = _disclosure()
            second = _disclosure(
                SDF_ID="form-2",
                Unique_Sales_ID="sale-2",
                P2_13_Date_Sale="2025-01-01",
            )
            parcels = [_parcel(), _parcel(SDF_ID="form-2", A5_ZipCode="99999")]
            digest = _archive(path, [first, second], parcels)
            train, _ = read_archive(path, digest, year=2024)
            self.assertEqual(train[0].sale_date, date(2024, 6, 15))
            digest = _archive(path, [second], [parcels[1]])
            validation, _ = read_archive(path, digest, year=2025)
            split_sales(train, validation)
            names, train_matrix, validation_matrix = encode_features(train, validation)
            self.assertIn("A5_ZipCode=46204", names)
            self.assertNotIn("A5_ZipCode=99999", names)
            self.assertEqual(train_matrix.shape[0], 1)
            self.assertEqual(validation_matrix.shape[0], 1)

    def test_past_only_baseline_and_saved_metric_replay(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.zip"
            train_disclosures = [
                _disclosure(),
                _disclosure(
                    SDF_ID="form-2",
                    Unique_Sales_ID="sale-2",
                    E1_Sales_Price="50000000",
                ),
            ]
            train_parcels = [_parcel(), _parcel(SDF_ID="form-2")]
            digest = _archive(path, train_disclosures, train_parcels)
            training, _ = read_archive(path, digest, year=2024)
            digest = _archive(
                path,
                [
                    _disclosure(
                        SDF_ID="form-3",
                        Unique_Sales_ID="sale-3",
                        P2_13_Date_Sale="2025-01-01",
                    )
                ],
                [_parcel(SDF_ID="form-3", A5_ZipCode="99999")],
            )
            validation, _ = read_archive(path, digest, year=2025)
            baseline = baseline_predictions(training, validation, min_zip_sales=2)
            self.assertEqual(baseline, (400000.0,))
            output = Path(directory) / "predictions.csv"
            write_predictions(output, validation, (300000.0,), baseline)
            summaries = replay_predictions(output)
            self.assertEqual(summaries["xgboost"]["eligible_count"], 1)
            self.assertEqual(summaries["xgboost"]["mdape"], 0.0)
            self.assertAlmostEqual(summaries["zip_county_median"]["mdape"], 1 / 3)


if __name__ == "__main__":
    unittest.main()
