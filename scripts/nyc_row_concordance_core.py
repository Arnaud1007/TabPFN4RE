"""Exact, trim-only comparison of two NYC DOF borough representations.

This diagnostic does not establish transaction eligibility or certify sale labels.
Source values are retained only while one borough is compared. Returned private
trace entries contain ordinals and fingerprints, never raw source values.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from hashlib import sha256
from typing import Iterable

PROTOCOL = "nyc-dof-same-publisher-row-concordance-v1"
BOROUGH_CODES = {"Bronx": "2", "Brooklyn": "3", "Queens": "4", "Staten Island": "5"}
FIELD_COUNT = 21
MAX_RESIDENT_CELL_CHARS = 32_000_000
KEY_COLUMNS = (0, 4, 5, 9, 20, 19)  # borough, block, lot, apartment, date, price
REQUIRED_KEY_POSITIONS = (0, 1, 2, 4, 5)  # apartment may be blank
ADDRESS_COLUMN = 8
BUILDING_CLASS_COLUMN = 18
METRIC_NAMES = (
    "csv_complete_key_rows",
    "xlsx_complete_key_rows",
    "csv_incomplete_key_rows",
    "xlsx_incomplete_key_rows",
    "csv_complete_key_groups",
    "xlsx_complete_key_groups",
    "exact_full_row_multiset_matches",
    "csv_full_row_multiset_residual_rows",
    "xlsx_full_row_multiset_residual_rows",
    "unique_key_pairs",
    "unique_full_row_matches",
    "unique_full_row_mismatches",
    "unique_address_matches",
    "unique_address_mismatches",
    "unique_building_class_matches",
    "unique_building_class_mismatches",
    "csv_duplicate_key_groups",
    "xlsx_duplicate_key_groups",
    "duplicate_key_groups",
    "csv_duplicate_key_rows",
    "xlsx_duplicate_key_rows",
    "shared_ambiguous_key_groups",
    "csv_ambiguous_shared_key_rows",
    "xlsx_ambiguous_shared_key_rows",
    "multiplicity_disagreement_groups",
    "csv_only_key_groups",
    "csv_only_rows",
    "xlsx_only_key_groups",
    "xlsx_only_rows",
)

Row = tuple[int, tuple[str, ...]]
NormalizedRow = tuple[int, tuple[str, ...], tuple[str, ...]]


def _valid_borough(borough: object, borough_code: object) -> bool:
    return (
        isinstance(borough, str)
        and isinstance(borough_code, str)
        and BOROUGH_CODES.get(borough) == borough_code
    )


def _normalized(
    rows: Iterable[Row], borough_code: str, remaining_characters: int
) -> tuple[list[NormalizedRow], int]:
    result: list[NormalizedRow] = []
    ordinals: set[int] = set()
    used_characters = 0
    for item in rows:
        if not isinstance(item, tuple) or len(item) != 2:
            raise ValueError("Source row must be an ordinal and 21-field tuple")
        ordinal, values = item
        if (
            type(ordinal) is not int
            or ordinal < 1
            or ordinal in ordinals
            or not isinstance(values, tuple)
            or len(values) != FIELD_COUNT
            or any(not isinstance(value, str) for value in values)
        ):
            raise ValueError("Source row has invalid ordinal or field structure")
        used_characters += sum(map(len, values))
        if used_characters > remaining_characters:
            raise ValueError("Borough source strings exceed combined character cap")
        trimmed = tuple(value.strip() for value in values)
        if trimmed[0] != borough_code:
            raise ValueError("Source row borough code does not match borough frame")
        ordinals.add(ordinal)
        result.append((ordinal, trimmed, tuple(trimmed[i] for i in KEY_COLUMNS)))
    return result, used_characters


def _complete(key: tuple[str, ...]) -> bool:
    return all(key[position] != "" for position in REQUIRED_KEY_POSITIONS)


def _fingerprint(kind: bytes, fields: tuple[str, ...]) -> str:
    encoded = json.dumps(fields, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )
    return sha256(kind + b"\0" + encoded).hexdigest()


def _groups(
    rows: list[NormalizedRow],
) -> tuple[dict[tuple[str, ...], list[NormalizedRow]], int]:
    groups: dict[tuple[str, ...], list[NormalizedRow]] = defaultdict(list)
    incomplete = 0
    for row in rows:
        if _complete(row[2]):
            groups[row[2]].append(row)
        else:
            incomplete += 1
    return groups, incomplete


def _paired_counts(csv: NormalizedRow, xlsx: NormalizedRow, counts: dict) -> None:
    counts["unique_key_pairs"] += 1
    for name, left, right in (
        ("unique_full_row", csv[1], xlsx[1]),
        ("unique_address", csv[1][ADDRESS_COLUMN], xlsx[1][ADDRESS_COLUMN]),
        (
            "unique_building_class",
            csv[1][BUILDING_CLASS_COLUMN],
            xlsx[1][BUILDING_CLASS_COLUMN],
        ),
    ):
        suffix = "matches" if left == right else "mismatches"
        counts[f"{name}_{suffix}"] += 1


def _classify_groups(
    csv_groups: dict,
    xlsx_groups: dict,
    counts: dict,
) -> tuple[dict[int, str], dict[int, str]]:
    csv_status: dict[int, str] = {}
    xlsx_status: dict[int, str] = {}
    for key in csv_groups.keys() | xlsx_groups.keys():
        csv_rows = csv_groups.get(key, [])
        xlsx_rows = xlsx_groups.get(key, [])
        if len(csv_rows) > 1 or len(xlsx_rows) > 1:
            counts["duplicate_key_groups"] += 1
        if not xlsx_rows:
            counts["csv_only_key_groups"] += 1
            counts["csv_only_rows"] += len(csv_rows)
            status = "csv_only"
        elif not csv_rows:
            counts["xlsx_only_key_groups"] += 1
            counts["xlsx_only_rows"] += len(xlsx_rows)
            status = "xlsx_only"
        elif len(csv_rows) == len(xlsx_rows) == 1:
            _paired_counts(csv_rows[0], xlsx_rows[0], counts)
            status = (
                "unique_pair_exact"
                if csv_rows[0][1] == xlsx_rows[0][1]
                else "unique_pair_mismatch"
            )
        else:
            counts["shared_ambiguous_key_groups"] += 1
            counts["csv_ambiguous_shared_key_rows"] += len(csv_rows)
            counts["xlsx_ambiguous_shared_key_rows"] += len(xlsx_rows)
            if len(csv_rows) != len(xlsx_rows):
                counts["multiplicity_disagreement_groups"] += 1
            status = "duplicate_key"
        csv_status.update((row[0], status) for row in csv_rows)
        xlsx_status.update((row[0], status) for row in xlsx_rows)
    return csv_status, xlsx_status


def _ledger(
    rows: list[NormalizedRow], source: str, status: dict[int, str]
) -> list[dict]:
    return [
        {
            "source": source,
            "ordinal": ordinal,
            "status": status.get(ordinal, "incomplete_key"),
            "row_sha256": _fingerprint(b"row", values),
            "key_sha256": _fingerprint(b"key", key),
        }
        for ordinal, values, key in sorted(rows, key=lambda row: row[0])
    ]


def compare_borough(
    csv_rows: Iterable[Row],
    xlsx_rows: Iterable[Row],
    *,
    borough: str,
    borough_code: str,
) -> dict:
    """Compare complete rows and candidate keys within one approved borough.

    Source-only key counts cover complete keys only. Exact multiset matches cover
    all rows, including incomplete keys. For each source, total rows equal
    complete plus incomplete rows, and complete rows equal unique pairs plus
    ambiguous shared rows plus source-only rows. Complete key groups equal
    unique pairs plus ambiguous shared groups plus source-only groups. Exact
    multiset matches plus each source's residual equal its source total. Each
    of full-row, address and class matches plus mismatches equals unique pairs.
    """
    if not _valid_borough(borough, borough_code):
        raise ValueError("Borough name and code are not an approved pair")
    csv, csv_characters = _normalized(csv_rows, borough_code, MAX_RESIDENT_CELL_CHARS)
    xlsx, _ = _normalized(
        xlsx_rows, borough_code, MAX_RESIDENT_CELL_CHARS - csv_characters
    )
    csv_groups, csv_incomplete = _groups(csv)
    xlsx_groups, xlsx_incomplete = _groups(xlsx)
    counts = dict.fromkeys(METRIC_NAMES, 0)
    counts["csv_complete_key_rows"] = len(csv) - csv_incomplete
    counts["xlsx_complete_key_rows"] = len(xlsx) - xlsx_incomplete
    counts["csv_incomplete_key_rows"] = csv_incomplete
    counts["xlsx_incomplete_key_rows"] = xlsx_incomplete
    counts["csv_complete_key_groups"] = len(csv_groups)
    counts["xlsx_complete_key_groups"] = len(xlsx_groups)

    csv_full = Counter(row[1] for row in csv)
    xlsx_full = Counter(row[1] for row in xlsx)
    exact = sum(
        min(csv_full[row], xlsx_full[row]) for row in csv_full.keys() & xlsx_full.keys()
    )
    counts["exact_full_row_multiset_matches"] = exact
    counts["csv_full_row_multiset_residual_rows"] = len(csv) - exact
    counts["xlsx_full_row_multiset_residual_rows"] = len(xlsx) - exact
    for source, groups in (("csv", csv_groups), ("xlsx", xlsx_groups)):
        duplicates = [rows for rows in groups.values() if len(rows) > 1]
        counts[f"{source}_duplicate_key_groups"] = len(duplicates)
        counts[f"{source}_duplicate_key_rows"] = sum(map(len, duplicates))
    csv_status, xlsx_status = _classify_groups(csv_groups, xlsx_groups, counts)

    return {
        "protocol": PROTOCOL,
        "borough": borough,
        "borough_code": borough_code,
        "csv_rows": len(csv),
        "xlsx_rows": len(xlsx),
        "counts": counts,
        "ledger": _ledger(csv, "csv", csv_status) + _ledger(xlsx, "xlsx", xlsx_status),
        "label_status": "unqualified",
        "sale_labels_certified": 0,
    }


def public_projection(result: dict) -> dict:
    """Expose fixed counts, suppressing the whole breakdown for a small cell."""
    if (
        not isinstance(result, dict)
        or result.get("protocol") != PROTOCOL
        or not _valid_borough(result.get("borough"), result.get("borough_code"))
    ):
        raise ValueError("Invalid concordance result")
    csv_rows, xlsx_rows = result.get("csv_rows"), result.get("xlsx_rows")
    if any(type(value) is not int or value < 0 for value in (csv_rows, xlsx_rows)):
        raise ValueError("Invalid source row denominator")
    source_counts = result.get("counts")
    if not isinstance(source_counts, dict) or set(source_counts) != set(METRIC_NAMES):
        raise ValueError("Invalid concordance metric schema")
    if any(type(value) is not int or value < 0 for value in source_counts.values()):
        raise ValueError("Invalid concordance metric count")
    if (
        source_counts["csv_complete_key_rows"]
        + source_counts["csv_incomplete_key_rows"]
        != csv_rows
        or source_counts["xlsx_complete_key_rows"]
        + source_counts["xlsx_incomplete_key_rows"]
        != xlsx_rows
    ):
        raise ValueError("Concordance key counts do not reconcile")
    for source in ("csv", "xlsx"):
        if (
            source_counts[f"{source}_complete_key_groups"]
            != source_counts["unique_key_pairs"]
            + source_counts["shared_ambiguous_key_groups"]
            + source_counts[f"{source}_only_key_groups"]
            or source_counts[f"{source}_complete_key_rows"]
            != source_counts["unique_key_pairs"]
            + source_counts[f"{source}_ambiguous_shared_key_rows"]
            + source_counts[f"{source}_only_rows"]
        ):
            raise ValueError("Concordance complete-key groups do not reconcile")
    exact = source_counts["exact_full_row_multiset_matches"]
    if (
        exact + source_counts["csv_full_row_multiset_residual_rows"] != csv_rows
        or exact + source_counts["xlsx_full_row_multiset_residual_rows"] != xlsx_rows
    ):
        raise ValueError("Concordance full-row counts do not reconcile")
    for prefix in ("unique_full_row", "unique_address", "unique_building_class"):
        if (
            source_counts[f"{prefix}_matches"] + source_counts[f"{prefix}_mismatches"]
            != source_counts["unique_key_pairs"]
        ):
            raise ValueError("Unique-pair concordance counts do not reconcile")
    suppress = any(0 < value < 5 for value in source_counts.values())
    return {
        "protocol": PROTOCOL,
        "borough": result["borough"],
        "borough_code": result["borough_code"],
        "csv_rows": csv_rows,
        "xlsx_rows": xlsx_rows,
        "counts": None
        if suppress
        else {name: source_counts[name] for name in METRIC_NAMES},
        "suppression_reason": "small_positive_cell_1_to_4" if suppress else None,
        "label_status": "unqualified",
        "sale_labels_certified": 0,
    }
