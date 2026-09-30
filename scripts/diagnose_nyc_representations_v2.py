"""Diagnose pinned NYC source representations without admitting sale labels."""

from __future__ import annotations

import argparse
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import compare_nyc_rolling_borough_rows as v1
import nyc_representation_core as core
from private_review_io import secure_directory, verify_acl

PROJECT_ROOT = v1.PROJECT_ROOT
PRIVATE_ROOT = v1.PRIVATE_ROOT
V1_DIR = PRIVATE_ROOT / "row-concordance-v1-20260930T132740Z-93eb58530149"
ENVIRONMENT_LOCK = (
    PROJECT_ROOT / "locks/nyc-representation-diagnostic-v2-environment.json"
)
PROTOCOL = "nyc-dof-representation-diagnostic-v2"
SELECTED = v1.SELECTED
V1_CODE_COMMIT = "642f6afa284b444b342535ef4b241c3d75fd6932"
V1_ARTIFACT_SHA = {
    "intent.json": "c10ad7081062043e1116a1b83c94069aba6b95302eeb5b272180d0cd304685b5",
    "result.json": "5fd432e081911ff47df78bf183a40df99da00077d0e666175ca79840f18451ee",
    "public.json": "4d52add2b6a65df050c9bf0a920e0f9ccc4e7fad8959f1d7e6c1154fb84ea524",
    "hash_manifest.json": "3d454e3b7dcd6ec0ab9d2d6e3766b16ab61da7aa1cd00573f323b7d46ac6ca7b",
}
MAX_PRIVATE_RESULT_BYTES = 64 * 1024 * 1024
CODE_PATHS = (
    "scripts/diagnose_nyc_representations_v2.py",
    "scripts/nyc_representation_core.py",
    "scripts/nyc_representation_parsing.py",
)

_sha = v1._sha
_json_bytes = v1._json_bytes
_publish_json = v1._publish_json
_provenance = v1._provenance


def _run_dir(directory: Path, *, new: bool) -> Path:
    target = Path(directory).absolute()
    v1.earlier._check_ancestors(PRIVATE_ROOT)
    v1.earlier._check_ancestors(target)
    match = re.fullmatch(
        r"representation-diagnostic-v2-(\d{8}T\d{6}Z)-([0-9a-f]{12})",
        target.name,
    )
    if target.parent != PRIVATE_ROOT.absolute() or match is None:
        raise ValueError("Representation run path is outside private NYC root")
    try:
        datetime.strptime(match.group(1), "%Y%m%dT%H%M%SZ")
    except ValueError as error:
        raise ValueError("Representation run ID is invalid") from error
    if not PRIVATE_ROOT.is_dir():
        raise ValueError("Private NYC root is missing")
    verify_acl(PRIVATE_ROOT)
    if new and (target.exists() or v1.earlier._reparse(target)):
        raise FileExistsError("Representation run already exists")
    if not new and not target.is_dir():
        raise ValueError("Representation run does not exist")
    return target


def _parse_pinned(body: bytes, kind: str) -> dict:
    try:
        value = json.loads(body)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"Pinned {kind} is invalid JSON") from error
    if not isinstance(value, dict) or body != _json_bytes(value):
        raise ValueError(f"Pinned {kind} is not canonical")
    return value


def _verify_v1() -> dict[str, dict]:
    v1.earlier._check_ancestors(V1_DIR)
    verify_acl(V1_DIR)
    if {item.name for item in V1_DIR.iterdir()} != set(V1_ARTIFACT_SHA):
        raise ValueError("Pinned v1 artifact inventory differs")
    documents = {}
    for name, expected in V1_ARTIFACT_SHA.items():
        limit = (
            MAX_PRIVATE_RESULT_BYTES
            if name == "result.json"
            else v1.earlier.MAX_JSON_BYTES
        )
        body = v1._pinned_bytes(V1_DIR / name, limit, expected, "v1 artifact")
        documents[name] = _parse_pinned(body, "v1 artifact")
    intent = documents["intent.json"]
    result = documents["result.json"]
    public = documents["public.json"]
    hashes = documents["hash_manifest.json"]
    if (
        intent.get("protocol") != v1.PROTOCOL
        or intent.get("run_id") != V1_DIR.name
        or intent.get("code_commit") != V1_CODE_COMMIT
        or intent.get("dirty_tree") is not False
        or result.get("protocol") != v1.PROTOCOL
        or result.get("sale_labels_certified") != 0
        or result.get("csv_frame_rows") != 62792
        or result.get("xlsx_frame_rows") != 62792
        or hashes.get("intent_sha256") != V1_ARTIFACT_SHA["intent.json"]
        or hashes.get("result_sha256") != V1_ARTIFACT_SHA["result.json"]
        or hashes.get("public_sha256") != V1_ARTIFACT_SHA["public.json"]
        or _json_bytes(v1._public_projection(result)) != _json_bytes(public)
    ):
        raise ValueError("Pinned v1 evidence is incompatible")
    boroughs = result.get("boroughs")
    if (
        not isinstance(boroughs, list)
        or len(boroughs) != len(SELECTED)
        or [item.get("borough") for item in boroughs]
        != [name for name, _, _ in SELECTED]
    ):
        raise ValueError("Pinned v1 borough inventory differs")
    return {item["borough"]: item["counts"] for item in boroughs}


