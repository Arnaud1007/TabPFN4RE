# HCPA OFF runner preflight plan

Date: 2026-10-06  
Run ID: `u0-hcpa-off-preflight-v1-20261006`  
Base commit: `0f7fa1d6f8df350bc4358985a8437429547fb608`  
Worktree during verification: dirty by design; runner, tests and ADR were not yet committed.

## Hypothesis

The HCPA OFF baseline entry point can return the current blocked source state
quickly and deterministically without reading a raw row, archive, private
ledger, label or model and without writing an output or fitting a model.

## Fixed checks

1. Run the 13 preflight tests with branch coverage of the runner.
2. Run the admission and runner suites together.
3. Run Ruff lint and format checks on the runner and its tests.
4. Invoke the direct and module CLIs and require byte-identical blocked JSON
   with exit 3.
5. Supply an invalid argument and require generic stderr, empty stdout, exit 2
   and no argument echo.
6. Inspect the runner boundary and test that it contains no raw, archive,
   ledger, label, numerical-model or output-writing implementation.

This run is preflight evidence only. It must not open HCPA source material,
reserve a model run, parse a price, train a model or write prediction output.
