"""Replay the pinned Cook source observations and write a private quality funnel."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys

from scripts import assemble_cook_parcel_observations as stage
from scripts import private_review_io as private_io
from scripts import review_cook_sales_sample as review
from tabpfn4realestate.data.cook_parcel_sales import CookParcelSaleObservation
from tabpfn4realestate.data.cook_quality import profile_quality


PROTOCOL = "cook_source_quality_v1"
CAPTURE_SHA256 = stage.CAPTURE_SHA256
SOURCE_METADATA_SHA256 = stage.SOURCE_METADATA_SHA256
STAGED_SHA256 = "7b315b4b001d3b14ffc64ab0277f486738e53b83b120da592a952f94a175c167"
SAMPLE_ROWS = stage.SAMPLE_ROWS
RAW_ROOT = stage.RAW_ROOT
RUN_NAME = f"parcel-quality-v1-{CAPTURE_SHA256[:16]}"
MAX_FINDINGS_BYTES = 256 * 1024
MAX_COUNTS_BYTES = 16 * 1024
MAX_COMPLETE_BYTES = 4096
PUBLIC_FIELDS = frozenset(
    {
        "protocol",
        "capture_manifest_sha256",
        "source_metadata_sha256",
        "staged_observations_sha256",
        "private_findings_sha256",
        "sample_rows",
        "certified_sale_labels",
        "historical_asof_eligible",
        "u0_gate",
        "g_us_gate",
    }
)


def _encoded(value: object) -> bytes:
    return (
        json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n"
    ).encode("utf-8")


def _hash(content: bytes) -> str:
    return sha256(content).hexdigest()


def _private_root() -> Path:
    private_io.real_directory(RAW_ROOT, RAW_ROOT.parent)
    private_io.verify_acl(RAW_ROOT)
    return RAW_ROOT


def _staged_directory() -> Path:
    return RAW_ROOT / stage.RUN_NAME


def _source_observations() -> tuple[CookParcelSaleObservation, ...]:
    """Require an exact replay of the original capture and staged bytes."""
    directory = _staged_directory()
    result = stage.verify(directory)
    if (
        result.get("private_observations_sha256") != STAGED_SHA256
        or result.get("sample_rows") != SAMPLE_ROWS
        or result.get("capture_manifest_sha256") != CAPTURE_SHA256
    ):
        raise ValueError("Cook staged observation identity differs")
    path = private_io.private_path(
        directory / "observations.jsonl", directory, must_exist=True
    )
    content = review._bounded(path, stage.MAX_OBSERVATIONS_BYTES)
    if _hash(content) != STAGED_SHA256:
        raise ValueError("Cook staged observation hash differs")
    lines = content.splitlines()
    if len(lines) != SAMPLE_ROWS or not content.endswith(b"\n"):
        raise ValueError("Cook staged observation count differs")
    observations = []
    for ordinal, line in enumerate(lines, start=1):
        try:
            entry = json.loads(line)
        except (UnicodeError, json.JSONDecodeError) as error:
            raise ValueError("Cook staged observation JSON differs") from error
        if (
            type(entry) is not dict
            or set(entry) != {"ordinal", "observation"}
            or type(entry["ordinal"]) is not int
            or entry["ordinal"] != ordinal
        ):
            raise ValueError("Cook staged observation order differs")
        observations.append(CookParcelSaleObservation.from_record(entry["observation"]))
    return tuple(observations)


def build_outputs(
    observations: tuple[CookParcelSaleObservation, ...],
    *,
    expected_rows: int,
    expected_capture_sha256: str,
) -> tuple[bytes, bytes]:
    """Build deterministic, restricted findings and complete private counts."""
    profile = profile_quality(
        observations,
        expected_capture_sha256=expected_capture_sha256,
        expected_rows=expected_rows,
    )
    findings = b"".join(_encoded(row.to_record()) for row in profile.findings)
    counts = _encoded(profile.private_counts_record())
    if len(findings) > MAX_FINDINGS_BYTES or len(counts) > MAX_COUNTS_BYTES:
        raise ValueError("Cook quality output exceeds private byte cap")
    return findings, counts


def public_summary(findings: bytes) -> dict[str, object]:
    """Expose only fixed, aggregate-safe fields after private replay."""
    result: dict[str, object] = {
        "protocol": PROTOCOL,
        "capture_manifest_sha256": CAPTURE_SHA256,
        "source_metadata_sha256": SOURCE_METADATA_SHA256,
        "staged_observations_sha256": STAGED_SHA256,
        "private_findings_sha256": _hash(findings),
        "sample_rows": SAMPLE_ROWS,
        "certified_sale_labels": 0,
        "historical_asof_eligible": False,
        "u0_gate": "PENDING",
        "g_us_gate": "PENDING",
    }
    if set(result) != PUBLIC_FIELDS:
        raise ValueError("Cook quality public allowlist differs")
    return result


def _complete(findings: bytes, counts: bytes) -> dict[str, object]:
    return {
        "protocol": PROTOCOL,
        "capture_manifest_sha256": CAPTURE_SHA256,
        "staged_observations_sha256": STAGED_SHA256,
        "findings_sha256": _hash(findings),
        "counts_sha256": _hash(counts),
        "sample_rows": SAMPLE_ROWS,
        "certified_sale_labels": 0,
    }


def _new_run() -> Path:
    root = _private_root()
    directory = root / RUN_NAME
    directory.mkdir(mode=0o700, exist_ok=False)
    private_io.secure_directory(directory)
    private_io.real_directory(directory, root)
    private_io.verify_acl(directory)
    return directory


def _public_destination(output: Path) -> Path:
    output = Path(output)
    if output.parent.resolve().is_relative_to(RAW_ROOT.resolve()):
        raise ValueError("Public output must be outside private raw data")
    return private_io.summary_target(
        output,
        (_staged_directory() / "observations.jsonl",),
    )


def run(output: Path) -> dict[str, object]:
    """Write a create-only private run, replay it, then publish a safe summary."""
    _public_destination(output)
    observations = _source_observations()
    findings, counts = build_outputs(
        observations,
        expected_rows=SAMPLE_ROWS,
        expected_capture_sha256=CAPTURE_SHA256,
    )
    directory = _new_run()
    for filename, content in (
        ("findings.jsonl", findings),
        ("counts.json", counts),
        ("complete.json", _encoded(_complete(findings, counts))),
    ):
        private_io.new_file(
            private_io.private_path(directory / filename, directory), content
        )
    summary = verify(directory)
    private_io.write_summary_new(
        output, summary, (_staged_directory() / "observations.jsonl",)
    )
    return summary


def verify(directory: Path) -> dict[str, object]:
    """Rebuild from the pinned source and compare every private output byte."""
    root = _private_root()
    directory = Path(directory)
    private_io.real_directory(directory, root)
    private_io.verify_acl(directory)
    if not private_io.same_path(directory, root / RUN_NAME):
        raise ValueError("Cook quality directory identity differs")
    expected_names = {"findings.jsonl", "counts.json", "complete.json"}
    if {path.name for path in directory.iterdir()} != expected_names:
        raise ValueError("Cook quality file set differs")
    expected_findings, expected_counts = build_outputs(
        _source_observations(),
        expected_rows=SAMPLE_ROWS,
        expected_capture_sha256=CAPTURE_SHA256,
    )
    for filename, expected, cap in (
        ("findings.jsonl", expected_findings, MAX_FINDINGS_BYTES),
        ("counts.json", expected_counts, MAX_COUNTS_BYTES),
        (
            "complete.json",
            _encoded(_complete(expected_findings, expected_counts)),
            MAX_COMPLETE_BYTES,
        ),
    ):
        path = private_io.private_path(directory / filename, directory, must_exist=True)
        if review._bounded(path, cap) != expected:
            raise ValueError("Cook quality private output differs")
    return public_summary(expected_findings)


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("run", "verify"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--run-dir", type=Path)
    options = parser.parse_args(arguments)
    try:
        if options.action == "run":
            if options.run_dir is not None or options.output is None:
                parser.error("run needs --output and takes no --run-dir")
            result = run(options.output)
        else:
            if options.run_dir is None or options.output is not None:
                parser.error("verify needs --run-dir and takes no --output")
            result = verify(options.run_dir)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (OSError, ValueError, UnicodeError):
        print("Cook source quality failed; inspect private state", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
