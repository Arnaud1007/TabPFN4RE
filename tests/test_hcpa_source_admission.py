from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import hcpa_source_admission as admission  # noqa: E402


FINDING_TYPES = {
    "closing_date_semantics",
    "historical_availability",
    "transaction_grouping_and_exclusion",
    "use_rights",
}


def _write_json(path: Path, value: object) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()
    path.write_bytes(content)
    return hashlib.sha256(content).hexdigest()


def _evidence(
    root: Path,
    name: str,
    text: str = "authoritative evidence",
    *,
    decision: bool = False,
) -> dict:
    if decision:
        path = root / "decisions/0109-hcpa-off-baseline-readiness.md"
    else:
        path = root / "data/source_evidence/hcpa" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    content = f"{text}: {name}".encode()
    path.write_bytes(content)
    return {
        "kind": "decision" if decision else "evidence",
        "path": path.relative_to(root).as_posix(),
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def _admitted_document(evidence: list[dict]) -> dict:
    by_type = dict(zip(sorted(FINDING_TYPES), evidence[1:], strict=True))
    return {
        "schema_version": "hcpa_source_admission_v1",
        "source_id": "hillsborough_hcpa_allsales",
        "status": "pending",
        "admitted": False,
        "decision": evidence[0],
        "evidence": evidence[1:],
        "findings": [
            {
                "type": finding_type,
                "status": "verified",
                "evidence_sha256": [by_type[finding_type]["sha256"]],
            }
            for finding_type in sorted(FINDING_TYPES)
        ],
        "requirements": {
            "s_date_is_closing_date": True,
            "conservative_availability_method": True,
            "deterministic_grouping_and_exclusion": True,
            "rights": {
                "research_training": True,
                "commercial_training": True,
                "commercial_serving": True,
                "derived_artifacts": True,
                "comparable_display": False,
            },
        },
    }


def test_committed_pending_artifact_and_frozen_policy_validate() -> None:
    result = admission.validate_files(
        ROOT / "data/source_admission/hcpa_allsales_v1.json",
        ROOT / "data/model_policies/hcpa_off_absolute_error_v1.json",
        ROOT,
    )

    assert result == {
        "source_id": "hillsborough_hcpa_allsales",
        "status": "pending",
        "source_admitted": False,
        "comparable_display_permitted": False,
        "model_fit_permitted": False,
        "fit_readiness_status": "blocked",
        "fit_readiness_blockers": (
            "semantic_feature_flags_pending",
            "historical_property_attributes_pending",
            "eligibility_rules_pending",
        ),
    }


def test_exact_four_typed_findings_and_comparable_display_may_be_false(
    tmp_path: Path,
) -> None:
    evidence = [
        _evidence(tmp_path, f"{index}.md", decision=index == 0)
        for index in range(len(FINDING_TYPES) + 1)
    ]
    document = _admitted_document(evidence)

    result = admission.validate_document(document, tmp_path)

    assert result["source_admitted"] is False
    assert "model_fit_permitted" not in result
    assert result["comparable_display_permitted"] is False


def test_source_admission_does_not_bypass_separate_fit_readiness(
    tmp_path: Path,
) -> None:
    evidence = [
        _evidence(tmp_path, f"{index}.md", decision=index == 0)
        for index in range(len(FINDING_TYPES) + 1)
    ]
    admission_path = tmp_path / "admission.json"
    admission_sha = _write_json(admission_path, _admitted_document(evidence))
    policy = json.loads(
        (ROOT / "data/model_policies/hcpa_off_absolute_error_v1.json").read_text()
    )
    policy["admission_sha256"] = admission_sha
    policy_path = tmp_path / "policy.json"
    _write_json(policy_path, policy)

    result = admission.validate_files(admission_path, policy_path, tmp_path)

    assert result["source_admitted"] is False
    assert result["model_fit_permitted"] is False
    assert result["fit_readiness_status"] == "blocked"
    assert result["fit_readiness_blockers"]


@pytest.mark.parametrize(
    ("status", "admitted"),
    [("admitted", True), ("admitted", False), ("pending", True)],
)
def test_authoritative_acceptance_is_not_implemented(
    tmp_path: Path, status: str, admitted: bool
) -> None:
    evidence = [
        _evidence(tmp_path, f"{index}.md", decision=index == 0)
        for index in range(len(FINDING_TYPES) + 1)
    ]
    document = _admitted_document(evidence)
    document.update(status=status, admitted=admitted)

    with pytest.raises(ValueError, match="authoritative_acceptance_not_implemented"):
        admission.validate_document(document, tmp_path)


@pytest.mark.parametrize(
    ("field", "rights_field"),
    [
        ("s_date_is_closing_date", None),
        ("conservative_availability_method", None),
        ("deterministic_grouping_and_exclusion", None),
        ("rights", "research_training"),
        ("rights", "commercial_training"),
        ("rights", "commercial_serving"),
        ("rights", "derived_artifacts"),
    ],
)
def test_pending_metadata_remains_closed_when_a_required_fact_is_false(
    tmp_path: Path, field: str, rights_field: str | None
) -> None:
    evidence = [
        _evidence(tmp_path, f"{index}.md", decision=index == 0)
        for index in range(len(FINDING_TYPES) + 1)
    ]
    document = _admitted_document(evidence)
    requirements = document["requirements"]
    if rights_field is None:
        requirements[field] = False
    else:
        requirements["rights"][rights_field] = False

    result = admission.validate_document(document, tmp_path)
    assert result["source_admitted"] is False


@pytest.mark.parametrize(
    "mutation,match",
    [
        (lambda doc: doc.update(extra=True), "schema differs"),
        (lambda doc: doc["findings"].pop(), "four findings"),
        (
            lambda doc: doc["findings"][0].update(type="new_finding"),
            "finding types differ",
        ),
        (
            lambda doc: doc["findings"].append(dict(doc["findings"][0])),
            "four findings",
        ),
        (
            lambda doc: doc["findings"][0]["evidence_sha256"].append("f" * 64),
            "unknown evidence hash",
        ),
        (
            lambda doc: doc["findings"][0].update(
                evidence_sha256=[doc["decision"]["sha256"]]
            ),
            "unknown evidence hash",
        ),
        (
            lambda doc: doc["findings"][0].update(evidence_sha256=[]),
            "verified finding needs evidence",
        ),
        (
            lambda doc: doc["evidence"].append(dict(doc["evidence"][0])),
            "duplicate evidence hash",
        ),
        (
            lambda doc: doc["evidence"][0].update(kind="decision"),
            "Evidence list kind is invalid",
        ),
    ],
)
def test_unknown_missing_duplicate_and_invalid_evidence_fail_closed(
    tmp_path: Path, mutation, match: str
) -> None:
    evidence = [
        _evidence(tmp_path, f"{index}.md", decision=index == 0)
        for index in range(len(FINDING_TYPES) + 1)
    ]
    document = _admitted_document(evidence)
    mutation(document)

    with pytest.raises(ValueError, match=match):
        admission.validate_document(document, tmp_path)


def test_hash_mismatch_and_row_or_raw_inputs_are_rejected(tmp_path: Path) -> None:
    evidence = [
        _evidence(tmp_path, f"{index}.md", decision=index == 0)
        for index in range(len(FINDING_TYPES) + 1)
    ]
    document = _admitted_document(evidence)
    evidence[0]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="hash differs"):
        admission.validate_document(document, tmp_path)

    evidence = [
        _evidence(tmp_path, f"{index}.md", decision=index == 0)
        for index in range(len(FINDING_TYPES) + 1)
    ]
    document = _admitted_document(evidence)
    raw = tmp_path / "data/raw/hcpa/archive.zip"
    raw.parent.mkdir(parents=True)
    raw.write_bytes(b"row data")
    evidence[1].update(
        path="data/raw/hcpa/archive.zip",
        sha256=hashlib.sha256(b"row data").hexdigest(),
    )
    with pytest.raises(ValueError, match="dedicated HCPA evidence path"):
        admission.validate_document(document, tmp_path)


