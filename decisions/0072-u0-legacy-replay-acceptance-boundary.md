# ADR 0072: keep U0 pending after the legacy replay audit

Date: 2026-10-03

Owner: project implementation

Status: accepted decision; U0 remains PENDING

Requirements: US02, US24

Protocol: `u0_gate_review_v1`

## Decision

Do not declare the archived Day 8 XGBoost result reproduced or accept U0 by
exception. The original `ames.csv`, row-level historical predictions, fitted
checkpoint and actual historical runtime are unavailable. The recovered
`uv.lock` selects the same nine checked numerical/model package versions as
the guarded replay environment, but it cannot establish what was installed
for the archived run. The saved mean XGBoost MAE is $15,624.4750 and the
guarded development replay is $15,499.7416; the maximum absolute fold MAE
difference is $653.3657. Six corrected-parser replay runs had identical local
predictions, so this difference exceeds observed local repeat variability.

The missing `feature_catalog.csv` and earlier Word specification remain
documented dependencies. The catalogue's absence does not stop independent
foundation work, and the old holdout remains retrospective because its prior
exposure is unknown.

## Alternatives considered

1. **Accept U0 as inventory only.** The inventory is well evidenced, but this
   would silently weaken US02's historical reproduction requirement. Rejected.
2. **Accept U0 with an explicit exception.** This could separate migration
   from current engineering, but it changes a mandatory criterion without
   project-owner approval. Deferred; no exception is adopted here.
3. **Keep U0 pending and continue independent work.** Preserve the failed
   result and pursue source qualification and engineering controls that do not
   depend on the archived XGBoost score. Chosen.

## Boundary and reopening rule

The incomplete Cook and NYC 200-record audits, modern transaction rights,
historical publication timing and close-date semantics are U2/G-US
dependencies. They are not newly invented U0 conditions. No real-market model
training or certification is authorised by this decision.

Reopen the reproduction criterion only with the original dataset or equivalent
row-level historical artifacts and a registered replay plan. A revised U0
acceptance criterion requires a versioned decision approved by the project
owner; it cannot retroactively make the failed replay a match. See the
[consolidated gate review](../runs/u0-gate-review-20261003T134443Z/report.md).
