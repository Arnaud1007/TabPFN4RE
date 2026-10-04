"""Synthetic contracts for the research-only King County date benchmark."""

from __future__ import annotations

from datetime import date
from hashlib import sha256
from pathlib import Path
import tempfile
import unittest

from scripts.king_historical_benchmark import (
    COLUMNS,
    FEATURES,
    encode_features,
    read_source,
    split_sales,
)


def synthetic_sale(sale_date: str, *, parcel: str = "parcel-1", zipcode: str = "98001") -> str:
    values = {
        "id": parcel,
        "date": f"{sale_date}T000000",
        "price": "300000",
        "bedrooms": "3",
        "bathrooms": "2",
        "sqft_living": "1500",
        "sqft_lot": "6000",
        "floors": "1",
        "waterfront": "0",
        "view": "0",
        "condition": "3",
        "grade": "7",
        "sqft_above": "1500",
        "sqft_basement": "0",
        "yr_built": "1980",
        "yr_renovated": "0",
        "zipcode": zipcode,
        "lat": "47.5",
        "long": "-122.2",
        "sqft_living15": "1600",
        "sqft_lot15": "6200",
    }
    return ",".join(values[name] for name in COLUMNS)


def write_fixture(path: Path, rows: tuple[str, ...]) -> str:
    attributes = "\n".join(f"@ATTRIBUTE {name} STRING" for name in COLUMNS)
    path.write_text(f"@RELATION house_sales\n{attributes}\n@DATA\n" + "\n".join(rows) + "\n", encoding="utf-8")
    return sha256(path.read_bytes()).hexdigest()


class KingHistoricalBenchmarkTests(unittest.TestCase):
    def test_source_hash_schema_and_price_are_guarded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "synthetic.arff"
            digest = write_fixture(source, (synthetic_sale("20141231"),))
            sales = read_source(source, digest, expected_rows=1)
            self.assertEqual(len(sales), 1)
            self.assertEqual(sales[0].sale_date, date(2014, 12, 31))
            with self.assertRaisesRegex(ValueError, "checksum"):
                read_source(source, "0" * 64, expected_rows=1)
            with self.assertRaisesRegex(ValueError, "row count"):
                read_source(source, digest, expected_rows=2)
            bad = write_fixture(source, (synthetic_sale("20141231").replace("300000", "0", 1),))
            with self.assertRaisesRegex(ValueError, "price"):
                read_source(source, bad, expected_rows=1)

    def test_model_features_exclude_identifiers_outcome_and_unknown_vintages(self) -> None:
        self.assertFalse(
            {"id", "date", "price", "yr_renovated", "sqft_living15", "sqft_lot15"} & set(FEATURES)
        )

    def test_chronological_split_is_disjoint_at_boundaries(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "synthetic.arff"
            dates = ("20141231", "20150101", "20150228", "20150301")
            digest = write_fixture(source, tuple(synthetic_sale(value, parcel=f"p-{i}") for i, value in enumerate(dates)))
            sales = read_source(source, digest, expected_rows=4)
            splits = split_sales(sales)
            self.assertEqual([len(splits[name]) for name in ("train", "validation", "test")], [1, 2, 1])
            self.assertEqual({sale.row_id for role in splits.values() for sale in role}, {sale.row_id for sale in sales})
            reversed_splits = split_sales(tuple(reversed(sales)))
            self.assertEqual(
                {name: [sale.row_id for sale in rows] for name, rows in splits.items()},
                {name: [sale.row_id for sale in rows] for name, rows in reversed_splits.items()},
            )

    def test_encoding_uses_only_training_zipcodes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "synthetic.arff"
            digest = write_fixture(source, (synthetic_sale("20141231"), synthetic_sale("20150301", parcel="p-2", zipcode="99999")))
            train, test = read_source(source, digest, expected_rows=2)
            feature_names, train_matrix, test_matrix = encode_features((train,), (test,))
            self.assertIn("zipcode=98001", feature_names)
            self.assertNotIn("zipcode=99999", feature_names)
            self.assertEqual(train_matrix[0][-1], 1.0)
            self.assertEqual(test_matrix[0][-1], 0.0)


if __name__ == "__main__":
    unittest.main()
