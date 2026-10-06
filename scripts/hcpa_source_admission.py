"""Validate the non-row evidence gate before any HCPA model fit."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import sys
from types import MappingProxyType
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
ADMISSION_PATH = ROOT / "data/source_admission/hcpa_allsales_v1.json"
POLICY_PATH = ROOT / "data/model_policies/hcpa_off_absolute_error_v1.json"
MAX_DOCUMENT_BYTES = 64 * 1024
MAX_EVIDENCE_BYTES = 1024 * 1024
MAX_TOTAL_EVIDENCE_BYTES = 4 * 1024 * 1024
HEX = frozenset("0123456789abcdef")
FINDING_TYPES = frozenset(
    {
        "closing_date_semantics",
        "historical_availability",
        "transaction_grouping_and_exclusion",
        "use_rights",
    }
)
EVIDENCE_PREFIX = ("data", "source_evidence", "hcpa")
DECISION_PATH = ("decisions", "0109-hcpa-off-baseline-readiness.md")
ALLOWED_EVIDENCE_SUFFIXES = frozenset({".json", ".md", ".pdf", ".txt", ".yaml", ".yml"})
ARCHIVE_SUFFIXES = frozenset(
    {".7z", ".arff", ".csv", ".dbf", ".gz", ".jsonl", ".parquet", ".tar", ".zip"}
)

ADMISSION_KEYS = frozenset(
    {
        "schema_version",
        "source_id",
        "status",
        "admitted",
        "decision",
        "evidence",
        "findings",
        "requirements",
    }
)
REFERENCE_KEYS = frozenset({"kind", "path", "sha256"})
FINDING_KEYS = frozenset({"type", "status", "evidence_sha256"})
REQUIREMENT_KEYS = frozenset(
    {
        "s_date_is_closing_date",
        "conservative_availability_method",
        "deterministic_grouping_and_exclusion",
        "rights",
    }
)
RIGHTS_KEYS = frozenset(
    {
        "research_training",
        "commercial_training",
        "commercial_serving",
        "derived_artifacts",
        "comparable_display",
    }
)
MODEL = {
    "colsample_bytree": 0.8,
    "learning_rate": 0.05,
    "max_depth": 6,
    "min_child_weight": 10,
    "n_estimators": 250,
    "n_jobs": 4,
    "objective": "reg:absoluteerror",
    "random_state": 42,
    "subsample": 0.8,
    "tree_method": "hist",
}
SEMANTIC_FLAGS = frozenset(
    {
        "closing_date_semantics",
        "historical_availability",
        "transaction_grouping_and_exclusion",
        "property_attributes_as_of",
        "eligibility_codes",
    }
)
POLICY_KEYS = frozenset(
    {
        "schema_version",
        "policy_id",
        "source_id",
        "status",
        "mode",
        "fit_count",
        "target",
        "model",
        "semantic_feature_flags",
        "admission_sha256",
        "execution_constraints",
    }
)


def _pairs_without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("JSON contains a duplicate key")
        result[key] = value
    return result


def _is_hex_sha256(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and set(value) <= HEX


def _has_reparse_attribute(info: os.stat_result) -> bool:
    return bool(getattr(info, "st_file_attributes", 0) & 0x400)


def _bounded_regular_bytes(path: Path, limit: int) -> bytes:
    try:
        named_before = path.lstat()
        if (
            stat.S_ISLNK(named_before.st_mode)
            or not stat.S_ISREG(named_before.st_mode)
            or named_before.st_nlink != 1
            or _has_reparse_attribute(named_before)
        ):
            raise ValueError("Input is not a regular file")
        if named_before.st_size > limit:
            raise ValueError("Input is oversized")
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        try:
            opened = os.fstat(descriptor)
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_nlink != 1
                or _has_reparse_attribute(opened)
                or opened.st_size > limit
                or (opened.st_dev, opened.st_ino)
                != (named_before.st_dev, named_before.st_ino)
            ):
                raise ValueError("Input changed while opening")
            chunks: list[bytes] = []
            remaining = limit + 1
            while remaining:
                chunk = os.read(descriptor, min(64 * 1024, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            content = b"".join(chunks)
            opened_after = os.fstat(descriptor)
            named_after = path.stat(follow_symlinks=False)
            if (
                (opened.st_dev, opened.st_ino, opened.st_size)
                != (opened_after.st_dev, opened_after.st_ino, opened_after.st_size)
                or (opened.st_dev, opened.st_ino)
                != (named_after.st_dev, named_after.st_ino)
                or len(content) != opened.st_size
            ):
                raise ValueError("Input changed while reading")
        finally:
            os.close(descriptor)
    except ValueError:
        raise
    except OSError as exc:
        raise ValueError("Input is unavailable") from exc
    if len(content) > limit:
        raise ValueError("Input is oversized")
    return content


def _json_bytes(content: bytes) -> dict[str, Any]:
    try:
        value = json.loads(
            content.decode("utf-8"), object_pairs_hook=_pairs_without_duplicates
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("JSON document is invalid") from exc
    if not isinstance(value, dict):
        raise ValueError("JSON root must be an object")
    return value


def load_admission(path: Path) -> dict[str, Any]:
    """Load one bounded, duplicate-key-free admission document."""
    return _json_bytes(_bounded_regular_bytes(path, MAX_DOCUMENT_BYTES))


def _evidence_path(reference: Mapping[str, Any], root: Path) -> Path:
    if set(reference) != REFERENCE_KEYS:
        raise ValueError("Evidence reference schema differs")
    kind, raw_path, digest = (
        reference["kind"],
        reference["path"],
        reference["sha256"],
    )
    if (
        not isinstance(kind, str)
        or kind not in {"decision", "evidence"}
        or not _is_hex_sha256(digest)
    ):
        raise ValueError("Evidence reference is invalid")
    if not isinstance(raw_path, str) or "\\" in raw_path:
        raise ValueError("Evidence reference is invalid")
    relative = PurePosixPath(raw_path)
    if relative.is_absolute() or ".." in relative.parts or not relative.parts:
        raise ValueError("Evidence reference is invalid")
    parts = relative.parts
    if kind == "decision":
        if parts != DECISION_PATH:
            raise ValueError("Decision reference is outside the frozen decision")
    elif parts[: len(EVIDENCE_PREFIX)] != EVIDENCE_PREFIX:
        raise ValueError("Reference is not a dedicated HCPA evidence path")
    suffix = relative.suffix.lower()
    if suffix not in ALLOWED_EVIDENCE_SUFFIXES or suffix in ARCHIVE_SUFFIXES:
        raise ValueError("Reference is not a non-row evidence path")
    try:
        root_absolute = root.resolve(strict=True)
        root_info = root.lstat()
    except OSError as exc:
        raise ValueError("Evidence root is unavailable") from exc
    if (
        root.is_symlink()
        or _has_reparse_attribute(root_info)
        or root_absolute != root.absolute()
    ):
        raise ValueError("Evidence root is not a regular directory")
    candidate = root_absolute.joinpath(*parts)
    current = root_absolute
    for component in parts[:-1]:
        current = current / component
        try:
            component_info = current.stat(follow_symlinks=False)
        except (FileNotFoundError, OSError) as exc:
            raise ValueError("Input is unavailable") from exc
        if (
            current.is_symlink()
            or _has_reparse_attribute(component_info)
            or not stat.S_ISDIR(component_info.st_mode)
        ):
            raise ValueError("Evidence path contains a linked directory")
    try:
        candidate.resolve(strict=True).relative_to(root_absolute)
    except FileNotFoundError as exc:
        raise ValueError("Input is unavailable") from exc
    except OSError as exc:
        raise ValueError("Input is unavailable") from exc
    except ValueError as exc:
        raise ValueError("Evidence reference escapes project root") from exc
    return candidate


def _parent_snapshot(path: Path, root: Path) -> tuple[tuple[object, ...], ...]:
    """Snapshot each approved parent; same-privilege hostile races are out of scope."""
    try:
        root_absolute = root.resolve(strict=True)
        relative = path.absolute().relative_to(root_absolute)
    except (FileNotFoundError, OSError, ValueError) as exc:
        raise ValueError("Input escapes its approved root") from exc
    directories = [root_absolute]
    current = root_absolute
    for component in relative.parts[:-1]:
        current /= component
        directories.append(current)
    snapshot: list[tuple[object, ...]] = []
    for directory in directories:
        try:
            info = directory.stat(follow_symlinks=False)
        except OSError as exc:
            raise ValueError("Input parent is unavailable") from exc
        if (
            directory.is_symlink()
            or _has_reparse_attribute(info)
            or not stat.S_ISDIR(info.st_mode)
        ):
            raise ValueError("Input parent redirects")
        snapshot.append(
            (
                os.path.normcase(str(directory)),
                info.st_dev,
                info.st_ino,
                info.st_mode,
                info.st_nlink,
                getattr(info, "st_file_attributes", 0),
            )
        )
    return tuple(snapshot)


def _read_under_root(path: Path, root: Path, limit: int) -> bytes:
    before = _parent_snapshot(path, root)
    content = _bounded_regular_bytes(path, limit)
    after = _parent_snapshot(path, root)
    if before != after:
        raise ValueError("Input parent changed while reading")
    return content


def _validate_reference(reference: Mapping[str, Any], root: Path) -> tuple[str, int]:
    path = _evidence_path(reference, root)
    content = _read_under_root(path, root, MAX_EVIDENCE_BYTES)
    digest = hashlib.sha256(content).hexdigest()
    if digest != reference["sha256"]:
        raise ValueError("Evidence hash differs")
    return digest, len(content)


def _validate_requirements(value: object) -> tuple[bool, bool]:
    if not isinstance(value, dict) or set(value) != REQUIREMENT_KEYS:
        raise ValueError("Admission requirements schema differs")
    for key in REQUIREMENT_KEYS - {"rights"}:
        if type(value[key]) is not bool:
            raise ValueError("Admission requirement is not boolean")
    rights = value["rights"]
    if not isinstance(rights, dict) or set(rights) != RIGHTS_KEYS:
        raise ValueError("Rights schema differs")
    if any(type(rights[key]) is not bool for key in RIGHTS_KEYS):
        raise ValueError("Rights decision is not boolean")
    required = all(value[key] for key in REQUIREMENT_KEYS - {"rights"}) and all(
        rights[key] for key in RIGHTS_KEYS - {"comparable_display"}
    )
    return required, rights["comparable_display"]


def validate_document(document: object, root: Path = ROOT) -> Mapping[str, object]:
    """Validate exact evidence and compute a fail-closed admission result."""
    if not isinstance(document, dict) or set(document) != ADMISSION_KEYS:
        raise ValueError("Admission schema differs")
    status = document["status"]
    admitted = document["admitted"]
    if not isinstance(status, str) or type(admitted) is not bool:
        raise ValueError("Admission metadata differs")
    if status == "admitted" or admitted:
        raise ValueError("authoritative_acceptance_not_implemented")
    if (
        document["schema_version"] != "hcpa_source_admission_v1"
        or document["source_id"] != "hillsborough_hcpa_allsales"
        or status not in {"pending", "rejected"}
    ):
        raise ValueError("Admission metadata differs")
    decision = document["decision"]
    evidence = document["evidence"]
    if not isinstance(decision, dict) or not isinstance(evidence, list):
        raise ValueError("Evidence collection is invalid")
    references = [decision, *evidence]
    if any(not isinstance(item, dict) for item in references):
        raise ValueError("Evidence collection is invalid")
    if decision.get("kind") != "decision":
        raise ValueError("Decision reference is invalid")
    if any(item.get("kind") != "evidence" for item in evidence):
        raise ValueError("Evidence list kind is invalid")
    hashes: set[str] = set()
    evidence_hashes: set[str] = set()
    total_bytes = 0
    for reference in references:
        digest, size = _validate_reference(reference, root)
        if digest in hashes:
            raise ValueError("Evidence has a duplicate evidence hash")
        hashes.add(digest)
        if reference["kind"] == "evidence":
            evidence_hashes.add(digest)
        total_bytes += size
        if total_bytes > MAX_TOTAL_EVIDENCE_BYTES:
            raise ValueError("Cumulative evidence is oversized")

    findings = document["findings"]
    if not isinstance(findings, list) or len(findings) != 4:
        raise ValueError("Admission needs exactly four findings")
    finding_types: set[str] = set()
    for finding in findings:
        if not isinstance(finding, dict) or set(finding) != FINDING_KEYS:
            raise ValueError("Finding schema differs")
        finding_type = finding["type"]
        status = finding["status"]
        references_for_finding = finding["evidence_sha256"]
        if not isinstance(finding_type, str) or not isinstance(status, str):
            raise ValueError("Finding values are invalid")
        finding_types.add(finding_type)
        if status not in {"unknown", "verified"}:
            raise ValueError("Finding status is invalid")
        if not isinstance(references_for_finding, list) or any(
            not _is_hex_sha256(value) for value in references_for_finding
        ):
            raise ValueError("Finding evidence hashes are invalid")
        if len(set(references_for_finding)) != len(references_for_finding):
            raise ValueError("Finding has duplicate evidence hashes")
        if any(value not in evidence_hashes for value in references_for_finding):
            raise ValueError("Finding has an unknown evidence hash")
        if status == "verified" and not references_for_finding:
            raise ValueError("A verified finding needs evidence")
    if finding_types != FINDING_TYPES:
        raise ValueError("Admission finding types differ")

    _validate_requirements(document["requirements"])
    return MappingProxyType(
        {
            "source_id": document["source_id"],
            "status": document["status"],
            "source_admitted": False,
            "comparable_display_permitted": False,
        }
    )


def validate_policy(policy: object) -> None:
    """Validate the exact predeclared single-fit policy without running it."""
    if not isinstance(policy, dict) or set(policy) != POLICY_KEYS:
        raise ValueError("Model policy schema differs")
    if (
        policy["schema_version"] != "hcpa_model_policy_v1"
        or policy["policy_id"] != "hcpa_off_absolute_error_v1"
        or policy["source_id"] != "hillsborough_hcpa_allsales"
        or policy["status"] != "pending_source_admission"
        or policy["mode"] != "OFF"
        or type(policy["fit_count"]) is not int
        or policy["fit_count"] != 1
        or policy["target"]
        != {
            "field": "S_AMT",
            "transformation": "log",
            "point_estimate_semantics": "median_like",
        }
    ):
        raise ValueError("Model policy metadata differs")
    if policy["model"] != MODEL:
        raise ValueError("Model configuration differs")
    flags = policy["semantic_feature_flags"]
    if (
        not isinstance(flags, dict)
        or set(flags) != SEMANTIC_FLAGS
        or any(not isinstance(value, str) for value in flags.values())
        or set(flags.values()) != {"pending"}
    ):
        raise ValueError("Semantic feature flags differ")
    if not _is_hex_sha256(policy["admission_sha256"]):
        raise ValueError("Admission hash is invalid")
    if policy["execution_constraints"] != {
        "train_only_if_admitted": True,
        "one_registered_fit": True,
        "no_raw_access_in_validator": True,
    }:
        raise ValueError("Execution constraints differ")


def validate_files(
    admission_path: Path, policy_path: Path, root: Path = ROOT
) -> Mapping[str, object]:
    admission_bytes = _read_under_root(admission_path, root, MAX_DOCUMENT_BYTES)
    document = _json_bytes(admission_bytes)
    result = validate_document(document, root)
    policy = _json_bytes(_read_under_root(policy_path, root, MAX_DOCUMENT_BYTES))
    validate_policy(policy)
    if hashlib.sha256(admission_bytes).hexdigest() != policy["admission_sha256"]:
        raise ValueError("Model policy admission hash differs")
    return MappingProxyType(
        {
            **result,
            "model_fit_permitted": False,
            "fit_readiness_status": "blocked",
            "fit_readiness_blockers": (
                "semantic_feature_flags_pending",
                "historical_property_attributes_pending",
                "eligibility_rules_pending",
            ),
        }
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    try:
        result = validate_files(ADMISSION_PATH, POLICY_PATH, ROOT)
    except (TypeError, ValueError):
        print("HCPA admission validation failed", file=sys.stderr)
        return 2
    print(json.dumps(dict(result), sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
