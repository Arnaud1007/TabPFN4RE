"""Frozen date, price and lexical grammars for NYC source representations."""

from __future__ import annotations

import re
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

START_DATE = date(2025, 9, 1)
END_DATE = date(2026, 8, 31)
EXCEL_EPOCH = date(1899, 12, 30)
DATE_FORMS = (
    "iso_date",
    "us_date",
    "iso_midnight",
    "excel_serial",
    "blank",
    "other_or_invalid",
)
PRICE_FORMS = (
    "plain_integer",
    "grouped_integer",
    "plain_decimal",
    "grouped_decimal",
    "scientific",
    "blank",
    "other_or_invalid",
)

_ISO = re.compile(r"([0-9]{4})-([0-9]{2})-([0-9]{2})\Z")
_US = re.compile(r"([0-9]{2})/([0-9]{2})/([0-9]{4})\Z")
_MIDNIGHT = re.compile(r"([0-9]{4})-([0-9]{2})-([0-9]{2})[T ]00:00:00(?:\.0{1,6})?\Z")
_SERIAL = re.compile(r"[0-9]+(?:\.0+)?\Z")
_CSV_PRICE = re.compile(r"-?(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)(?:\.[0-9]+)?\Z")
_XLSX_PRICE = re.compile(r"(-?)([0-9]+)(?:\.([0-9]+))?(?:[Ee]([+-]?[0-9]{1,2}))?\Z")


def _valid_date(year: int, month: int, day: int) -> date | None:
    try:
        candidate = date(year, month, day)
    except ValueError:
        return None
    return candidate if START_DATE <= candidate <= END_DATE else None


def parse_date(value: str, *, source: str, date_system: str) -> date | None:
    """Parse only frozen calendar, local-midnight and 1900 XLSX serial forms."""
    if source not in ("csv", "xlsx") or date_system != "1900_default":
        raise ValueError("Unsupported date source or workbook date system")
    if type(value) is not str:
        raise TypeError("Date representation must be a string")
    value = value.strip()
    match = _ISO.fullmatch(value) or _MIDNIGHT.fullmatch(value)
    if match:
        return _valid_date(*(int(part) for part in match.groups()[:3]))
    match = _US.fullmatch(value)
    if match:
        month, day, year = (int(part) for part in match.groups())
        return _valid_date(year, month, day)
    if source == "xlsx" and _SERIAL.fullmatch(value):
        try:
            serial = int(value.partition(".")[0])
            if serial == 60:
                return None  # Excel's nonexistent 1900-02-29.
            candidate = EXCEL_EPOCH + timedelta(days=serial)
        except (OverflowError, ValueError):
            return None
        return candidate if START_DATE <= candidate <= END_DATE else None
    return None


def parse_price(value: str, *, source: str) -> Decimal | None:
    """Parse exact finite prices without rounding or sale-label eligibility."""
    if source not in ("csv", "xlsx"):
        raise ValueError("Unsupported price source")
    if type(value) is not str:
        raise TypeError("Price representation must be a string")
    value = value.strip()
    if source == "csv":
        if not _CSV_PRICE.fullmatch(value):
            return None
        numeric = value.replace(",", "")
    else:
        match = _XLSX_PRICE.fullmatch(value)
        if match is None:
            return None
        _, whole, fraction, exponent = match.groups()
        mantissa = (whole + (fraction or "")).lstrip("0")
        if len(mantissa) > 18 or (exponent is not None and abs(int(exponent)) > 12):
            return None
        numeric = value
    try:
        parsed = Decimal(numeric)
    except InvalidOperation:
        return None
    return parsed if parsed.is_finite() else None


def date_form(value: str, source: str) -> str:
    if not value:
        return "blank"
    if _ISO.fullmatch(value):
        return "iso_date"
    if _US.fullmatch(value):
        return "us_date"
    if _MIDNIGHT.fullmatch(value):
        return "iso_midnight"
    if source == "xlsx" and _SERIAL.fullmatch(value):
        return "excel_serial"
    return "other_or_invalid"


def price_form(value: str, source: str) -> str:
    if not value:
        return "blank"
    if parse_price(value, source=source) is None:
        return "other_or_invalid"
    if "e" in value.lower():
        return "scientific"
    if "," in value:
        return "grouped_decimal" if "." in value else "grouped_integer"
    return "plain_decimal" if "." in value else "plain_integer"
