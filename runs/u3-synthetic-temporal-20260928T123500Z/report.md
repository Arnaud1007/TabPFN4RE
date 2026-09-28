# U3 synthetic temporal-fold engineering report

Run ID: `u3-synthetic-temporal-20260928T123500Z`

Code commit: `ec7ce3537b1a00eaad01ee1a57449604bd90809f`

Status: **verified synthetic engineering increment; U3 and G-US remain pending**

Requirements: US11, US22, US23

## Objective and changes

Build a rolling-origin membership guard before any real temporal training. The fold uses outcome-free validation origins and training-side close/availability metadata; reserved validation labels are rejected. It hashes boundaries and membership, normalizes timestamp comparisons to UTC, and rejects a fold with no matured training label. The synthetic fold drives the guarded OFF median baseline in one integration test. No new real-estate source rows were ingested or trained.

## Commands and observed results

`run_gate.ps1` records the exact commands, exit codes, durations, output hashes, code commit, environment lock and configuration hash in `test_gate.json`. The local ignored Ames ARFF was available to unrelated suite tests; its checksum is recorded but it supplies no temporal certification cohort.

| Check | Observed result | Evidence |
| --- | --- | --- |
| Python 3.11 unittest suite under coverage | 157 passed, 0 skipped, exit 0 | `tests.log` |
| Statement coverage | 90.40% of current package, exit 0 | `coverage_report.log`, `coverage.json` |
| Ruff lint and format | Both passed, exit 0 | `lint.log`, `format.log` |
| Gate checks | Expected test count, no skips and 80% coverage floor passed | `test_gate.json` |

The `split_hash` and checkpoint fields are null because this is a test-suite gate, not a fitted-model run with one frozen cohort or checkpoint. The test asserts deterministic split hashes for its synthetic folds. The manifest records `dirty_tree: true` because its gate artifacts were untracked during execution; the tested code was committed at the stated hash. A prior launcher attempt at `u3-synthetic-temporal-20260928T123348Z/` failed in PowerShell JSON parsing after tests ran; it is retained as incomplete evidence.

## Limitations and next action

The exact-timestamp synthetic horizon does not define 90 source-local calendar days for date-only records or ambiguous fallback hours. There is no real multi-market source with audited per-row availability, no four rolling windows, calibration or locked test split, and no geographic or unseen-property scorecard. This gate is code coverage, not prediction-interval coverage or model accuracy.

Follow `next_action.md`: recover legacy artifacts if provided and qualify a transaction source with close/availability dates and historical attribute vintages. Define a real-source origin policy before U3 acceptance.
