"""Test-first contract for the small Ames engineering pipeline.

The optional source test uses an explicitly supplied ARFF path. It never
downloads data or treats an engineering split as the historical holdout.
"""

import math
import hashlib
import os
from pathlib import Path
import sys
import tempfile
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tabpfn4realestate.ames import (  # noqa: E402
    Split,
    engineering_split,
    fit_median_baseline,
    load_ames_arff,
    median_absolute_percentage_error,
    signed_percentage_error,
)


def ames_row(identifier: int, price: object) -> dict[str, object]:
    return {"Id": str(identifier), "SalePrice": price, "GrLivArea": "1500"}


class AmesSourceTests(unittest.TestCase):
    def write_arff(self, attributes: str, records: str) -> Path:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        path = Path(temp_dir.name) / "ames.arff"
        path.write_text(
            "@RELATION house_prices\n" + attributes + "\n@DATA\n" + records,
            encoding="utf-8",
        )
        return path

    def test_loads_schema_and_preserves_source_identifiers(self) -> None:
        path = self.write_arff(
            "@ATTRIBUTE Id NUMERIC\n"
            "@ATTRIBUTE GrLivArea NUMERIC\n"
            "@ATTRIBUTE SalePrice NUMERIC",
            "1,1500,100000\n2,1800,200000\n",
        )

        rows = load_ames_arff(path, expected_rows=2)

        self.assertEqual([row["Id"] for row in rows], ["1", "2"])
        self.assertEqual([float(row["SalePrice"]) for row in rows], [100000, 200000])
        self.assertEqual(rows[0]["GrLivArea"], "1500")

    def test_rejects_missing_required_column(self) -> None:
        path = self.write_arff(
            "@ATTRIBUTE Id NUMERIC\n@ATTRIBUTE GrLivArea NUMERIC",
            "1,1500\n",
        )

        with self.assertRaisesRegex(ValueError, "SalePrice"):
            load_ames_arff(path)

    def test_rejects_wrong_expected_row_count(self) -> None:
        path = self.write_arff(
            "@ATTRIBUTE Id NUMERIC\n@ATTRIBUTE SalePrice NUMERIC",
            "1,100000\n",
        )

        with self.assertRaisesRegex(ValueError, "row|count|expected"):
            load_ames_arff(path, expected_rows=1460)

    def test_rejects_nonpositive_and_nonfinite_source_prices(self) -> None:
        for bad_price in ("0", "-1", "NaN", "Infinity", "?"):
            with self.subTest(price=bad_price):
                path = self.write_arff(
                    "@ATTRIBUTE Id NUMERIC\n@ATTRIBUTE SalePrice NUMERIC",
                    f"1,{bad_price}\n",
                )
                with self.assertRaises(ValueError):
                    load_ames_arff(path)

    def test_rejects_duplicate_source_ids(self) -> None:
        path = self.write_arff(
            "@ATTRIBUTE Id NUMERIC\n@ATTRIBUTE SalePrice NUMERIC",
            "1,100000\n1,200000\n",
        )

        with self.assertRaisesRegex(ValueError, "Id|duplicate"):
            load_ames_arff(path)

    def test_rejects_nonnumeric_and_formula_leading_source_ids(self) -> None:
        for bad_id in ("abc", "=1+1", "+1", "-2", "@SUM(1)"):
            with self.subTest(identifier=bad_id):
                path = self.write_arff(
                    "@ATTRIBUTE Id NUMERIC\n@ATTRIBUTE SalePrice NUMERIC",
                    f"{bad_id},100000\n",
                )
                with self.assertRaisesRegex(ValueError, "Id|identifier"):
                    load_ames_arff(path)

    def test_canonicalizes_padded_numeric_id_and_rejects_canonical_duplicate(
        self,
    ) -> None:
        padded = self.write_arff(
            "@ATTRIBUTE Id NUMERIC\n@ATTRIBUTE SalePrice NUMERIC",
            " 1 ,100000\n 2 ,200000\n",
        )
        self.assertEqual([row["Id"] for row in load_ames_arff(padded)], ["1", "2"])

        duplicate = self.write_arff(
            "@ATTRIBUTE Id NUMERIC\n@ATTRIBUTE SalePrice NUMERIC",
            "1,100000\n 1 ,200000\n",
        )
        with self.assertRaisesRegex(ValueError, "Id|duplicate"):
            load_ames_arff(duplicate)

    def test_verifies_source_checksum_and_size_before_parsing(self) -> None:
        path = self.write_arff(
            "@ATTRIBUTE Id NUMERIC\n@ATTRIBUTE SalePrice NUMERIC",
            "1,100000\n",
        )
        expected = hashlib.sha256(path.read_bytes()).hexdigest()
        self.assertEqual(len(load_ames_arff(path, expected_sha256=expected)), 1)
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            load_ames_arff(path, expected_sha256="0" * 64)
        with self.assertRaisesRegex(ValueError, "size|bytes"):
            load_ames_arff(path, max_bytes=path.stat().st_size - 1)

    def test_handles_arff_quoted_categorical_comma(self) -> None:
        path = self.write_arff(
            "@ATTRIBUTE Id NUMERIC\n"
            "@ATTRIBUTE Neighborhood STRING\n"
            "@ATTRIBUTE SalePrice NUMERIC",
            "1,'North, East',100000\n",
        )
        self.assertEqual(load_ames_arff(path)[0]["Neighborhood"], "North, East")


