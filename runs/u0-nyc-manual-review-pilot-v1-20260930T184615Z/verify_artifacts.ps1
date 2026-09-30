$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$python = Join-Path $root '.venv\Scripts\python.exe'
$code = @'
import hashlib
import json
import os
import re
import sys
from pathlib import Path

from scripts import private_review_io, review_nyc_sample

root = Path(sys.argv[1]).resolve(strict=True)
run = Path(sys.argv[2]).resolve(strict=True)
raw = root / "data/raw/nyc_dof"
private = raw / "manual-review-v1"
snapshot_ledger = private / "pilot-snapshot-20260930T190000Z-8edca1c8-reviews.jsonl"
snapshot_manifest = private / "pilot-snapshot-20260930T190000Z-8edca1c8-manifest.json"
evidence = private / "manual-review-pilot-evidence-direct-20260930T190000Z-8edca1c8.json"
pilot = raw / "verified-export-pilot-v1-20260930T181620Z-70ed3ced7f7d/result.json"
source = raw / "nyc-usep-8jbt-20260928T225530.250496Z-2d84779d0195.csv"
sample = raw / "review-usep-8jbt-20260928T234700Z.jsonl"

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def require(value, message):
    if not value:
        raise ValueError(message)

def verify_file_acl(path):
    if os.name != "nt":
        require(path.stat().st_mode & 0o077 == 0, "Private artifact file permissions are too broad")
        return
    sid = private_review_io.user_sid()
    script = (
        "$ErrorActionPreference='Stop'; $acl=Get-Acl -LiteralPath $env:TABPFN_ACL_DIR; "
        "$entries=@($acl.Access|ForEach-Object{ $_.IdentityReference.Translate([System.Security.Principal.SecurityIdentifier]).Value }); "
        "@{entries=$entries}|ConvertTo-Json -Compress"
    )
    entries = private_review_io._powershell_acl(path, script, sid).get("entries")
    allowed = {sid, "S-1-5-18", "S-1-5-32-544"}
    require(isinstance(entries, list) and sid in entries and set(entries).issubset(allowed), "Private artifact file ACL is too broad")

require(digest(evidence) == "018f2a356f9e8a2d3c7a0480410c2316b12d98b20c105dbbb323d3fb5d3288b6", "Private evidence manifest changed")
inventory = json.loads(evidence.read_text(encoding="utf-8"))
require(inventory["protocol"] == "nyc-manual-review-pilot-v1" and len(inventory["files"]) == 47, "Private inventory changed")
require(inventory["complete_records"] == 10 and inventory["unreviewed_records"] == 190, "Private count changed")
private_review_io.verify_acl(private)
seen = set()
verified_directories = {private.resolve(strict=True)}
for record in inventory["files"]:
    relative = Path(record["path"])
    path = private / relative
    require(not relative.is_absolute() and ".." not in relative.parts and not path.is_symlink(), "Unsafe private artifact path")
    resolved = path.resolve(strict=True)
    require(resolved.is_relative_to(private.resolve(strict=True)), "Private artifact escaped directory")
    require(record["path"] not in seen, "Duplicate private artifact")
    seen.add(record["path"])
    require(resolved.is_file() and resolved.stat().st_size == record["bytes"], "Private artifact size changed")
    require(digest(resolved) == record["sha256"], "Private artifact hash changed")
    verify_file_acl(resolved)
    for parent in resolved.parents:
        if parent == private:
            break
        if parent not in verified_directories:
            private_review_io.verify_acl(parent)
            verified_directories.add(parent)
require(digest(source) == inventory["source_sha256"] and digest(sample) == inventory["sample_sha256"], "Source or sample changed")
require(digest(snapshot_ledger) == inventory["ledger_sha256"], "Frozen ledger changed")
require(digest(pilot) == inventory["pilot_result_sha256"], "Pilot comparison changed")

pilot_data = json.loads(pilot.read_text(encoding="utf-8"))
entries = [json.loads(line) for line in snapshot_ledger.read_text(encoding="utf-8").splitlines()]
require(len(entries) == 10, "Review entry count changed")
require({entry["ordinal"] for entry in entries} == set(pilot_data["pilot_ordinals"]), "Frozen pilot set changed")
dimensions = set(review_nyc_sample.DIMENSIONS)
for entry in entries:
    require(entry["review_status"] == "complete" and entry["attested"] is True, "Review status changed")
    findings = entry["rubric"]
    require(set(findings) == dimensions, "Review rubric changed")
    require(all(findings[name]["value"] == "unknown" for name in dimensions - {"price_semantics"}), "Unsupported affirmative finding")
    require(findings["price_semantics"]["value"] in {"reported_positive", "reported_zero", "invalid"}, "Published price state changed")

