# Synthetic split-conformal engineering check

- Run ID: `u5-synthetic-conformal-20260928T184900Z`
- Executed: 2026-09-28 18:58 UTC
- Base commit: `4d7527a3121ae7346cee326f36991a5c593857ff`; working tree was dirty and the exact checked files are hashed in `manifest.json`.
- Protocol: `us_synthetic_off_90d_split_conformal_v2`
- Certification eligible: **no**

## Objective and changes

Implement US19/T09 arithmetic and timing guards using synthetic, disjoint US OFF rows. `evaluation/conformal.py` has a pure one-based finite-sample rank check, 1,000-row minimum for fitted overall calibration, exact 80%/90% multiplicative residual thresholds, immutable dated evidence, a self-consistency hash, and outward-rounded interval bounds. Separate scoring requires exact reserved test IDs and matured labels. It checks bounds against saved point predictions, reports empirical interval coverage only among successful estimates, and counts failures/abstentions in service coverage.

ADR 0016 records why this module is separate from point metrics and why its synthetic results cannot establish housing-market coverage. No transaction source, checkpoint, pre-outcome prediction ledger or real calibration/test split was used.

## Commands and observed results

The exact executed gate script is archived as `run_gate_executed.ps1.txt`; its SHA-256 is in `manifest.json`. The command list, exit codes, durations, output paths and SHA-256 hashes are in `test_gate.json`. The manifest and this report were amended after execution to document a safe replay tool; the original gate, logs and coverage file were preserved. For a new replay, run `& 'runs/u5-synthetic-conformal-20260928T184900Z/run_gate.ps1' -OutputDirectory 'runs/a-new-unique-run-id'` from the project root. This safe runner refuses an existing output directory, requires a direct child of a non-junction `runs` directory, quotes paths with spaces and checks source-tree dirtiness before creating outputs. The final revision passed in `runs/synthetic conformal replay 20260928T191000Z/` without changing this recorded gate or coverage file. Earlier replay revisions remain preserved in the 19:01 and 19:06 run directories.

| Check | Observed result |
| --- | --- |
| Full `unittest` suite under coverage | 277 tests, 0 skipped, exit 0 |
| Package statement coverage | 90.93% (1,334/1,467 lines), above the 80% project threshold |
| Ruff lint and format | Both exit 0 |
| `pip check` | Exit 0 |
| Pinned dependency audit | Exit 0; no known vulnerabilities reported for the audited lock |
| Artifact verifier | `verify_artifacts.ps1` checks the gate, all listed file hashes and every log hash |

All inputs to the new interval tests are synthetic. Their sample 50% coverage case is a hand-calculated fixture, **not** a measured real-estate calibration result. The exact-rank test includes an insufficient-small-sample case. Regression tests cover altered calibration radii/factors, future or immature labels, predictor mismatch, changed point predictions, exact endpoint ties, distinct 64-digit prices, and explicit failure when an endpoint exceeds the supported numeric representation.

## Failed attempts and review

The initial gate script stopped when Windows PowerShell treated `unittest` stderr as a terminating error. A second attempt ran all checks but Windows PowerShell could not parse coverage's JSON object with empty-string function keys. Both harness errors were fixed; neither attempt was recorded as a valid passed gate. Independent code, Python and security reviews found two high-severity implementation defects in the first version: a changed radius could retain the same calibration ID, and rounded log/exp arithmetic could exclude an exact calibration tie. Both defects were reproduced, corrected and regression-tested before the final gate. The final reviewers reported no remaining critical or high findings for this synthetic scope.

## Gate and remaining work

**Synthetic engineering check: PASS. U5 milestone: pending. US19 release requirement: planned. G-US: pending.** The self-consistency SHA detects accidental or locally inconsistent mutation; it is not authentication of an external artifact. Real acceptance still requires a trusted hashed release bundle, independently frozen eligible calibration/test populations, pre-outcome prediction timestamps and opening ledger, 1,000 real calibration labels, a later 12-month US test, 80%/90% empirical coverage and width with uncertainty and subgroup analysis, and a prospective shadow cohort. Source rights and as-of provenance remain U0 dependencies. No model was trained on HCPA or any modern US transaction source.

Next dependency-ready task: continue U0 source qualification and the 200-record HCPA manual audit described in `next_action.md`. The exact local resume command is `& 'runs/u5-synthetic-conformal-20260928T184900Z/verify_artifacts.ps1'` for this engineering evidence, then use the U0 commands in `next_action.md`.
