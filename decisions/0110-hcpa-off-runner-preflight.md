# ADR 0110: Stop the HCPA OFF runner at source preflight

## Status

Accepted as a blocked, executable runner preflight. No source row is read and
no model fit is run.

## Context

ADR 0109 established a fixed HCPA admission and model-policy validator. Its
current result is pending and explicitly denies source admission and model
fitting. A future baseline runner must invoke that gate before it can replay a
ledger, inspect an archive or DBF, parse a price or label, import a numerical
or model library, reserve a run, or write an artifact.

Preparing the boundary now makes the blocked state fast and machine-readable
without weakening the source-wide evidence requirements. It does not create a
model execution path while that design remains unreviewed.

## Decision

Add `scripts/run_hcpa_off_baseline.py` as a preflight-only production CLI. It
accepts no paths or other arguments. Its first operation calls the fixed
ADR 0109 validator using the committed admission and policy locations. The
public `run_preflight` function has no injection point and unconditionally
calls that fixed gate. Tests replace the private `_current_gate` binding to
prove ordering and failure behavior without creating a production bypass.

The preflight accepts only the exact current pending result: the HCPA source
is not admitted, model fit is not permitted, fit readiness is blocked, and the
three frozen readiness blockers are present in order. Drift, a premature
admitted/permitted response, malformed output, or gate-integrity failure is
rejected. This exact-result check consumes the validator result and therefore
inherits its binding to the current admission bytes and policy hash.

For the valid pending result, the CLI emits deterministic JSON containing four
blockers, with `source_not_admitted` first, and explicit false values for
`model_fit_executed` and `outputs_written`. It exits 3 so automation can
distinguish an expected evidence block from success. Gate or integrity errors
emit only `HCPA OFF baseline preflight failed` to stderr and exit 2. Any
supplied argument is rejected without parsing or echoing its value and also
exits 2 with the same generic error.

The module has no NumPy, XGBoost, DBF, archive, ledger, raw-row, price, label,
fit, or output-writing implementation. Adding any downstream execution path
requires a later reviewed decision and RED tests that prove the admission gate
executes before every side effect.

## Consequences

The runner now gives an immediate bounded result instead of starting a long
model workflow. HCPA remains blocked pending authoritative source semantics,
availability, transaction handling, and rights evidence. The preflight does
not claim model readiness, accuracy, certification, or G-US progress.
