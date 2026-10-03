"""Create-only JSON bundle for the synthetic US OFF median baseline.

The caller must retain the returned digest in a trusted, separate manifest.
This bundle is an engineering fixture and is never a certification release.
"""

from __future__ import annotations

from dataclasses import fields
from datetime import datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from typing import Any
from uuid import uuid4

from tabpfn4realestate.data.schema import (
    Attribute,
    ListingEvent,
    Property,
    SourceSnapshot,
    Transaction,
)
from tabpfn4realestate.features.asof import (
    ASSEMBLER_POLICY_VERSION,
    FeatureSnapshot,
)
from tabpfn4realestate.models.off_baseline import (
    CORE_OFF_FEATURES,
    GuardedOffMedian,
    ServingOffMedian,
)


_FORMAT_VERSION = "synthetic_off_median_v2"
_MAX_BUNDLE_BYTES = 1_048_576
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_ENVELOPE_KEYS = frozenset(
    {
        "format_version",
        "model_kind",
        "country",
        "mode",
        "currency",
        "horizon_days",
        "point_semantics",
        "feature_schema_sha256",
        "input_schema_sha256",
        "certification_eligible",
        "model",
    }
)
_MODEL_KEYS = frozenset(
    {
        "amount",
        "train_count",
        "feature_snapshot_hashes_sha256",
        "training_cutoff",
    }
)


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _fingerprint(value: object) -> str:
    return sha256(_canonical_bytes(value)).hexdigest()


def _feature_schema_sha256() -> str:
    definitions = [
        {
            "name": name,
            "dependencies": list(definition.dependencies),
            "modes": list(definition.modes),
        }
        for name, definition in sorted(CORE_OFF_FEATURES.items())
    ]
    return _fingerprint(
        {
            "policy_version": "core_off_synthetic_v1",
            "assembler_policy_version": ASSEMBLER_POLICY_VERSION,
            "fields": definitions,
        }
    )


def _input_schema_sha256() -> str:
    contracts = (
        Property,
        Transaction,
        Attribute,
        ListingEvent,
        SourceSnapshot,
        FeatureSnapshot,
    )
    return _fingerprint(
        {
            "schema_version": "us_synthetic_u1_v2",
            "contracts": [
                {
                    "name": contract.__name__,
                    "fields": [
                        {"name": field.name, "type": str(field.type)}
                        for field in fields(contract)
                    ],
                }
                for contract in contracts
            ],
        }
    )


def _fixed_decimal_width(amount: Decimal) -> int:
    """Count fixed-point characters without expanding a huge exponent."""
    decimal_parts = amount.as_tuple()
    digit_count = len(decimal_parts.digits)
    exponent = decimal_parts.exponent
    if exponent >= 0:
        return digit_count + exponent
    if digit_count + exponent > 0:
        return digit_count + 1
    return 2 - exponent


def _payload(model: GuardedOffMedian) -> dict[str, object]:
    if not isinstance(model, GuardedOffMedian):
        raise TypeError("Expected GuardedOffMedian")
    if _fixed_decimal_width(model.amount) > _MAX_BUNDLE_BYTES:
        raise ValueError("Synthetic bundle exceeds the size limit")
    return {
        "format_version": _FORMAT_VERSION,
        "model_kind": "guarded_off_median",
        "country": "US",
        "mode": "OFF",
        "currency": "USD",
        "horizon_days": 90,
        "point_semantics": "historical_median",
        "feature_schema_sha256": _feature_schema_sha256(),
        "input_schema_sha256": _input_schema_sha256(),
        "certification_eligible": False,
        "model": {
            "amount": format(model.amount, "f"),
            "train_count": len(model.train_row_ids),
            "feature_snapshot_hashes_sha256": _fingerprint(
                list(model.feature_snapshot_hashes)
            ),
            "training_cutoff": model.training_cutoff.isoformat(),
        },
    }


def save_off_median_bundle(model: GuardedOffMedian, path: Path) -> str:
    """Publish a deterministic bundle once and return its exact-byte SHA-256."""
    target = Path(path)
    if not target.parent.is_dir():
        raise FileNotFoundError("Bundle parent directory does not exist")
    encoded = _canonical_bytes(_payload(model))
    if len(encoded) > _MAX_BUNDLE_BYTES:
        raise ValueError("Synthetic bundle exceeds the size limit")
    temporary = target.parent / f".{target.name}.{uuid4().hex}.tmp"
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return sha256(encoded).hexdigest()


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON field: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError(f"Invalid JSON constant: {value}")


def _exact_object(value: object, keys: frozenset[str], name: str) -> dict[str, Any]:
    if type(value) is not dict or set(value) != keys:
        raise ValueError(f"Invalid {name} fields")
    return value


def _validated_payload(value: object) -> ServingOffMedian:
    envelope = _exact_object(value, _ENVELOPE_KEYS, "bundle")
    expected: dict[str, object] = {
        "format_version": _FORMAT_VERSION,
        "model_kind": "guarded_off_median",
        "country": "US",
        "mode": "OFF",
        "currency": "USD",
        "horizon_days": 90,
        "point_semantics": "historical_median",
        "feature_schema_sha256": _feature_schema_sha256(),
        "input_schema_sha256": _input_schema_sha256(),
        "certification_eligible": False,
    }
    for name, required in expected.items():
        if type(envelope[name]) is not type(required) or envelope[name] != required:
            raise ValueError(f"Incompatible synthetic bundle {name}")
    model = _exact_object(envelope["model"], _MODEL_KEYS, "model")
    if type(model["amount"]) is not str or type(model["training_cutoff"]) is not str:
        raise ValueError("Invalid model amount or cutoff")
    if type(model["train_count"]) is not int:
        raise ValueError("Invalid model train count")
    if type(model["feature_snapshot_hashes_sha256"]) is not str:
        raise ValueError("Invalid model feature manifest hash")
    try:
        amount = Decimal(model["amount"])
        cutoff = datetime.fromisoformat(model["training_cutoff"])
    except (InvalidOperation, ValueError) as error:
        raise ValueError("Invalid model amount or cutoff") from error
    return ServingOffMedian(
        amount=amount,
        training_cutoff=cutoff,
        train_count=model["train_count"],
        feature_snapshot_hashes_sha256=model["feature_snapshot_hashes_sha256"],
    )


def load_off_median_bundle(path: Path, *, expected_sha256: str) -> ServingOffMedian:
    """Load only a bounded bundle matching a separately trusted digest."""
    if (
        type(expected_sha256) is not str
        or _SHA256_RE.fullmatch(expected_sha256) is None
    ):
        raise ValueError("Expected SHA-256 must be a lowercase 64-hex digest")
    with Path(path).open("rb") as stream:
        encoded = stream.read(_MAX_BUNDLE_BYTES + 1)
    if len(encoded) > _MAX_BUNDLE_BYTES:
        raise ValueError("Synthetic bundle exceeds the size limit")
    if sha256(encoded).hexdigest() != expected_sha256:
        raise ValueError("Bundle hash mismatch")
    try:
        decoded = encoded.decode("utf-8")
        value = json.loads(
            decoded, object_pairs_hook=_unique_object, parse_constant=_reject_constant
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Invalid synthetic bundle JSON") from error
    return _validated_payload(value)