def test_symlink_oversized_and_non_regular_evidence_are_rejected(
    tmp_path: Path,
) -> None:
    evidence = [
        _evidence(tmp_path, f"{index}.md", decision=index == 0)
        for index in range(len(FINDING_TYPES) + 1)
    ]
    document = _admitted_document(evidence)
    target = tmp_path / evidence[1]["path"]
    target.write_bytes(b"x" * (admission.MAX_EVIDENCE_BYTES + 1))
    evidence[1]["sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="oversized"):
        admission.validate_document(document, tmp_path)

    target.write_bytes(b"safe")
    link = target.with_name("link.md")
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symlink creation is unavailable")
    evidence[1].update(
        path=link.relative_to(tmp_path).as_posix(),
        sha256=hashlib.sha256(b"safe").hexdigest(),
    )
    with pytest.raises(ValueError, match="regular file"):
        admission.validate_document(document, tmp_path)


def test_parent_directory_link_escape_is_rejected(tmp_path: Path) -> None:
    evidence = [
        _evidence(tmp_path, f"{index}.md", decision=index == 0)
        for index in range(len(FINDING_TYPES) + 1)
    ]
    document = _admitted_document(evidence)
    evidence_dir = tmp_path / "data/source_evidence/hcpa"
    external = tmp_path / "external"
    external.mkdir()
    for path in evidence_dir.iterdir():
        path.replace(external / path.name)
    evidence_dir.rmdir()
    try:
        evidence_dir.symlink_to(external, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlink creation is unavailable")
    with pytest.raises(ValueError, match="linked directory"):
        admission.validate_document(document, tmp_path)


def test_parent_reparse_attribute_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    evidence = [
        _evidence(tmp_path, f"{index}.md", decision=index == 0)
        for index in range(len(FINDING_TYPES) + 1)
    ]
    document = _admitted_document(evidence)
    original = admission._has_reparse_attribute
    calls = 0

    def second_directory_is_reparse(info) -> bool:
        nonlocal calls
        calls += 1
        return calls == 2 or original(info)

    monkeypatch.setattr(
        admission, "_has_reparse_attribute", second_directory_is_reparse
    )
    with pytest.raises(ValueError, match="linked directory"):
        admission.validate_document(document, tmp_path)


def test_snapshot_identity_change_and_open_errors_are_normalized(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "document.json"
    path.write_text("{}")
    actual = path.stat()
    changed = SimpleNamespace(
        st_mode=actual.st_mode,
        st_nlink=actual.st_nlink,
        st_size=actual.st_size,
        st_dev=actual.st_dev,
        st_ino=actual.st_ino + 1,
        st_file_attributes=0,
    )
    monkeypatch.setattr(admission.os, "fstat", lambda _descriptor: changed)
    with pytest.raises(ValueError, match="changed while opening"):
        admission._bounded_regular_bytes(path, 100)

    monkeypatch.undo()

    def denied(*_args, **_kwargs):
        raise PermissionError

    monkeypatch.setattr(admission.os, "open", denied)
    with pytest.raises(ValueError, match="unavailable"):
        admission._bounded_regular_bytes(path, 100)


def test_parent_identity_is_revalidated_after_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "document.json"
    path.write_text("{}")
    calls = 0

    def changing_parent_snapshot(_path: Path, _root: Path):
        nonlocal calls
        calls += 1
        return (("parent", calls),)

    monkeypatch.setattr(admission, "_parent_snapshot", changing_parent_snapshot)
    with pytest.raises(ValueError, match="parent changed while reading"):
        admission._read_under_root(path, tmp_path, 100)


def test_policy_is_exact_one_fit_absolute_error_and_semantics_are_pending() -> None:
    policy = json.loads(
        (ROOT / "data/model_policies/hcpa_off_absolute_error_v1.json").read_text()
    )

    admission.validate_policy(policy)
    assert policy["fit_count"] == 1
    assert policy["model"] == {
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
    assert set(policy["semantic_feature_flags"].values()) == {"pending"}


def test_policy_drift_is_rejected() -> None:
    policy = json.loads(
        (ROOT / "data/model_policies/hcpa_off_absolute_error_v1.json").read_text()
    )
    policy["model"]["n_estimators"] += 1
    with pytest.raises(ValueError, match="[Mm]odel configuration differs"):
        admission.validate_policy(policy)


def test_loader_rejects_duplicate_keys_invalid_roots_and_missing_file(
    tmp_path: Path,
) -> None:
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text('{"status":"pending","status":"admitted"}')
    with pytest.raises(ValueError, match="duplicate key"):
        admission.load_admission(duplicate)

    invalid = tmp_path / "invalid.json"
    invalid.write_bytes(b"\xff")
    with pytest.raises(ValueError, match="JSON document is invalid"):
        admission.load_admission(invalid)
    invalid.write_text("[]")
    with pytest.raises(ValueError, match="root must be an object"):
        admission.load_admission(invalid)
    with pytest.raises(ValueError, match="unavailable"):
        admission.load_admission(tmp_path / "missing.json")


@pytest.mark.parametrize(
    "mutation,match",
    [
        (lambda doc: doc.update(schema_version="future"), "metadata differs"),
        (lambda doc: doc.update(admitted=1), "metadata differs"),
        (lambda doc: doc.update(status=[]), "metadata differs"),
        (lambda doc: doc.update(decision=[]), "collection is invalid"),
        (lambda doc: doc["evidence"].append("bad"), "collection is invalid"),
        (lambda doc: doc["decision"].pop("path"), "reference schema differs"),
        (lambda doc: doc["decision"].update(kind="evidence"), "Decision reference"),
        (lambda doc: doc["decision"].update(sha256="ABC"), "reference is invalid"),
        (lambda doc: doc["decision"].update(kind=[]), "Decision reference"),
        (
            lambda doc: doc["decision"].update(path="../escape.md"),
            "reference is invalid",
        ),
        (
            lambda doc: doc["decision"].update(path="decisions\\bad.md"),
            "reference is invalid",
        ),
        (
            lambda doc: doc["evidence"][0].update(path="data/raw/file.md"),
            "dedicated HCPA evidence path",
        ),
        (
            lambda doc: doc["decision"].update(path="decisions/file.zip"),
            "frozen decision",
        ),
        (
            lambda doc: doc["findings"][0].update(status="asserted"),
            "status is invalid",
        ),
        (
            lambda doc: doc["findings"][0].update(type=[]),
            "values are invalid",
        ),
        (
            lambda doc: doc["findings"][0].update(evidence_sha256="hash"),
            "hashes are invalid",
        ),
        (
            lambda doc: doc["findings"][0].update(
                evidence_sha256=[doc["decision"]["sha256"]] * 2
            ),
            "duplicate evidence hashes",
        ),
        (lambda doc: doc["requirements"].pop("rights"), "requirements schema"),
        (
            lambda doc: doc["requirements"].update(s_date_is_closing_date=1),
            "requirement is not boolean",
        ),
        (
            lambda doc: doc["requirements"]["rights"].pop("derived_artifacts"),
            "Rights schema",
        ),
        (
            lambda doc: doc["requirements"]["rights"].update(derived_artifacts=1),
            "Rights decision is not boolean",
        ),
    ],
)
def test_additional_schema_and_path_failures_are_closed(
    tmp_path: Path, mutation, match: str
) -> None:
    evidence = [
        _evidence(tmp_path, f"{index}.md", decision=index == 0)
        for index in range(len(FINDING_TYPES) + 1)
    ]
    document = _admitted_document(evidence)
    mutation(document)
    with pytest.raises(ValueError, match=match):
        admission.validate_document(document, tmp_path)


def test_hardlinked_evidence_and_policy_binding_drift_are_rejected(
    tmp_path: Path,
) -> None:
    evidence = [
        _evidence(tmp_path, f"{index}.md", decision=index == 0)
        for index in range(len(FINDING_TYPES) + 1)
    ]
    document = _admitted_document(evidence)
    original = tmp_path / evidence[1]["path"]
    hardlink = original.with_name("hardlink.md")
    try:
        os.link(original, hardlink)
    except OSError:
        pytest.skip("hard links are unavailable")
    evidence[1]["path"] = hardlink.relative_to(tmp_path).as_posix()
    with pytest.raises(ValueError, match="regular file"):
        admission.validate_document(document, tmp_path)

    policy = json.loads(
        (ROOT / "data/model_policies/hcpa_off_absolute_error_v1.json").read_text()
    )
    evidence = [
        _evidence(tmp_path, f"fresh-{index}.md", decision=index == 0)
        for index in range(len(FINDING_TYPES) + 1)
    ]
    admission_path = tmp_path / "admission.json"
    _write_json(admission_path, _admitted_document(evidence))
    policy["admission_sha256"] = "0" * 64
    policy_path = tmp_path / "policy.json"
    _write_json(policy_path, policy)
    with pytest.raises(ValueError, match="admission hash differs"):
        admission.validate_files(
            admission_path,
            policy_path,
            tmp_path,
        )


@pytest.mark.parametrize(
    "mutation,match",
    [
        (lambda policy: policy.update(extra=True), "policy schema differs"),
        (lambda policy: policy.update(fit_count=True), "metadata differs"),
        (
            lambda policy: policy["semantic_feature_flags"].update(extra="pending"),
            "feature flags differ",
        ),
        (
            lambda policy: policy["semantic_feature_flags"].update(
                eligibility_codes=[]
            ),
            "feature flags differ",
        ),
        (lambda policy: policy.update(admission_sha256="bad"), "hash is invalid"),
        (
            lambda policy: policy["execution_constraints"].update(
                train_only_if_admitted=False
            ),
            "constraints differ",
        ),
    ],
)
def test_additional_policy_drift_is_rejected(mutation, match: str) -> None:
    policy = json.loads(
        (ROOT / "data/model_policies/hcpa_off_absolute_error_v1.json").read_text()
    )
    mutation(policy)
    with pytest.raises(ValueError, match=match):
        admission.validate_policy(policy)


def test_cli_returns_deterministic_pending_result_and_generic_failure(
    capsys: pytest.CaptureFixture[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert admission.main([]) == 0
    assert capsys.readouterr().out == (
        '{"comparable_display_permitted":false,"fit_readiness_blockers":'
        '["semantic_feature_flags_pending","historical_property_attributes_pending",'
        '"eligibility_rules_pending"],"fit_readiness_status":"blocked",'
        '"model_fit_permitted":false,"source_admitted":false,'
        '"source_id":"hillsborough_hcpa_allsales",'
        '"status":"pending"}\n'
    )

    with pytest.raises(SystemExit) as rejected:
        admission.main(["--admission", str(tmp_path / "other.json")])
    assert rejected.value.code == 2
    capsys.readouterr()

    bad_admission = tmp_path / "data/source_admission/hcpa_allsales_v1.json"
    bad_policy = tmp_path / "data/model_policies/hcpa_off_absolute_error_v1.json"
    bad_admission.parent.mkdir(parents=True)
    bad_policy.parent.mkdir(parents=True)
    bad_admission.write_text('{"broken":')
    bad_policy.write_text("{}")
    monkeypatch.setattr(admission, "ROOT", tmp_path)
    monkeypatch.setattr(admission, "ADMISSION_PATH", bad_admission)
    monkeypatch.setattr(admission, "POLICY_PATH", bad_policy)

    assert admission.main([]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "HCPA admission validation failed\n"