def _verify_v3() -> dict[str, dict]:
    return v1._verify_v3()


def _preflight() -> dict:
    inherited = v1._preflight()
    v1_counts = _verify_v1()
    v3_status = _verify_v3()
    for borough, _, _ in SELECTED:
        if v3_status[borough].get("date_system") != "1900_default":
            raise ValueError("Pinned workbook date system differs")
    return {
        **inherited,
        "v1_counts": v1_counts,
        "v3_status": v3_status,
        "v1_result_sha256": V1_ARTIFACT_SHA["result.json"],
    }


def _code_hashes() -> dict[str, str]:
    return {
        **v1._code_hashes(),
        **{
            name: _sha(
                v1._pinned_bytes(PROJECT_ROOT / name, 1024 * 1024, None, "code file")
            )
            for name in CODE_PATHS
        },
    }


def _intent(output: Path, inputs: dict) -> dict:
    return {
        "protocol": PROTOCOL,
        "run_id": output.name,
        "started_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "capture_manifest_sha256": inputs["capture_manifest_sha256"],
        "csv_snapshot_sha256": inputs["csv_snapshot_sha256"],
        "v3_result_sha256": inputs["v3_result_sha256"],
        "v1_result_sha256": inputs["v1_result_sha256"],
        **_provenance(),
        "environment_lock_sha256": _sha(
            v1._pinned_bytes(ENVIRONMENT_LOCK, 64 * 1024, None, "environment lock")
        ),
        "code_hashes": _code_hashes(),
    }


def _reconcile_k0(actual: dict, expected: dict) -> None:
    mapping = {
        "unique_candidate_edges": "unique_key_pairs",
        "csv_valid_rows": "csv_complete_key_rows",
        "xlsx_valid_rows": "xlsx_complete_key_rows",
        "csv_invalid_or_incomplete_rows": "csv_incomplete_key_rows",
        "xlsx_invalid_or_incomplete_rows": "xlsx_incomplete_key_rows",
        "csv_only_rows": "csv_only_rows",
        "xlsx_only_rows": "xlsx_only_rows",
        "csv_shared_ambiguous_rows": "csv_ambiguous_shared_key_rows",
        "xlsx_shared_ambiguous_rows": "xlsx_ambiguous_shared_key_rows",
        "csv_key_groups": "csv_complete_key_groups",
        "xlsx_key_groups": "xlsx_complete_key_groups",
        "csv_duplicate_key_groups": "csv_duplicate_key_groups",
        "xlsx_duplicate_key_groups": "xlsx_duplicate_key_groups",
        "ambiguous_shared_groups": "shared_ambiguous_key_groups",
        "csv_only_key_groups": "csv_only_key_groups",
        "xlsx_only_key_groups": "xlsx_only_key_groups",
    }
    if any(actual.get(left) != expected.get(right) for left, right in mapping.items()):
        raise ValueError("K0 counts differ from frozen v1")


def _aggregate(inputs: dict, timer, start: float) -> dict:
    boroughs = []
    for borough, code, expected in SELECTED:
        csv_rows = v1._csv_rows(inputs, code, timer, start)
        xlsx_rows = v1._xlsx_rows(inputs, borough, code, timer, start)
        if len(csv_rows) != expected or len(xlsx_rows) != expected:
            raise ValueError("Pinned borough row count differs")
        result = core.analyze_borough(
            csv_rows,
            xlsx_rows,
            borough=borough,
            borough_code=code,
            date_system=inputs["v3_status"][borough]["date_system"],
        )
        original_k0 = v1.core.compare_borough(
            csv_rows,
            xlsx_rows,
            borough=borough,
            borough_code=code,
        )
        if original_k0["counts"] != inputs["v1_counts"][borough]:
            raise ValueError("Full K0 diagnostic differs from frozen v1")
        _reconcile_k0(result["counts"]["tiers"]["K0"], inputs["v1_counts"][borough])
        boroughs.append(result)
        v1.earlier._check_time(timer, start)
    return {
        "protocol": PROTOCOL,
        "capture_manifest_sha256": inputs["capture_manifest_sha256"],
        "csv_snapshot_sha256": inputs["csv_snapshot_sha256"],
        "v3_result_sha256": inputs["v3_result_sha256"],
        "v1_result_sha256": inputs["v1_result_sha256"],
        "csv_source_rows": 82345,
        "excluded_manhattan_csv_rows": v1.CSV_COUNTS["1"],
        "csv_frame_rows": sum(item["csv_rows"] for item in boroughs),
        "xlsx_frame_rows": sum(item["xlsx_rows"] for item in boroughs),
        "boroughs": boroughs,
        "label_status": "unqualified",
        "sale_labels_certified": 0,
    }


