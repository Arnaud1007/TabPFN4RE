"""Inspect fixed aggregate fields in the pinned NYC v2 result, without source rows."""

from __future__ import annotations

import argparse
import copy
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import diagnose_nyc_representations_v2 as v2
import nyc_representation_core as core
from private_review_io import secure_directory, verify_acl

PROJECT_ROOT = v2.PROJECT_ROOT
PRIVATE_ROOT = v2.PRIVATE_ROOT
V2_DIR = PRIVATE_ROOT / "representation-diagnostic-v2-20260930T152830Z-460cba306f9d"
ENVIRONMENT_LOCK = PROJECT_ROOT / "locks/nyc-v2-field-diagnostic-environment.json"
TRACKED_V2_PUBLIC = (
    PROJECT_ROOT / "runs/u0-nyc-representation-v2-20260930T152830Z/aggregate.json"
)
V1_PUBLIC_PATH = (
    PROJECT_ROOT / "runs/u0-nyc-row-concordance-v1-20260930T132740Z/aggregate.json"
)
V1_PUBLIC_SHA = "4d52add2b6a65df050c9bf0a920e0f9ccc4e7fad8959f1d7e6c1154fb84ea524"
V2_CODE_COMMIT = "cbbc14e3f3351b75a32956e4841f219fba314745"
V2_ARTIFACT_SHA = {
    "intent.json": "1b87392277fd57298192bbd037c0b3f5805b0119554bdcac4a90a41e45e6624a",
    "result.json": "2b7b7643c6b07a763e0e3cd842b5f60b2819805acb50341d485c7aa910141199",
    "public.json": "e3ae01bd7d551a66cf84f8862668e90f0a4071c3352ce8ac622d22938c4d766f",
    "hash_manifest.json": "a0cba0b35b4d9cc683d2df64119d05f16212e74cf372a7735b640443fe222fe1",
}
PROTOCOL = "nyc-dof-v2-field-diagnostic-v1"
APPROVED_ORIGIN_URL = "https://github.com/Arnaud1007/TabPFN4RE.git"
SELECTED = v2.SELECTED
FIELD_NAMES = (
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
MAX_PRIVATE_RESULT_BYTES = 64 * 1024 * 1024
CODE_PATHS = ("scripts/diagnose_nyc_representation_fields_v1.py",)
SOURCE_HASH_FIELDS = (
    "capture_manifest_sha256",
    "csv_snapshot_sha256",
    "v3_result_sha256",
    "v1_result_sha256",
)

_sha = v2._sha
_json_bytes = v2._json_bytes
_publish_json = v2._publish_json
_provenance = v2._provenance


def _tracked_public(path: Path, expected_sha: str) -> dict:
    body = v2.v1._pinned_bytes(path, 1024 * 1024, expected_sha, "tracked public")
    return v2._parse_pinned(body, "tracked public")


def _preflight() -> dict:
    """Inspect tracked files only; protected v2 evidence stays unopened."""
    if FIELD_NAMES != tuple(v2.v1.profile.HEADER):
        raise ValueError("Pinned NYC field order differs")
    lock = v2.v1._pinned_bytes(ENVIRONMENT_LOCK, 64 * 1024, None, "environment lock")
    v2._parse_pinned(lock, "environment lock")
    v1_public = _tracked_public(V1_PUBLIC_PATH, V1_PUBLIC_SHA)
    v2_public = _tracked_public(TRACKED_V2_PUBLIC, V2_ARTIFACT_SHA["public.json"])
    expected = [name for name, _, _ in SELECTED]
    for public in (v1_public, v2_public):
        boroughs = public.get("boroughs")
        if (
            not isinstance(boroughs, list)
            or [item.get("borough") for item in boroughs] != expected
        ):
            raise ValueError("Tracked borough frame differs")
        if public.get("sale_labels_certified") != 0:
            raise ValueError("Tracked label status differs")
    return {
        "environment_lock_sha256": _sha(lock),
        "v1_public": v1_public,
        "v2_public": v2_public,
        "source_hashes": {name: v2_public[name] for name in SOURCE_HASH_FIELDS},
        "v1_public_sha256": V1_PUBLIC_SHA,
        "v2_result_sha256": V2_ARTIFACT_SHA["result.json"],
        "v2_public_sha256": V2_ARTIFACT_SHA["public.json"],
    }


def _code_hashes() -> dict[str, str]:
    return {
        **v2._code_hashes(),
        **{
            name: _sha(
                v2.v1._pinned_bytes(PROJECT_ROOT / name, 1024 * 1024, None, "code file")
            )
            for name in CODE_PATHS
        },
    }


def _remote_pushed(commit: str) -> bool:
    origin = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    ).stdout.strip()
    if origin != APPROVED_ORIGIN_URL:
        return False
    branch = subprocess.run(
        ["git", "branch", "--show-current"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    ).stdout.strip()
    if not branch or not re.fullmatch(r"[A-Za-z0-9._/-]+", branch):
        return False
    remote = subprocess.run(
        ["git", "ls-remote", "--exit-code", "origin", f"refs/heads/{branch}"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return remote.returncode == 0 and remote.stdout.split("\t", 1)[0] == commit


def _run_dir(directory: Path, *, new: bool) -> Path:
    target = Path(directory).absolute()
    v2.v1.earlier._check_ancestors(PRIVATE_ROOT)
    v2.v1.earlier._check_ancestors(target)
    match = re.fullmatch(
        r"field-diagnostic-v1-(\d{8}T\d{6}Z)-([0-9a-f]{12})", target.name
    )
    if target.parent != PRIVATE_ROOT.absolute() or match is None:
        raise ValueError("Field run path is outside private NYC root")
    try:
        datetime.strptime(match.group(1), "%Y%m%dT%H%M%SZ")
    except ValueError as error:
        raise ValueError("Field run ID is invalid") from error
    if not PRIVATE_ROOT.is_dir():
        raise ValueError("Private NYC root is missing")
    verify_acl(PRIVATE_ROOT)
    if new and (target.exists() or v2.v1.earlier._reparse(target)):
        raise FileExistsError("Field run already exists")
    if not new and not target.is_dir():
        raise ValueError("Field run does not exist")
    return target


def _verify_v2() -> tuple[dict, dict]:
    """Validate pinned private artifacts without exposing ledger entries."""
    v2.v1.earlier._check_ancestors(V2_DIR)
    if V2_DIR.parent != PRIVATE_ROOT:
        raise ValueError("Pinned v2 path differs")
    verify_acl(PRIVATE_ROOT)
    verify_acl(V2_DIR)
    if {entry.name for entry in V2_DIR.iterdir()} != set(V2_ARTIFACT_SHA):
        raise ValueError("Pinned v2 artifact inventory differs")
    documents = {}
    for name, digest in V2_ARTIFACT_SHA.items():
        limit = MAX_PRIVATE_RESULT_BYTES if name == "result.json" else 1024 * 1024
        body = v2.v1._pinned_bytes(V2_DIR / name, limit, digest, "v2 artifact")
        documents[name] = v2._parse_pinned(body, "v2 artifact")
    intent = documents["intent.json"]
    result = documents["result.json"]
    public = documents["public.json"]
    hashes = documents["hash_manifest.json"]
    if (
        intent.get("protocol") != v2.PROTOCOL
        or intent.get("run_id") != V2_DIR.name
        or intent.get("code_commit") != V2_CODE_COMMIT
        or intent.get("dirty_tree") is not False
        or result.get("protocol") != v2.PROTOCOL
        or result.get("label_status") != "unqualified"
        or result.get("sale_labels_certified") != 0
        or hashes.get("intent_sha256") != V2_ARTIFACT_SHA["intent.json"]
        or hashes.get("result_sha256") != V2_ARTIFACT_SHA["result.json"]
        or hashes.get("public_sha256") != V2_ARTIFACT_SHA["public.json"]
        or any(
            intent.get(name) != result.get(name) or result.get(name) != public.get(name)
            for name in SOURCE_HASH_FIELDS
        )
    ):
        raise ValueError("Pinned v2 evidence is incompatible")
    _validate_frame(result)
    if _json_bytes(v2._public_projection(result)) != _json_bytes(public) or _json_bytes(
        _tracked_public(TRACKED_V2_PUBLIC, V2_ARTIFACT_SHA["public.json"])
    ) != _json_bytes(public):
        raise ValueError("Pinned v2 public projection differs")
    return result, public


def _validate_frame(result: dict) -> None:
    expected = [name for name, _, _ in SELECTED]
    boroughs = result.get("boroughs")
    if (
        not isinstance(boroughs, list)
        or [item.get("borough") for item in boroughs] != expected
    ):
        raise ValueError("Representation borough frame differs")
    for item, (_, code, rows) in zip(boroughs, SELECTED, strict=True):
        if (
            item.get("borough_code") != code
            or item.get("csv_rows") != rows
            or item.get("xlsx_rows") != rows
        ):
            raise ValueError("Representation borough row count differs")
        core._validate_result(item)
        fields = item["counts"]["fields"]
        if any(
            fields["column_disagreements"][index] > fields["other_19_mismatches"]
            for index in range(19)
        ):
            raise ValueError("Representation other-field disagreement differs")
    expected_rows = sum(rows for _, _, rows in SELECTED)
    if (
        result.get("csv_frame_rows") != expected_rows
        or result.get("xlsx_frame_rows") != expected_rows
    ):
        raise ValueError("Representation frame total differs")
    if (
        result.get("csv_source_rows")
        != result.get("excluded_manhattan_csv_rows", -1) + expected_rows
    ):
        raise ValueError("Representation source total differs")


def _derive(v2_private: dict) -> dict:
    """Select only fixed aggregates into a fresh private diagnostic."""
    if (
        not isinstance(v2_private, dict)
        or v2_private.get("protocol") != v2.PROTOCOL
        or v2_private.get("sale_labels_certified") != 0
        or v2_private.get("label_status") != "unqualified"
    ):
        raise ValueError("Representation result metadata differs")
    _validate_frame(v2_private)
    boroughs = []
    for item in v2_private["boroughs"]:
        counts = item["counts"]
        columns = counts["fields"]["column_disagreements"]
        ranked = sorted(
            range(len(FIELD_NAMES)), key=lambda index: (-columns[index], index)
        )
        boroughs.append(
            {
                "borough": item["borough"],
                "borough_code": item["borough_code"],
                "csv_rows": item["csv_rows"],
                "xlsx_rows": item["xlsx_rows"],
                "isolated_pairs": counts["statuses"]["csv_isolated_candidate"],
                "fields": copy.deepcopy(counts["fields"]),
                "overlap": copy.deepcopy(counts["overlap"]),
                "parse_failures": dict(counts["parse_failures"]),
                "lexical_forms": copy.deepcopy(counts["lexical_forms"]),
                "ranked_columns": [
                    {"header": FIELD_NAMES[index], "count": columns[index]}
                    for index in ranked
                ],
            }
        )
    return {
        "protocol": PROTOCOL,
        "v2_result_sha256": V2_ARTIFACT_SHA["result.json"],
        "v2_public_sha256": V2_ARTIFACT_SHA["public.json"],
        "boroughs": boroughs,
        "label_status": "unqualified",
        "sale_labels_certified": 0,
    }


def _public_projection(private: dict, v2_public: dict, v1_public: dict) -> dict:
    """Publish a fixed, non-data-dependent inventory for every borough."""
    boroughs = []
    for item, newer, older in zip(
        private["boroughs"], v2_public["boroughs"], v1_public["boroughs"], strict=True
    ):
        if item["borough"] != newer.get("borough") or item["borough"] != older.get(
            "borough"
        ):
            raise ValueError("Published borough order differs")
        name = item["borough"]
        if name == "Staten Island":
            if newer.get("counts") is not None or older.get("counts") is not None:
                raise ValueError("Staten Island publication differs")
        else:
            counts = newer.get("counts")
            if counts is not None and (
                item["isolated_pairs"] != counts["isolated_pairs"]
                or item["fields"]["format_only_candidates"]
                != counts["format_only_candidates"]
            ):
                raise ValueError("Pinned candidate counts differ")
        if item["csv_rows"] != newer.get("csv_rows") or item["xlsx_rows"] != newer.get(
            "xlsx_rows"
        ):
            raise ValueError("Pinned source denominators differ")
        boroughs.append(
            {
                "borough": name,
                "flags": None,
                "disagreement_headers": None,
                "suppression_reason": "private_only_v1",
            }
        )
    return {
        "protocol": PROTOCOL,
        "v2_result_sha256": V2_ARTIFACT_SHA["result.json"],
        "boroughs": boroughs,
        "label_status": "unqualified",
        "sale_labels_certified": 0,
    }


def _aggregate(inputs: dict) -> dict:
    v2_private, v2_public = _verify_v2()
    if _json_bytes(v2_public) != _json_bytes(inputs["v2_public"]):
        raise ValueError("Pinned v2 public changed")
    return _derive(v2_private)


def _intent(output: Path, inputs: dict, provenance: dict) -> dict:
    return {
        "protocol": PROTOCOL,
        "run_id": output.name,
        "started_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "v2_run_id": V2_DIR.name,
        "v2_result_sha256": V2_ARTIFACT_SHA["result.json"],
        "v1_public_sha256": inputs["v1_public_sha256"],
        "v2_public_sha256": inputs["v2_public_sha256"],
        **inputs["source_hashes"],
        "environment_lock_sha256": inputs["environment_lock_sha256"],
        "code_hashes": _code_hashes(),
        **provenance,
    }


def _hash_manifest(output: Path, intent: bytes, private: bytes, public: bytes) -> dict:
    return {
        "protocol": PROTOCOL,
        "run_id": output.name,
        "intent_sha256": _sha(intent),
        "result_sha256": _sha(private),
        "public_sha256": _sha(public),
    }


def analyze(output_dir: Path) -> dict:
    """Create one private diagnostic, reserving intent before protected v2 reads."""
    lock_bytes = v2.v1._pinned_bytes(
        ENVIRONMENT_LOCK, 64 * 1024, None, "environment lock"
    )
    v2._parse_pinned(lock_bytes, "environment lock")
    inputs = _preflight()
    inputs = {**inputs, "environment_lock_sha256": _sha(lock_bytes)}
    provenance = _provenance()
    if provenance["dirty_tree"] or not _remote_pushed(provenance["code_commit"]):
        raise ValueError("Field diagnostic requires a clean pushed code commit")
    output = _run_dir(output_dir, new=True)
    intent_bytes = _json_bytes(_intent(output, inputs, provenance))
    output.mkdir(mode=0o700)
    try:
        secure_directory(output)
        verify_acl(output)
        _publish_json(output, "intent.json", intent_bytes)
        private = _aggregate(inputs)
        private_bytes = _json_bytes(private)
        if len(private_bytes) > MAX_PRIVATE_RESULT_BYTES:
            raise ValueError("Field result exceeds size cap")
        public = _public_projection(private, inputs["v2_public"], inputs["v1_public"])
        public_bytes = _json_bytes(public)
        _publish_json(output, "result.json", private_bytes)
        _publish_json(output, "public.json", public_bytes)
        _publish_json(
            output,
            "hash_manifest.json",
            _json_bytes(
                _hash_manifest(output, intent_bytes, private_bytes, public_bytes)
            ),
        )
        return public
    except BaseException as error:
        category = (
            "timeout"
            if isinstance(error, TimeoutError)
            else "interrupted"
            if isinstance(error, (KeyboardInterrupt, SystemExit))
            else "integrity_or_io_failure"
        )
        try:
            _publish_json(
                output,
                "failure.json",
                _json_bytes(
                    {
                        "protocol": PROTOCOL,
                        "run_id": output.name,
                        "status": "incomplete",
                        "category": category,
                    }
                ),
            )
        except Exception as artifact_error:
            error.add_note(
                "Failure artifact could not be saved: " + type(artifact_error).__name__
            )
        raise


def replay(output_dir: Path) -> dict:
    """Rebuild exact private and redacted bytes from pinned v2 artifacts."""
    output = _run_dir(output_dir, new=False)
    verify_acl(output)
    if (output / "failure.json").exists() or v2.v1.earlier._reparse(
        output / "failure.json"
    ):
        raise ValueError("Field run is incomplete")
    expected_names = {"intent.json", "result.json", "public.json", "hash_manifest.json"}
    if {entry.name for entry in output.iterdir()} != expected_names:
        raise ValueError("Field run inventory differs")
    bodies = {
        name: v2.v1._pinned_bytes(
            output / name,
            MAX_PRIVATE_RESULT_BYTES if name == "result.json" else 1024 * 1024,
            None,
            "field artifact",
        )
        for name in expected_names
    }
    documents = {
        name: v2._parse_pinned(body, "field artifact") for name, body in bodies.items()
    }
    inputs = _preflight()
    intent = documents["intent.json"]
    if (
        intent.get("protocol") != PROTOCOL
        or intent.get("run_id") != output.name
        or intent.get("dirty_tree") is not False
        or re.fullmatch(r"[0-9a-f]{40}", intent.get("code_commit", "")) is None
        or intent.get("v2_run_id") != V2_DIR.name
        or intent.get("v2_result_sha256") != V2_ARTIFACT_SHA["result.json"]
        or intent.get("v1_public_sha256") != inputs["v1_public_sha256"]
        or intent.get("v2_public_sha256") != inputs["v2_public_sha256"]
        or any(
            intent.get(name) != inputs["source_hashes"][name]
            for name in SOURCE_HASH_FIELDS
        )
        or intent.get("environment_lock_sha256") != inputs["environment_lock_sha256"]
        or intent.get("code_hashes") != _code_hashes()
        or documents["hash_manifest.json"]
        != _hash_manifest(
            output, bodies["intent.json"], bodies["result.json"], bodies["public.json"]
        )
    ):
        raise ValueError("Field run provenance differs")
    recomputed = _aggregate(inputs)
    public = _public_projection(recomputed, inputs["v2_public"], inputs["v1_public"])
    if (
        _json_bytes(recomputed) != bodies["result.json"]
        or _json_bytes(public) != bodies["public.json"]
    ):
        raise ValueError("Field replay differs")
    return public


def plan() -> dict:
    return {
        "protocol": PROTOCOL,
        "v2_run_id": V2_DIR.name,
        "v2_result_sha256": V2_ARTIFACT_SHA["result.json"],
        "expected_boroughs": [name for name, _, _ in SELECTED],
        "status": "plan_only_no_private_read",
        "label_status": "unqualified",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("plan")
    for name in ("analyze", "replay"):
        command = commands.add_parser(name)
        command.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    try:
        result = (
            plan()
            if args.command == "plan"
            else (
                analyze(args.output_dir)
                if args.command == "analyze"
                else replay(args.output_dir)
            )
        )
    except Exception as error:
        parser.exit(2, f"Field diagnostic failed: {type(error).__name__}\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