regenerated = review_nyc_sample.summarize_reviews(source, sample, snapshot_ledger, snapshot_manifest)
aggregate = json.loads((run / "aggregate.json").read_text(encoding="utf-8"))
require(regenerated == aggregate, "Public aggregate differs from protected ledger")
require(aggregate["complete_records"] == 10 and aggregate["unreviewed_records"] == 190, "Public counts changed")
manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
gate = json.loads((run / "test_gate.json").read_text(encoding="utf-8"))
for field, path in {
    "aggregate_sha256": run / "aggregate.json",
    "report_sha256": run / "report.md",
    "test_gate_sha256": run / "test_gate.json",
    "focused_tests_log_sha256": run / "focused_tests.log",
    "verification_log_sha256": run / "verification.log",
    "source_card_sha256": root / "data/source_cards/nyc_dof_rolling_sales.yaml",
    "review_code_sha256": root / "scripts/review_nyc_sample.py",
    "private_io_sha256": root / "scripts/private_review_io.py",
    "decision_sha256": root / "decisions/0027-nyc-ledger-evidence-boundary.md",
    "environment_lock_sha256": root / "locks/nyc-review-ledger-environment.json",
    "prior_full_suite_log_sha256": root / "runs/u0-nyc-verified-export-pilot-v1-20260930T181620Z/full_suite.log",
}.items():
    require(manifest[field] == digest(path), f"Public evidence changed: {field}")
require(manifest["private_evidence_manifest_sha256"] == digest(evidence), "Private evidence provenance changed")
require(manifest["sale_labels_certified"] == 0 and manifest["u0_gate"] == "PENDING" and manifest["g_us_gate"] == "PENDING", "Gate claim changed")
require(gate["sale_labels_certified"] == 0 and gate["u0_gate"] == "PENDING" and gate["g_us_gate"] == "PENDING", "Gate evidence changed")
require(manifest["code_commit_at_review"] == "57747d8a1a083aa786f7fdb938e0b43bbba0af8e", "Code version changed")
checks = gate["checks"]
require(len(checks) == 2, "Gate check inventory changed")
require(checks[0]["command"] == r".\.venv\Scripts\python.exe -m unittest discover -s tests -p test_nyc_sample_review.py -q", "Focused test command changed")
require(checks[0]["exit_code"] == 0 and checks[0]["duration_seconds_reported_by_unittest"] == 42.947, "Focused test result changed")
require(checks[0]["output_artifact"] == f"runs/{run.name}/focused_tests.log", "Focused test output path changed")
require(checks[1]["command"] == f"& 'runs/{run.name}/verify_artifacts.ps1'", "Verifier command changed")
require(checks[1]["exit_code"] == 0 and checks[1]["duration_seconds"] == 22.232, "Verifier result changed")
require(checks[1]["output_artifact"] == f"runs/{run.name}/verification.log", "Verifier output path changed")
focused_log = (run / "focused_tests.log").read_text(encoding="utf-8")
verification_log = (run / "verification.log").read_text(encoding="utf-8-sig")
full_log = (root / "runs/u0-nyc-verified-export-pilot-v1-20260930T181620Z/full_suite.log").read_text(encoding="utf-8")
require(re.search(r"(?m)^Ran 18 tests in 42\.947s\r?$", focused_log) and re.search(r"(?m)^OK\r?$", focused_log), "Focused test log changed")
require(verification_log.strip() == "verified_nyc_ten_manual_reviews_zero_labels", "Verifier log changed")
require(re.search(r"(?m)^Ran 786 tests in 186\.814s\r?$", full_log) and re.search(r"(?m)^OK\r?$", full_log), "Prior full-suite log changed")
print("verified_nyc_ten_manual_reviews_zero_labels")
'@
Push-Location $root
try {
    $code | & $python - $root $PSScriptRoot
    if ($LASTEXITCODE -ne 0) { throw 'Protected NYC source-review verification failed' }
} finally {
    Pop-Location
}
