"""Build a narrow, retrospective Indiana single-family sale research cohort."""

from __future__ import annotations

import csv
import hashlib
import io
import math
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from zipfile import ZipFile

SPECIAL_FLAGS = (
    "B3_Vacant_Land",
    "B4_Trade",
    "B5_Land_Contract",
    "B6_Partial_Interest",
    "B7_Easement",
    "B8_Court_Order",
    "B9_Partition",
    "B10_Charity",
    "C1_Sheriff_Sale",
    "C2_Short_Sale",
    "C3_Quitclaim",
    "C4_Auction",
    "C6_Multiple_Forms",
)
ADDITIONAL_SPECIAL_FLAGS = (
    "G11_Special_Relationship",
    "G11_Special_Foreclosure",
    "G11_Special_Auction",
    "G11_Special_Trade",
    "G11_Special_Partial",
)
DISCLOSURE_FIELDS = (
    "SDF_ID",
    "Unique_Sales_ID",
    "County_ID",
    "P2_13_Date_Sale",
    "E1_Sales_Price",
    "E2_PersProp",
    "E4_Relationship_Discount",
    "C9_Num_Parcels",
    "C10_Residential_Property",
    "B1_Valuable_Consider",
    *SPECIAL_FLAGS,
    *ADDITIONAL_SPECIAL_FLAGS,
)
PARCEL_FIELDS = (
    "SDF_ID",
    "A4_Improvement",
    "A5_ZipCode",
    "P2_6_Prop_Class_Code",
    "P2_9_Acreage",
)
MODEL_FEATURES = ("County_ID", "A5_ZipCode", "P2_9_Acreage")
ONE_FAMILY_CODES = frozenset(str(code) for code in range(510, 516))
MAX_MEMBER_BYTES = 1_000_000_000


@dataclass(frozen=True)
class Sale:
    row_id: str
    sale_date: date
    price: Decimal
    county_id: str
    zipcode: str
    acreage: float | None


@dataclass(frozen=True)
class _Candidate:
    form_id: str
    economic_id: str
    county_id: str
    sale_date: date
    price: Decimal


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _rows(archive: ZipFile, member: str, required: Sequence[str]):
    try:
        info = archive.getinfo(member)
    except KeyError as error:
        raise ValueError(f"Indiana archive is missing {member}") from error
    if info.file_size > MAX_MEMBER_BYTES:
        raise ValueError(f"Indiana archive member {member} exceeds size limit")
    with (
        archive.open(info) as raw,
        io.TextIOWrapper(raw, encoding="utf-16", newline="") as text,
    ):
        reader = csv.DictReader(text, delimiter="\t")
        if reader.fieldnames is None or not set(required) <= set(reader.fieldnames):
            raise ValueError(f"Indiana {member} schema is incompatible")
        yield from reader


def _fixed_decimal(value: str | None, scale: int) -> Decimal | None:
    """Decode an integer source field with an implied decimal scale."""
    text = (value or "").strip()
    if not re.fullmatch(r"-?\d+", text):
        return None
    try:
        return Decimal(text) / Decimal(scale)
    except InvalidOperation:
        return None


def _parse_candidate(
    row: Mapping[str, str], year: int
) -> tuple[_Candidate | None, str | None]:
    price = _fixed_decimal(row["E1_Sales_Price"], 100)
    if price is None or price <= 0:
        return None, "invalid_price"
    try:
        sale_date = date.fromisoformat(row["P2_13_Date_Sale"].strip())
    except ValueError:
        return None, "invalid_sale_date"
    if sale_date.year != year:
        return None, "outside_year"
    if not re.fullmatch(r"\d{1,3}", row["County_ID"].strip()):
        return None, "invalid_county"
    if row["B1_Valuable_Consider"].strip() != "Y":
        return None, "no_valuable_consideration"
    if row["C10_Residential_Property"].strip() != "Y":
        return None, "nonresidential"
    if row["C9_Num_Parcels"].strip() != "1":
        return None, "declared_multiparcel"
    if any(row[name].strip() != "N" for name in SPECIAL_FLAGS):
        return None, "special_transfer"
    if any(row[name].strip() == "Y" for name in ADDITIONAL_SPECIAL_FLAGS):
        return None, "special_transfer"
    if _fixed_decimal(row["E2_PersProp"], 100) != 0:
        return None, "personal_property"
    if _fixed_decimal(row["E4_Relationship_Discount"], 100) != 0:
        return None, "relationship_discount"
    return _Candidate(
        form_id=row["SDF_ID"].strip(),
        economic_id=row["Unique_Sales_ID"].strip(),
        county_id=row["County_ID"].strip(),
        sale_date=sale_date,
        price=price,
    ), None


def _parcel_reason(row: Mapping[str, str]) -> str | None:
    if row["P2_6_Prop_Class_Code"].strip() not in ONE_FAMILY_CODES:
        return "property_class"
    if row["A4_Improvement"].strip() != "Y":
        return "no_improvement"
    if not re.fullmatch(r"\d{5}(?:-?\d{4})?", row["A5_ZipCode"].strip()):
        return "invalid_zipcode"
    return None


