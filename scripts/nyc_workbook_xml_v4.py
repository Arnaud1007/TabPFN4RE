"""Versioned Manhattan-only structural exception over the unchanged v3 parser."""

from __future__ import annotations

import time
from io import BufferedIOBase

import nyc_manhattan_formula_xml_v1 as diagnostic
import nyc_workbook_xml as base
import nyc_workbook_xml_v3 as v3


PROTOCOL = "nyc-borough-worksheet-inspection-v4"
BOROUGHS = frozenset({"Bronx", "Brooklyn", "Manhattan", "Queens", "Staten Island"})


def _inspect_with_pin(
    handle: BufferedIOBase,
    pin: tuple[int, str],
    *,
    borough: str,
    expected_formula: dict | None = None,
    timer: base.Timer = time.monotonic,
    start: float | None = None,
) -> dict:
    """Inspect a synthetic workbook with an explicit printer-settings pin."""
    if borough not in BOROUGHS:
        raise ValueError("Unsupported NYC borough")
    if borough != "Manhattan" and expected_formula is not None:
        raise ValueError("Formula exception is Manhattan-only")
    origin = timer() if start is None else start
    prior = v3._inspect_with_pin(handle, pin, timer=timer, start=origin)
    if borough == "Manhattan":
        if not isinstance(expected_formula, dict):
            raise ValueError("Private Manhattan formula record is missing")
        diagnostic._require_v3(prior)
        if prior["raw_header_sha256"] != v3.EXPECTED_RAW_HEADER_SHA256:
            raise ValueError("Manhattan raw header fingerprint differs")
        observed = diagnostic._extract(handle, timer, origin)
        base._check_time(timer, origin)
        if observed != expected_formula:
            raise ValueError("Manhattan preamble formula differs from private pin")
        qualified = True
        exception_count = 1
    else:
        qualified = prior["worksheet_qualified"]
        exception_count = 0
    return {
        **prior,
        "protocol": PROTOCOL,
        "v3_worksheet_qualified": prior["worksheet_qualified"],
        "worksheet_qualified": qualified,
        "formula_exception_count": exception_count,
        "label_status": "unqualified",
        "sale_labels_certified": 0,
    }


def inspect_workbook(
    handle: BufferedIOBase,
    *,
    borough: str,
    expected_formula: dict | None = None,
    timer: base.Timer = time.monotonic,
    start: float | None = None,
) -> dict:
    """Inspect the pinned source under the v4 structural policy."""
    return _inspect_with_pin(
        handle,
        base.PRODUCTION_PRINTER_PIN,
        borough=borough,
        expected_formula=expected_formula,
        timer=timer,
        start=start,
    )
