"""Strict, private representation diagnostics for pinned NYC source rows.

Candidate links are evidence about field representations, not certified sales.
No source field value is included in the returned result or public projection.
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from hashlib import sha256
from typing import Iterable

from nyc_representation_parsing import (
    DATE_FORMS as _DATE_FORMS,
)
from nyc_representation_parsing import (
    PRICE_FORMS as _PRICE_FORMS,
)
from nyc_representation_parsing import date_form as _date_form
from nyc_representation_parsing import parse_date, parse_price
from nyc_representation_parsing import price_form as _price_form

PROTOCOL = "nyc-dof-representation-diagnostic-v2"
BOROUGH_CODES = {"Bronx": "2", "Brooklyn": "3", "Queens": "4", "Staten Island": "5"}
FIELD_COUNT = 21
MAX_RESIDENT_CELL_CHARS = 32_000_000
KEY_COLUMNS = (0, 4, 5, 9, 20, 19)
REQUIRED_KEY_POSITIONS = (0, 1, 2, 4, 5)
TIERS = ("K0", "K1", "K2", "K3", "K4")

_POSITIVE_ASCII = re.compile(r"[0-9]+\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_TIER_METRICS = (
    "csv_valid_rows",
    "xlsx_valid_rows",
    "csv_invalid_or_incomplete_rows",
    "xlsx_invalid_or_incomplete_rows",
    "unique_candidate_edges",
    "ambiguous_shared_groups",
    "csv_unique_edge_rows",
    "xlsx_unique_edge_rows",
    "csv_shared_ambiguous_rows",
    "xlsx_shared_ambiguous_rows",
    "csv_only_rows",
    "xlsx_only_rows",
    "csv_key_groups",
    "xlsx_key_groups",
    "csv_duplicate_key_groups",
    "xlsx_duplicate_key_groups",
    "csv_only_key_groups",
    "xlsx_only_key_groups",
)
_STATUSES = ("isolated_candidate", "ambiguous", "unmatched", "raw_key_incomplete")


@dataclass(frozen=True, slots=True)
class _Row:
    ordinal: int
    values: tuple[str, ...]
    raw_key: tuple[str, ...]
    parsed_date: date | None
    parsed_price: Decimal | None


def _raw_complete(key: tuple[str, ...]) -> bool:
    return all(key[index] != "" for index in REQUIRED_KEY_POSITIONS)


def _block_lot(value: str) -> str | None:
    if _POSITIVE_ASCII.fullmatch(value) is None:
        return None
    normalized = value.lstrip("0")
    return normalized or None


def _fingerprint(kind: bytes, fields: tuple[str, ...]) -> str:
    encoded = json.dumps(fields, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )
    return sha256(kind + b"\0" + encoded).hexdigest()


def _normalize_rows(
    rows: Iterable[tuple[int, tuple[str, ...]]],
    *,
    source: str,
    borough_code: str,
    date_system: str,
    remaining_characters: int,
) -> tuple[list[_Row], int]:
    normalized = []
    ordinals: set[int] = set()
    used = 0
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
            or any(type(value) is not str for value in values)
        ):
            raise ValueError("Source row has invalid ordinal or field structure")
        used += sum(map(len, values))
        if used > remaining_characters:
            raise ValueError("Borough source strings exceed combined character cap")
        trimmed = tuple(value.strip() for value in values)
        if trimmed[0] != borough_code:
            raise ValueError("Source row borough code differs from borough frame")
        ordinals.add(ordinal)
        normalized.append(
            _Row(
                ordinal,
                trimmed,
                tuple(trimmed[index] for index in KEY_COLUMNS),
                parse_date(trimmed[20], source=source, date_system=date_system),
                parse_price(trimmed[19], source=source),
            )
        )
    return normalized, used


def _tier_key(row: _Row, tier: str) -> tuple | None:
    if not _raw_complete(row.raw_key):
        return None
    borough, block, lot, apartment, raw_date, raw_price = row.raw_key
    if tier in ("K1", "K3", "K4") and row.parsed_date is None:
        return None
    if tier in ("K2", "K3", "K4") and row.parsed_price is None:
        return None
    if tier == "K4":
        block, lot = _block_lot(block), _block_lot(lot)
        if block is None or lot is None:
            return None
    return (
        borough,
        block,
        lot,
        apartment,
        row.parsed_date if tier in ("K1", "K3", "K4") else raw_date,
        row.parsed_price if tier in ("K2", "K3", "K4") else raw_price,
    )


def _tier_counts(
    csv: list[_Row],
    xlsx: list[_Row],
    tier: str,
    edges: dict[int, set[int]],
    reverse_edges: dict[int, set[int]],
    ambiguous_csv: set[int],
    ambiguous_xlsx: set[int],
    collisions: dict[str, dict[str, int]],
) -> dict[str, int]:
    groups: dict[str, dict[tuple, list[_Row]]] = {
        "csv": defaultdict(list),
        "xlsx": defaultdict(list),
    }
    for source, rows in (("csv", csv), ("xlsx", xlsx)):
        for row in rows:
            key = _tier_key(row, tier)
            if key is not None:
                groups[source][key].append(row)
    counts = dict.fromkeys(_TIER_METRICS, 0)
    for source, rows in (("csv", csv), ("xlsx", xlsx)):
        own = groups[source]
        counts[f"{source}_valid_rows"] = sum(map(len, own.values()))
        counts[f"{source}_invalid_or_incomplete_rows"] = (
            len(rows) - counts[f"{source}_valid_rows"]
        )
        counts[f"{source}_key_groups"] = len(own)
        counts[f"{source}_duplicate_key_groups"] = sum(
            len(group) > 1 for group in own.values()
        )
        if tier == "K4":
            for group in own.values():
                if len({(row.raw_key[1], row.raw_key[2]) for row in group}) > 1:
                    collisions[source]["groups"] += 1
                    collisions[source]["rows"] += len(group)
                    # Even a source-only normalization collision cannot be paired.
                    (ambiguous_csv if source == "csv" else ambiguous_xlsx).update(
                        row.ordinal for row in group
                    )
    for key in groups["csv"].keys() | groups["xlsx"].keys():
        left = groups["csv"].get(key, ())
        right = groups["xlsx"].get(key, ())
        if not right:
            counts["csv_only_key_groups"] += 1
            counts["csv_only_rows"] += len(left)
        elif not left:
            counts["xlsx_only_key_groups"] += 1
            counts["xlsx_only_rows"] += len(right)
        elif len(left) == len(right) == 1:
            counts["unique_candidate_edges"] += 1
            counts["csv_unique_edge_rows"] += 1
            counts["xlsx_unique_edge_rows"] += 1
            edges[left[0].ordinal].add(right[0].ordinal)
            reverse_edges[right[0].ordinal].add(left[0].ordinal)
        else:
            counts["ambiguous_shared_groups"] += 1
            counts["csv_shared_ambiguous_rows"] += len(left)
            counts["xlsx_shared_ambiguous_rows"] += len(right)
            ambiguous_csv.update(row.ordinal for row in left)
            ambiguous_xlsx.update(row.ordinal for row in right)
    _validate_tier(counts, len(csv), len(xlsx))
    return counts


def _validate_tier(counts: dict[str, int], csv_total: int, xlsx_total: int) -> None:
    if (
        not isinstance(counts, dict)
        or set(counts) != set(_TIER_METRICS)
        or any(type(value) is not int or value < 0 for value in counts.values())
    ):
        raise ValueError("Tier metric schema is invalid")
    for source, total in (("csv", csv_total), ("xlsx", xlsx_total)):
        if (
            counts[f"{source}_valid_rows"]
            + counts[f"{source}_invalid_or_incomplete_rows"]
            != total
            or counts[f"{source}_valid_rows"]
            != counts[f"{source}_unique_edge_rows"]
            + counts[f"{source}_shared_ambiguous_rows"]
            + counts[f"{source}_only_rows"]
            or counts[f"{source}_key_groups"]
            != counts["unique_candidate_edges"]
            + counts["ambiguous_shared_groups"]
            + counts[f"{source}_only_key_groups"]
            or counts[f"{source}_unique_edge_rows"] != counts["unique_candidate_edges"]
        ):
            raise ValueError("Tier source rows or groups do not reconcile")


def _statuses(
    csv: list[_Row],
    xlsx: list[_Row],
    edges: dict[int, set[int]],
    reverse_edges: dict[int, set[int]],
    ambiguous_csv: set[int],
    ambiguous_xlsx: set[int],
) -> tuple[dict[str, dict[int, str]], list[tuple[_Row, _Row]]]:
    by_csv = {row.ordinal: row for row in csv}
    by_xlsx = {row.ordinal: row for row in xlsx}
    isolated: list[tuple[_Row, _Row]] = []
    isolated_csv: set[int] = set()
    isolated_xlsx: set[int] = set()
    for csv_ordinal, neighbors in edges.items():
        if csv_ordinal in ambiguous_csv or len(neighbors) != 1:
            continue
        xlsx_ordinal = next(iter(neighbors))
        if xlsx_ordinal not in ambiguous_xlsx and reverse_edges[xlsx_ordinal] == {
            csv_ordinal
        }:
            isolated.append((by_csv[csv_ordinal], by_xlsx[xlsx_ordinal]))
            isolated_csv.add(csv_ordinal)
            isolated_xlsx.add(xlsx_ordinal)
    result = {"csv": {}, "xlsx": {}}
    for source, rows, linked, marked, matched in (
        ("csv", csv, edges, ambiguous_csv, isolated_csv),
        ("xlsx", xlsx, reverse_edges, ambiguous_xlsx, isolated_xlsx),
    ):
        for row in rows:
            if not _raw_complete(row.raw_key):
                status = "raw_key_incomplete"
            elif row.ordinal in matched:
                status = "isolated_candidate"
            elif row.ordinal in marked or linked.get(row.ordinal):
                status = "ambiguous"
            else:
                status = "unmatched"
            result[source][row.ordinal] = status
    return result, isolated


def _field_counts(pairs: list[tuple[_Row, _Row]]) -> dict:
    names = (
        "raw_date_matches",
        "raw_date_mismatches",
        "canonical_date_matches",
        "canonical_date_mismatches",
        "canonical_date_unparseable",
        "raw_price_matches",
        "raw_price_mismatches",
        "decimal_price_matches",
        "decimal_price_mismatches",
        "decimal_price_unparseable",
        "full_row_matches",
        "full_row_mismatches",
        "other_19_exact",
        "other_19_mismatches",
        "address_matches",
        "address_mismatches",
        "building_class_matches",
        "building_class_mismatches",
        "format_only_candidates",
    )
    counts = dict.fromkeys(names, 0)
    disagreements = [0] * FIELD_COUNT
    for left, right in pairs:
        for index, (a, b) in enumerate(zip(left.values, right.values, strict=True)):
            disagreements[index] += a != b
        for prefix, a, b in (
            ("raw_date", left.values[20], right.values[20]),
            ("raw_price", left.values[19], right.values[19]),
            ("full_row", left.values, right.values),
            ("address", left.values[8], right.values[8]),
            ("building_class", left.values[18], right.values[18]),
        ):
            counts[f"{prefix}_{'matches' if a == b else 'mismatches'}"] += 1
        other_19 = all(
            left.values[index] == right.values[index]
            for index in range(FIELD_COUNT)
            if index not in (19, 20)
        )
        counts["other_19_exact" if other_19 else "other_19_mismatches"] += 1
        for prefix, a, b in (
            ("canonical_date", left.parsed_date, right.parsed_date),
            ("decimal_price", left.parsed_price, right.parsed_price),
        ):
            suffix = (
                "unparseable"
                if a is None or b is None
                else ("matches" if a == b else "mismatches")
            )
            counts[f"{prefix}_{suffix}"] += 1
        if (
            other_19
            and left.values != right.values
            and left.parsed_date is not None
            and left.parsed_date == right.parsed_date
            and left.parsed_price is not None
            and left.parsed_price == right.parsed_price
        ):
            counts["format_only_candidates"] += 1
    counts["column_disagreements"] = disagreements
    return counts


def _lexical_and_failures(csv: list[_Row], xlsx: list[_Row]) -> tuple[dict, dict]:
    lexical = {
        source: {
            "date": dict.fromkeys(_DATE_FORMS, 0),
            "price": dict.fromkeys(_PRICE_FORMS, 0),
        }
        for source in ("csv", "xlsx")
    }
    failures = dict.fromkeys(("csv_date", "xlsx_date", "csv_price", "xlsx_price"), 0)
    for source, rows in (("csv", csv), ("xlsx", xlsx)):
        for row in rows:
            lexical[source]["date"][_date_form(row.values[20], source)] += 1
            lexical[source]["price"][_price_form(row.values[19], source)] += 1
            failures[f"{source}_date"] += row.parsed_date is None
            failures[f"{source}_price"] += row.parsed_price is None
    return lexical, failures


def _multiset_overlap(csv_tokens: Iterable, xlsx_tokens: Iterable) -> int:
    left, right = Counter(csv_tokens), Counter(xlsx_tokens)
    return sum((left & right).values())


def _overlap(csv: list[_Row], xlsx: list[_Row]) -> dict:
    raw = [
        _multiset_overlap(
            (row.values[index] for row in csv),
            (row.values[index] for row in xlsx),
        )
        for index in range(FIELD_COUNT)
    ]
    return {
        "raw_columns": raw,
        "canonical_date": _multiset_overlap(
            (row.parsed_date for row in csv if row.parsed_date is not None),
            (row.parsed_date for row in xlsx if row.parsed_date is not None),
        ),
        "decimal_price": _multiset_overlap(
            (row.parsed_price for row in csv if row.parsed_price is not None),
            (row.parsed_price for row in xlsx if row.parsed_price is not None),
        ),
        "canonical_block": _multiset_overlap(
            (value for row in csv if (value := _block_lot(row.values[4])) is not None),
            (value for row in xlsx if (value := _block_lot(row.values[4])) is not None),
        ),
        "canonical_lot": _multiset_overlap(
            (value for row in csv if (value := _block_lot(row.values[5])) is not None),
            (value for row in xlsx if (value := _block_lot(row.values[5])) is not None),
        ),
    }


def analyze_borough(
    csv_rows: Iterable[tuple[int, tuple[str, ...]]],
    xlsx_rows: Iterable[tuple[int, tuple[str, ...]]],
    *,
    borough: str,
    borough_code: str,
    date_system: str,
) -> dict:
    """Analyze strict representations and candidate graph for one borough."""
    if BOROUGH_CODES.get(borough) != borough_code or date_system != "1900_default":
        raise ValueError("Borough or workbook date system is out of scope")
    csv, used = _normalize_rows(
        csv_rows,
        source="csv",
        borough_code=borough_code,
        date_system=date_system,
        remaining_characters=MAX_RESIDENT_CELL_CHARS,
    )
    xlsx, _ = _normalize_rows(
        xlsx_rows,
        source="xlsx",
        borough_code=borough_code,
        date_system=date_system,
        remaining_characters=MAX_RESIDENT_CELL_CHARS - used,
    )
    edges: dict[int, set[int]] = defaultdict(set)
    reverse_edges: dict[int, set[int]] = defaultdict(set)
    ambiguous_csv: set[int] = set()
    ambiguous_xlsx: set[int] = set()
    collisions = {source: {"groups": 0, "rows": 0} for source in ("csv", "xlsx")}
    tiers = {
        name: _tier_counts(
            csv,
            xlsx,
            name,
            edges,
            reverse_edges,
            ambiguous_csv,
            ambiguous_xlsx,
            collisions,
        )
        for name in TIERS
    }
    statuses, isolated = _statuses(
        csv, xlsx, edges, reverse_edges, ambiguous_csv, ambiguous_xlsx
    )
    status_counts = {
        f"{source}_{status}": sum(value == status for value in own.values())
        for source, own in statuses.items()
        for status in _STATUSES
    }
    lexical, parse_failures = _lexical_and_failures(csv, xlsx)
    counts = {
        "tiers": tiers,
        "statuses": status_counts,
        "fields": _field_counts(isolated),
        "overlap": _overlap(csv, xlsx),
        "lexical_forms": lexical,
        "parse_failures": parse_failures,
        "normalization_collisions": collisions,
    }
    result = {
        "protocol": PROTOCOL,
        "borough": borough,
        "borough_code": borough_code,
        "date_system": date_system,
        "csv_rows": len(csv),
        "xlsx_rows": len(xlsx),
        "counts": counts,
        "ledger": [
            {
                "source": source,
                "ordinal": row.ordinal,
                "status": statuses[source][row.ordinal],
                "row_sha256": _fingerprint(b"row", row.values),
                "key_sha256": _fingerprint(b"key", row.raw_key),
            }
            for source, rows in (("csv", csv), ("xlsx", xlsx))
            for row in sorted(rows, key=lambda item: item.ordinal)
        ],
        "label_status": "unqualified",
        "sale_labels_certified": 0,
    }
    _validate_result(result)
    return result


def _validate_result(result: dict) -> None:
    if (
        result.get("protocol") != PROTOCOL
        or type(result.get("borough")) is not str
        or BOROUGH_CODES.get(result.get("borough")) != result.get("borough_code")
        or result.get("date_system") != "1900_default"
        or result.get("label_status") != "unqualified"
        or type(result.get("sale_labels_certified")) is not int
        or result.get("sale_labels_certified") != 0
    ):
        raise ValueError("Representation result metadata is invalid")
    csv_total, xlsx_total = result.get("csv_rows"), result.get("xlsx_rows")
    if any(type(value) is not int or value < 0 for value in (csv_total, xlsx_total)):
        raise ValueError("Representation source denominator is invalid")
    counts = result.get("counts")
    if (
        not isinstance(counts, dict)
        or set(counts)
        != {
            "tiers",
            "statuses",
            "fields",
            "overlap",
            "lexical_forms",
            "parse_failures",
            "normalization_collisions",
        }
        or not isinstance(counts.get("tiers"), dict)
        or set(counts["tiers"]) != set(TIERS)
    ):
        raise ValueError("Representation count schema is invalid")
    for tier in TIERS:
        _validate_tier(counts["tiers"][tier], csv_total, xlsx_total)
    statuses = counts.get("statuses", {})
    if (
        not isinstance(statuses, dict)
        or set(statuses)
        != {f"{source}_{status}" for source in ("csv", "xlsx") for status in _STATUSES}
        or any(type(value) is not int or value < 0 for value in statuses.values())
    ):
        raise ValueError("Representation statuses are invalid")
    for source, total in (("csv", csv_total), ("xlsx", xlsx_total)):
        if sum(statuses[f"{source}_{status}"] for status in _STATUSES) != total:
            raise ValueError("Representation source statuses do not reconcile")
        if (
            statuses[f"{source}_raw_key_incomplete"]
            != counts["tiers"]["K0"][f"{source}_invalid_or_incomplete_rows"]
        ):
            raise ValueError("Representation incomplete keys do not reconcile")
    if statuses["csv_isolated_candidate"] != statuses["xlsx_isolated_candidate"]:
        raise ValueError("Representation isolated pairs do not reconcile")
    pairs = statuses["csv_isolated_candidate"]
    fields = counts.get("fields", {})
    expected_fields = (
        {
            "format_only_candidates",
            "other_19_exact",
            "other_19_mismatches",
            "column_disagreements",
        }
        | {
            f"{prefix}_{suffix}"
            for prefix in (
                "raw_date",
                "raw_price",
                "full_row",
                "address",
                "building_class",
            )
            for suffix in ("matches", "mismatches")
        }
        | {
            f"{prefix}_{suffix}"
            for prefix in ("canonical_date", "decimal_price")
            for suffix in ("matches", "mismatches", "unparseable")
        }
    )
    if (
        not isinstance(fields, dict)
        or set(fields) != expected_fields
        or any(
            type(value) is not int or value < 0
            for name, value in fields.items()
            if name != "column_disagreements"
        )
    ):
        raise ValueError("Representation field counts are invalid")
    for prefix in ("raw_date", "raw_price", "full_row", "address", "building_class"):
        if (
            fields.get(f"{prefix}_matches", -1) + fields.get(f"{prefix}_mismatches", -1)
            != pairs
        ):
            raise ValueError("Representation pair field counts do not reconcile")
    for prefix in ("canonical_date", "decimal_price"):
        if (
            sum(
                fields.get(f"{prefix}_{suffix}", -1)
                for suffix in ("matches", "mismatches", "unparseable")
            )
            != pairs
        ):
            raise ValueError("Representation typed field counts do not reconcile")
    if (
        fields.get("other_19_exact", -1) + fields.get("other_19_mismatches", -1)
        != pairs
    ):
        raise ValueError("Representation other-field counts do not reconcile")
    disagreements = fields.get("column_disagreements")
    if (
        not isinstance(disagreements, list)
        or len(disagreements) != FIELD_COUNT
        or any(
            type(item) is not int or not 0 <= item <= pairs for item in disagreements
        )
    ):
        raise ValueError("Representation per-column counts are invalid")
    if (
        disagreements[20] != fields["raw_date_mismatches"]
        or disagreements[19] != fields["raw_price_mismatches"]
        or disagreements[8] != fields["address_mismatches"]
        or disagreements[18] != fields["building_class_mismatches"]
        or fields["full_row_mismatches"] > sum(disagreements)
        or fields["full_row_mismatches"] < max(disagreements)
        or fields["format_only_candidates"]
        > min(
            fields["other_19_exact"],
            fields["canonical_date_matches"],
            fields["decimal_price_matches"],
            fields["full_row_mismatches"],
        )
    ):
        raise ValueError("Representation field agreement does not reconcile")
    failures = counts.get("parse_failures")
    if (
        not isinstance(failures, dict)
        or set(failures)
        != {
            f"{source}_{family}"
            for source in ("csv", "xlsx")
            for family in ("date", "price")
        }
        or any(
            type(failures[f"{source}_{family}"]) is not int
            or not 0 <= failures[f"{source}_{family}"] <= total
            for source, total in (("csv", csv_total), ("xlsx", xlsx_total))
            for family in ("date", "price")
        )
    ):
        raise ValueError("Representation parse failures are invalid")
    lexical = counts.get("lexical_forms")
    if not isinstance(lexical, dict) or set(lexical) != {"csv", "xlsx"}:
        raise ValueError("Representation lexical schema is invalid")
    for source, total in (("csv", csv_total), ("xlsx", xlsx_total)):
        if not isinstance(lexical[source], dict) or set(lexical[source]) != {
            "date",
            "price",
        }:
            raise ValueError("Representation lexical source schema is invalid")
        for family, categories in (("date", _DATE_FORMS), ("price", _PRICE_FORMS)):
            histogram = lexical[source][family]
            if (
                not isinstance(histogram, dict)
                or set(histogram) != set(categories)
                or any(
                    type(value) is not int or value < 0 for value in histogram.values()
                )
                or sum(histogram.values()) != total
            ):
                raise ValueError("Representation lexical counts do not reconcile")
    overlap = counts.get("overlap")
    shared_cap = min(csv_total, xlsx_total)
    if (
        not isinstance(overlap, dict)
        or set(overlap)
        != {
            "raw_columns",
            "canonical_date",
            "decimal_price",
            "canonical_block",
            "canonical_lot",
        }
        or not isinstance(overlap["raw_columns"], list)
        or len(overlap["raw_columns"]) != FIELD_COUNT
        or any(
            type(value) is not int or not 0 <= value <= shared_cap
            for value in (
                *overlap["raw_columns"],
                overlap["canonical_date"],
                overlap["decimal_price"],
                overlap["canonical_block"],
                overlap["canonical_lot"],
            )
        )
    ):
        raise ValueError("Representation overlap counts are invalid")
    collisions = counts.get("normalization_collisions")
    if not isinstance(collisions, dict) or set(collisions) != {"csv", "xlsx"}:
        raise ValueError("Representation collision schema is invalid")
    for source, total in (("csv", csv_total), ("xlsx", xlsx_total)):
        item = collisions[source]
        if (
            not isinstance(item, dict)
            or set(item) != {"groups", "rows"}
            or any(type(value) is not int or value < 0 for value in item.values())
            or item["groups"] > item["rows"] // 2
            or item["rows"] > total
        ):
            raise ValueError("Representation normalization collisions are invalid")
    _validate_ledger(result.get("ledger"), statuses, csv_total, xlsx_total)


def _validate_ledger(
    ledger: object, statuses: dict[str, int], csv_total: int, xlsx_total: int
) -> None:
    """Reject extra fields and ensure every private row has one valid status."""
    if not isinstance(ledger, list) or len(ledger) != csv_total + xlsx_total:
        raise ValueError("Representation ledger length is invalid")
    observed = dict.fromkeys(statuses, 0)
    ordinals = {"csv": set(), "xlsx": set()}
    allowed = {"source", "ordinal", "status", "row_sha256", "key_sha256"}
    for entry in ledger:
        if not isinstance(entry, dict) or set(entry) != allowed:
            raise ValueError("Representation ledger entry schema is invalid")
        source, ordinal, status = (entry["source"], entry["ordinal"], entry["status"])
        if (
            type(source) is not str
            or source not in ordinals
            or type(ordinal) is not int
            or ordinal < 1
            or ordinal in ordinals[source]
            or status not in _STATUSES
            or any(
                type(entry[name]) is not str or _SHA256.fullmatch(entry[name]) is None
                for name in ("row_sha256", "key_sha256")
            )
        ):
            raise ValueError("Representation ledger entry is invalid")
        ordinals[source].add(ordinal)
        observed[f"{source}_{status}"] += 1
    if observed != statuses:
        raise ValueError("Representation ledger statuses do not reconcile")


def public_projection(result: dict) -> dict:
    """Expose only safe categories, with whole-borough suppression."""
    if not isinstance(result, dict):
        raise ValueError("Representation result is invalid")
    _validate_result(result)
    tiers = result["counts"]["tiers"]
    fields = result["counts"]["fields"]
    statuses = result["counts"]["statuses"]
    public_counts = {
        "tiers": {
            name: {"unique_candidate_edges": tiers[name]["unique_candidate_edges"]}
            for name in TIERS
        },
        "isolated_pairs": statuses["csv_isolated_candidate"],
        "format_only_candidates": fields["format_only_candidates"],
    }
    values = [
        *(tiers[name]["unique_candidate_edges"] for name in TIERS),
        public_counts["isolated_pairs"],
        public_counts["format_only_candidates"],
    ]
    denominators = (result["csv_rows"], result["xlsx_rows"])
    small_cell = (
        any(0 < value < 5 for value in values)
        or any(0 < abs(a - b) < 5 for a in values for b in values)
        or any(0 < total - value < 5 for total in denominators for value in values)
    )
    staten = result["borough"] == "Staten Island"
    return {
        "protocol": PROTOCOL,
        "borough": result["borough"],
        "borough_code": result["borough_code"],
        "csv_rows": result["csv_rows"],
        "xlsx_rows": result["xlsx_rows"],
        "counts": None if staten or small_cell else public_counts,
        "suppression_reason": (
            "staten_cross_version_protection"
            if staten
            else "small_positive_cell_1_to_4"
            if small_cell
            else None
        ),
        "label_status": "unqualified",
        "sale_labels_certified": 0,
    }