def read_archive(
    path: Path, expected_sha256: str, *, year: int
) -> tuple[tuple[Sale, ...], dict[str, int]]:
    """Pin source bytes and retain at most one labelled home per economic sale."""
    if year not in (2024, 2025):
        raise ValueError("The research protocol supports only 2024 and 2025")
    if not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        raise ValueError("Expected checksum must be lowercase SHA-256")
    if _file_digest(path) != expected_sha256:
        raise ValueError("Indiana archive checksum mismatch")

    funnel: Counter[str] = Counter()
    economic_counts: Counter[str] = Counter()
    form_counts: Counter[str] = Counter()
    candidates: list[_Candidate] = []
    parcel_counts: Counter[str] = Counter()
    first_parcels: dict[str, dict[str, str]] = {}

    with ZipFile(path) as archive:
        for row in _rows(archive, "SALEDISC.txt", DISCLOSURE_FIELDS):
            funnel["disclosure_rows"] += 1
            form_id = (row.get("SDF_ID") or "").strip()
            economic_id = (row.get("Unique_Sales_ID") or "").strip()
            if form_id:
                form_counts[form_id] += 1
            if economic_id:
                economic_counts[economic_id] += 1
            if None in row or any(value is None for value in row.values()):
                funnel["malformed_disclosure"] += 1
                continue
            if not form_id or not economic_id:
                funnel["missing_identity"] += 1
                continue
            candidate, reason = _parse_candidate(row, year)
            if reason:
                funnel[reason] += 1
            else:
                assert candidate is not None
                candidates.append(candidate)
        candidate_form_ids = {candidate.form_id for candidate in candidates}
        for row in _rows(archive, "SALEPARCEL.txt", PARCEL_FIELDS):
            funnel["parcel_rows"] += 1
            form_id = (row.get("SDF_ID") or "").strip()
            if form_id in candidate_form_ids:
                parcel_counts[form_id] += 1
            if None in row or any(value is None for value in row.values()):
                funnel["malformed_parcel"] += 1
                continue
            if not form_id:
                funnel["malformed_parcel"] += 1
                continue
            if form_id in candidate_form_ids and parcel_counts[form_id] == 1:
                first_parcels[form_id] = {name: row[name] for name in PARCEL_FIELDS}

    eligible: list[Sale] = []
    for candidate in candidates:
        if economic_counts[candidate.economic_id] != 1:
            funnel["duplicate_economic_sale"] += 1
            continue
        if form_counts[candidate.form_id] != 1:
            funnel["duplicate_form"] += 1
            continue
        if (
            parcel_counts[candidate.form_id] != 1
            or candidate.form_id not in first_parcels
        ):
            funnel["parcel_count_mismatch"] += 1
            continue
        parcel = first_parcels[candidate.form_id]
        reason = _parcel_reason(parcel)
        if reason:
            funnel[reason] += 1
            continue
        acres = _fixed_decimal(parcel["P2_9_Acreage"], 10_000)
        acreage = float(acres) if acres is not None and acres >= 0 else None
        if acreage is not None and not math.isfinite(acreage):
            acreage = None
        eligible.append(
            Sale(
                row_id=hashlib.sha256(
                    candidate.economic_id.encode("utf-8")
                ).hexdigest(),
                sale_date=candidate.sale_date,
                price=candidate.price,
                county_id=candidate.county_id,
                zipcode=parcel["A5_ZipCode"].strip()[:5],
                acreage=acreage,
            )
        )
    funnel["eligible"] = len(eligible)
    return tuple(
        sorted(eligible, key=lambda sale: (sale.sale_date, sale.row_id))
    ), dict(funnel)


def split_sales(
    training: Sequence[Sale], validation: Sequence[Sale]
) -> dict[str, tuple[Sale, ...]]:
    """Reject overlap and year drift in the fixed 2024-to-2025 comparison."""
    if not training or not validation:
        raise ValueError("Both research periods need eligible sales")
    train_ids = {sale.row_id for sale in training}
    validation_ids = {sale.row_id for sale in validation}
    if (
        len(train_ids) != len(training)
        or len(validation_ids) != len(validation)
        or train_ids & validation_ids
        or any(sale.sale_date.year != 2024 for sale in training)
        or any(sale.sale_date.year != 2025 for sale in validation)
    ):
        raise ValueError("Indiana split has duplicate IDs, overlap, or wrong years")
    return {"train": tuple(training), "validation": tuple(validation)}


def encode_features(training: Sequence[Sale], validation: Sequence[Sale]):
    """Fit the categorical vocabulary only on 2024 training observations."""
    from sklearn.feature_extraction import DictVectorizer

    if not training:
        raise ValueError("Feature encoder requires training sales")

    def features(sale: Sale) -> dict[str, float | str]:
        return {
            "County_ID": sale.county_id,
            "A5_ZipCode": sale.zipcode,
            "P2_9_Acreage": math.log1p(sale.acreage or 0.0),
            "acreage_missing": float(sale.acreage is None),
        }

    encoder = DictVectorizer(sparse=True)
    train_matrix = encoder.fit_transform(features(sale) for sale in training)
    validation_matrix = encoder.transform(features(sale) for sale in validation)
    return tuple(encoder.get_feature_names_out()), train_matrix, validation_matrix
