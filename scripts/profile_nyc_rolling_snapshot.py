"""Profile a frozen NYC rolling CSV without publishing row-level source data.

The result is an inventory and audit-sampling aid, not sale eligibility evidence.
The source file remains private. Positive prices at or below USD 1,000 are a
review bucket only and never an exclusion rule.
"""

from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from io import TextIOWrapper
import json
import os
from pathlib import Path, PureWindowsPath
import re
from uuid import uuid4


PRIVATE_ROOT = Path(__file__).resolve().parents[1] / "data" / "raw" / "nyc_dof"
APPROVED_SNAPSHOT_SHA256 = (
    "84c06057c52a2822f982cd98fb77ef7edf2c14134d00f46b073d2e4b762b2ef2"
)
MAX_MANIFEST_BYTES = 64 * 1024
MAX_CSV_BYTES = 128 * 1024 * 1024
MAX_ROWS = 150_000
HEADER = (
    "BOROUGH",
    "NEIGHBORHOOD",
    "BUILDING CLASS CATEGORY",
    "TAX CLASS AT PRESENT",
    "BLOCK",
    "LOT",
    "EASE-MENT",
    "BUILDING CLASS AT PRESENT",
    "ADDRESS",
    "APARTMENT NUMBER",
    "ZIP CODE",
    "RESIDENTIAL UNITS",
    "COMMERCIAL UNITS",
    "TOTAL UNITS",
    "LAND SQUARE FEET",
    "GROSS SQUARE FEET",
    "YEAR BUILT",
    "TAX CLASS AT TIME OF SALE",
    "BUILDING CLASS AT TIME OF SALE",
    "SALE PRICE",
    "SALE DATE",
)
BOROUGHS = ("1", "2", "3", "4", "5", "unknown")
CLASSES = ("A", "R", "other", "missing")
PRICE_STATES = ("positive", "zero", "negative", "invalid", "missing")
NUMBER_PATTERN = re.compile(r"-?(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)(?:\.[0-9]+)?\Z")
SHA_PATTERN = re.compile(r"[0-9a-f]{64}\Z")


def _private_root() -> Path:
    root = PRIVATE_ROOT.absolute()
    for candidate in (root, *root.parents):
        if candidate.is_symlink() or (
            candidate.exists()
            and os.path.normcase(str(candidate.resolve()))
            != os.path.normcase(str(candidate))
        ):
            raise ValueError(
                "Private root or ancestor redirects outside local raw data"
            )
    return root.resolve(strict=True)


def _basename(value: object) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value in (".", "..")
        or Path(value).name != value
        or PureWindowsPath(value).name != value
        or "/" in value
        or "\\" in value
    ):
        raise ValueError("Snapshot raw filename must be a private basename")
    return value


def _manifest(path: Path) -> dict:
    with path.open("rb") as source:
        body = source.read(MAX_MANIFEST_BYTES + 1)
    if len(body) > MAX_MANIFEST_BYTES:
        raise ValueError("Snapshot manifest exceeds byte limit")
    try:
        manifest = json.loads(body)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("Snapshot manifest is invalid JSON") from error
    if not isinstance(manifest, dict):
        raise ValueError("Snapshot manifest must be an object")
    if (
        manifest.get("source_id") != "nyc_dof_rolling_usep_8jbt"
        or manifest.get("capture_status") != "inventory_only_not_asof_eligible"
        or manifest.get("header_kind") != "name"
    ):
        raise ValueError("Snapshot manifest identifies an incompatible source")
    _basename(manifest.get("raw_filename"))
    if not isinstance(manifest.get("sha256"), str) or not SHA_PATTERN.fullmatch(
        manifest["sha256"]
    ):
        raise ValueError("Snapshot manifest has invalid SHA-256")
    if manifest["sha256"] != APPROVED_SNAPSHOT_SHA256:
        raise ValueError("Snapshot SHA-256 is not the pre-registered NYC revision")
    if any(
        type(manifest.get(key)) is not int or manifest[key] < 0
        for key in ("bytes", "rows")
    ):
        raise ValueError("Snapshot manifest has invalid byte or row count")
    if manifest["bytes"] > MAX_CSV_BYTES:
        raise ValueError("Snapshot manifest exceeds CSV byte limit")
    if manifest["rows"] > MAX_ROWS:
        raise ValueError("Snapshot manifest exceeds row limit")
    return manifest


def _number(value: str) -> tuple[str, Decimal | None]:
    stripped = value.strip()
    if not stripped:
        return "missing", None
    if not NUMBER_PATTERN.fullmatch(stripped):
        return "invalid", None
    try:
        number = Decimal(stripped.replace(",", ""))
    except InvalidOperation:
        return "invalid", None
    if number > 0:
        return "positive", number
    if number < 0:
        return "negative", number
    return "zero", number


