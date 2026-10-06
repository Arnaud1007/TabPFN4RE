"""Stop the frozen HCPA OFF baseline before source access while admission is pending."""

from __future__ import annotations

import json
import sys
from types import MappingProxyType
from typing import Mapping

if __package__:
    from scripts import hcpa_source_admission
else:  # Support the documented direct-script command from the project root.
    import hcpa_source_admission


PROTOCOL = "hcpa_off_baseline_preflight_v1"
EXPECTED_GATE_KEYS = frozenset(
    {
        "source_id",
        "status",
        "source_admitted",
        "comparable_display_permitted",
        "model_fit_permitted",
        "fit_readiness_status",
        "fit_readiness_blockers",
    }
)
EXPECTED_SOURCE_ID = "hillsborough_hcpa_allsales"
EXPECTED_GATE_BLOCKERS = (
    "semantic_feature_flags_pending",
    "historical_property_attributes_pending",
    "eligibility_rules_pending",
)


def _current_gate() -> Mapping[str, object]:
    """Validate only the fixed production admission and policy artifacts."""
    return hcpa_source_admission.validate_files(
        hcpa_source_admission.ADMISSION_PATH,
        hcpa_source_admission.POLICY_PATH,
        hcpa_source_admission.ROOT,
    )


def run_preflight() -> Mapping[str, object]:
    """Return the immutable blocked state after the source gate passes integrity."""
    result = _current_gate()
    if (
        not isinstance(result, Mapping)
        or set(result) != EXPECTED_GATE_KEYS
        or result["source_id"] != EXPECTED_SOURCE_ID
        or result["status"] != "pending"
        or result["source_admitted"] is not False
        or result["comparable_display_permitted"] is not False
        or result["model_fit_permitted"] is not False
        or result["fit_readiness_status"] != "blocked"
        or type(result["fit_readiness_blockers"]) is not tuple
        or result["fit_readiness_blockers"] != EXPECTED_GATE_BLOCKERS
    ):
        raise ValueError("HCPA preflight gate result differs")
    return MappingProxyType(
        {
            "protocol": PROTOCOL,
            "status": "blocked",
            "source_id": EXPECTED_SOURCE_ID,
            "source_status": "pending",
            "source_admitted": False,
            "model_fit_permitted": False,
            "fit_readiness_status": "blocked",
            "fit_readiness_blockers": (
                "source_not_admitted",
                *EXPECTED_GATE_BLOCKERS,
            ),
            "model_fit_executed": False,
            "outputs_written": False,
        }
    )


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if arguments:
        print("HCPA OFF baseline preflight failed", file=sys.stderr)
        return 2
    try:
        result = run_preflight()
    except Exception:
        print("HCPA OFF baseline preflight failed", file=sys.stderr)
        return 2
    print(json.dumps(dict(result), sort_keys=True, separators=(",", ":")))
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
