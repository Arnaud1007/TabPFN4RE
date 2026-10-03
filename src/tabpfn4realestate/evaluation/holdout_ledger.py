"""Synthetic, one-use reserved-label evaluation with a durable opening intent.

The evaluation process must own the ledger path and keep the label loader
inaccessible to model fitting. An opened cohort is consumed even if scoring
fails. This is an engineering fixture, not a real-market certification runner.
"""

from __future__ import annotations

from contextlib import closing
from dataclasses import asdict, dataclass, fields
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from typing import Callable, Mapping, Sequence

from tabpfn4realestate.data.schema import _identifier
from tabpfn4realestate.evaluation.metrics import (
    PredictionRow,
    Scorecard,
    _positive_decimal,
    score_predictions,
)


_PROTOCOL = "us_synthetic_holdout_v1"
_DECIMAL_SCORE_FIELDS = {
    "success_coverage",
    "mdape",
    "mape",
    "within_5",
    "within_10",
    "within_20",
    "p90_ape",
    "p95_ape",
    "median_signed_percentage_error",
    "mae",
    "r2",
}


def _digest(value: str, name: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{name} must be a lowercase SHA-256 digest")


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class HoldoutIdentity:
    protocol_id: str
    split_hash: str
    source_snapshot_hash: str
    model_bundle_hash: str
    row_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.protocol_id != _PROTOCOL:
            raise ValueError("Only the synthetic holdout protocol is supported")
        for name in ("split_hash", "source_snapshot_hash", "model_bundle_hash"):
            _digest(getattr(self, name), name)
        if (
            not isinstance(self.row_ids, tuple)
            or not self.row_ids
            or tuple(sorted(set(self.row_ids))) != self.row_ids
        ):
            raise ValueError("row_ids must be a nonempty sorted unique tuple")
        for row_id in self.row_ids:
            _identifier(row_id, "row_id")


@dataclass(frozen=True)
class FrozenEstimate:
    row_id: str
    status: str
    predicted: Decimal | None
    currency: str | None
    reason: str | None = None

    def __post_init__(self) -> None:
        _identifier(self.row_id, "row_id")
        if self.status == "estimated":
            _positive_decimal(self.predicted, "predicted")
            if self.currency != "USD" or self.reason is not None:
                raise ValueError("Estimated prediction needs USD and no failure reason")
        elif self.status in {"failed", "abstained"}:
            if self.predicted is not None or self.currency is not None:
                raise ValueError("Non-estimated prediction cannot contain an amount")
            _identifier(self.reason, "reason")
        else:
            raise ValueError("Unknown prediction status")


def _identity_json(identity: HoldoutIdentity) -> str:
    return _json(asdict(identity))


def _cohort_key(identity: HoldoutIdentity) -> str:
    return _sha256(_json(identity.row_ids))


def _durable_path(value: Path) -> Path:
    path = Path(value)
    if not path.is_absolute() or not path.parent.is_dir() or path.is_dir():
        raise ValueError(
            "A durable ledger path under an existing directory is required"
        )
    return path


def _predictions_json(
    identity: HoldoutIdentity, predictions: Sequence[FrozenEstimate]
) -> str:
    if not isinstance(predictions, Sequence) or any(
        not isinstance(row, FrozenEstimate) for row in predictions
    ):
        raise ValueError("predictions must be frozen estimates")
    if (
        len(predictions) != len(identity.row_ids)
        or tuple(sorted(row.row_id for row in predictions)) != identity.row_ids
    ):
        raise ValueError("prediction IDs must exactly match reserved row IDs")
    return _json(
        [
            {
                "row_id": row.row_id,
                "status": row.status,
                "predicted": str(row.predicted) if row.predicted is not None else None,
                "currency": row.currency,
                "reason": row.reason,
            }
            for row in sorted(predictions, key=lambda item: item.row_id)
        ]
    )


def _connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path, timeout=10)
    try:
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute(
            "CREATE TABLE IF NOT EXISTS attempts ("
            "cohort_key TEXT PRIMARY KEY, identity_json TEXT NOT NULL, "
            "predictions_json TEXT NOT NULL, predictions_sha256 TEXT NOT NULL, "
            "status TEXT NOT NULL, scorecard_json TEXT, scorecard_sha256 TEXT)"
        )
        connection.execute(
            "CREATE TABLE IF NOT EXISTS reserved_rows ("
            "row_id TEXT PRIMARY KEY, cohort_key TEXT NOT NULL)"
        )
        connection.commit()
        return connection
    except BaseException:
        connection.close()
        raise


def _connect_read_only(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)


