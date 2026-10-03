# Cook / Additional PIN offline v2 failure

- Date: 2026-10-03 UTC
- Protocol: `illinois-additional-pin-offline-v2`
- Status: **FAILED**; no public aggregate or complete private diagnostic was created.
- Command: `.\.venv\Scripts\python.exe -B -m scripts.audit_illinois_additional_pins run --source-run-dir data/raw/illinois_ptax203/ptax-additional-v2-130b5169ff81ccbc --output runs/u0-illinois-additional-pin-offline-v2-20261003T051910Z/aggregate.json`
- Exit code: 1; the CLI reported `Offline Additional PIN triage failed; inspect private state`.

The pinned Cook, PTAX, Additional PIN and prior-worklist inputs passed read-only preflight. Worklist construction then rejected the frozen 500-reference resource cap. A read-only bounded diagnostic established only that candidate pairs did **not** exceed 500, observation references **did** exceed 500 and did **not** exceed 5,000, and the worklist did **not** exceed 1 MiB. Exact counts and all row-level relations remain private. No output was written, no label was certified, and no gate changed status.

Keep the frozen [v2 plan](plan.md) and this failure as evidence. [ADR 0063](../../decisions/0063-illinois-additional-pin-reference-cap-v3.md) records the separately versioned resource-cap correction. A v3 run must use a new private directory and public run ID; it cannot convert this failed run into a valid result.
