"""A synthetic training capture must supply the rows and the digest used by fit."""

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tabpfn4realestate.evaluation.calendar_schedule import (  # noqa: E402
    CalendarOriginRef,
    build_calendar_schedule,
)
from tabpfn4realestate.evaluation.chronological_plan import (  # noqa: E402
    ChronologicalMaturityRef,
    build_chronological_plan,
    origin_policy_hash,
)
from tabpfn4realestate.evaluation.local_dates import DateOnlyAvailability  # noqa: E402
from tabpfn4realestate.models.local_date_artifact import (  # noqa: E402
    fit_synthetic_calendar_capture,
    verify_synthetic_calendar_capture,
)


UTC = timezone.utc
ZONE = "America/New_York"
FIT_CUTOFFS = tuple(
    datetime(year, month, 1, tzinfo=UTC)
    for year, month in ((2023, 1), (2023, 4), (2023, 7), (2023, 10), (2024, 1))
)
ORIGINS = tuple(
    CalendarOriginRef(name, f"property-{name}", day)
    for name, day in (
        ("history", date(2021, 1, 1)),
        ("q1", date(2023, 1, 1)),
        ("q2", date(2023, 4, 1)),
        ("q3", date(2023, 7, 1)),
        ("q4", date(2023, 10, 1)),
        ("calibration", date(2024, 1, 1)),
        ("test", date(2024, 4, 1)),
    )
)
ZONES = {row.row_id: ZONE for row in ORIGINS}


def raw_row(origin: CalendarOriginRef, price: str = "100000") -> dict[str, str]:
    close = origin.origin_date + timedelta(days=90)
    return {
        "protocol": "synthetic_calendar_capture_v1",
        "row_id": origin.row_id,
        "property_id": origin.property_id,
        "transaction_id": f"deed-{origin.row_id}",
        "source_id": "synthetic-county",
        "snapshot_id": f"snapshot-{origin.row_id}",
        "close_date": close.isoformat(),
        "close_zone": ZONE,
        "published_on": close.isoformat(),
        "price_usd": price,
        "property_observed_at_utc": "2020-01-01T00:00:00Z",
        "property_published_on": "2020-01-02",
        "living_area_sqft": "1500",
    }


