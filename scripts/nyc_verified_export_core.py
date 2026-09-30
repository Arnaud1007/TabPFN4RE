"""Select and compare a frozen NYC sample across same-publisher exports.

Only row ordinals, comparison statuses and disagreement positions leave this
module. A representation candidate is never a certified transaction label.
"""

from __future__ import annotations

import re
from collections import defaultdict
from hashlib import sha256
from typing import Iterable

import nyc_representation_core as representation

PROTOCOL = "nyc-verified-export-pilot-v1"
SAMPLE_COUNT = 200
PILOT_COUNT = 10
QUALIFIED_CODES = "2345"
KEY_COLUMNS = frozenset(representation.KEY_COLUMNS)
STATUSES = frozenset(
    {
        "invalid_key",
        "ambiguous",
        "unmatched",
        "unique_candidate_with_field_disagreement",
        "canonical_full_21_concordance",
        "raw_full_21_concordance",
    }
)
_SHA = re.compile(r"[0-9a-f]{64}\Z")


def _rank(ordinal: int, sample_sha256: str) -> tuple[str, int]:
    seed = f"{PROTOCOL}|{sample_sha256}|{ordinal}".encode("utf-8")
    return sha256(seed).hexdigest(), ordinal


def select_pilot(
    sample_ordinals: set[int], borough_by_ordinal: dict[int, str], sample_sha256: str
) -> tuple[int, ...]:
    """Select two per qualified borough and two from the residual global pool."""
    if (
        type(sample_ordinals) is not set
        or len(sample_ordinals) != SAMPLE_COUNT
        or any(type(item) is not int or item < 1 for item in sample_ordinals)
        or type(borough_by_ordinal) is not dict
        or set(borough_by_ordinal) != sample_ordinals
        or any(
            type(value) is not str or value not in "12345"
            for value in borough_by_ordinal.values()
        )
        or type(sample_sha256) is not str
        or _SHA.fullmatch(sample_sha256) is None
    ):
        raise ValueError("Frozen sample or source borough mapping is invalid")
    chosen: list[int] = []
    eligible = {
        item for item in sample_ordinals if borough_by_ordinal[item] in QUALIFIED_CODES
    }
    for code in QUALIFIED_CODES:
        group = [item for item in eligible if borough_by_ordinal[item] == code]
        if len(group) < 2:
            raise ValueError("Qualified borough lacks pilot sample quota")
        chosen.extend(sorted(group, key=lambda item: _rank(item, sample_sha256))[:2])
    residual = eligible - set(chosen)
    if len(residual) < 2:
        raise ValueError("Pilot residual pool is too small")
    chosen.extend(sorted(residual, key=lambda item: _rank(item, sample_sha256))[:2])
    if len(chosen) != PILOT_COUNT or len(set(chosen)) != PILOT_COUNT:
        raise ValueError("Pilot selection did not reconcile")
    return tuple(chosen)


def _groups(rows: list, tier: str) -> dict[tuple, list]:
    groups: dict[tuple, list] = defaultdict(list)
    for item in rows:
        key = representation._tier_key(item, tier)
        if key is not None:
            groups[key].append(item)
    return groups


def _graph(csv: list, xlsx: list) -> tuple[dict, dict, set[int], set[int], dict, dict]:
    edges: dict[int, set[int]] = defaultdict(set)
    reverse: dict[int, set[int]] = defaultdict(set)
    marked_csv: set[int] = set()
    marked_xlsx: set[int] = set()
    canonical_csv: dict = {}
    canonical_xlsx: dict = {}
    for tier in representation.TIERS:
        left, right = _groups(csv, tier), _groups(xlsx, tier)
        if tier == "K3":
            canonical_csv, canonical_xlsx = left, right
        for groups, marked in ((left, marked_csv), (right, marked_xlsx)):
            for group in groups.values():
                if len(group) > 1:
                    marked.update(item.ordinal for item in group)
                if tier == "K4" and len({item.raw_key[1:3] for item in group}) > 1:
                    marked.update(item.ordinal for item in group)
        for key in left.keys() & right.keys():
            lhs, rhs = left[key], right[key]
            if len(lhs) != 1 or len(rhs) != 1:
                marked_csv.update(item.ordinal for item in lhs)
                marked_xlsx.update(item.ordinal for item in rhs)
                continue
            edges[lhs[0].ordinal].add(rhs[0].ordinal)
            reverse[rhs[0].ordinal].add(lhs[0].ordinal)
    return edges, reverse, marked_csv, marked_xlsx, canonical_csv, canonical_xlsx


def compare_borough(
    csv_rows: Iterable[tuple[int, tuple[str, ...]]],
    xlsx_rows: Iterable[tuple[int, tuple[str, ...]]],
    *,
    selected: set[int],
    borough: str,
    borough_code: str,
) -> list[dict]:
    """Assess selected CSV rows against complete, validated borough row sets."""
    if (
        representation.BOROUGH_CODES.get(borough) != borough_code
        or type(selected) is not set
        or any(type(item) is not int or item < 1 for item in selected)
    ):
        raise ValueError("Pilot borough or selected ordinals are invalid")
    csv, used = representation._normalize_rows(
        csv_rows,
        source="csv",
        borough_code=borough_code,
        date_system="1900_default",
        remaining_characters=representation.MAX_RESIDENT_CELL_CHARS,
    )
    xlsx, _ = representation._normalize_rows(
        xlsx_rows,
        source="xlsx",
        borough_code=borough_code,
        date_system="1900_default",
        remaining_characters=representation.MAX_RESIDENT_CELL_CHARS - used,
    )
    by_csv = {item.ordinal: item for item in csv}
    by_xlsx = {item.ordinal: item for item in xlsx}
    if not selected <= by_csv.keys():
        raise ValueError("Pilot sample row is absent from complete borough scan")
    edges, reverse, marked_csv, marked_xlsx, canonical_csv, canonical_xlsx = _graph(
        csv, xlsx
    )
    assessed = []
    for ordinal in sorted(selected):
        item = by_csv[ordinal]
        key = representation._tier_key(item, "K3")
        matches = edges.get(ordinal, set())
        target = None
        if key is None:
            status = "invalid_key"
        elif ordinal in marked_csv or len(matches) > 1:
            status = "ambiguous"
        elif not matches:
            status = "unmatched"
        else:
            candidate = next(iter(matches))
            left = canonical_csv.get(key, ())
            right = canonical_xlsx.get(key, ())
            reciprocal = reverse.get(candidate, set())
            if (
                len(left) != 1
                or len(right) != 1
                or right[0].ordinal != candidate
                or candidate in marked_xlsx
                or reciprocal != {ordinal}
            ):
                status = "ambiguous"
            else:
                target = by_xlsx[candidate]
                differences = [
                    index + 1
                    for index, (a, b) in enumerate(
                        zip(item.values, target.values, strict=True)
                    )
                    if index not in KEY_COLUMNS and a != b
                ]
                if differences:
                    status = "unique_candidate_with_field_disagreement"
                elif item.values[19:21] == target.values[19:21]:
                    status = "raw_full_21_concordance"
                else:
                    status = "canonical_full_21_concordance"
        assessed.append(
            {
                "ordinal": ordinal,
                "borough": borough,
                "status": status,
                "workbook_row_number": target.ordinal if target else None,
                "difference_positions": differences if target and differences else [],
            }
        )
    return assessed
