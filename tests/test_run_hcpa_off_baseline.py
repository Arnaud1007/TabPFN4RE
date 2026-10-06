"""The HCPA baseline runner must stop before any source or model work."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

from scripts import run_hcpa_off_baseline as runner

ROOT = Path(__file__).resolve().parents[1]


PENDING_GATE = {
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


def test_preflight_calls_gate_first_and_returns_immutable_blocked_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def gate():
        calls.append("gate")
        return PENDING_GATE

    monkeypatch.setattr(runner, "_current_gate", gate)
    result = runner.run_preflight()

    assert calls == ["gate"]
    assert dict(result) == {
        "protocol": "hcpa_off_baseline_preflight_v1",
        "status": "blocked",
        "source_id": "hillsborough_hcpa_allsales",
        "source_status": "pending",
        "source_admitted": False,
        "model_fit_permitted": False,
        "fit_readiness_status": "blocked",
        "fit_readiness_blockers": (
            "source_not_admitted",
            "semantic_feature_flags_pending",
            "historical_property_attributes_pending",
            "eligibility_rules_pending",
        ),
        "model_fit_executed": False,
        "outputs_written": False,
    }
    with pytest.raises(TypeError):
        result["status"] = "ready"  # type: ignore[index]


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value.update(source_admitted=True),
        lambda value: value.update(model_fit_permitted=True),
        lambda value: value.update(fit_readiness_status="ready"),
        lambda value: value.update(status="rejected"),
        lambda value: value.pop("fit_readiness_blockers"),
        lambda value: value.update(fit_readiness_blockers=[]),
        lambda value: value.update(
            fit_readiness_blockers=iter(PENDING_GATE["fit_readiness_blockers"])
        ),
    ],
)
def test_preflight_fails_closed_on_unimplemented_or_drifted_gate_result(
    mutation, monkeypatch: pytest.MonkeyPatch
) -> None:
    changed = dict(PENDING_GATE)
    mutation(changed)
    monkeypatch.setattr(runner, "_current_gate", lambda: changed)
    with pytest.raises(ValueError, match="HCPA preflight gate result differs"):
        runner.run_preflight()


def test_gate_error_propagates_before_any_later_operation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    marker = RuntimeError("gate integrity failed")

    def gate():
        raise marker

    monkeypatch.setattr(runner, "_current_gate", gate)
    with pytest.raises(RuntimeError, match="gate integrity failed"):
        runner.run_preflight()


def test_module_has_no_ml_or_raw_pipeline_imports_and_no_output_writer() -> None:
    source = (ROOT / "scripts/run_hcpa_off_baseline.py").read_text(encoding="utf-8")
    forbidden = (
        "numpy",
        "xgboost",
        "dbf",
        "zipfile",
        "review_hcpa_sample",
        "hcpa_release_observation_ledger",
        "open(",
        "write_text",
        "write_bytes",
    )
    assert all(token not in source.lower() for token in forbidden)


def test_cli_is_deterministic_accepts_no_paths_and_fails_generically(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    assert runner.main([]) == 3
    first = capsys.readouterr()
    assert first.err == ""
    assert json.loads(first.out) == json.loads(json.dumps(dict(runner.run_preflight())))

    assert runner.main([]) == 3
    assert capsys.readouterr().out == first.out

    sensitive_path = "data/raw/hcpa/PRIVATE-file.zip"
    assert runner.main(["--source", sensitive_path]) == 2
    rejected = capsys.readouterr()
    assert rejected.out == ""
    assert rejected.err == "HCPA OFF baseline preflight failed\n"
    assert secret not in rejected.err

    monkeypatch.setattr(
        runner,
        "run_preflight",
        lambda: (_ for _ in ()).throw(
            RuntimeError("sensitive detail at C:/private/source.zip")
        ),
    )
    assert runner.main([]) == 2
    failed = capsys.readouterr()
    assert failed.out == ""
    assert failed.err == "HCPA OFF baseline preflight failed\n"
    assert "sensitive" not in failed.err


def test_package_module_invocation_returns_exact_blocked_result() -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "scripts.run_hcpa_off_baseline"],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
        timeout=10,
    )

    assert completed.returncode == 3
    assert completed.stderr == ""
    assert json.loads(completed.stdout) == json.loads(
        json.dumps(dict(runner.run_preflight()))
    )


def test_direct_script_invocation_returns_exact_blocked_result() -> None:
    completed = subprocess.run(
        [sys.executable, "scripts/run_hcpa_off_baseline.py"],
        cwd=ROOT,
        capture_output=True,
        check=False,
        text=True,
        timeout=10,
    )

    assert completed.returncode == 3
    assert completed.stderr == ""
    assert json.loads(completed.stdout) == json.loads(
        json.dumps(dict(runner.run_preflight()))
    )
