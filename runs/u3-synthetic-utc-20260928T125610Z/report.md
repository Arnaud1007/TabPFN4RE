# Synthetic UTC timestamp-integrity report

Run ID: `u3-synthetic-utc-20260928T125610Z`

Code commit: `7ea3f95e47b483bd5ff6a78ec7dca9cce5ae5993`

Status: **verified synthetic engineering fix; U0 through U3 and G-US remain pending**

Requirements: US06, US08, US10, US11, US22, US23

## Objective and changes

Prevent future information from entering OFF feature assembly, comparable retrieval and baseline fitting during a repeated daylight-saving hour. All ordering, maturity checks, recency calculations and point-in-time context checks now use UTC instants. Snapshot and split hashes canonicalize equivalent timestamps. The synthetic horizon and month window use UTC; the fold builder accepts only `us_synthetic_rolling_v2`. ADR 0010 records the reasoning and real-source dependency.

## Commands and observed results

`run_gate.ps1` records exact commands, exit codes, durations, hashes and environment in `test_gate.json`. The ignored local Ames ARFF was available for unrelated suite tests; it is not a time-stamped certification cohort.

| Check | Observed result | Evidence |
| --- | --- | --- |
| Python 3.11 unittest suite under coverage | 171 passed, 0 skipped, exit 0 | `tests.log` |
| Statement coverage | 90.54% of the current package, exit 0 | `coverage_report.log`, `coverage.json` |
| Ruff lint and format | Both passed, exit 0 | `lint.log`, `format.log` |
| Gate checks | Expected count, no skips, 80% floor and artifact hashes verified | `test_gate.json` |

The new daylight-saving suite has 13 tests. Its original RED run failed the point-in-time canaries; the final GREEN suite verifies property/attribute/prior-sale and comparable visibility, training-label maturity, context reuse, equivalent-instant hashes and boundary behaviour. A separate RED/GREEN test prevents a synthetic fold from being labelled as a real-data protocol. Independent code, Python and security re-reviews found no remaining high or medium finding in this synthetic scope.

## Limitations and next action

This gate is code coverage, not prediction-interval coverage or model accuracy. The manifest's split and checkpoint identities are null because this is a test-suite gate with several synthetic folds and no fitted release model. It records `dirty_tree: true` because gate artifacts and ADR 0010 were untracked during execution; tested code was committed at the stated hash.

UTC 90-day engineering horizons do not implement the specification's source-local 90-calendar-day origin. Before real U3 evaluation, an audited source must establish close-date semantics, local timezone/date rules, first availability, historical vintages and eligible labels. No real multi-market cohort was trained or tested. Follow `next_action.md` for U0 recovery and source qualification.
