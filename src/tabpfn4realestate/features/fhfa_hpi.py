"""Bounded, point-in-time controls for FHFA HPI research adjustments."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import csv
import hashlib
import io
import math
from pathlib import Path
import re


_QUARTER = re.compile(r"(?P<year>\d{4})Q(?P<quarter>[1-4])")
_SHA256 = re.compile(r"[0-9a-f]{64}")


def _quarter_end(value: str) -> date:
    match = _QUARTER.fullmatch(value)
    if match is None:
        raise ValueError("HPI quarter must use YYYYQ1 through YYYYQ4")
    year = int(match.group("year"))
    quarter = int(match.group("quarter"))
    month = quarter * 3
    day = 31 if month in (3, 12) else 30
    return date(year, month, day)


@dataclass(frozen=True)
class HpiObservation:
    """One exact value from a dated FHFA source snapshot."""

    quarter: str
    index_value: float
    available_at: date

    def __post_init__(self) -> None:
        _quarter_end(self.quarter)
        if (
            type(self.index_value) not in (int, float)
            or not math.isfinite(float(self.index_value))
            or self.index_value <= 0
        ):
            raise ValueError("HPI index value must be a finite positive number")
        if not isinstance(self.available_at, date):
            raise ValueError("HPI availability must be a date")


@dataclass(frozen=True)
class HpiSeries:
    """Identity and observations for one immutable FHFA index snapshot."""

    series_id: str
    cbsa_code: str
    geography: str
    index_type: str
    seasonality: str
    source_sha256: str
    source_release_date: date
    retrieved_at: date
    observations: tuple[HpiObservation, ...]

    def __post_init__(self) -> None:
        if not self.series_id or not self.geography:
            raise ValueError("HPI series identity is required")
        if not re.fullmatch(r"\d{5}", self.cbsa_code):
            raise ValueError("HPI CBSA code must contain five digits")
        if self.index_type != "purchase-only":
            raise ValueError("Only the purchase-only HPI series is supported")
        if self.seasonality != "not-seasonally-adjusted":
            raise ValueError("Only the nonseasonally adjusted HPI is supported")
        if _SHA256.fullmatch(self.source_sha256) is None:
            raise ValueError("HPI source SHA-256 is invalid")
        if not isinstance(self.source_release_date, date) or not isinstance(
            self.retrieved_at, date
        ):
            raise ValueError("HPI source dates are invalid")
        if self.source_release_date > self.retrieved_at:
            raise ValueError("HPI source release cannot follow retrieval")
        if not isinstance(self.observations, tuple) or not self.observations:
            raise ValueError("HPI series requires an immutable observation tuple")
        if any(not isinstance(item, HpiObservation) for item in self.observations):
            raise ValueError("HPI series observations are invalid")
        if any(item.available_at != self.retrieved_at for item in self.observations):
            raise ValueError(
                "HPI observations must use snapshot retrieval availability"
            )
        quarters = tuple(item.quarter for item in self.observations)
        if len(quarters) != len(set(quarters)):
            raise ValueError("HPI series contains a duplicate quarter")


@dataclass(frozen=True)
class HpiAdjustment:
    """A reproducible ratio adjustment between two exact quarters."""

    amount: float
    factor: float
    base_index: float
    target_index: float
    base_quarter: str
    target_quarter: str
    as_of: date


def _exact_observation(series: HpiSeries, quarter: str, as_of: date) -> HpiObservation:
    matches = tuple(item for item in series.observations if item.quarter == quarter)
    if len(matches) != 1:
        raise ValueError(f"HPI series has no exact observation for {quarter}")
    observation = matches[0]
    if observation.available_at > as_of:
        raise ValueError(f"HPI observation {quarter} was not available at {as_of}")
    return observation


def adjust_price(
    amount: float,
    series: HpiSeries,
    base_quarter: str,
    target_quarter: str,
    as_of: date,
) -> HpiAdjustment:
    """Scale an amount by an exact HPI ratio without interpolation."""
    if (
        type(amount) not in (int, float)
        or not math.isfinite(float(amount))
        or amount <= 0
    ):
        raise ValueError("Price amount must be a finite positive number")
    if not isinstance(series, HpiSeries) or not isinstance(as_of, date):
        raise ValueError("HPI series and as-of date are required")
    if series.retrieved_at > as_of:
        raise ValueError(f"HPI source snapshot was not available at {as_of}")
    if _quarter_end(target_quarter) > as_of:
        raise ValueError(f"HPI target is a future quarter: {target_quarter}")
    if _quarter_end(base_quarter) > _quarter_end(target_quarter):
        raise ValueError("HPI base quarter cannot follow target quarter")
    base = _exact_observation(series, base_quarter, as_of)
    target = _exact_observation(series, target_quarter, as_of)
    factor = float(target.index_value) / float(base.index_value)
    adjusted = float(amount) * factor
    if not math.isfinite(adjusted) or adjusted <= 0:
        raise ValueError("HPI-adjusted amount is invalid")
    return HpiAdjustment(
        amount=adjusted,
        factor=factor,
        base_index=float(base.index_value),
        target_index=float(target.index_value),
        base_quarter=base_quarter,
        target_quarter=target_quarter,
        as_of=as_of,
    )


def load_verified_metro_series(
    path: Path,
    *,
    expected_sha256: str,
    cbsa_code: str,
    geography: str,
    quarters: tuple[str, ...],
    source_release_date: date,
    retrieved_at: date,
) -> HpiSeries:
    """Verify official TSV bytes and extract exact nonseasonally adjusted rows."""
    if _SHA256.fullmatch(expected_sha256) is None:
        raise ValueError("Expected HPI SHA-256 is invalid")
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 2_000_000:
        raise ValueError("HPI source file is missing, redirected, or too large")
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != expected_sha256:
        raise ValueError("HPI source checksum mismatch")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ValueError("HPI source encoding is invalid") from error
    reader = csv.DictReader(io.StringIO(text), delimiter="\t")
    if reader.fieldnames != [
        "cbsa",
        "metro_name",
        "yr",
        "qtr",
        "index_nsa",
        "index_sa",
    ]:
        raise ValueError("HPI source schema is incompatible")
    requested = set(quarters)
    if len(requested) != len(quarters) or not requested:
        raise ValueError("HPI requested quarters must be unique")
    values: dict[str, float] = {}
    for row in reader:
        if row["cbsa"] != cbsa_code:
            continue
        if row["metro_name"] != geography:
            raise ValueError("HPI CBSA geography is incompatible")
        quarter = f"{row['yr']}Q{row['qtr']}"
        if quarter not in requested:
            continue
        if quarter in values:
            raise ValueError(f"HPI source duplicates {quarter}")
        try:
            values[quarter] = float(row["index_nsa"])
        except (TypeError, ValueError) as error:
            raise ValueError(f"HPI value is invalid for {quarter}") from error
    missing = requested - values.keys()
    if missing:
        raise ValueError(f"HPI source lacks exact quarters: {sorted(missing)}")
    observations = tuple(
        HpiObservation(quarter, values[quarter], retrieved_at) for quarter in quarters
    )
    return HpiSeries(
        series_id="FHFA_PO_NSA_SEATTLE_BELLEVUE_KENT",
        cbsa_code=cbsa_code,
        geography=geography,
        index_type="purchase-only",
        seasonality="not-seasonally-adjusted",
        source_sha256=expected_sha256,
        source_release_date=source_release_date,
        retrieved_at=retrieved_at,
        observations=observations,
    )
