"""Isolated-environment integration checks for the historical Ames prototype."""

from __future__ import annotations

import csv
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import numpy as np
import pandas as pd

from scripts.ames_dev_prototype import (
    _components,
    allowed_feature_names,
    MANUAL12_FEATURES,
    MANUAL12_PROTOCOL,
    predict,
    run_experiment,
)
from scripts.replay_legacy_ames_dev import (
    _load_development,
    load_frozen_holdout,
    HOLDOUT_SHA256,
)

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data/raw/openml/house_prices-42165.arff"
HOLDOUT = ROOT / "data/legacy/holdout_ids.csv"
REQUEST = json.loads(
    (ROOT / "examples/ames-prototype-request.json").read_text(encoding="utf-8")
)
MANUAL_REQUEST = json.loads(
    (ROOT / "examples/ames-manual12-request.json").read_text(encoding="utf-8")
)


class AmesPrototypeFlowTests(unittest.TestCase):
    def test_example_is_physically_consistent(self) -> None:
        self.assertEqual(
            REQUEST["GrLivArea"],
            REQUEST["1stFlrSF"] + REQUEST["2ndFlrSF"] + REQUEST["LowQualFinSF"],
        )
        self.assertEqual(
            REQUEST["TotalBsmtSF"],
            REQUEST["BsmtFinSF1"] + REQUEST["BsmtFinSF2"] + REQUEST["BsmtUnfSF"],
        )
        self.assertFalse(REQUEST["PoolArea"] == 0 and REQUEST["PoolQC"] is not None)
        self.assertFalse(REQUEST["BsmtFinType1"] == "Unf" and REQUEST["BsmtFinSF1"] > 0)

    @classmethod
    def setUpClass(cls) -> None:
        private_root = ROOT / "data/raw/ames-prototype"
        private_root.mkdir(parents=True, exist_ok=True)
        cls.temporary = tempfile.TemporaryDirectory(dir=private_root)
        cls.output = Path(cls.temporary.name) / "prototype"
        run_experiment(SOURCE, HOLDOUT, cls.output)
        cls.manual_output = Path(cls.temporary.name) / "manual12"
        run_experiment(SOURCE, HOLDOUT, cls.manual_output, profile="manual12")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def test_fold_preprocessing_never_fits_validation_values(self) -> None:
        features = pd.DataFrame(
            {"Area": [1.0, np.nan, 99999.0], "Neighborhood": ["A", "A", "B"]}
        )
        pipeline, _, _ = _components(features, "median")
        pipeline.fit(features.iloc[:2], [100, 200])
        transform = pipeline.named_steps["preprocess"]
        self.assertEqual(transform.named_transformers_["num"].statistics_[0], 1.0)
        categories = (
            transform.named_transformers_["cat"].named_steps["encode"].categories_[0]
        )
        self.assertEqual(tuple(categories), ("A",))
        self.assertEqual(len(pipeline.predict(features.iloc[2:])), 1)

    def test_oof_coverage_and_holdout_isolation(self) -> None:
        manifest = json.loads(
            (self.output / "manifest.json").read_text(encoding="utf-8")
        )
        scorecards = json.loads(
            (self.output / "scorecards.json").read_text(encoding="utf-8")
        )
        with (self.output / "predictions.csv").open(
            encoding="utf-8", newline=""
        ) as stream:
            records = list(csv.DictReader(stream))
        reserved = set(
            load_frozen_holdout(
                HOLDOUT,
                expected_sha256=HOLDOUT_SHA256,
                expected_count=292,
                source_count=1460,
            )
        )
        self.assertEqual(manifest["reserved_rows_unparsed"], 292)
        self.assertEqual(manifest["development_rows"], 1168)
        self.assertEqual(len(records), 2336)
        for model in ("median", "xgboost"):
            subset = [record for record in records if record["model"] == model]
            indices = [int(record["source_row_index"]) for record in subset]
            self.assertEqual(len(indices), len(set(indices)))
            self.assertEqual(len(indices), 1168)
            self.assertFalse(set(indices) & reserved)
            self.assertEqual(scorecards[model]["eligible_count"], 1168)
            self.assertEqual(scorecards[model]["success_count"], 1168)

    def test_manual12_uses_same_folds_and_no_reserved_rows(self) -> None:
        old = json.loads(
            (ROOT / "runs/ames-dev-prototype-20261004-v1/manifest.json").read_text(
                encoding="utf-8"
            )
        )
        manual = json.loads(
            (self.manual_output / "manifest.json").read_text(encoding="utf-8")
        )
        policy = json.loads(
            (self.manual_output / "feature_policy.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manual["split_sha256"], old["split_sha256"])
        self.assertEqual(manual["profile"], "manual12")
        self.assertEqual(tuple(policy["included"]), MANUAL12_FEATURES)
        reserved = set(
            load_frozen_holdout(
                HOLDOUT,
                expected_sha256=HOLDOUT_SHA256,
                expected_count=292,
                source_count=1460,
            )
        )
        with (self.manual_output / "predictions.csv").open(encoding="utf-8") as stream:
            records = list(csv.DictReader(stream))
        for model in ("median", "xgboost"):
            indices = [
                int(row["source_row_index"]) for row in records if row["model"] == model
            ]
            self.assertEqual(len(indices), 1168)
            self.assertEqual(len(indices), len(set(indices)))
            self.assertFalse(set(indices) & reserved)

    def test_manual12_cli_and_bundle_match_training_pipeline(self) -> None:
        bundle_path = self.manual_output / "bundle.json"
        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
        digest = hashlib.sha256(bundle_path.read_bytes()).hexdigest()
        direct = predict(self.manual_output, MANUAL_REQUEST, digest)
        self.assertEqual(direct["protocol"], MANUAL12_PROTOCOL)
        self.assertEqual(tuple(MANUAL_REQUEST), MANUAL12_FEATURES)
        data = _load_development(SOURCE, HOLDOUT)
        features = data.features.loc[:, list(MANUAL12_FEATURES)]
        pipeline, _, _ = _components(features, bundle["model"])
        pipeline.fit(features, data.labels)
        expected = float(pipeline.predict(pd.DataFrame([MANUAL_REQUEST]))[0])
        self.assertAlmostEqual(direct["amount"], expected, delta=0.001)
        full_digest = hashlib.sha256(
            (self.output / "bundle.json").read_bytes()
        ).hexdigest()
        with self.assertRaisesRegex(ValueError, "exactly"):
            predict(self.output, MANUAL_REQUEST, full_digest)
        with self.assertRaisesRegex(ValueError, "exactly"):
            predict(self.manual_output, REQUEST, digest)
        with self.assertRaisesRegex(ValueError, "changed"):
            predict(self.manual_output, MANUAL_REQUEST, "0" * 64)
        environment = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
        process = subprocess.run(
            [
                sys.executable,
                "-m",
                "scripts.ames_dev_prototype",
                "predict",
                "--bundle",
                str(self.manual_output),
                "--request",
                str(ROOT / "examples/ames-manual12-request.json"),
                "--bundle-sha256",
                digest,
            ],
            cwd=ROOT,
            env=environment,
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertEqual(json.loads(process.stdout), direct)

    def test_cli_matches_direct_prediction_and_rejects_wrong_digest(self) -> None:
        bundle = json.loads((self.output / "bundle.json").read_text(encoding="utf-8"))
        bundle_hash = hashlib.sha256(
            (self.output / "bundle.json").read_bytes()
        ).hexdigest()
        direct = predict(self.output, REQUEST, bundle_hash)
        data = _load_development(SOURCE, HOLDOUT)
        names = allowed_feature_names(tuple(data.features.columns))
        features = data.features.loc[:, list(names)]
        pipeline, _, _ = _components(features, bundle["model"])
        pipeline.fit(features, data.labels)
        self.assertFalse(features.eq(pd.Series(REQUEST)).all(axis=1).any())
        in_memory = float(
            pipeline.predict(pd.DataFrame([REQUEST]).loc[:, list(names)])[0]
        )
        self.assertAlmostEqual(in_memory, direct["amount"], delta=0.001)
        for position in range(1, 6):
            raw_row = features.iloc[position]
            row_request = {
                name: (
                    None
                    if pd.isna(value)
                    else value.item()
                    if hasattr(value, "item")
                    else value
                )
                for name, value in raw_row.items()
            }
            expected = float(pipeline.predict(features.iloc[[position]])[0])
            observed = predict(self.output, row_request, bundle_hash)["amount"]
            self.assertAlmostEqual(expected, observed, delta=0.001)
        request_file = Path(self.temporary.name) / "request.json"
        request_file.write_text(json.dumps(REQUEST), encoding="utf-8")
        environment = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
        command = [
            sys.executable,
            "-m",
            "scripts.ames_dev_prototype",
            "predict",
            "--bundle",
            str(self.output),
            "--request",
            str(request_file),
            "--bundle-sha256",
            bundle_hash,
        ]
        process = subprocess.run(
            command,
            cwd=ROOT,
            env=environment,
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertEqual(json.loads(process.stdout), direct)
        self.assertGreater(direct["amount"], 0)
        with self.assertRaisesRegex(ValueError, "changed"):
            predict(self.output, REQUEST, "0" * 64)
        unseen_request = {**REQUEST, "Neighborhood": "UnknownPlace"}
        unseen_result = predict(self.output, unseen_request, bundle_hash)
        unseen_frame = pd.DataFrame([REQUEST]).loc[:, list(names)]
        unseen_frame["Neighborhood"] = "UnknownPlace"
        expected_unseen = float(pipeline.predict(unseen_frame)[0])
        self.assertAlmostEqual(expected_unseen, unseen_result["amount"], delta=0.001)
        self.assertEqual(unseen_result["support_status"], "unseen_category")
        self.assertIn("Neighborhood", unseen_result["unseen_category_features"])


if __name__ == "__main__":
    unittest.main()
