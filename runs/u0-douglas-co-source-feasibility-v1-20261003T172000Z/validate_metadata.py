"""Validate the bounded Douglas County metadata audit, not source rows."""

from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml


RUN_ID = "u0-douglas-co-source-feasibility-v1-20261003T172000Z"
RUN_DIR = Path(__file__).resolve().parent
ROOT = RUN_DIR.parents[1]
REQUIREMENT_IDS = ("US02", "US05", "US06", "US08", "US24")


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def atomic_text(path: Path, content: str) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    os.replace(temporary, path)


def write_gate(result: dict) -> None:
    atomic_text(RUN_DIR / "test_gate.json", json.dumps(result, indent=2) + "\n")


def validate() -> dict:
    started = time.perf_counter()
    config = load_json(RUN_DIR / "run_config.json")
    metadata = load_json(RUN_DIR / "head_metadata.json")
    environment = ROOT / "locks" / "u0-douglas-metadata-environment.json"
    card_path = ROOT / "data" / "source_cards" / "douglas_county_co_assessor_downloads.yaml"
    card = yaml.safe_load(card_path.read_text(encoding="utf-8"))
    requirements = yaml.safe_load((ROOT / "requirements.yaml").read_text(encoding="utf-8"))
    report_path = RUN_DIR / "report.md"
    decision_path = ROOT / "decisions" / "0080-douglas-county-western-source-candidate.md"
    checks: list[str] = []

    require(config["run_id"] == metadata["run_id"] == RUN_ID, "run IDs differ")
    require(config["method"] == "HEAD", "method must be HEAD")
    require(config["download_row_level_body"] is False, "body download configured")
    require(config["max_row_level_records"] == 0, "row-level limit is nonzero")
    checks.append("bounded HEAD-only configuration")

    expected_urls = {card["sales_file_url"], card["improvements_file_url"]}
    require(len(config["urls"]) == 2, "expected exactly two configured URLs")
    require(set(config["urls"]) == expected_urls, "configured URLs differ from source card")
    files = metadata["files"]
    require(len(files) == len(expected_urls) == 2, "expected two metadata responses")
    require({entry["request_url"] for entry in files} == expected_urls, "response URLs differ")
    for entry in files:
        require(entry["request_url"] == entry["response_url"], "unexpected redirect")
        require(entry["method"] == "HEAD" and entry["status_code"] == 200, "HEAD failed")
        require(entry["response_body_downloaded"] is False, "response body downloaded")
        require(entry["content_length_bytes"] > 0, "empty source file")
        modified = datetime.strptime(entry["last_modified"], "%a, %d %b %Y %H:%M:%S GMT").replace(tzinfo=timezone.utc)
        observed = datetime.fromisoformat(entry["observed_at_utc"].replace("Z", "+00:00"))
        require(modified <= observed, "modification time after observation")
    checks.append("two matching 200 HEAD responses with positive lengths and no bodies")

    require(card["certified_sale_labels"] == 0, "source card claims certified labels")
    require(card["raw_file_sha256"] is None, "source card claims a raw snapshot")
    require(card["historical_asof_eligible"] is False, "source marked as-of eligible")
    require(card["primary_90_day_close_origin_eligible"] is False, "source marked primary eligible")
    require(card["head_metadata_run"] == str((RUN_DIR / "head_metadata.json").relative_to(ROOT)).replace("\\", "/"), "source-card run path differs")
    checks.append("unadmitted source policy and zero certified labels")

    require(report_path.is_file() and decision_path.is_file() and environment.is_file(), "audit artifact missing")
    for requirement_id in REQUIREMENT_IDS:
        evidence = requirements["requirements"][requirement_id]["evidence"]
        require(requirements["requirements"][requirement_id]["status"] == "planned", "requirement status changed")
        report_link = str(report_path.relative_to(ROOT)).replace("\\", "/")
        require(report_link in evidence, f"missing {requirement_id} report link")
    checks.append("YAML parses, audit artifacts exist and five planned requirements link evidence")

    result = {
        "run_id": RUN_ID,
        "gate": "metadata_artifact_validation_only",
        "status": "PASS",
        "command": f"py -3.14 runs/{RUN_ID}/validate_metadata.py",
        "exit_code": 0,
        "duration_seconds": round(time.perf_counter() - started, 6),
        "environment_lock_sha256": hashlib.sha256(environment.read_bytes()).hexdigest(),
        "checks": checks,
        "source_rows_downloaded": 0,
        "certified_sale_labels": 0,
        "us_gate_status": "PENDING",
    }
    return result


def main() -> None:
    common = {
        "run_id": RUN_ID,
        "gate": "metadata_artifact_validation_only",
        "command": f"py -3.14 runs/{RUN_ID}/validate_metadata.py",
        "source_rows_downloaded": 0,
        "certified_sale_labels": 0,
        "us_gate_status": "PENDING",
    }
    write_gate({**common, "status": "INCOMPLETE", "exit_code": None})
    try:
        result = validate()
    except Exception as error:
        atomic_text(RUN_DIR / "validation.log", f"FAIL: {type(error).__name__}: {error}\n")
        write_gate({**common, "status": "FAIL", "exit_code": 1,
                    "failure_type": type(error).__name__, "failure_message": str(error)})
        raise
    atomic_text(RUN_DIR / "validation.log", "PASS: " + "; ".join(result["checks"]) + "\n")
    write_gate(result)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
