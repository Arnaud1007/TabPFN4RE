"""Auditable, non-certifying 200-row Ames engineering run."""

from __future__ import annotations

import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import time
from typing import Any
from uuid import uuid4

from . import ames as ames_module
from .ames import (
    MAX_AMES_BYTES,
    engineering_split,
    fit_median_baseline,
    load_ames_arff,
    median_absolute_percentage_error,
    signed_percentage_error,
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")


def _write_json(path: Path, value: Any) -> None:
    path.write_bytes(_json_bytes(value))


def _git_state(project_root: Path) -> tuple[str | None, bool]:
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=project_root, capture_output=True, text=True,
        check=False,
    )
    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all", "--", ".", ":(exclude)runs"],
        cwd=project_root, capture_output=True, text=True,
        check=False,
    )
    if commit.returncode != 0 or status.returncode != 0:
        return None, True
    return commit.stdout.strip(), bool(status.stdout.strip())


def _executed_modules(
    project_root: Path,
) -> tuple[dict[str, str], bool, dict[str, bytes]]:
    module_files = {
        "tabpfn4realestate.ames": Path(ames_module.__file__).resolve(),
        "tabpfn4realestate.ames_smoke": Path(__file__).resolve(),
    }
    expected = {
        "tabpfn4realestate.ames": project_root / "src" / "tabpfn4realestate" / "ames.py",
        "tabpfn4realestate.ames_smoke": project_root / "src" / "tabpfn4realestate" / "ames_smoke.py",
    }
    contents = {name: path.read_bytes() for name, path in module_files.items()}
    hashes = {name: _sha256_bytes(value) for name, value in contents.items()}
    in_project = all(path == expected[name].resolve() for name, path in module_files.items())
    return hashes, in_project, contents


def _committed_inputs_match(
    project_root: Path,
    commit: str | None,
    module_bytes: dict[str, bytes],
    lock_bytes: bytes,
    policy_bytes: bytes,
) -> bool:
    if commit is None:
        return False
    required = {
        "src/tabpfn4realestate/ames.py": module_bytes["tabpfn4realestate.ames"],
        "src/tabpfn4realestate/ames_smoke.py": module_bytes["tabpfn4realestate.ames_smoke"],
        "locks/ames-smoke-environment.json": lock_bytes,
        "policies/ames-smoke.json": policy_bytes,
    }
    for relative, content in required.items():
        head = subprocess.run(
            ["git", "rev-parse", f"{commit}:{relative}"],
            cwd=project_root, capture_output=True, check=False,
        )
        current = subprocess.run(
            ["git", "hash-object", "--stdin", f"--path={relative}"],
            cwd=project_root, input=content, capture_output=True, check=False,
        )
        if (
            head.returncode != 0
            or current.returncode != 0
            or head.stdout.strip() != current.stdout.strip()
        ):
            return False
    return True


def _locked_inputs(project_root: Path) -> tuple[bytes, bytes, dict[str, Any]]:
    lock_bytes = (project_root / "locks" / "ames-smoke-environment.json").read_bytes()
    policy_bytes = (project_root / "policies" / "ames-smoke.json").read_bytes()
    lock = json.loads(lock_bytes)
    if lock["python_implementation"] != platform.python_implementation():
        raise RuntimeError("Ames smoke Python implementation differs from environment lock")
    if lock["python_version"] != platform.python_version():
        raise RuntimeError("Ames smoke Python version differs from environment lock")
    policy = json.loads(policy_bytes)
    if policy["protocol_id"] != "ames_engineering_v1" or policy["model_input_features"]:
        raise RuntimeError("Ames smoke feature policy is incompatible")
    return lock_bytes, policy_bytes, policy


def _copy_source_bounded(source: Path, destination: Path) -> None:
    total = 0
    with source.open("rb") as incoming, destination.open("wb") as saved:
        for chunk in iter(lambda: incoming.read(1024 * 1024), b""):
            total += len(chunk)
            if total > MAX_AMES_BYTES:
                raise ValueError("Source exceeds the Ames size limit")
            saved.write(chunk)


def _write_predictions(path: Path, reserved_rows: list[dict[str, str]], price: float) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["Id", "actual", "predicted"])
        writer.writeheader()
        writer.writerows(
            {"Id": row["Id"], "actual": row["SalePrice"], "predicted": price}
            for row in reserved_rows
        )