def _persist_intent(
    path: Path, identity: HoldoutIdentity, predictions_json: str
) -> None:
    """Commit the frozen predictions and opening intent before label access."""
    with closing(_connect(path)) as connection:
        try:
            connection.execute("BEGIN IMMEDIATE")
            cohort_key = _cohort_key(identity)
            if connection.execute(
                "SELECT 1 FROM attempts WHERE cohort_key = ?", (cohort_key,)
            ).fetchone():
                raise RuntimeError("Reserved cohort already opened")
            connection.execute(
                "INSERT INTO attempts VALUES (?, ?, ?, ?, ?, NULL, NULL)",
                (
                    cohort_key,
                    _identity_json(identity),
                    predictions_json,
                    _sha256(predictions_json),
                    "opening_intent",
                ),
            )
            try:
                connection.executemany(
                    "INSERT INTO reserved_rows VALUES (?, ?)",
                    ((row_id, cohort_key) for row_id in identity.row_ids),
                )
            except sqlite3.IntegrityError as error:
                raise RuntimeError("Reserved cohort already opened") from error
            connection.commit()
        except BaseException:
            connection.rollback()
            raise


def _scorecard_json(scorecard: Scorecard) -> str:
    return _json(
        {
            name: str(value) if isinstance(value, Decimal) else value
            for name, value in asdict(scorecard).items()
        }
    )


def _persist_result(
    path: Path, identity: HoldoutIdentity, scorecard: Scorecard
) -> None:
    result_json = _scorecard_json(scorecard)
    with closing(_connect(path)) as connection:
        with connection:
            cursor = connection.execute(
                "UPDATE attempts SET status = 'complete', scorecard_json = ?, "
                "scorecard_sha256 = ? WHERE cohort_key = ? AND identity_json = ? "
                "AND status = 'opening_intent'",
                (
                    result_json,
                    _sha256(result_json),
                    _cohort_key(identity),
                    _identity_json(identity),
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("Opening intent changed before result commit")


def evaluate_once(
    ledger_path: Path,
    identity: HoldoutIdentity,
    predictions: Sequence[FrozenEstimate],
    load_labels: Callable[[], Mapping[str, Decimal]],
) -> Scorecard:
    """Persist an intent, then access reserved labels exactly once for scoring."""
    if not isinstance(identity, HoldoutIdentity):
        raise ValueError("identity must be a frozen holdout identity")
    frozen_predictions = tuple(predictions)
    predictions_json = _predictions_json(identity, frozen_predictions)
    if not callable(load_labels):
        raise ValueError("load_labels must be callable")
    path = _durable_path(ledger_path)
    _persist_intent(path, identity, predictions_json)
    labels = load_labels()
    if not isinstance(labels, Mapping) or set(labels) != set(identity.row_ids):
        raise ValueError("label IDs must exactly match reserved row IDs")
    by_id = {row.row_id: row for row in frozen_predictions}
    rows = tuple(
        PredictionRow(
            row_id=row_id,
            actual=labels[row_id],
            predicted=by_id[row_id].predicted,
            actual_currency="USD",
            predicted_currency=by_id[row_id].currency,
            status=by_id[row_id].status,
            reason=by_id[row_id].reason,
        )
        for row_id in identity.row_ids
    )
    result = score_predictions(rows)
    _persist_result(path, identity, result)
    return result


def replay_scorecard(ledger_path: Path, identity: HoldoutIdentity) -> Scorecard:
    """Read a completed result without invoking a label loader or reopening."""
    if not isinstance(identity, HoldoutIdentity):
        raise ValueError("identity must be a frozen holdout identity")
    path = Path(ledger_path)
    if not path.is_file():
        raise RuntimeError("no completed scorecard")
    with closing(_connect_read_only(path)) as connection:
        if not connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'attempts'"
        ).fetchone():
            raise RuntimeError("no completed scorecard")
        row = connection.execute(
            "SELECT identity_json, predictions_json, predictions_sha256, "
            "status, scorecard_json, scorecard_sha256 FROM attempts "
            "WHERE cohort_key = ?",
            (_cohort_key(identity),),
        ).fetchone()
        if row is None:
            if connection.execute("SELECT 1 FROM attempts LIMIT 1").fetchone():
                raise ValueError("Holdout identity mismatch")
            raise RuntimeError("no completed scorecard")
    (
        stored_identity,
        predictions_json,
        predictions_hash,
        status,
        result_json,
        result_hash,
    ) = row
    if stored_identity != _identity_json(identity):
        raise ValueError("Holdout identity mismatch")
    if _sha256(predictions_json) != predictions_hash:
        raise ValueError("Stored prediction digest mismatch")
    if status != "complete" or result_json is None or result_hash is None:
        raise RuntimeError("no completed scorecard")
    if _sha256(result_json) != result_hash:
        raise ValueError("Stored scorecard digest mismatch")
    parsed = json.loads(result_json)
    expected = {field.name for field in fields(Scorecard)}
    if not isinstance(parsed, dict) or set(parsed) != expected:
        raise ValueError("Stored scorecard schema mismatch")
    return Scorecard(
        **{
            name: Decimal(value)
            if name in _DECIMAL_SCORE_FIELDS and value is not None
            else value
            for name, value in parsed.items()
        }
    )