class EngineeringSplitTests(unittest.TestCase):
    def test_split_is_deterministic_disjoint_and_explicitly_engineering(self) -> None:
        rows = [
            ames_row(identifier, 100000 + identifier) for identifier in range(1, 11)
        ]

        first = engineering_split(rows, seed=42)
        second = engineering_split(rows, seed=42)

        self.assertEqual(first, second)
        self.assertEqual(first.protocol_id, "ames_engineering_v1")
        self.assertEqual(len(first.development_ids), 8)
        self.assertEqual(len(first.reserved_ids), 2)
        self.assertFalse(set(first.development_ids) & set(first.reserved_ids))
        self.assertEqual(
            set(first.development_ids) | set(first.reserved_ids),
            {str(identifier) for identifier in range(1, 11)},
        )

    def test_split_rejects_too_few_rows_and_duplicate_ids(self) -> None:
        with self.assertRaises(ValueError):
            engineering_split([ames_row(1, 100000)])
        with self.assertRaises(ValueError):
            engineering_split([ames_row(1, 100000), ames_row(1, 200000)])


class MedianBaselineTests(unittest.TestCase):
    def test_fits_development_median_and_predicts_positive_price(self) -> None:
        rows = [ames_row(1, 100), ames_row(2, 200), ames_row(3, 400)]

        model = fit_median_baseline(rows, split=Split(("1", "2", "3"), ("4",)))

        self.assertEqual(
            model.predict([ames_row(4, 999), ames_row(5, 999)]), [200.0, 200.0]
        )

    def test_refuses_any_reserved_id_in_fit(self) -> None:
        rows = [ames_row(1, 100), ames_row(2, 200)]

        with self.assertRaisesRegex(ValueError, "reserved|development|Id"):
            fit_median_baseline(rows, split=Split(("1",), ("2",)))

    def test_requires_split_context_at_fit(self) -> None:
        with self.assertRaises(TypeError):
            fit_median_baseline([ames_row(1, 100)])

    def test_refuses_empty_or_invalid_training_targets(self) -> None:
        with self.assertRaises(ValueError):
            fit_median_baseline([], split=Split(("1",), ("2",)))
        for bad_price in (0, -1, float("nan"), float("inf"), None):
            with self.subTest(price=bad_price):
                with self.assertRaises(ValueError):
                    fit_median_baseline(
                        [ames_row(1, bad_price)], split=Split(("1",), ("2",))
                    )


class MetricTests(unittest.TestCase):
    def test_signed_percentage_error_has_declared_direction(self) -> None:
        self.assertAlmostEqual(signed_percentage_error(100, 110), 0.10)
        self.assertAlmostEqual(signed_percentage_error(100, 90), -0.10)
        self.assertAlmostEqual(
            median_absolute_percentage_error([100, 100], [110, 90]), 0.10
        )

    def test_rejects_invalid_labels_predictions_and_length_mismatch(self) -> None:
        for actual, predicted in ((0, 10), (100, 0), (100, math.nan), (math.inf, 100)):
            with self.subTest(actual=actual, predicted=predicted):
                with self.assertRaises(ValueError):
                    signed_percentage_error(actual, predicted)
        with self.assertRaises(ValueError):
            median_absolute_percentage_error([], [])
        with self.assertRaises(ValueError):
            median_absolute_percentage_error([100], [100, 200])

    def test_rejects_percentage_error_overflow(self) -> None:
        with self.assertRaises(ValueError):
            signed_percentage_error(1e-320, 1e308)


@unittest.skipUnless(
    os.environ.get("AMES_ARFF_PATH"), "set AMES_ARFF_PATH for source integration"
)
class RealAmesSourceTests(unittest.TestCase):
    def test_openml_source_has_expected_row_count_and_identifiers(self) -> None:
        path = Path(os.environ["AMES_ARFF_PATH"])
        rows = load_ames_arff(
            path,
            expected_rows=1460,
            expected_sha256="10db9fe72ed693212a222e39981133ec1b3ee5090d7f2caf2461190a4ad51279",
        )
        self.assertEqual(len({row["Id"] for row in rows}), 1460)
        self.assertTrue(all(float(row["SalePrice"]) > 0 for row in rows))


if __name__ == "__main__":
    unittest.main()
