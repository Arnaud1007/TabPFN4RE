# NYC rolling archive versus current snapshot: representation comparison

Run ID: `archive-current-v1-20261002T214801Z-d4b589edff65`
Protocol: [ADR 0044](../../decisions/0044-nyc-archive-current-concordance-v1.md)
Code commit: `635e621b256e3a2a07c3e34072bf6b3be8714294`
Status: **verified source representation only; U0 and G-US pending**
Requirements: US05, US06, US08, US22, US23, US24

## Question and inputs

The reviewed comparator, tested and pushed before the private read, compared
the pinned April 2026 version-62 NYC rolling archive with the pinned September
2026 current rolling CSV. The archive contains 81,567 source rows; the current
snapshot contains 82,345. These are published rows, not certified distinct
economic transfers. The [public manifest](manifest.json) records the exact
whole-file hashes, code commit, configuration and environment. No source row,
address, unit, price, date, ordinal or row fingerprint is in this directory.

## Observed result

| Comparison | Public result |
| --- | --- |
| Complete 21-field trimmed-string multiset overlap | `zero` |
| Complete 21-field overlap after strict calendar normalization of `SALE DATE` only | `1000_plus` |
| NYC sale labels certified | 0 |
| Historical as-of eligible | false |

The second tier changes only the calendar-date representation. Its broad
overlap bucket therefore establishes that at least some source rows agree
on the other 20 trimmed fields and calendar date despite different date
strings. It does **not** identify a transfer, distinguish additions from
corrections, prove first publication, or establish a close date. Private
aggregate counters, including invalid-date and residual denominators, are
retained under the protected local run and are not published because exact
differences could expose small cells. The fixed public projection is
[`aggregate.json`](aggregate.json).

## Verification

The command
`.venv\Scripts\python.exe scripts/compare_nyc_archive_snapshot_v1.py compare data/raw/nyc_dof/archive-current-v1-20261002T214801Z-d4b589edff65`
exited 0 after checking the pushed code ref, private ACLs, source manifests,
whole-file hashes, schemas, counts and resource caps. An offline replay of
the same private run exited 0 with the same public projection. The
[`verify_artifacts.ps1`](verify_artifacts.ps1) command checks the saved
protected hashes and reruns that replay; its [gate](test_gate.json) and
[log](verifier.log) record exit 0. The earlier
[code gate](../u0-nyc-archive-current-v1-code-20261002T213428Z/report.md)
records 919 passing repository tests with no skips, 17 focused synthetic
tests, 83% branch-aware comparator coverage, lint/dependency checks and
the preserved failed PowerShell wrapper attempt.

## Decision and next work

Keep the two CSV vintages in private source inventory. The archive is a
candidate historical known-by bound only after its reconstruction and
publication semantics are confirmed. Qualify the DOF sale-date meaning,
dataset-specific use rights, economic-transfer/unit identity and historical
attribute vintages before admitting NYC labels or as-of features. A
separately frozen v2 representation diagnostic may explain residuals if it
helps those source-qualification decisions. The September borough workbooks
are a current-period control and cannot establish April row availability.

NYC certified sale labels remain **0**. U0 and G-US remain **PENDING**.
No model training or international implementation is unlocked.
