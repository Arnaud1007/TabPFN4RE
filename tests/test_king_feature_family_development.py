from __future__ import annotations

import hashlib
import json
import math
import os
import stat
import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from scripts import run_king_feature_family_development as family
from scripts.king_historical_benchmark import COLUMNS, NUMERIC_FEATURES, Sale


def sale(row_id: str, when: date, price: str = "100000") -> Sale:
    attributes = {name: 1.0 for name in NUMERIC_FEATURES}
    attributes["zipcode"] = "98001"
    return Sale(row_id, row_id, when, Decimal(price), attributes)


def source_line(identifier: str, when: str, renovation: str = "0") -> str:
    fields = {name: "1" for name in COLUMNS}
    fields.update(
        id=identifier,
        date=when,
        price="100000",
        zipcode="98001",
        yr_built="1900",
        yr_renovated=renovation,
        sqft_living15="1200",
        sqft_lot15="5000",
    )
    return ",".join(fields[name] for name in COLUMNS)


class KingFeatureFamilyDevelopmentTests(unittest.TestCase):
    def test_reader_retains_zero_masks_future_renovation_and_never_parses_march(
        self,
    ) -> None:
        header = [f"@ATTRIBUTE {name} NUMERIC" for name in COLUMNS] + ["@DATA"]
        zero = source_line("1", "20150201T000000", "0")
        future = source_line("2", "20150202T000000", "2016")
        march = source_line("3", "20150301T000000", "SECRET")
        lines = header + [zero, future, march] + [march] * 21_610
        with patch.object(family, "read_source_snapshot", return_value=lines):
            rows = family.read_development_source(Path("ignored"))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].added_values, (0.0, 1200.0, 5000.0))
        self.assertFalse(rows[0].future_renovation_replaced)
        self.assertTrue(math.isnan(rows[1].added_values[0]))
        self.assertTrue(rows[1].future_renovation_replaced)

    def test_source_snapshot_rejects_oversized_and_symlink_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            oversized = root / "oversized.arff"
            oversized.write_bytes(b"12345")
            with (
                patch.object(family, "MAX_SOURCE_BYTES", 4),
                self.assertRaisesRegex(ValueError, "size limit"),
            ):
                family.read_source_snapshot(oversized)

            target = root / "target.arff"
            target.write_bytes(b"content")
            link = root / "link.arff"
            try:
                os.symlink(target, link)
            except OSError:
                self.skipTest("Symlink creation is unavailable")
            with self.assertRaisesRegex(ValueError, "reparse|symbolic link"):
                family.read_source_snapshot(link)

    def test_source_snapshot_rejects_reparse_attribute_before_read(self) -> None:
        metadata = SimpleNamespace(
            st_file_attributes=getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        )
        source = Mock()
        source.lstat.return_value = metadata
        reader = Mock()
        with (
            patch.object(family, "read_regular_snapshot", reader),
            self.assertRaisesRegex(ValueError, "reparse point"),
        ):
            family.read_source_snapshot(source)
        reader.assert_not_called()

    def test_source_snapshot_rejects_missing_changed_and_non_utf8_sources(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaisesRegex(ValueError, "could not be inspected"):
                family.read_source_snapshot(root / "missing.arff")
            changed = root / "changed.arff"
            changed.write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                family.read_source_snapshot(changed)
            invalid_utf8 = root / "invalid.arff"
            invalid_utf8.write_bytes(b"\xff")
            with (
                patch.object(
                    family,
                    "SOURCE_SHA256",
                    hashlib.sha256(invalid_utf8.read_bytes()).hexdigest(),
                ),
                self.assertRaisesRegex(ValueError, "not UTF-8"),
            ):
                family.read_source_snapshot(invalid_utf8)

    def test_development_reader_rejects_bad_added_features_and_row_count(self) -> None:
        header = [f"@ATTRIBUTE {name} NUMERIC" for name in COLUMNS] + ["@DATA"]
        invalid = source_line("1", "20150201T000000", "not-a-number")
        future = source_line("2", "20150301T000000")
        with (
            patch.object(
                family,
                "read_source_snapshot",
                return_value=header + [invalid] + [future] * 21_612,
            ),
            self.assertRaisesRegex(ValueError, "Added source feature is invalid"),
        ):
            family.read_development_source(Path("ignored"))
        with (
            patch.object(
                family, "read_source_snapshot", return_value=header + [future]
            ),
            self.assertRaisesRegex(ValueError, "row count"),
        ):
            family.read_development_source(Path("ignored"))

    def test_encoding_appends_exact_joint_family_without_changing_base_constants(
        self,
    ) -> None:
        train = sale("train", date(2014, 1, 1))
        valid = sale("valid", date(2014, 11, 1))
        base_numeric = tuple(NUMERIC_FEATURES)
        names, encoded_train, encoded_valid = family.encode_feature_family(
            (train,),
            (valid,),
            {"train": (0.0, 1200.0, 5000.0), "valid": (math.nan, 1300.0, 6000.0)},
        )
        self.assertEqual(names[-3:], family.ADDED_FEATURES)
        self.assertEqual(encoded_train[0][-3:], (0.0, 1200.0, 5000.0))
        self.assertTrue(math.isnan(encoded_valid[0][-3]))
        self.assertEqual(tuple(NUMERIC_FEATURES), base_numeric)
        self.assertEqual(family.configuration()["individual_variants"], [])
        with self.assertRaisesRegex(ValueError, "identity"):
            family.encode_feature_family((train,), (valid,), {"train": (0.0, 1.0, 2.0)})

    def test_incumbent_manifest_requires_exact_hash_and_metadata(self) -> None:
        payload = {
            "protocol": "king_log_absolute_error_development_screen_v1",
            "status": "complete",
            "source_sha256": family.SOURCE_SHA256,
            "frozen_rolling_split_sha256": family.FROZEN_SPLIT_SHA256,
            "prediction_artifact_sha256": family.INCUMBENT_PREDICTION_SHA256,
            "declared_lock_sha256": "e" * 64,
            "window_membership": {},
        }
        content = json.dumps(payload).encode()
        with (
            patch.object(family, "read_regular_snapshot", return_value=content),
            patch.object(
                family, "INCUMBENT_MANIFEST_SHA256", hashlib.sha256(content).hexdigest()
            ),
        ):
            self.assertEqual(family.load_incumbent_manifest(), payload)
        payload["status"] = "failed"
        content = json.dumps(payload).encode()
        with (
            patch.object(family, "read_regular_snapshot", return_value=content),
            patch.object(
                family, "INCUMBENT_MANIFEST_SHA256", hashlib.sha256(content).hexdigest()
            ),
            self.assertRaisesRegex(ValueError, "metadata"),
        ):
            family.load_incumbent_manifest()

    def test_incumbent_manifest_rejects_changed_bytes_and_non_object(self) -> None:
        with (
            patch.object(family, "read_regular_snapshot", return_value=b"{}"),
            self.assertRaisesRegex(ValueError, "manifest hash"),
        ):
            family.load_incumbent_manifest()
        content = b"[]"
        with (
            patch.object(family, "read_regular_snapshot", return_value=content),
            patch.object(
                family,
                "INCUMBENT_MANIFEST_SHA256",
                hashlib.sha256(content).hexdigest(),
            ),
            self.assertRaisesRegex(TypeError, "must be an object"),
        ):
            family.load_incumbent_manifest()

    def test_runtime_verifier_maps_incumbent_lock_identity(self) -> None:
        verifier = Mock(return_value={"python": "3.11.6"})
        with patch.object(family, "verify_runtime_versions", verifier):
            self.assertEqual(
                family.verify_incumbent_runtime({"declared_lock_sha256": "e" * 64}),
                {"python": "3.11.6"},
            )
        verifier.assert_called_once_with({"dependency_lock_sha256": "e" * 64})

    def test_incumbent_predictions_require_exact_schema_hash_and_membership(
        self,
    ) -> None:
        valid = sale("valid", date(2014, 11, 1), "125000")
        windows = (("2014-11", (sale("train", date(2014, 1, 1)),), (valid,)),)
        payload = (
            "row_id,sale_date,window,actual_usd,xgboost_usd,xgboost_log_absolute_error_usd\n"
            "valid,2014-11-01,2014-11,125000,123000,124000\n"
        ).encode()
        digest = hashlib.sha256(payload).hexdigest()
        manifest = {"outputs": {"predictions.csv": digest}}
        with (
            patch.object(family, "read_regular_snapshot", return_value=payload),
            patch.object(family, "INCUMBENT_PREDICTION_SHA256", digest),
        ):
            self.assertEqual(
                family.read_incumbent_predictions(Path("ignored"), manifest, windows),
                {"2014-11": (124000.0,)},
            )
        tampered = payload.replace(b"valid,", b"other,")
        tampered_digest = hashlib.sha256(tampered).hexdigest()
        with (
            patch.object(family, "read_regular_snapshot", return_value=tampered),
            patch.object(family, "INCUMBENT_PREDICTION_SHA256", tampered_digest),
            self.assertRaisesRegex(ValueError, "membership"),
        ):
            family.read_incumbent_predictions(
                Path("ignored"),
                {"outputs": {"predictions.csv": tampered_digest}},
                windows,
            )

    def test_incumbent_predictions_reject_schema_count_and_invalid_value(self) -> None:
        valid = sale("valid", date(2014, 11, 1), "125000")
        windows = (("2014-11", (), (valid,)),)

        def assert_rejected(payload: bytes, message: str) -> None:
            digest = hashlib.sha256(payload).hexdigest()
            with (
                patch.object(family, "read_regular_snapshot", return_value=payload),
                patch.object(family, "INCUMBENT_PREDICTION_SHA256", digest),
                self.assertRaisesRegex(ValueError, message),
            ):
                family.read_incumbent_predictions(
                    Path("ignored"),
                    {"outputs": {"predictions.csv": digest}},
                    windows,
                )

        assert_rejected(b"wrong,columns\n", "schema")
        assert_rejected(
            (",".join(family.INCUMBENT_COLUMNS) + "\n").encode(), "membership"
        )
        assert_rejected(
            (
                ",".join(family.INCUMBENT_COLUMNS)
                + "\nvalid,2014-11-01,2014-11,125000,123000,nan\n"
            ).encode(),
            "invalid",
        )

    def test_selection_rule_boundaries(self) -> None:
        incumbent = SimpleNamespace(
            mdape=Decimal("0.10"), within_10=Decimal("0.50"), p90_ape=Decimal("0.30")
        )
        passing = SimpleNamespace(
            mdape=Decimal("0.098"), within_10=Decimal("0.495"), p90_ape=Decimal("0.305")
        )
        self.assertEqual(
            family.select_candidate(incumbent, passing, 3),
            "xgboost_log_absolute_error_plus_source_family",
        )
        self.assertEqual(
            family.select_candidate(incumbent, passing, 2), "xgboost_log_absolute_error"
        )
        for failing in (
            SimpleNamespace(
                mdape=Decimal("0.0980001"),
                within_10=Decimal("0.495"),
                p90_ape=Decimal("0.305"),
            ),
            SimpleNamespace(
                mdape=Decimal("0.098"),
                within_10=Decimal("0.4949"),
                p90_ape=Decimal("0.305"),
            ),
            SimpleNamespace(
                mdape=Decimal("0.098"),
                within_10=Decimal("0.495"),
                p90_ape=Decimal("0.3051"),
            ),
        ):
            with self.subTest(failing=failing):
                self.assertEqual(
                    family.select_candidate(incumbent, failing, 3),
                    "xgboost_log_absolute_error",
                )
        with self.assertRaisesRegex(ValueError, "between zero and four"):
            family.select_candidate(incumbent, passing, 5)

    def test_runner_uses_four_fits_frozen_membership_and_atomic_outputs(self) -> None:
        sales = tuple(
            sale(str(index), when, str(100000 + index * 1000))
            for index, when in enumerate(
                (
                    date(2014, 10, 1),
                    date(2014, 11, 15),
                    date(2014, 12, 15),
                    date(2015, 1, 15),
                    date(2015, 2, 15),
                )
            )
        )
        source_rows = tuple(
            family.SourceFeatureRow(item, (0.0, 1000.0, 5000.0), False)
            for item in sales
        )
        windows = family.monthly_windows(sales)
        membership = family.membership_for(windows)
        manifest = {"window_membership": membership, "declared_lock_sha256": "e" * 64}
        incumbents = {
            name: tuple(float(item.price) * 1.02 for item in valid)
            for name, _, valid in windows
        }
        calls: list[str] = []

        class Model:
            def save_model(self, path: Path) -> None:
                path.write_text("model", encoding="utf-8")

        def fit(training: object, validation: object, values: object):
            del training, values
            calls.append(family.WINDOWS[len(calls)][0])
            return tuple(float(item.price) for item in validation), Model()

        with tempfile.TemporaryDirectory() as temporary:
            private = Path(temporary) / "private"
            private.mkdir()
            output = private / "run"
            with (
                patch.object(family, "PRIVATE_ROOT", private),
                patch.object(family, "_committed_code", return_value="a" * 40),
                patch.object(family, "real_directory"),
                patch.object(family, "secure_directory"),
                patch.object(family, "verify_acl"),
                patch.object(family, "load_incumbent_manifest", return_value=manifest),
                patch.object(
                    family, "verify_incumbent_runtime", return_value={"python": "test"}
                ),
                patch.object(
                    family, "read_development_source", return_value=source_rows
                ),
                patch.object(family, "select_eligible_sales", return_value=(sales, {})),
                patch.object(
                    family, "membership_sha256", return_value=family.FROZEN_SPLIT_SHA256
                ),
                patch.object(
                    family, "read_incumbent_predictions", return_value=incumbents
                ),
                patch.object(family, "fit_feature_family", side_effect=fit),
            ):
                result = family.run(Path("source"), Path("incumbent"), output)
            self.assertEqual(calls, [name for name, _, _ in family.WINDOWS])
            self.assertEqual(result["fit_count"], 4)
            self.assertEqual(result["march_may_labels_parsed"], 0)
            self.assertFalse(result["promotion_eligible"])
            saved_manifest = json.loads((output / "manifest.json").read_text())
            self.assertEqual(
                saved_manifest["added_features"], list(family.ADDED_FEATURES)
            )
            self.assertEqual(len(saved_manifest["challenger_checkpoint_identities"]), 4)

    def test_fit_failure_leaves_no_complete_output(self) -> None:
        sales = tuple(
            sale(str(i), when)
            for i, when in enumerate(
                (
                    date(2014, 10, 1),
                    date(2014, 11, 15),
                    date(2014, 12, 15),
                    date(2015, 1, 15),
                    date(2015, 2, 15),
                )
            )
        )
        source_rows = tuple(
            family.SourceFeatureRow(item, (0.0, 1.0, 2.0), False) for item in sales
        )
        windows = family.monthly_windows(sales)
        membership = family.membership_for(windows)
        with tempfile.TemporaryDirectory() as temporary:
            private = Path(temporary) / "private"
            private.mkdir()
            output = private / "failed"
            with (
                patch.object(family, "PRIVATE_ROOT", private),
                patch.object(family, "_committed_code", return_value="a" * 40),
                patch.object(family, "real_directory"),
                patch.object(family, "secure_directory"),
                patch.object(family, "verify_acl"),
                patch.object(
                    family,
                    "load_incumbent_manifest",
                    return_value={"window_membership": membership},
                ),
                patch.object(family, "verify_incumbent_runtime", return_value={}),
                patch.object(
                    family, "read_development_source", return_value=source_rows
                ),
                patch.object(family, "select_eligible_sales", return_value=(sales, {})),
                patch.object(
                    family, "membership_sha256", return_value=family.FROZEN_SPLIT_SHA256
                ),
                patch.object(
                    family,
                    "read_incumbent_predictions",
                    return_value={
                        name: tuple(100000.0 for _ in valid)
                        for name, _, valid in windows
                    },
                ),
                patch.object(
                    family, "fit_feature_family", side_effect=RuntimeError("fit failed")
                ),
                self.assertRaisesRegex(RuntimeError, "fit failed"),
            ):
                family.run(Path("source"), Path("incumbent"), output)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
