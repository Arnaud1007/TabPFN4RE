"""Policy and request guards for the historical Ames prediction prototype."""

from __future__ import annotations

import unittest
from pathlib import Path
import tempfile
from unittest.mock import patch

from scripts.ames_dev_prototype import (
    _validate_dependency_lock,
    allowed_feature_names,
    validate_request,
)


class AmesDevPrototypeTests(unittest.TestCase):
    def test_feature_policy_excludes_identity_target_and_sale_outcomes(self) -> None:
        columns = (
            "Id",
            "GrLivArea",
            "OverallQual",
            "Neighborhood",
            "MoSold",
            "YrSold",
            "SaleType",
            "SaleCondition",
            "SalePrice",
        )
        self.assertEqual(
            allowed_feature_names(columns),
            ("GrLivArea", "OverallQual", "Neighborhood"),
        )

    def test_feature_policy_rejects_new_target_copy(self) -> None:
        with self.assertRaisesRegex(ValueError, "target-derived"):
            allowed_feature_names(("GrLivArea", "SalePrice_copy"))

    def test_request_rejects_unknown_and_target_inputs(self) -> None:
        features = ("GrLivArea", "OverallQual", "Neighborhood")
        numeric = frozenset(("GrLivArea", "OverallQual"))
        with self.assertRaisesRegex(ValueError, "exactly"):
            validate_request(
                {"GrLivArea": 1500, "OverallQual": 6, "Neighborhood": "NAmes", "Id": 1},
                features,
                numeric,
            )
        with self.assertRaisesRegex(ValueError, "exactly"):
            validate_request(
                {
                    "GrLivArea": 1500,
                    "OverallQual": 6,
                    "Neighborhood": "NAmes",
                    "SalePrice": 1,
                },
                features,
                numeric,
            )

    def test_request_normalizes_supported_inputs(self) -> None:
        features = ("GrLivArea", "OverallQual", "Neighborhood", "LotArea")
        numeric = frozenset(("GrLivArea", "OverallQual", "LotArea"))
        normalized = validate_request(
            {
                "GrLivArea": 1500,
                "OverallQual": 6,
                "Neighborhood": "NAmes",
                "LotArea": None,
            },
            features,
            numeric,
        )
        self.assertEqual(normalized["GrLivArea"], 1500.0)
        self.assertEqual(normalized["Neighborhood"], "NAmes")
        self.assertIsNone(normalized["LotArea"])
        self.assertEqual(tuple(normalized), features)

    def test_request_requires_full_feature_contract(self) -> None:
        with self.assertRaisesRegex(ValueError, "exactly"):
            validate_request(
                {"GrLivArea": 1500, "OverallQual": 6, "Neighborhood": "NAmes"},
                ("GrLivArea", "OverallQual", "Neighborhood", "LotArea"),
                frozenset(("GrLivArea", "OverallQual", "LotArea")),
            )

    def test_request_rejects_bad_types(self) -> None:
        features = ("GrLivArea", "OverallQual", "Neighborhood")
        numeric = frozenset(("GrLivArea", "OverallQual"))
        cases = (
            {"GrLivArea": True, "OverallQual": 6, "Neighborhood": "NAmes"},
            {"GrLivArea": float("inf"), "OverallQual": 6, "Neighborhood": "NAmes"},
            {"GrLivArea": None, "OverallQual": 6, "Neighborhood": "NAmes"},
            {"GrLivArea": 1500, "OverallQual": 6, "Neighborhood": " "},
        )
        for case in cases:
            with self.subTest(case=case), self.assertRaises(ValueError):
                validate_request(case, features, numeric)

    def test_dependency_mismatch_blocks_training(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            lock_dir = Path(temporary) / "locks"
            lock_dir.mkdir()
            (lock_dir / "ames-prototype-requirements.txt").write_text(
                "\n".join(f"package{i}==1.0" for i in range(8)) + "\n",
                encoding="utf-8",
            )
            with patch(
                "scripts.ames_dev_prototype.metadata.version", return_value="1.0"
            ):
                self.assertEqual(len(_validate_dependency_lock(Path(temporary))), 64)
            with patch(
                "scripts.ames_dev_prototype.metadata.version", return_value="2.0"
            ):
                with self.assertRaisesRegex(ValueError, "mismatch"):
                    _validate_dependency_lock(Path(temporary))


if __name__ == "__main__":
    unittest.main()