def run_smoke(
    source_path: str | Path,
    output_dir: str | Path,
    *,
    expected_sha256: str,
    sample_size: int = 200,
    seed: int = 42,
    project_root: str | Path | None = None,
) -> Path:
    """Run one engineering check and retain its evidence under a unique ID."""
    started = time.monotonic()
    root = Path(project_root) if project_root is not None else Path.cwd()
    project_commit, dirty_tree = _git_state(root)
    module_hashes, code_in_project, module_bytes = _executed_modules(root)
    commit = None
    replayable = False
    run_id = f"u0-smoke-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{uuid4().hex[:12]}"
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    staging = output / f".incomplete-{run_id}"
    final = output / run_id
    staging.mkdir()

    try:
        if sample_size < 2:
            raise ValueError("sample_size must be at least 2 rows")
        lock_bytes, policy_bytes, policy = _locked_inputs(root)
        committed_inputs = code_in_project and _committed_inputs_match(
            root, project_commit, module_bytes, lock_bytes, policy_bytes
        )
        commit = project_commit if committed_inputs else None
        replayable = not dirty_tree and committed_inputs
        source = Path(source_path)
        rows = load_ames_arff(source, expected_sha256=expected_sha256)
        _copy_source_bounded(source, staging / "source.arff")
        source_sha256 = _sha256(staging / "source.arff")
        if source_sha256 != expected_sha256.lower():
            raise ValueError("Source SHA-256 changed after verified load")
        if len(rows) < sample_size:
            raise ValueError(f"Source has {len(rows)} rows, fewer than sample_size {sample_size}")
        is_official = (
            source_sha256 == policy["official_source_sha256"]
            and len(rows) == policy["official_source_rows"]
        )
        source_identity = "openml_42165_v1" if is_official else "unverified_fixture"
        if is_official and not replayable:
            raise RuntimeError("Official Ames run requires a clean committed project")
        (staging / "environment.lock.json").write_bytes(lock_bytes)
        (staging / "feature_policy.json").write_bytes(policy_bytes)
        selected = rows[:sample_size]
        split = engineering_split(selected, seed=seed)
        development = set(split.development_ids)
        reserved = set(split.reserved_ids)
        train_rows = [row for row in selected if row["Id"] in development]
        reserved_rows = [row for row in selected if row["Id"] in reserved]
        selected_ids = {row["Id"] for row in selected}
        if (
            development & reserved
            or development | reserved != selected_ids
            or len(train_rows) != len(split.development_ids)
            or len(reserved_rows) != len(split.reserved_ids)
        ):
            raise ValueError("Engineering split partition does not match selected Id values")
        model = fit_median_baseline(train_rows, split=split)
        predictions = model.predict(reserved_rows)
        actuals = [float(row["SalePrice"]) for row in reserved_rows]

        config = {
            "protocol_id": split.protocol_id,
            "sample_size": sample_size,
            "seed": seed,
            "model": "median_baseline_v1",
            "selection": "first_n_source_rows",
        }
        _write_json(staging / "config.json", config)
        _write_json(staging / "split.json", {
            "protocol_id": split.protocol_id,
            "development_ids": split.development_ids,
            "reserved_ids": split.reserved_ids,
        })
        _write_json(staging / "baseline.json", {"median_price": model.median_price})
        _write_predictions(staging / "predictions.csv", reserved_rows, model.median_price)
        errors = [signed_percentage_error(actual, predicted)
                  for actual, predicted in zip(actuals, predictions, strict=True)]
        _write_json(staging / "metrics.json", {
            "count": len(errors),
            "mdape": median_absolute_percentage_error(actuals, predictions),
            "within_10": sum(abs(error) <= 0.10 for error in errors) / len(errors),
        })
        manifest = {
            "run_id": run_id,
            "status": "incomplete",
            "protocol_id": split.protocol_id,
            "certification_eligible": False,
            "source_identity": source_identity,
            "code_commit": commit,
            "dirty_tree": dirty_tree,
            "replayable": replayable,
            "executed_module_sha256": module_hashes,
            "source_sha256": source_sha256,
            "data_snapshot_hash": source_sha256,
            "split_sha256": _sha256(staging / "split.json"),
            "config_sha256": _sha256(staging / "config.json"),
            "feature_policy_sha256": _sha256(staging / "feature_policy.json"),
            "environment_lock_sha256": _sha256(staging / "environment.lock.json"),
            "checkpoint_identity": "median_baseline_v1",
            "checkpoint_sha256": _sha256(staging / "baseline.json"),
            "predictions_sha256": _sha256(staging / "predictions.csv"),
            "metrics_sha256": _sha256(staging / "metrics.json"),
            "duration_seconds": time.monotonic() - started,
        }
        _write_json(staging / "manifest.json", manifest)
        staging.rename(final)
        _write_json(final / "manifest.complete.tmp", {**manifest, "status": "complete"})
        (final / "manifest.complete.tmp").replace(final / "manifest.json")
        return final
    except Exception as error:
        failure_dir = final if final.exists() else staging
        _write_json(failure_dir / "manifest.json", {
            "run_id": run_id,
            "status": "failed",
            "protocol_id": "ames_engineering_v1",
            "certification_eligible": False,
            "code_commit": commit,
            "dirty_tree": dirty_tree,
            "error_type": type(error).__name__,
            "error_message": str(error),
        })
        raise


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--output", type=Path, default=Path("runs"))
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    arguments = parser.parse_args()
    run_dir = run_smoke(
        arguments.source,
        arguments.output,
        expected_sha256=arguments.sha256,
        project_root=arguments.project_root,
    )
    print(run_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
