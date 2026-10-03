"""Synthetic OFF median bundle canaries; no source or reserved labels are used."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tabpfn4realestate.data.schema import Property, SourceSnapshot  # noqa: E402
from tabpfn4realestate.models.bundle import (  # noqa: E402
    load_off_median_bundle,
    save_off_median_bundle,
)
from tabpfn4realestate.models.off_baseline import (  # noqa: E402
    GuardedOffMedian,
    ServingOffMedian,
)


CUTOFF = datetime(2024, 1, 1, 12, tzinfo=timezone(timedelta(hours=5, minutes=30)))
ORIGIN = datetime(2024, 3, 1, 12, tzinfo=timezone.utc)


def synthetic_model() -> GuardedOffMedian:
    return GuardedOffMedian(
        amount=Decimal("123456.789"),
        train_row_ids=("transfer-01", "transfer-02"),
        feature_snapshot_hashes=("a" * 64, "b" * 64),
        training_cutoff=CUTOFF,
    )


def synthetic_prediction(model: GuardedOffMedian):
    subject = Property(
        property_id="synthetic-home",
        country="US",
        property_type="single_family",
        source_id="synthetic-assessor",
        observed_at=datetime(2023, 6, 1, tzinfo=timezone.utc),
        available_at=datetime(2023, 6, 2, tzinfo=timezone.utc),
        living_area=Decimal("1500"),
        living_area_unit="sqft",
    )
    source = SourceSnapshot(
        snapshot_id="synthetic-snapshot",
        source_ids=("synthetic-assessor",),
        as_of=ORIGIN,
    )
    return model.predict(subject, ORIGIN, source)


class OffMedianBundleTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "median.json"

    def saved_payload(self):
        digest = save_off_median_bundle(synthetic_model(), self.path)
        return json.loads(self.path.read_text(encoding="utf-8")), digest

    def replace_payload(self, payload):
        encoded = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        self.path.write_bytes(encoded)
        return sha256(encoded).hexdigest()

    def test_round_trip_preserves_model_manifest_cutoff_and_prediction(self):
        model = synthetic_model()
        digest = save_off_median_bundle(model, self.path)
        loaded = load_off_median_bundle(self.path, expected_sha256=digest)

        self.assertIsInstance(loaded, ServingOffMedian)
        self.assertEqual(loaded.amount, model.amount)
        self.assertEqual(loaded.train_count, len(model.train_row_ids))
        self.assertRegex(loaded.feature_snapshot_hashes_sha256, r"^[0-9a-f]{64}$")
        self.assertEqual(loaded.training_cutoff.isoformat(), CUTOFF.isoformat())
        self.assertEqual(loaded.training_cutoff.utcoffset(), CUTOFF.utcoffset())
        expected = synthetic_prediction(model)
        actual = synthetic_prediction(loaded)
        self.assertEqual(actual.amount, expected.amount)
        self.assertEqual(actual.snapshot.snapshot_hash, expected.snapshot.snapshot_hash)
        self.assertEqual(
            actual.snapshot.snapshot_hash,
            "e45e16198d1773e7aa78b163ec888cdb6a89d49cd0be60aa7e11ec501e6b90b7",
        )
        self.assertEqual(actual.snapshot.mode, "OFF")

    def test_bundle_is_deterministic_and_digest_covers_exact_bytes(self):
        first = save_off_median_bundle(synthetic_model(), self.path)
        other_path = Path(self.directory.name) / "second.json"
        second = save_off_median_bundle(synthetic_model(), other_path)
        self.assertEqual(first, second)
        self.assertEqual(self.path.read_bytes(), other_path.read_bytes())
        self.assertEqual(first, sha256(self.path.read_bytes()).hexdigest())
        self.assertRegex(first, r"^[0-9a-f]{64}$")

    def test_bundle_declares_narrow_uncertified_off_us_contract(self):
        payload, _ = self.saved_payload()
        self.assertEqual(payload["format_version"], "synthetic_off_median_v2")
        self.assertEqual(payload["model_kind"], "guarded_off_median")
        self.assertEqual(payload["mode"], "OFF")
        self.assertEqual(payload["country"], "US")
        self.assertEqual(payload["currency"], "USD")
        self.assertEqual(payload["horizon_days"], 90)
        self.assertEqual(payload["point_semantics"], "historical_median")
        self.assertIs(payload["certification_eligible"], False)
        for name in ("feature_schema_sha256", "input_schema_sha256"):
            self.assertRegex(payload[name], r"^[0-9a-f]{64}$")
        self.assertEqual(payload["model"]["amount"], "123456.789")
        self.assertEqual(payload["model"]["train_count"], 2)

    def test_bundle_omits_raw_training_row_identifiers(self):
        self.saved_payload()
        encoded = self.path.read_bytes()
        self.assertNotIn(b"transfer-01", encoded)
        self.assertNotIn(b"transfer-02", encoded)
        self.assertNotIn(b"a" * 64, encoded)
        self.assertNotIn(b"b" * 64, encoded)

    def test_modified_bytes_fail_digest_check_even_if_json_remains_valid(self):
        _, digest = self.saved_payload()
        self.path.write_bytes(self.path.read_bytes() + b"\n")
        with self.assertRaisesRegex(ValueError, "(?i)(hash|digest|sha256)"):
            load_off_median_bundle(self.path, expected_sha256=digest)

    def test_rehashed_incompatible_envelope_is_rejected(self):
        original, _ = self.saved_payload()
        incompatible = (
            ("format_version", "synthetic_off_median_v1"),
            ("model_kind", "unknown_model"),
            ("mode", "ON"),
            ("country", "FR"),
            ("currency", "EUR"),
            ("horizon_days", 30),
            ("point_semantics", "mean"),
            ("feature_schema_sha256", "0" * 64),
            ("input_schema_sha256", "0" * 64),
            ("certification_eligible", True),
        )
        for field, value in incompatible:
            with self.subTest(field=field):
                digest = self.replace_payload(original | {field: value})
                with self.assertRaises(ValueError):
                    load_off_median_bundle(self.path, expected_sha256=digest)

    def test_changed_feature_assembler_policy_rejects_existing_bundle(self):
        _, digest = self.saved_payload()
        with patch(
            "tabpfn4realestate.models.bundle.ASSEMBLER_POLICY_VERSION",
            "synthetic_off_asof_v2",
        ):
            with self.assertRaisesRegex(ValueError, "feature_schema_sha256"):
                load_off_median_bundle(self.path, expected_sha256=digest)

    def test_rehashed_malformed_model_fields_are_rejected(self):
        original, _ = self.saved_payload()
        model = original["model"]
        malformed = (
            {"amount": "0"},
            {"amount": "NaN"},
            {"amount": "not-a-price"},
            {"train_count": 0},
            {"train_count": True},
            {"feature_snapshot_hashes_sha256": "not-a-hash"},
            {"feature_snapshot_hashes_sha256": "0" * 63},
            {"training_cutoff": "2024-01-01T12:00:00"},
            {"training_cutoff": "not-a-date"},
        )
        for change in malformed:
            with self.subTest(change=change):
                digest = self.replace_payload(original | {"model": model | change})
                with self.assertRaises(ValueError):
                    load_off_median_bundle(self.path, expected_sha256=digest)

    def test_missing_and_extra_fields_are_rejected(self):
        original, _ = self.saved_payload()
        for payload in (
            {key: value for key, value in original.items() if key != "mode"},
            original | {"unexpected": "value"},
            original
            | {
                "model": {
                    key: value
                    for key, value in original["model"].items()
                    if key != "amount"
                }
            },
            original | {"model": original["model"] | {"prediction": "999999"}},
        ):
            with self.subTest(payload=payload):
                digest = self.replace_payload(payload)
                with self.assertRaises(ValueError):
                    load_off_median_bundle(self.path, expected_sha256=digest)

    def test_non_json_and_non_object_payloads_are_rejected(self):
        for encoded in (b"not JSON", b"[]", b"null", b"\xff"):
            with self.subTest(encoded=encoded):
                self.path.write_bytes(encoded)
                with self.assertRaises(ValueError):
                    load_off_median_bundle(
                        self.path, expected_sha256=sha256(encoded).hexdigest()
                    )

    def test_existing_bundle_is_not_overwritten(self):
        first_digest = save_off_median_bundle(synthetic_model(), self.path)
        before = self.path.read_bytes()
        with self.assertRaises(FileExistsError):
            save_off_median_bundle(synthetic_model(), self.path)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(first_digest, sha256(before).hexdigest())
        self.assertEqual(
            sorted(path.name for path in Path(self.directory.name).iterdir()),
            ["median.json"],
        )

    def test_huge_finite_decimal_is_rejected_before_fixed_point_expansion(self):
        model = GuardedOffMedian(
            amount=Decimal("1E+1100000"),
            train_row_ids=("synthetic-transfer",),
            feature_snapshot_hashes=("a" * 64,),
            training_cutoff=CUTOFF,
        )
        with patch(
            "tabpfn4realestate.models.bundle.format",
            side_effect=AssertionError("fixed-point expansion happened"),
            create=True,
        ):
            with self.assertRaisesRegex(ValueError, "size limit"):
                save_off_median_bundle(model, self.path)
        self.assertFalse(self.path.exists())

    def test_model_exposes_the_same_save_load_contract(self):
        model = synthetic_model()
        digest = model.save(self.path)
        loaded = GuardedOffMedian.load(self.path, expected_sha256=digest)
        self.assertIsInstance(loaded, ServingOffMedian)
        self.assertEqual(synthetic_prediction(loaded), synthetic_prediction(model))

    def test_failed_atomic_publish_leaves_no_bundle_or_temporary_file(self):
        with patch(
            "tabpfn4realestate.models.bundle.os.link", side_effect=OSError("disk error")
        ):
            with self.assertRaisesRegex(OSError, "disk error"):
                save_off_median_bundle(synthetic_model(), self.path)
        self.assertEqual(list(Path(self.directory.name).iterdir()), [])

    def test_duplicate_json_key_is_rejected_even_with_matching_digest(self):
        payload, _ = self.saved_payload()
        encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        tampered = encoded.replace(b'"mode":"OFF"', b'"mode":"ON","mode":"OFF"')
        self.assertNotEqual(tampered, encoded)
        self.path.write_bytes(tampered)
        with self.assertRaises(ValueError):
            load_off_median_bundle(
                self.path, expected_sha256=sha256(tampered).hexdigest()
            )


if __name__ == "__main__":
    unittest.main()
