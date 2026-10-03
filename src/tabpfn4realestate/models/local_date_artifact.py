"""Bind a synthetic OFF fit to bytes of a training-only source capture.

This deliberately accepts one fixed synthetic feed, not county transaction data.
The frozen schedule must have been created from the capture's observed digest.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
from typing import Mapping, Sequence

from tabpfn4realestate.data.local_date_facts import DatePublishedProperty
from tabpfn4realestate.data.local_date_sale import LocalDateSale
from tabpfn4realestate.data.schema import SourceSnapshot
from tabpfn4realestate.evaluation.calendar_schedule import CalendarOriginRef
from tabpfn4realestate.evaluation.chronological_plan import (
    ChronologicalMaturityRef,
    ChronologicalPlan,
)
from tabpfn4realestate.evaluation.local_dates import (
    DateOnlyAvailability,
    availability_cutoff_utc,
    derive_local_date_origin,
)
from tabpfn4realestate.features.asof import LOCAL_DATE_ASSEMBLER_POLICY_VERSION_V2
from tabpfn4realestate.models.local_date_median import (
    CalendarTrainingExample,
    GuardedLocalDateMedian,
)


PROTOCOL = "synthetic_calendar_capture_v1"
SOURCE_ID = "synthetic-county"
MAX_CAPTURE_BYTES = 1_000_000
MAX_CAPTURE_ROWS = 10_000
_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}\Z")
_UTC = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z\Z")
_MONEY = re.compile(r"[0-9]+(?:\.[0-9]{1,2})?\Z")
_AREA = re.compile(r"[0-9]+(?:\.[0-9]+)?\Z")
_FIELDS = frozenset(
    (
        "protocol",
        "row_id",
        "property_id",
        "transaction_id",
        "source_id",
        "snapshot_id",
        "close_date",
        "close_zone",
        "published_on",
        "price_usd",
        "property_observed_at_utc",
        "property_published_on",
        "living_area_sqft",
    )
)


def _read_capture(path: Path) -> bytes:
    if not isinstance(path, Path) or path.is_symlink() or not path.is_file():
        raise ValueError("Synthetic capture must be a regular local file")
    try:
        with path.open("rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ValueError("Synthetic capture must be a regular local file")
            body = stream.read(MAX_CAPTURE_BYTES + 1)
    except OSError as error:
        raise ValueError("Synthetic capture could not be read") from error
    if not body or len(body) > MAX_CAPTURE_BYTES or not body.endswith(b"\n"):
        raise ValueError("Synthetic capture is empty, oversized or truncated")
    return body


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Synthetic capture contains a duplicate JSON key")
        result[key] = value
    return result


def _source_date(value: object, name: str) -> date:
    if type(value) is not str or _DATE.fullmatch(value) is None:
        raise ValueError(f"{name} must be an exact source-local date")
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{name} is not a calendar date") from error


def _observed_utc(value: object) -> datetime:
    if type(value) is not str or _UTC.fullmatch(value) is None:
        raise ValueError("Synthetic property observation needs exact UTC seconds")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("Synthetic property observation is invalid") from error


def _positive_decimal(value: object, pattern: re.Pattern[str], name: str) -> Decimal:
    if type(value) is not str or pattern.fullmatch(value) is None:
        raise ValueError(f"{name} must be a decimal string")
    try:
        amount = Decimal(value)
    except InvalidOperation as error:
        raise ValueError(f"{name} is invalid") from error
    if not amount.is_finite() or amount <= 0:
        raise ValueError(f"{name} must be positive")
    return amount


def _example(raw: object) -> CalendarTrainingExample:
    if not isinstance(raw, dict) or set(raw) != _FIELDS:
        raise ValueError("Synthetic capture row has an incompatible schema")
    if raw["protocol"] != PROTOCOL or raw["source_id"] != SOURCE_ID:
        raise ValueError("Synthetic capture protocol or source differs")
    close_date = _source_date(raw["close_date"], "close_date")
    publication = _source_date(raw["published_on"], "published_on")
    property_publication = _source_date(
        raw["property_published_on"], "property_published_on"
    )
    zone = raw["close_zone"]
    origin = derive_local_date_origin(close_date, zone)
    published_at = DateOnlyAvailability(publication, zone)
    observed_at = _observed_utc(raw["property_observed_at_utc"])
    property_available_at = DateOnlyAvailability(property_publication, zone)
    if observed_at > availability_cutoff_utc(property_available_at):
        raise ValueError("Synthetic property was published before observation")
    property_fact = DatePublishedProperty(
        raw["property_id"],
        "US",
        "single_family",
        SOURCE_ID,
        observed_at,
        property_available_at,
        _positive_decimal(raw["living_area_sqft"], _AREA, "living_area_sqft"),
        "sqft",
    )
    label = LocalDateSale(
        raw["transaction_id"],
        raw["row_id"],
        raw["property_id"],
        close_date,
        zone,
        published_at,
        _positive_decimal(raw["price_usd"], _MONEY, "price_usd"),
        "USD",
        SOURCE_ID,
        "single_property",
        "gross_recorded_sale",
        "confirmed",
        (),
    )
    snapshot = SourceSnapshot(
        raw["snapshot_id"], (SOURCE_ID,), origin.cutoff_exclusive_utc
    )
    return CalendarTrainingExample(
        raw["row_id"], property_fact, origin, snapshot, label
    )


def _parse_capture(body: bytes) -> tuple[CalendarTrainingExample, ...]:
    try:
        lines = body.decode("utf-8").splitlines()
    except UnicodeError as error:
        raise ValueError("Synthetic capture must be UTF-8") from error
    if not lines or len(lines) > MAX_CAPTURE_ROWS or any(not line for line in lines):
        raise ValueError("Synthetic capture row count or blank line is invalid")
    examples = []
    for line in lines:
        try:
            raw = json.loads(line, object_pairs_hook=_unique_object)
        except json.JSONDecodeError as error:
            raise ValueError("Synthetic capture contains malformed JSON") from error
        examples.append(_example(raw))
    return tuple(examples)


def fit_synthetic_calendar_capture(
    path: Path,
    plan: ChronologicalPlan,
    origins: Sequence[CalendarOriginRef],
    zones: Mapping[str, str],
    maturity: Sequence[ChronologicalMaturityRef],
) -> GuardedLocalDateMedian:
    """Fit only rows parsed from the exact frozen synthetic capture bytes."""
    if not isinstance(plan, ChronologicalPlan):
        raise ValueError("A frozen chronological plan is required")
    body = _read_capture(path)
    digest = sha256(body).hexdigest()
    if digest != plan.schedule.source_snapshot_sha256:
        raise ValueError("Synthetic capture digest differs from frozen schedule")
    examples = _parse_capture(body)
    model = GuardedLocalDateMedian.fit(
        examples,
        plan,
        origins,
        zones,
        maturity,
        source_snapshot_sha256=digest,
        feature_policy_version=LOCAL_DATE_ASSEMBLER_POLICY_VERSION_V2,
    )
    return replace(model, source_binding_kind="synthetic_capture_bytes_v1")


def verify_synthetic_calendar_capture(
    path: Path,
    model: GuardedLocalDateMedian,
    plan: ChronologicalPlan,
    origins: Sequence[CalendarOriginRef],
    zones: Mapping[str, str],
    maturity: Sequence[ChronologicalMaturityRef],
) -> None:
    """Rehash source bytes and reproduce a saved synthetic model exactly.

    Model metadata alone does not attest to the capture; this replay is required
    when reporting the byte-bound engineering result.
    """
    if not isinstance(model, GuardedLocalDateMedian):
        raise ValueError("Synthetic replay needs a saved calendar median")
    replay = fit_synthetic_calendar_capture(path, plan, origins, zones, maturity)
    if replay != model:
        raise ValueError("Synthetic capture replay differs from saved model")