def _public_projection(private: dict) -> dict:
    return {
        "protocol": PROTOCOL,
        "capture_manifest_sha256": private["capture_manifest_sha256"],
        "csv_snapshot_sha256": private["csv_snapshot_sha256"],
        "v3_result_sha256": private["v3_result_sha256"],
        "v1_result_sha256": private["v1_result_sha256"],
        "csv_source_rows": private["csv_source_rows"],
        "excluded_manhattan_csv_rows": private["excluded_manhattan_csv_rows"],
        "csv_frame_rows": private["csv_frame_rows"],
        "xlsx_frame_rows": private["xlsx_frame_rows"],
        "boroughs": [core.public_projection(item) for item in private["boroughs"]],
        "label_status": "unqualified",
        "sale_labels_certified": 0,
    }


def _hash_manifest(output: Path, intent: bytes, private: bytes, public: bytes) -> dict:
    return {
        "protocol": PROTOCOL,
        "run_id": output.name,
        "intent_sha256": _sha(intent),
        "result_sha256": _sha(private),
        "public_sha256": _sha(public),
    }


def compare_sources(output_dir: Path, *, timer=time.monotonic) -> dict:
    """Run a create-only private source diagnostic with no label admission."""
    start = timer()
    inputs = _preflight()
    output = _run_dir(output_dir, new=True)
    intent = _intent(output, inputs)
    if intent["dirty_tree"]:
        raise ValueError("Representation run requires a clean code tree")
    intent_bytes = _json_bytes(intent)
    output.mkdir(mode=0o700)
    try:
        secure_directory(output)
        verify_acl(output)
        _publish_json(output, "intent.json", intent_bytes)
        private = _aggregate(inputs, timer, start)
        private_bytes = _json_bytes(private)
        if len(private_bytes) > MAX_PRIVATE_RESULT_BYTES:
            raise ValueError("Representation private result exceeds cap")
        public = _public_projection(private)
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
        if isinstance(error, TimeoutError):
            category = "timeout"
        elif isinstance(error, (KeyboardInterrupt, SystemExit)):
            category = "interrupted"
        else:
            category = "integrity_or_io_failure"
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
                "Representation failure artifact could not be saved: "
                + type(artifact_error).__name__
            )
        raise


def replay(output_dir: Path, *, timer=time.monotonic) -> dict:
    """Recompute exact private/public bytes from unchanged pinned sources."""
    start = timer()
    output = _run_dir(output_dir, new=False)
    verify_acl(output)
    if (output / "failure.json").exists() or v1.earlier._reparse(
        output / "failure.json"
    ):
        raise ValueError("Representation run is incomplete")
    intent, intent_bytes = v1.earlier._load_private_json(output, "intent.json")
    _, private_bytes = v1._load_private_result(output)
    _, public_bytes = v1.earlier._load_private_json(output, "public.json")
    hashes, _ = v1.earlier._load_private_json(output, "hash_manifest.json")
    inputs = _preflight()
    expected = (
        PROTOCOL,
        output.name,
        inputs["capture_manifest_sha256"],
        inputs["csv_snapshot_sha256"],
        inputs["v3_result_sha256"],
        inputs["v1_result_sha256"],
        _sha(v1._pinned_bytes(ENVIRONMENT_LOCK, 64 * 1024, None, "environment lock")),
        _code_hashes(),
        True,
        False,
    )
    observed = (
        intent.get("protocol"),
        intent.get("run_id"),
        intent.get("capture_manifest_sha256"),
        intent.get("csv_snapshot_sha256"),
        intent.get("v3_result_sha256"),
        intent.get("v1_result_sha256"),
        intent.get("environment_lock_sha256"),
        intent.get("code_hashes"),
        bool(re.fullmatch(r"[0-9a-f]{40}", intent.get("code_commit", ""))),
        intent.get("dirty_tree"),
    )
    if observed != expected:
        raise ValueError("Representation intent differs from pinned inputs")
    if hashes != _hash_manifest(output, intent_bytes, private_bytes, public_bytes):
        raise ValueError("Representation hash manifest differs")
    recomputed = _aggregate(inputs, timer, start)
    public = _public_projection(recomputed)
    if _json_bytes(recomputed) != private_bytes or _json_bytes(public) != public_bytes:
        raise ValueError("Representation replay differs from saved result")
    return public


def plan() -> dict:
    """Show fixed scope and hashes without opening source rows."""
    return {
        "protocol": PROTOCOL,
        "capture_manifest_sha256": v1.CAPTURE_MANIFEST_SHA,
        "csv_snapshot_sha256": v1.profile.APPROVED_SNAPSHOT_SHA256,
        "v3_result_sha256": v1.V3_ARTIFACT_SHA["result.json"],
        "v1_result_sha256": V1_ARTIFACT_SHA["result.json"],
        "expected_boroughs": [item[0] for item in SELECTED],
        "expected_rows_per_source": sum(item[2] for item in SELECTED),
        "status": "plan_only_no_row_read",
        "label_status": "unqualified",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("plan")
    for name in ("compare", "replay"):
        command = commands.add_parser(name)
        command.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "plan":
            result = plan()
        elif args.command == "compare":
            result = compare_sources(args.output_dir)
        else:
            result = replay(args.output_dir)
    except Exception as error:
        parser.exit(2, f"Representation diagnostic failed: {type(error).__name__}\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
