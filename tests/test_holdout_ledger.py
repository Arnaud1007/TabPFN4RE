"""Synthetic T12 checks: one durable opening per reserved cohort."""

from dataclasses import replace
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path
import sqlite3
import sys
from tempfile import TemporaryDirectory
from threading import Barrier
import unittest
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tabpfn4realestate.evaluation.holdout_ledger import (  # noqa: E402
    FrozenEstimate,
    HoldoutIdentity,
    evaluate_once,
    replay_scorecard,
)


IDENTITY = HoldoutIdentity(
    protocol_id="us_synthetic_holdout_v1",
    split_hash="a" * 64,
    source_snapshot_hash="b" * 64,
    model_bundle_hash="c" * 64,
    row_ids=("sale-1", "sale-2"),
)
PREDICTIONS = (
    FrozenEstimate("sale-1", "estimated", Decimal("110"), "USD"),
    FrozenEstimate("sale-2", "abstained", None, None, "low_support"),
)
LABELS = {"sale-1": Decimal("100"), "sale-2": Decimal("200")}


class HoldoutLedgerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.ledger = Path(self.temporary.name) / "holdout.sqlite3"

    def test_intent_and_predictions_are_committed_before_label_loader(self):
        def load_labels():
            with closing(sqlite3.connect(self.ledger)) as connection:
                status, payload, digest = connection.execute(
                    "SELECT status, predictions_json, predictions_sha256 FROM attempts"
                ).fetchone()
            self.assertEqual(status, "opening_intent")
            self.assertIn("sale-1", payload)
            self.assertEqual(len(digest), 64)
            return LABELS

        result = evaluate_once(self.ledger, IDENTITY, PREDICTIONS, load_labels)
        self.assertEqual(result.eligible_count, 2)
        self.assertEqual(result.success_count, 1)
        self.assertEqual(result.abstained_count, 1)
        self.assertEqual(result.mdape, Decimal("0.1"))
        self.assertEqual(replay_scorecard(self.ledger, IDENTITY), result)

    def test_crash_after_intent_consumes_test_without_reading_labels(self):
        from tabpfn4realestate.evaluation import holdout_ledger

        original = holdout_ledger._persist_intent

        def crash_after_commit(*args, **kwargs):
            original(*args, **kwargs)
            raise RuntimeError("synthetic process crash")

        calls = []
        with patch.object(holdout_ledger, "_persist_intent", crash_after_commit):
            with self.assertRaisesRegex(RuntimeError, "synthetic process crash"):
                evaluate_once(
                    self.ledger,
                    IDENTITY,
                    PREDICTIONS,
                    lambda: calls.append("opened") or LABELS,
                )
        self.assertEqual(calls, [])
        with self.assertRaisesRegex(RuntimeError, "already opened"):
            evaluate_once(
                self.ledger,
                IDENTITY,
                PREDICTIONS,
                lambda: calls.append("reopened") or LABELS,
            )
        self.assertEqual(calls, [])
        with self.assertRaisesRegex(RuntimeError, "no completed scorecard"):
            replay_scorecard(self.ledger, IDENTITY)

    def test_label_failure_leaves_no_score_and_second_model_cannot_reopen(self):
        def fail_labels():
            raise OSError("source unavailable")

        with self.assertRaisesRegex(OSError, "source unavailable"):
            evaluate_once(self.ledger, IDENTITY, PREDICTIONS, fail_labels)
        with self.assertRaisesRegex(RuntimeError, "already opened"):
            evaluate_once(
                self.ledger,
                replace(IDENTITY, model_bundle_hash="d" * 64),
                PREDICTIONS,
                lambda: LABELS,
            )
        with self.assertRaisesRegex(RuntimeError, "no completed scorecard"):
            replay_scorecard(self.ledger, IDENTITY)

    def test_replay_requires_exact_identity_and_untampered_predictions(self):
        result = evaluate_once(self.ledger, IDENTITY, PREDICTIONS, lambda: LABELS)
        self.assertEqual(replay_scorecard(self.ledger, IDENTITY), result)
        for changed in (
            replace(IDENTITY, split_hash="d" * 64),
            replace(IDENTITY, model_bundle_hash="d" * 64),
            replace(IDENTITY, row_ids=("sale-1", "sale-3")),
        ):
            with self.subTest(changed=changed):
                with self.assertRaisesRegex(ValueError, "identity mismatch"):
                    replay_scorecard(self.ledger, changed)
        with closing(sqlite3.connect(self.ledger)) as connection:
            connection.execute("UPDATE attempts SET predictions_json = ?", ("[]",))
            connection.commit()
        with self.assertRaisesRegex(ValueError, "prediction digest mismatch"):
            replay_scorecard(self.ledger, IDENTITY)

    def test_incomplete_or_changed_prediction_cohort_is_rejected_before_open(self):
        with self.assertRaisesRegex(ValueError, "prediction IDs"):
            evaluate_once(self.ledger, IDENTITY, PREDICTIONS[:1], lambda: LABELS)
        self.assertFalse(self.ledger.exists())
        with self.assertRaisesRegex(ValueError, "prediction IDs"):
            evaluate_once(
                self.ledger,
                IDENTITY,
                (PREDICTIONS[0], PREDICTIONS[0]),
                lambda: LABELS,
            )
        self.assertFalse(self.ledger.exists())

    def test_missing_label_aborts_score_without_making_valid_metric(self):
        with self.assertRaisesRegex(ValueError, "label IDs"):
            evaluate_once(
                self.ledger,
                IDENTITY,
                PREDICTIONS,
                lambda: {"sale-1": Decimal("100")},
            )
        with self.assertRaisesRegex(RuntimeError, "no completed scorecard"):
            replay_scorecard(self.ledger, IDENTITY)

    def test_loader_cannot_change_predictions_after_intent(self):
        caller_owned = list(PREDICTIONS)

        def mutate_then_load():
            caller_owned[0] = FrozenEstimate(
                "sale-1", "estimated", Decimal("200"), "USD"
            )
            return LABELS

        result = evaluate_once(self.ledger, IDENTITY, caller_owned, mutate_then_load)
        self.assertEqual(result.mdape, Decimal("0.1"))
        self.assertEqual(replay_scorecard(self.ledger, IDENTITY), result)

    def test_replay_does_not_create_tables_in_an_empty_database(self):
        with closing(sqlite3.connect(self.ledger)) as connection:
            self.assertEqual(
                connection.execute("SELECT name FROM sqlite_master").fetchall(), []
            )
        with self.assertRaisesRegex(RuntimeError, "no completed scorecard"):
            replay_scorecard(self.ledger, IDENTITY)
        with closing(sqlite3.connect(self.ledger)) as connection:
            self.assertEqual(
                connection.execute("SELECT name FROM sqlite_master").fetchall(), []
            )

    def test_overlapping_cohort_cannot_reopen_a_reserved_row(self):
        evaluate_once(self.ledger, IDENTITY, PREDICTIONS, lambda: LABELS)
        changed = replace(IDENTITY, row_ids=("sale-1", "sale-3"))
        changed_predictions = (
            PREDICTIONS[0],
            FrozenEstimate("sale-3", "estimated", Decimal("300"), "USD"),
        )
        with self.assertRaisesRegex(RuntimeError, "already opened"):
            evaluate_once(
                self.ledger,
                changed,
                changed_predictions,
                lambda: {"sale-1": Decimal("100"), "sale-3": Decimal("300")},
            )

    def test_simultaneous_attempts_open_labels_only_once(self):
        barrier = Barrier(2)
        calls = []

        def attempt():
            barrier.wait()

            def load():
                calls.append("opened")
                return LABELS

            try:
                return evaluate_once(self.ledger, IDENTITY, PREDICTIONS, load)
            except RuntimeError as error:
                return str(error)

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(attempt) for _ in range(2)]
            outcomes = [future.result() for future in futures]
        self.assertEqual(len(calls), 1)
        self.assertEqual(sum(hasattr(item, "mdape") for item in outcomes), 1)
        self.assertEqual(
            sum("already opened" in item for item in outcomes if isinstance(item, str)),
            1,
        )

    def test_memory_ledger_is_rejected_before_label_access(self):
        calls = []
        with self.assertRaisesRegex(ValueError, "durable ledger path"):
            evaluate_once(
                Path(":memory:"),
                IDENTITY,
                PREDICTIONS,
                lambda: calls.append("opened") or LABELS,
            )
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
