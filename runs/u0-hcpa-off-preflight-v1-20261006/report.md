# HCPA OFF runner preflight

Date: 2026-10-06  
Run ID: `u0-hcpa-off-preflight-v1-20261006`  
Status: **VERIFIED BLOCKED**

## Result

The new HCPA OFF entry point stops at the fixed source-admission gate. Both
production forms emitted the same JSON, returned exit 3 and reported
`source_admitted=false`, `model_fit_permitted=false`,
`model_fit_executed=false` and `outputs_written=false`. The four blockers are
the source admission itself followed by the three frozen fit-readiness
blockers.

An invalid argument returned exit 2, empty stdout and only
`HCPA OFF baseline preflight failed` on stderr. The argument was not echoed.

## Verification

| Check | Observed result | Evidence |
|---|---|---|
| Focused branch-aware suite | 13 passed; runner coverage 90% | `focused_tests.log`, `coverage.log` |
| Admission plus runner regression | 71 passed; 2 Windows symlink-creation skips | `combined_tests.log` |
| Ruff lint and format | Both passed | `ruff_check.log`, `ruff_format.log` |
| Module and direct CLI | Identical blocked JSON; exit 3 for both | `cli_module.json`, `cli_direct.json`, `cli_checks.json` |
| Invalid argument | Exit 2; generic stderr; empty stdout; no echo | `cli_invalid.stderr`, `cli_invalid.stdout`, `cli_checks.json` |

The boundary test inspects the production module and rejects numerical/model,
DBF, ZIP, private-ledger, raw-file and output-writer dependencies. The runner
itself calls only the fixed admission validator and JSON/stdout machinery.
Accordingly this preflight accessed no raw row, archive, private ledger, label
or model and created no run reservation or prediction artifact. The evidence
directory was written by the verification commands, outside the runner.

## Reproducibility boundary

Verification ran from base commit
`0f7fa1d6f8df350bc4358985a8437429547fb608` with a dirty tree because the
runner, tests and ADR were the changes under review. `manifest.json` binds
their exact bytes and the fixed admission inputs. Python was 3.11.6, pytest
9.0.2, coverage 7.16.2 and Ruff 0.13.0 on Windows.

## Decision

Accept the runner as a fast, fail-closed preflight. Do not describe this as an
HCPA model result: no label was opened, no model ran and no accuracy metric was
created. HCPA training remains blocked until authoritative source evidence and
a later reviewed execution protocol clear the admission and fit-readiness
gates.

Exact recheck: `& '.venv/Scripts/python.exe' -m scripts.run_hcpa_off_baseline`
