# ADR 0045: resolve legacy lock markers before further replay

Date: 2026-10-03
Owner: project implementation
Status: frozen marker audit; no new model fit authorised by this decision
Requirements: US02, US22, US24
Protocol: `ames_legacy_lock_markers_v1`

## Question

Does the recovered `uv.lock` select different numerical and model packages
from the guarded Day 8 development replay on Windows Python 3.11? The archived
XGBoost scores did not reproduce under that replay. A version mismatch is a
testable explanation only after the lock's environment markers are evaluated.

## Inputs and method

- Use the unchanged recovered `data/raw/legacy-repo/uv.lock`, whose SHA-256 is
  recorded in `migration_report.md`, and the saved v9
  `environment_packages.json` from the guarded development replay.
- Parse the TOML package entries and evaluate each `resolution-markers` clause
  for `python_full_version = 3.11.6` and `sys_platform = win32`. A package
  entry is selected when any of its clauses matches. For every compared name,
  exactly one version must be selected; duplicates or gaps fail the audit.
- Compare NumPy, pandas, SciPy, scikit-learn, XGBoost, joblib, threadpoolctl,
  python-dateutil and tzdata. Save the input hashes, selected versions,
  installed versions, exact comparison and command in a public aggregate-only
  run report. No source rows, predictions or holdout labels are accessed.

## Interpretation and stop rule

If the selected versions match, do not rerun the model solely because higher
package versions also appear elsewhere in the multi-environment lock. If they
differ, plan a separate single-factor replay before opening development data.
Either result leaves the historical installed runtime unverified: a recovered
lock is not a record of what was installed when archived metrics were made.
Preserve the prior non-reproduction finding and the retrospective holdout
status. U0 and G-US decisions require their own evidence review.

An initial uncommitted proposal to install the lock's highest visible package
versions was rejected in code review because it ignored the Python and
platform resolution markers. No such environment was installed and no replay
was launched under that proposal.
