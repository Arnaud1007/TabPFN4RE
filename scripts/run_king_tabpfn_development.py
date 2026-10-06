"""Preflight and run one bounded local TabPFN 3.5 King candidate."""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.metadata
import json
import math
import os
import platform
import shutil
import subprocess
import tempfile
import time
from collections.abc import Sequence
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path

from scripts.king_historical_benchmark import Sale, encode_features
from scripts.private_review_io import real_directory, secure_directory, verify_acl
from scripts.run_king_lightgbm_development import (
    FROZEN_MANIFEST_SHA256,
    FROZEN_PREDICTION_SHA256,
    FROZEN_SPLIT_SHA256,
    PRIVATE_ROOT,
    WINDOWS,
    load_frozen_manifest,
    monthly_windows,
    parse_frozen_incumbent,
    read_development_source,
    read_frozen_prediction_snapshot,
    verify_frozen_design,
    verify_frozen_membership,
)
from scripts.run_king_comparable_development import membership_for
from scripts.run_king_historical_benchmark import (
    _committed_code,
    _score,
    _score_summary,
)

ROOT = Path(__file__).resolve().parents[1]
DECLARED_LOCK = ROOT / "locks/king-tabpfn-development.json"
DECLARED_LOCK_SHA256 = (
    "5fdad383cdaa8141f18783b5a3fd4383b3e464a7b7690a475c47612a9b7f187b"
)
MAX_LOCK_BYTES = 20_000
MAX_LICENSE_BYTES = 20_000
MAX_CHECKPOINT_BYTES = 10 * 1024**3
MIN_FREE_DISK_BYTES = 8 * 1024**3
MIN_CUDA_MEMORY_BYTES = 8 * 1024**3
MAX_CONTEXT_ROWS = 10_000
PREDICTION_REPEAT_COUNT = 3
PREDICTION_ABS_TOLERANCE_USD = 0.01
PREDICTION_REL_TOLERANCE = 1e-6
FIT_REJECTION_CAP_SECONDS = 300.0
OVERALL_REJECTION_CAP_SECONDS = 1200.0

EXPECTED_LOCK: dict[str, object] = {
    "checkpoint": {
        "filename": "tabpfn-v3.5-20260909.safetensors",
        "hugging_face_repository": "Prior-Labs/tabpfn_3_5",
        "id": "tabpfn_3_5/tabpfn-v3.5-20260909.safetensors",
        "revision": None,
        "sha256": None,
    },
    "dependencies": {"numpy": "2.4.6", "tabpfn": "9.1.0", "torch": "2.10.0"},
    "license": {
        "acceptance_automated": False,
        "gated_weights": True,
        "release_eligibility": "unresolved",
    },
    "python": "3.11.6",
    "schema_version": 1,
    "source": {"commit": "0b1a081", "release_tag": "v9.1.0"},
}


def _read_small_regular(path: Path, limit: int, label: str) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} must be a regular local file")
    size = path.stat().st_size
    if size <= 0 or size > limit:
        raise ValueError(f"{label} size is invalid")
    with path.open("rb") as handle:
        return handle.read(limit + 1)