def _month(value: str) -> str | None:
    stripped = value.strip()
    if not stripped:
        return None
    for parser in (date.fromisoformat, datetime.fromisoformat):
        try:
            return parser(stripped).strftime("%Y-%m")
        except ValueError:
            pass
    try:
        return datetime.strptime(stripped, "%m/%d/%Y").strftime("%Y-%m")
    except ValueError:
        return None


def _class_at_sale(value: str) -> str:
    stripped = value.strip().upper()
    if not stripped:
        return "missing"
    if stripped.startswith("A"):
        return "A"
    if stripped.startswith("R"):
        return "R"
    return "other"


def _new_profile() -> dict:
    return {
        "rows": 0,
        "borough_counts": dict.fromkeys(BOROUGHS, 0),
        "building_class_prefix_counts": dict.fromkeys(CLASSES, 0),
        "sale_price_parse_state": dict.fromkeys(PRICE_STATES, 0),
        "missing_area_counts": {"gross": 0, "land": 0},
        "gross_area_review_buckets": {"missing": 0, "nonpositive": 0, "invalid": 0},
        "price_review_buckets": {
            "zero": 0,
            "positive_at_most_1000": 0,
            "negative": 0,
            "invalid": 0,
            "missing": 0,
        },
        "identity_review_buckets": {
            "missing_block": 0,
            "missing_lot": 0,
            "r_class_missing_apartment": 0,
        },
        "apartment_missing_by_class": {
            category: {"rows": 0, "missing": 0} for category in CLASSES
        },
        "screening_by_borough_and_class": {
            borough: {
                category: {
                    "rows": 0,
                    "positive_price": 0,
                    "positive_price_with_gross_area": 0,
                }
                for category in CLASSES
            }
            for borough in BOROUGHS
        },
        "one_family_by_borough": {
            borough: {"candidate": 0, "other_or_ambiguous": 0} for borough in BOROUGHS
        },
        "one_family_class_disagreements": 0,
    }


def _add_row(
    profile: dict, values: dict[str, str], keys: Counter, months: Counter
) -> None:
    profile["rows"] += 1
    borough_raw = values["BOROUGH"].strip()
    borough = borough_raw if borough_raw in BOROUGHS[:-1] else "unknown"
    category = _class_at_sale(values["BUILDING CLASS AT TIME OF SALE"])
    price_state, price = _number(values["SALE PRICE"])
    gross_state, _ = _number(values["GROSS SQUARE FEET"])
    land_missing = not values["LAND SQUARE FEET"].strip()
    apartment_missing = not values["APARTMENT NUMBER"].strip()
    class_category_one_family = (
        values["BUILDING CLASS CATEGORY"].strip().upper().startswith("01 ONE FAMILY")
    )
    cell = profile["screening_by_borough_and_class"][borough][category]

    profile["borough_counts"][borough] += 1
    profile["building_class_prefix_counts"][category] += 1
    profile["sale_price_parse_state"][price_state] += 1
    profile["apartment_missing_by_class"][category]["rows"] += 1
    cell["rows"] += 1
    if price_state == "positive":
        cell["positive_price"] += 1
        if gross_state == "positive":
            cell["positive_price_with_gross_area"] += 1
        if price <= Decimal("1000"):
            profile["price_review_buckets"]["positive_at_most_1000"] += 1
    else:
        profile["price_review_buckets"][price_state] += 1
    if gross_state == "missing":
        profile["missing_area_counts"]["gross"] += 1
        profile["gross_area_review_buckets"]["missing"] += 1
    elif gross_state in ("zero", "negative"):
        profile["gross_area_review_buckets"]["nonpositive"] += 1
    elif gross_state == "invalid":
        profile["gross_area_review_buckets"]["invalid"] += 1
    if land_missing:
        profile["missing_area_counts"]["land"] += 1
    if apartment_missing:
        profile["apartment_missing_by_class"][category]["missing"] += 1
        if category == "R":
            profile["identity_review_buckets"]["r_class_missing_apartment"] += 1
    one_family_group = (
        "candidate"
        if category == "A" and class_category_one_family
        else "other_or_ambiguous"
    )
    profile["one_family_by_borough"][borough][one_family_group] += 1
    if (category == "A") != class_category_one_family:
        profile["one_family_class_disagreements"] += 1

    block, lot = values["BLOCK"].strip(), values["LOT"].strip()
    if not block:
        profile["identity_review_buckets"]["missing_block"] += 1
    if not lot:
        profile["identity_review_buckets"]["missing_lot"] += 1
    duplicate_key = (
        borough_raw,
        block,
        lot,
        values["SALE DATE"].strip(),
        values["SALE PRICE"].strip(),
    )
    if all(duplicate_key):
        keys[duplicate_key] += 1
    else:
        profile["incomplete_duplicate_key_rows"] += 1
    month = _month(values["SALE DATE"])
    if month is None:
        profile["invalid_or_missing_sale_month"] += 1
    else:
        months[month] += 1


