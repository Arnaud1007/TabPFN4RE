"""Audit-only quality states for frozen Cook parcel-sale observations."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import re
from typing import Sequence

from tabpfn4realestate.data.cook_parcel_sales import CookParcelSaleObservation


_HEX64 = re.compile(r"[0-9a-f]{64}\Z")
_POSITIVE_INTEGER = re.compile(r"[0-9]+\Z")
_STATES = (
    ("price", ("positive", "nonpositive", "malformed", "missing", "null")),
    ("pin", ("valid", "malformed", "missing", "null")),
    ("recorded_date", ("valid", "malformed", "missing", "null")),
    ("multisale", ("true", "false", "malformed", "missing", "null")),
    ("parcel_count", ("single", "multiple", "malformed", "missing", "null")),
    ("document", ("unique", "repeated", "malformed", "missing", "null")),
)


def _source_state(raw: dict[str, object], field: str) -> tuple[str, object]:
    if field not in raw:
        return "missing", None
    if raw[field] is None:
        return "null", None
    return "present", raw[field]


def _multisale_state(raw: dict[str, object]) -> str:
    state, value = _source_state(raw, "is_multisale")
    if state != "present":
        return state
    if type(value) is not bool:
        return "malformed"
    return "true" if value else "false"


def _parcel_count_state(raw: dict[str, object]) -> str:
    state, value = _source_state(raw, "num_parcels_sale")
    if state != "present":
        return state
    if type(value) is int:
        count = value
    elif type(value) is str and _POSITIVE_INTEGER.fullmatch(value):
        if len(value) > 8:
            return "malformed"
        count = int(value)
    else:
        return "malformed"
    if count < 1 or count > 99_999_999:
        return "malformed"
    return "single" if count == 1 else "multiple"


def _document_key(raw: dict[str, object]) -> tuple[str, str | None]:
    state, value = _source_state(raw, "doc_no")
    if state != "present":
        return state, None
    if type(value) is not str or not value or value != value.strip():
        return "malformed", None
    return "usable", value


@dataclass(frozen=True)
class CookQualityFinding:
    ordinal: int
    row_id: str
    row_sha256: str
    price_state: str
    pin_state: str
    recorded_date_state: str
    multisale_state: str
    parcel_count_state: str
    document_state: str
    reason_codes: tuple[str, ...]
    status: str = "audit_only"

    def to_record(self) -> dict[str, object]:
        """Return a fresh private review record without raw price or location."""
        return {
            "ordinal": self.ordinal,
            "row_id": self.row_id,
            "row_sha256": self.row_sha256,
            "price_state": self.price_state,
            "pin_state": self.pin_state,
            "recorded_date_state": self.recorded_date_state,
            "multisale_state": self.multisale_state,
            "parcel_count_state": self.parcel_count_state,
            "document_state": self.document_state,
            "reason_codes": list(self.reason_codes),
            "status": self.status,
        }


@dataclass(frozen=True)
class CookQualityProfile:
    findings: tuple[CookQualityFinding, ...]
    counts: tuple[tuple[str, tuple[tuple[str, int], ...]], ...]
    attention_count: int
    sample_rows: int
    certified_sale_labels: int = 0

    def private_counts_record(self) -> dict[str, object]:
        """Return complete count partitions for the restricted audit file."""
        return {
            "sample_rows": self.sample_rows,
            "attention_count": self.attention_count,
            "counts": {
                name: {state: count for state, count in states}
                for name, states in self.counts
            },
            "certified_sale_labels": self.certified_sale_labels,
            "historical_asof_eligible": False,
        }


def profile_quality(
    observations: Sequence[CookParcelSaleObservation],
    *,
    expected_capture_sha256: str,
    expected_rows: int,
) -> CookQualityProfile:
    """Classify each verified source row without admitting a sale label."""
    if type(expected_rows) is not int or expected_rows < 1:
        raise ValueError("Expected Cook sample count is invalid")
    if type(expected_capture_sha256) is not str or not _HEX64.fullmatch(
        expected_capture_sha256
    ):
        raise ValueError("Expected Cook capture hash is invalid")
    if not isinstance(observations, Sequence) or len(observations) != expected_rows:
        raise ValueError("Cook sample denominator differs")
    row_ids: set[str] = set()
    document_keys: list[str | None] = []
    for row in observations:
        if not isinstance(row, CookParcelSaleObservation):
            raise ValueError("Cook observation type differs")
        if (
            row.capture_sha256 != expected_capture_sha256
            or row.row_id in row_ids
            or CookParcelSaleObservation.from_record(row.to_record()) != row
        ):
            raise ValueError("Cook observation lineage or identity differs")
        row_ids.add(row.row_id)
        _, document_key = _document_key(dict(row.raw_fields))
        document_keys.append(document_key)
    document_sizes = Counter(key for key in document_keys if key is not None)

    findings = []
    for ordinal, (row, document_key) in enumerate(
        zip(observations, document_keys, strict=True), start=1
    ):
        raw = dict(row.raw_fields)
        document_state, _ = _document_key(raw)
        if document_key is not None:
            document_state = (
                "repeated" if document_sizes[document_key] > 1 else "unique"
            )
        states = {
            "price": row.price_state,
            "pin": row.pin_state,
            "recorded_date": row.recorded_date_state,
            "multisale": _multisale_state(raw),
            "parcel_count": _parcel_count_state(raw),
            "document": document_state,
        }
        reasons = tuple(
            f"{name}_{state}"
            for name, allowed in _STATES
            if (state := states[name])
            not in {
                "price": {"positive"},
                "pin": {"valid"},
                "recorded_date": {"valid"},
                "multisale": {"false"},
                "parcel_count": {"single"},
                "document": {"unique"},
            }[name]
            and state in allowed
        )
        if any(states[name] not in allowed for name, allowed in _STATES):
            raise ValueError("Cook quality state is unregistered")
        findings.append(
            CookQualityFinding(
                ordinal=ordinal,
                row_id=row.row_id,
                row_sha256=row.row_sha256,
                price_state=states["price"],
                pin_state=states["pin"],
                recorded_date_state=states["recorded_date"],
                multisale_state=states["multisale"],
                parcel_count_state=states["parcel_count"],
                document_state=states["document"],
                reason_codes=reasons,
            )
        )
    frozen_findings = tuple(findings)
    counts = tuple(
        (
            name,
            tuple(
                (
                    state,
                    sum(
                        getattr(row, f"{name}_state") == state
                        for row in frozen_findings
                    ),
                )
                for state in allowed
            ),
        )
        for name, allowed in _STATES
    )
    return CookQualityProfile(
        findings=frozen_findings,
        counts=counts,
        attention_count=sum(bool(row.reason_codes) for row in frozen_findings),
        sample_rows=expected_rows,
    )