def _load_lock() -> dict[str, object]:
    content = _read_small_regular(DECLARED_LOCK, MAX_LOCK_BYTES, "Declared lock")
    if hashlib.sha256(content).hexdigest() != DECLARED_LOCK_SHA256:
        raise ValueError("Declared lock hash is incompatible")
    try:
        value = json.loads(content.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("Declared lock is invalid") from error
    if not isinstance(value, dict):
        raise ValueError("Declared lock must be an object")
    return value


def package_version() -> str | None:
    try:
        return importlib.metadata.version("tabpfn")
    except importlib.metadata.PackageNotFoundError:
        return None


def dependency_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def python_version() -> str:
    return platform.python_version()


def runtime_identity() -> dict[str, object]:
    versions = {
        name: importlib.metadata.version(name) for name in ("numpy", "tabpfn", "torch")
    }
    try:
        import torch

        torch_build = torch.__version__
        cuda_runtime = torch.version.cuda
    except (ImportError, OSError):
        torch_build = None
        cuda_runtime = None
    try:
        probe = subprocess.run(
            ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
        driver = probe.stdout.splitlines()[0].strip()
    except (OSError, subprocess.SubprocessError, IndexError):
        driver = None
    return {
        "python": python_version(),
        "packages": versions,
        "torch_build": torch_build,
        "cuda_runtime": cuda_runtime,
        "nvidia_driver": driver,
        "platform": platform.platform(),
        "machine": platform.machine(),
    }


def verify_runtime(lock: dict[str, object]) -> dict[str, object]:
    observed = runtime_identity()
    dependencies = lock.get("dependencies")
    if (
        not isinstance(dependencies, dict)
        or observed["python"] != lock.get("python")
        or observed["packages"] != dependencies
    ):
        raise ValueError("Runtime versions do not match the frozen lock")
    return observed


def cuda_capability() -> tuple[bool, int, str]:
    try:
        import torch
    except (ImportError, OSError) as error:
        return False, 0, f"torch unavailable: {type(error).__name__}"
    if not torch.cuda.is_available():
        return False, 0, "CUDA is unavailable"
    try:
        memory = int(torch.cuda.get_device_properties(0).total_memory)
    except (RuntimeError, AssertionError) as error:
        return False, 0, f"CUDA probe failed: {type(error).__name__}"
    return memory >= MIN_CUDA_MEMORY_BYTES, memory, "ok"


def free_disk_bytes(path: Path) -> int:
    anchor = path if path.exists() else path.parent
    while not anchor.exists() and anchor != anchor.parent:
        anchor = anchor.parent
    return shutil.disk_usage(anchor).free


def checkpoint_sha256(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise ValueError("Checkpoint must be a regular local file")
    size = path.stat().st_size
    if size <= 0 or size > MAX_CHECKPOINT_BYTES:
        raise ValueError("Checkpoint size is invalid")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _block(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def _license_compatible(path: Path, checkpoint: dict[str, object]) -> bool:
    try:
        content = _read_small_regular(path, MAX_LICENSE_BYTES, "License decision")
        value = json.loads(content.decode("utf-8-sig"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    return bool(
        isinstance(value, dict)
        and value.get("schema_version") == 1
        and value.get("checkpoint_id") == checkpoint.get("id")
        and value.get("checkpoint_revision") == checkpoint.get("revision")
        and value.get("checkpoint_sha256") == checkpoint.get("sha256")
        and value.get("research_use_permitted") is True
        and value.get("commercially_eligible") is False
        and value.get("decision") == "approved_for_local_research"
    )


def preflight(checkpoint_path: Path, license_decision: Path) -> dict[str, object]:
    """Return a path-free capability result without opening source labels."""
    lock = _load_lock()
    checkpoint = lock.get("checkpoint")
    if not isinstance(checkpoint, dict):
        raise ValueError("Declared checkpoint lock is invalid")
    blockers: list[dict[str, str]] = []
    observed_python = python_version()
    if observed_python != lock.get("python"):
        blockers.append(_block("python_version_mismatch", "Python 3.11.6 is required"))
    observed_package = package_version()
    if observed_package is None:
        blockers.append(_block("package_unavailable", "TabPFN is not installed"))
    elif observed_package != "9.1.0":
        blockers.append(
            _block("package_version_mismatch", "TabPFN is not version 9.1.0")
        )
    dependencies = lock.get("dependencies")
    if not isinstance(dependencies, dict):
        raise ValueError("Declared dependency lock is invalid")
    for name in ("numpy", "torch"):
        if dependency_version(name) != dependencies.get(name):
            blockers.append(
                _block(
                    f"{name}_version_mismatch", f"{name} does not match the frozen lock"
                )
            )
    cuda_ready, cuda_memory, cuda_reason = cuda_capability()
    if not cuda_ready:
        blockers.append(_block("cuda_unavailable", cuda_reason))
    free_bytes = free_disk_bytes(PRIVATE_ROOT)
    checkpoint_size = (
        checkpoint_path.stat().st_size
        if checkpoint_path.is_file() and not checkpoint_path.is_symlink()
        else 0
    )
    required_free_bytes = MIN_FREE_DISK_BYTES + checkpoint_size
    if free_bytes < required_free_bytes:
        blockers.append(
            _block(
                "destination_disk_insufficient",
                "Private output volume lacks checkpoint-copy space and safety reserve",
            )
        )
    expected_hash = checkpoint.get("sha256")
    revision = checkpoint.get("revision")
    if (
        not isinstance(expected_hash, str)
        or len(expected_hash) != 64
        or not isinstance(revision, str)
        or not revision
    ):
        blockers.append(
            _block(
                "checkpoint_identity_unresolved",
                "Authorized checkpoint revision and SHA-256 are not pinned",
            )
        )
    try:
        observed_hash = checkpoint_sha256(checkpoint_path)
    except ValueError:
        blockers.append(
            _block("checkpoint_unavailable", "Pinned local checkpoint is unavailable")
        )
    else:
        if isinstance(expected_hash, str) and observed_hash != expected_hash:
            blockers.append(
                _block(
                    "checkpoint_hash_mismatch",
                    "Local checkpoint does not match the pinned SHA-256",
                )
            )
    if not license_decision.is_file() or license_decision.is_symlink():
        blockers.append(
            _block(
                "license_decision_unavailable", "Owner license decision is unavailable"
            )
        )
    elif not _license_compatible(license_decision, checkpoint):
        blockers.append(
            _block(
                "license_decision_incompatible",
                "Owner license decision does not authorize this exact research checkpoint",
            )
        )
    return {
        "status": "ready" if not blockers else "blocked",
        "model": "TabPFN 3.5",
        "package_version": observed_package,
        "python_version": observed_python,
        "checkpoint_id": checkpoint.get("id"),
        "cuda_memory_bytes": cuda_memory,
        "free_disk_bytes": free_bytes,
        "required_free_disk_bytes": required_free_bytes,
        "commercially_eligible": False,
        "automatic_downloads": False,
        "remote_inference": False,
        "offline_environment_configured": True,
        "blockers": blockers,
    }


def configuration() -> dict[str, object]:
    return {
        "model_family": "tabpfn_3_5",
        "package": "tabpfn==9.1.0",
        "checkpoint_id": EXPECTED_LOCK["checkpoint"]["id"],  # type: ignore[index]
        "device": "cuda",
        "random_state": 42,
        "n_estimators": 8,
        "fit_count": 4,
        "max_context_rows": MAX_CONTEXT_ROWS,
        "context_selection": "most_recent_training_rows",
        "target": "log_price",
        "automatic_downloads": False,
        "remote_inference": False,
        "prediction_repeat_count": PREDICTION_REPEAT_COUNT,
        "prediction_absolute_tolerance_usd": PREDICTION_ABS_TOLERANCE_USD,
        "prediction_relative_tolerance": PREDICTION_REL_TOLERANCE,
        "fit_post_hoc_rejection_cap_seconds": FIT_REJECTION_CAP_SECONDS,
        "overall_post_hoc_rejection_cap_seconds": OVERALL_REJECTION_CAP_SECONDS,
        "comparison_class": "reduced_context_tabpfn_vs_full_history_tree",
        "superiority_claim_permitted": False,
        "windows": [
            (name, start.isoformat(), end.isoformat()) for name, start, end in WINDOWS
        ],
    }


def frozen_beat_rule(**values: object) -> str:
    improved_windows = int(values["improved_windows"])  # type: ignore[arg-type]
    if not 0 <= improved_windows <= len(WINDOWS):
        raise ValueError("improved_windows must be between zero and four")
    numeric = {
        key: Decimal(str(values[key]))
        for key in (
            "incumbent_mdape",
            "challenger_mdape",
            "incumbent_within_10",
            "challenger_within_10",
            "incumbent_p90",
            "challenger_p90",
        )
    }
    challenger_wins = (
        numeric["challenger_mdape"] <= numeric["incumbent_mdape"] * Decimal("0.98")
        and improved_windows >= 3
        and numeric["challenger_within_10"]
        >= numeric["incumbent_within_10"] - Decimal("0.005")
        and numeric["challenger_p90"] <= numeric["incumbent_p90"] + Decimal("0.005")
    )
    return (
        "tabpfn_3_5_reduced_context"
        if challenger_wins
        else "xgboost_log_absolute_error"
    )


def _regressor(checkpoint_path: Path):
    from tabpfn import TabPFNRegressor

    return TabPFNRegressor(
        model_path=str(checkpoint_path),
        device="cuda",
        random_state=42,
        n_estimators=8,
    )


@contextmanager
def offline_environment():
    required = {
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "HF_DATASETS_OFFLINE": "1",
        "TABPFN_DISABLE_TELEMETRY": "1",
    }
    previous = {name: os.environ.get(name) for name in required}
    os.environ.update(required)
    try:
        yield
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def fit_tabpfn(
    training: Sequence[Sale],
    validation: Sequence[Sale],
    checkpoint_path: Path,
    expected_checkpoint_sha256: str,
) -> tuple[tuple[float, ...], dict[str, object]]:
    import numpy as np

    context = tuple(
        sorted(training, key=lambda row: (row.sale_date, row.row_id))[
            -MAX_CONTEXT_ROWS:
        ]
    )
    _, training_rows, validation_rows = encode_features(context, validation)
    if checkpoint_sha256(checkpoint_path) != expected_checkpoint_sha256:
        raise ValueError("Verified checkpoint changed before model construction")
    with offline_environment():
        model = _regressor(checkpoint_path)
        model.fit(
            np.asarray(training_rows, dtype=np.float32),
            np.log(np.asarray([float(row.price) for row in context])),
        )
        repeats = tuple(
            tuple(
                float(value)
                for value in np.exp(
                    model.predict(np.asarray(validation_rows, dtype=np.float32))
                )
            )
            for _ in range(PREDICTION_REPEAT_COUNT)
        )
    if any(
        len(repeat) != len(validation)
        or not all(math.isfinite(value) and value > 0 for value in repeat)
        for repeat in repeats
    ):
        raise ValueError("TabPFN produced invalid predictions")
    predicted = repeats[0]
    absolute_variation = max(
        (
            abs(value - reference)
            for repeat in repeats[1:]
            for value, reference in zip(repeat, predicted, strict=True)
        ),
        default=0.0,
    )
    relative_variation = max(
        (
            abs(value - reference) / max(abs(reference), 1.0)
            for repeat in repeats[1:]
            for value, reference in zip(repeat, predicted, strict=True)
        ),
        default=0.0,
    )
    if (
        absolute_variation > PREDICTION_ABS_TOLERANCE_USD
        or relative_variation > PREDICTION_REL_TOLERANCE
    ):
        raise ValueError("TabPFN repeated predictions exceed frozen tolerance")
    context_ids = tuple(row.row_id for row in context)
    return predicted, {
        "context_row_count": len(context_ids),
        "context_row_ids_sha256": hashlib.sha256(
            json.dumps(context_ids, separators=(",", ":")).encode()
        ).hexdigest(),
        "prediction_repeat_count": PREDICTION_REPEAT_COUNT,
        "max_absolute_variation_usd": absolute_variation,
        "max_relative_variation": relative_variation,
    }


def run(
    source: Path,
    incumbent_predictions: Path,
    checkpoint_path: Path,
    license_decision: Path,
    output: Path,
) -> dict[str, object]:
    started = time.monotonic()
    capability = preflight(checkpoint_path, license_decision)
    if capability["status"] != "ready":
        raise RuntimeError("TabPFN preflight blocked; no source labels were opened")
    real_directory(PRIVATE_ROOT, PRIVATE_ROOT.parent)
    verify_acl(PRIVATE_ROOT)
    if (
        output.exists()
        or output.is_symlink()
        or output.parent.resolve() != PRIVATE_ROOT.resolve()
    ):
        raise ValueError("Output must be a new private King benchmark directory")
    lock = _load_lock()
    runtime = verify_runtime(lock)
    commit = _committed_code()
    locked_checkpoint = lock["checkpoint"]
    if not isinstance(locked_checkpoint, dict) or not isinstance(
        locked_checkpoint.get("sha256"), str
    ):
        raise ValueError("Pinned checkpoint identity is unresolved")
    expected_checkpoint_sha256 = locked_checkpoint["sha256"]
    frozen = load_frozen_manifest()
    verify_frozen_design(frozen)
    incumbent_snapshot = read_frozen_prediction_snapshot(incumbent_predictions, frozen)
    sales, source_hash = read_development_source(source)
    windows = monthly_windows(sales)
    membership = membership_for(windows)
    verify_frozen_membership(membership, frozen)
    incumbent = parse_frozen_incumbent(incumbent_snapshot, windows)
    staging = Path(tempfile.mkdtemp(prefix=".tabpfn-", dir=output.parent))
    verified_checkpoint: Path | None = None
    try:
        secure_directory(staging)
        real_directory(staging, PRIVATE_ROOT)
        verify_acl(staging)
        verified_checkpoint = staging / "verified-tabpfn-v3.5.safetensors"
        shutil.copyfile(checkpoint_path, verified_checkpoint)
        if checkpoint_sha256(verified_checkpoint) != expected_checkpoint_sha256:
            raise ValueError("Private checkpoint snapshot hash is incompatible")
        verified_checkpoint.chmod(0o400)
        rows: list[tuple[Sale, str, float, float]] = []
        window_scores: dict[str, object] = {}
        contexts: dict[str, object] = {}
        fit_seconds: dict[str, float] = {}
        improved_windows = 0
        for name, training, validation in windows:
            fit_started = time.monotonic()
            predictions, repeat_evidence = fit_tabpfn(
                training, validation, verified_checkpoint, expected_checkpoint_sha256
            )
            elapsed = time.monotonic() - fit_started
            if elapsed > FIT_REJECTION_CAP_SECONDS:
                raise TimeoutError(
                    "TabPFN completed fit exceeded post-hoc rejection cap"
                )
            fit_seconds[name] = elapsed
            contexts[name] = repeat_evidence
            scores = {
                "xgboost_log_absolute_error": _score(validation, incumbent[name]),
                "tabpfn_3_5_reduced_context": _score(validation, predictions),
            }
            improved_windows += int(
                scores["tabpfn_3_5_reduced_context"].mdape
                < scores["xgboost_log_absolute_error"].mdape
            )
            window_scores[name] = {
                key: _score_summary(value) for key, value in scores.items()
            }
            rows.extend(
                (row, name, old, new)
                for row, old, new in zip(
                    validation, incumbent[name], predictions, strict=True
                )
            )
        validations = tuple(row for row, _, _, _ in rows)
        pooled = {
            "xgboost_log_absolute_error": _score(
                validations, tuple(old for _, _, old, _ in rows)
            ),
            "tabpfn_3_5_reduced_context": _score(
                validations, tuple(new for _, _, _, new in rows)
            ),
        }
        selected = frozen_beat_rule(
            incumbent_mdape=pooled["xgboost_log_absolute_error"].mdape,
            challenger_mdape=pooled["tabpfn_3_5_reduced_context"].mdape,
            incumbent_within_10=pooled["xgboost_log_absolute_error"].within_10,
            challenger_within_10=pooled["tabpfn_3_5_reduced_context"].within_10,
            incumbent_p90=pooled["xgboost_log_absolute_error"].p90_ape,
            challenger_p90=pooled["tabpfn_3_5_reduced_context"].p90_ape,
            improved_windows=improved_windows,
        )
        with (staging / "predictions.csv").open(
            "w", encoding="utf-8", newline=""
        ) as handle:
            writer = csv.writer(handle)
            writer.writerow(
                (
                    "row_id",
                    "sale_date",
                    "window",
                    "actual_usd",
                    "incumbent_usd",
                    "tabpfn_usd",
                )
            )
            for row, name, old, new in rows:
                writer.writerow(
                    (
                        row.row_id,
                        row.sale_date.isoformat(),
                        name,
                        str(row.price),
                        repr(old),
                        repr(new),
                    )
                )
        if checkpoint_sha256(verified_checkpoint) != expected_checkpoint_sha256:
            raise ValueError("Private checkpoint snapshot changed during execution")
        configured = configuration()
        scorecards = {
            "windows": window_scores,
            "pooled": {key: _score_summary(value) for key, value in pooled.items()},
            "improved_windows": improved_windows,
            "operational_screening_candidate": selected,
            "comparison_class": "reduced_context_tabpfn_vs_full_history_tree",
            "superiority_claim_permitted": False,
        }
        (staging / "scorecards.json").write_text(
            json.dumps(scorecards, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        elapsed_total = time.monotonic() - started
        if elapsed_total > OVERALL_REJECTION_CAP_SECONDS:
            raise TimeoutError("TabPFN completed run exceeded post-hoc rejection cap")
        manifest = {
            "run_id": output.name,
            "protocol": "king_tabpfn_3_5_development_screen_v1",
            "status": "complete",
            "code_commit": commit,
            "research_only": True,
            "promotion_eligible": False,
            "g_us": "PENDING",
            "source_sha256": source_hash,
            "declared_lock_sha256": DECLARED_LOCK_SHA256,
            "runtime_identity": runtime,
            "configuration": configured,
            "configuration_sha256": hashlib.sha256(
                json.dumps(configured, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest(),
            "checkpoint_id": locked_checkpoint.get("id"),
            "checkpoint_revision": locked_checkpoint.get("revision"),
            "checkpoint_sha256": expected_checkpoint_sha256,
            "offline_environment_configured": True,
            "frozen_incumbent_split_sha256": FROZEN_SPLIT_SHA256,
            "feature_policy_sha256": frozen.get("feature_policy_sha256"),
            "frozen_incumbent_manifest_sha256": FROZEN_MANIFEST_SHA256,
            "frozen_incumbent_prediction_sha256": FROZEN_PREDICTION_SHA256,
            "license_decision_sha256": hashlib.sha256(
                _read_small_regular(
                    license_decision, MAX_LICENSE_BYTES, "License decision"
                )
            ).hexdigest(),
            "window_membership_sha256": {
                name: hashlib.sha256(
                    json.dumps(
                        {
                            "training": [row.row_id for row in training],
                            "validation": [row.row_id for row in validation],
                        },
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode()
                ).hexdigest()
                for name, training, validation in windows
            },
            "context_identity": contexts,
            "prediction_repeat_tolerances": {
                "absolute_usd": PREDICTION_ABS_TOLERANCE_USD,
                "relative": PREDICTION_REL_TOLERANCE,
            },
            "fit_seconds": fit_seconds,
            "elapsed_seconds": elapsed_total,
            "time_caps_are_post_hoc_rejection_caps": True,
            "scorecards": scorecards,
            "predictions_sha256": hashlib.sha256(
                (staging / "predictions.csv").read_bytes()
            ).hexdigest(),
        }
        (staging / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        verified_checkpoint.chmod(0o600)
        verified_checkpoint.unlink()
        real_directory(staging, PRIVATE_ROOT)
        verify_acl(staging)
        os.replace(staging, output)
        real_directory(output, PRIVATE_ROOT)
        verify_acl(output)
        return manifest
    finally:
        if verified_checkpoint is not None and verified_checkpoint.exists():
            try:
                verified_checkpoint.chmod(0o600)
            except OSError:
                pass
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    pre = subparsers.add_parser("preflight")
    pre.add_argument("--checkpoint", type=Path, required=True)
    pre.add_argument("--license-decision", type=Path, required=True)
    execute = subparsers.add_parser("run")
    execute.add_argument("--source", type=Path, required=True)
    execute.add_argument("--incumbent-predictions", type=Path, required=True)
    execute.add_argument("--checkpoint", type=Path, required=True)
    execute.add_argument("--license-decision", type=Path, required=True)
    execute.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "preflight":
        result = preflight(args.checkpoint, args.license_decision)
        print(json.dumps(result, sort_keys=True))
        return 0 if result["status"] == "ready" else 3
    run(
        args.source,
        args.incumbent_predictions,
        args.checkpoint,
        args.license_decision,
        args.output,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