def capture_bytes(rows: list[dict[str, str]]) -> bytes:
    return b"".join(
        (json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n").encode()
        for row in rows
    )


def frozen_plan(body: bytes):
    schedule = build_calendar_schedule(
        ORIGINS,
        history_start=date(2021, 1, 1),
        calibration_start=date(2024, 1, 1),
        test_start=date(2024, 4, 1),
        source_snapshot_sha256=sha256(body).hexdigest(),
        origin_policy_sha256=origin_policy_hash(ORIGINS, ZONES),
    )
    maturity = tuple(
        ChronologicalMaturityRef(
            row.row_id,
            row.origin_date + timedelta(days=90),
            DateOnlyAvailability(row.origin_date + timedelta(days=90), ZONE),
        )
        for row in ORIGINS[:5]
    )
    plan = build_chronological_plan(
        schedule, ORIGINS, ZONES, maturity, fit_cutoffs_utc=FIT_CUTOFFS
    )
    return plan, maturity


class SyntheticCaptureFitTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "training.jsonl"
        self.rows = [raw_row(row) for row in ORIGINS[:5]]
        self.body = capture_bytes(self.rows)
        self.path.write_bytes(self.body)
        self.plan, self.maturity = frozen_plan(self.body)

    def fit(self):
        return fit_synthetic_calendar_capture(
            self.path, self.plan, ORIGINS, ZONES, self.maturity
        )

    def test_exact_bytes_replay_and_distinct_provenance(self):
        first = self.fit()
        second = self.fit()
        self.assertEqual(first, second)
        self.assertEqual(first.amount, 100000)
        self.assertEqual(first.source_snapshot_sha256, sha256(self.body).hexdigest())
        self.assertEqual(first.source_binding_kind, "synthetic_capture_bytes_v1")
        self.assertEqual(first.train_row_ids, self.plan.final_fit.train_row_ids)

    def test_independent_replay_rejects_model_or_capture_drift(self):
        model = self.fit()
        verify_synthetic_calendar_capture(
            self.path, model, self.plan, ORIGINS, ZONES, self.maturity
        )
        with self.assertRaisesRegex(ValueError, "replay"):
            verify_synthetic_calendar_capture(
                self.path,
                replace(model, amount=model.amount + 1),
                self.plan,
                ORIGINS,
                ZONES,
                self.maturity,
            )
        altered = [dict(row) for row in self.rows]
        altered[0]["price_usd"] = "999999"
        self.path.write_bytes(capture_bytes(altered))
        with self.assertRaisesRegex(ValueError, "digest"):
            verify_synthetic_calendar_capture(
                self.path, model, self.plan, ORIGINS, ZONES, self.maturity
            )

    def test_modified_price_or_row_order_rejected_against_frozen_schedule(self):
        changed = [dict(row) for row in self.rows]
        changed[0]["price_usd"] = "999999"
        for body in (capture_bytes(changed), capture_bytes(list(reversed(self.rows)))):
            with self.subTest(body=sha256(body).hexdigest()):
                self.path.write_bytes(body)
                with self.assertRaisesRegex(ValueError, "digest"):
                    self.fit()

    def test_missing_extra_or_reserved_row_rejected_even_with_new_digest(self):
        for rows in (
            self.rows[:-1],
            [*self.rows, dict(self.rows[0])],
            [*self.rows, raw_row(ORIGINS[5], "999999")],
        ):
            with self.subTest(count=len(rows)):
                body = capture_bytes(rows)
                self.path.write_bytes(body)
                plan, maturity = frozen_plan(body)
                with self.assertRaises(ValueError):
                    fit_synthetic_calendar_capture(
                        self.path, plan, ORIGINS, ZONES, maturity
                    )

    def test_source_snapshot_and_publication_fields_are_checked(self):
        changes = (
            {"source_id": "real-county"},
            {"snapshot_id": ""},
            {"property_published_on": "2022-01-01"},
            {"published_on": "2020-01-01"},
            {"price_usd": "0"},
            {"close_zone": "UTC"},
        )
        for change in changes:
            with self.subTest(change=change):
                rows = [dict(row) for row in self.rows]
                rows[0].update(change)
                body = capture_bytes(rows)
                self.path.write_bytes(body)
                plan, maturity = frozen_plan(body)
                with self.assertRaises(ValueError):
                    fit_synthetic_calendar_capture(
                        self.path, plan, ORIGINS, ZONES, maturity
                    )

    def test_schema_duplicate_keys_and_truncation_fail(self):
        variants = (
            self.body.replace(b'"price_usd":"100000"', b'"price_usd":100000', 1),
            self.body.replace(
                b'"price_usd":"100000"',
                b'"price_usd":"100000","price_usd":"999999"',
                1,
            ),
            self.body[:-1],
        )
        for body in variants:
            with self.subTest(body=sha256(body).hexdigest()):
                self.path.write_bytes(body)
                plan, maturity = frozen_plan(body)
                with self.assertRaises(ValueError):
                    fit_synthetic_calendar_capture(
                        self.path, plan, ORIGINS, ZONES, maturity
                    )

    def test_symlink_and_oversize_capture_fail_before_fit(self):
        linked = self.path.with_name("linked.jsonl")
        try:
            linked.symlink_to(self.path)
        except (OSError, NotImplementedError):
            pass
        else:
            with self.assertRaises(ValueError):
                fit_synthetic_calendar_capture(
                    linked, self.plan, ORIGINS, ZONES, self.maturity
                )
        self.path.write_bytes(b"x" * 1_000_001)
        with self.assertRaises(ValueError):
            self.fit()


if __name__ == "__main__":
    unittest.main()