def _profile_csv(source, expected_rows: int) -> dict:
    profile = _new_profile()
    profile["incomplete_duplicate_key_rows"] = 0
    profile["invalid_or_missing_sale_month"] = 0
    keys: Counter = Counter()
    months: Counter = Counter()
    try:
        with TextIOWrapper(source, encoding="utf-8-sig", newline="") as text_source:
            reader = csv.reader(text_source, strict=True)
            if tuple(next(reader, ())) != HEADER:
                raise ValueError("NYC CSV header differs from pinned 21-column schema")
            for record in reader:
                if len(record) != len(HEADER):
                    raise ValueError("NYC CSV row has wrong field count")
                if profile["rows"] >= MAX_ROWS:
                    raise ValueError("NYC CSV exceeds row limit")
                _add_row(profile, dict(zip(HEADER, record, strict=True)), keys, months)
    except (csv.Error, UnicodeError) as error:
        raise ValueError("NYC CSV cannot be parsed") from error
    if profile["rows"] != expected_rows:
        raise ValueError("Snapshot row count differs from manifest")

    repeated = [count for count in keys.values() if count > 1]
    profile["exact_source_string_duplicate_candidates"] = {
        "complete_key_rows": sum(keys.values()),
        "incomplete_key_rows": profile.pop("incomplete_duplicate_key_rows"),
        "repeated_groups": len(repeated),
        "rows_in_repeated_groups": sum(repeated),
        "excess_rows": sum(count - 1 for count in repeated),
    }
    profile["sale_month_bounds"] = {
        "oldest": min(months) if months else None,
        "oldest_rows": months[min(months)] if months else 0,
        "newest": max(months) if months else None,
        "newest_rows": months[max(months)] if months else 0,
        "invalid_or_missing": profile.pop("invalid_or_missing_sale_month"),
    }
    return profile


def _write_private(output: Path, result: dict, root: Path) -> None:
    if output.parent.resolve(strict=True) != root or output.suffix != ".json":
        raise ValueError("Profile output must be a JSON file inside private raw data")
    if output.exists() or output.is_symlink():
        raise FileExistsError("Profile output already exists")
    temp = root / f".nyc-profile-{uuid4().hex}.part"
    try:
        with temp.open("x", encoding="utf-8", newline="\n") as sink:
            json.dump(result, sink, sort_keys=True, indent=2)
            sink.write("\n")
            sink.flush()
            os.fsync(sink.fileno())
        os.link(temp, output)
    finally:
        temp.unlink(missing_ok=True)


def profile_snapshot(snapshot_path: Path, output_path: Path) -> dict:
    """Verify the private file, stream rows and save only aggregate counters."""
    root = _private_root()
    output = Path(output_path).absolute()
    if output.parent.resolve(strict=True) != root:
        raise ValueError("Profile output must remain inside private raw data")
    manifest = _manifest(Path(snapshot_path))
    raw = root / _basename(manifest["raw_filename"])
    if raw.is_symlink() or not raw.is_file():
        raise ValueError("Snapshot raw file must be a private regular file")
    with raw.open("rb") as source:
        digest = sha256()
        byte_count = 0
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            byte_count += len(chunk)
            if byte_count > MAX_CSV_BYTES:
                raise ValueError("Snapshot CSV exceeds byte limit")
            digest.update(chunk)
        if byte_count != manifest["bytes"]:
            raise ValueError("Snapshot byte count differs from manifest")
        if digest.hexdigest() != manifest["sha256"]:
            raise ValueError("Snapshot SHA-256 differs from manifest")
        source.seek(0)
        result = _profile_csv(source, manifest["rows"])
    result = {
        "source_id": "nyc_dof_rolling_usep_8jbt",
        "snapshot_sha256": manifest["sha256"],
        "status": "source_inventory_only_not_sale_eligibility",
        "positive_at_most_1000_rule": "investigative USD bucket; no row exclusion",
        "duplicate_key_policy": (
            "trim-only on raw BOROUGH, BLOCK, LOT, SALE DATE, SALE PRICE; "
            "no semantic normalization"
        ),
        **result,
    }
    _write_private(output, result, root)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(profile_snapshot(args.snapshot, args.output), sort_keys=True))


if __name__ == "__main__":
    main()
