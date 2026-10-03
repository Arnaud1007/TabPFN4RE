"""Replay this synthetic capture checkpoint without opening real sale data."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from tests.test_local_date_artifact import ORIGINS, ZONES, frozen_plan  # noqa: E402
from tabpfn4realestate.models.local_date_artifact import (  # noqa: E402
    MAX_CAPTURE_BYTES,
    PROTOCOL,
    verify_synthetic_calendar_capture,
)
from tabpfn4realestate.models.local_date_median import (  # noqa: E402
    GuardedLocalDateMedian,
)


def restored_model(raw: dict) -> GuardedLocalDateMedian:
    """Use the explicit JSON record, never a pickle, for this local replay."""
    return GuardedLocalDateMedian(
        amount=Decimal(raw["amount"]),
        train_row_ids=tuple(raw["train_row_ids"]),
        feature_snapshot_hashes=tuple(raw["feature_snapshot_hashes"]),
        training_cutoff=datetime.fromisoformat(raw["training_cutoff"]),
        plan_hash=raw["plan_hash"],
        schedule_hash=raw["schedule_hash"],
        origin_policy_sha256=raw["origin_policy_sha256"],
        source_snapshot_sha256=raw["source_snapshot_sha256"],
        training_rows_sha256=raw["training_rows_sha256"],
        allowed_source_ids=tuple(raw["allowed_source_ids"]),
        feature_policy_version=raw["feature_policy_version"],
        source_binding_kind=raw["source_binding_kind"],
    )


def main() -> None:
    run = Path(__file__).resolve().parent
    expected = json.loads((run / "synthetic_replay.json").read_text(encoding="utf-8"))
    capture = run / "synthetic_training.jsonl"
    if capture.is_symlink() or not capture.is_file():
        raise ValueError("Retained synthetic capture must be a regular file")
    with capture.open("rb") as stream:
        body = stream.read(MAX_CAPTURE_BYTES + 1)
    if len(body) > MAX_CAPTURE_BYTES:
        raise ValueError("Retained synthetic capture exceeds size limit")
    if sha256(body).hexdigest() != expected["source_snapshot_sha256"]:
        raise ValueError("Retained synthetic capture digest changed")
    if len(body) != expected["capture_bytes"]:
        raise ValueError("Retained synthetic capture length changed")
    plan, maturity = frozen_plan(body)
    if (
        plan.plan_hash != expected["plan_hash"]
        or plan.schedule.schedule_hash != expected["schedule_hash"]
    ):
        raise ValueError("Frozen synthetic plan differs")
    model = restored_model(expected["model"])
    verify_synthetic_calendar_capture(capture, model, plan, ORIGINS, ZONES, maturity)
    if (
        expected["protocol"] != PROTOCOL
        or expected["replay_status"] != "PASS"
        or expected["source_snapshot_sha256"] != model.source_snapshot_sha256
        or expected["training_rows"] != len(model.train_row_ids)
        or model.train_row_ids != tuple(expected["train_row_ids"])
        or expected["training_rows_sha256"] != model.training_rows_sha256
        or tuple(expected["feature_snapshot_hashes"]) != model.feature_snapshot_hashes
        or expected["feature_policy_version"] != model.feature_policy_version
        or expected["source_binding_kind"] != model.source_binding_kind
        or Decimal(expected["median_amount"]) != model.amount
        or tuple(expected["reserved_row_ids"])
        != plan.schedule.calibration.row_ids + plan.schedule.final_test.row_ids
        or set(model.train_row_ids) & set(expected["reserved_row_ids"])
        or expected["real_market_labels"] != 0
        or expected["us_gate_status"] != "PENDING"
    ):
        raise ValueError("Synthetic training or gate summary differs")
    print(
        "PASS: exact synthetic capture and model replay; zero real labels; G-US pending"
    )


if __name__ == "__main__":
    main()
