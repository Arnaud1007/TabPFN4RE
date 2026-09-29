# U0 NYC ACRIS document-triage pilot v2: incomplete

Run ID: `u0-nyc-acris-v2-20260929T012700Z`  
Status: **INCOMPLETE_ERROR**; U0 and G-US **PENDING**  
Code commit at execution: `18ff5bc5feaa00080ef594cade1ba114a9df9f6e`  
Requirements: US04, US05, US06, US07, US08, US22, US23, US24

## Objective and frozen scope

[ADR 0023](../../decisions/0023-nyc-acris-document-triage-v2.md) retained the
same four selected rolling-sales rows as the failed v1 pilot. The snapshot,
sample ledger and official current document-code table matched their pinned
hashes before the live request. The v2 collector and 27 synthetic tests were
committed and pushed before this run. Private source rows, identifiers, query
URLs, response bodies and manual notes remain under Git-ignored
`data/raw/nyc_dof/` with a restricted run-directory ACL.

## Observed attempt

The live command exited 1 after nine bounded API requests in 10.894 seconds.
All four registered BBL queries finished. The private evidence contains valid
row-cap saturation and a Master response with duplicate document IDs; the
latter failed the registered one-record-per-requested-ID validation. Every
bounded response body was saved and hashed before validation. The collector
returned `INCOMPLETE_ERROR` and `document_triage_finished=false`. It made no
replacement selection and did not widen the protocol caps.

An offline replay exited 1 with the same aggregate status and request count.
The private state SHA-256 was identical before and after replay, and all nine
saved response files matched the hashes recorded in private state. The
private diagnosis is retained for a separately versioned source-rule review;
this tracked report contains no per-property outcomes or document IDs.

**No selected transfer was certified or manually reviewed. No sale price,
closing date, first availability time or commercial reuse right was
established.** The 200-record manual source audit still has zero completed
rubrics. This pilot cannot admit NYC labels to model training or the 90-day
as-of benchmark.

## Checks and next action

[test_gate.json](test_gate.json) records actual command exits and durations.
The 27 focused synthetic tests passed with 87% branch-enabled collector
coverage. The full repository suite ran 446 tests: 445 passed and one optional
OpenML test was skipped; no mandatory test was skipped. Ruff lint/format,
`pip check` and the scoped pinned-dependency audit passed. Negative code-table
fixtures account for the
expected error text in the full-suite log; that command exited 0. The
[manifest](manifest.json) pins code, environment, configuration, inputs and
private response evidence. Run
`& 'runs/u0-nyc-acris-v2-20260929T012700Z/verify_artifacts.ps1'` from the
project root to verify it.

Preserve this run as incomplete. Before another sampled ACRIS lookup, diagnose
duplicate Master record semantics and cap saturation under a new frozen
protocol. Continue the independent 200-record manual source review and resolve
source rights, sale-date meaning and first historical availability. No NYC
model training or certification is unlocked.
