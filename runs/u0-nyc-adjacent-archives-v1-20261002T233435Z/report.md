# NYC adjacent rolling archives: source-representation comparison

Status: **verified source inventory only; U0, U3 and G-US PENDING**. Requirements: US05, US06, US08, US22, US23 and US24. [ADR 0048](../../decisions/0048-nyc-adjacent-archive-concordance-v1.md) froze the protocol and the [plan](plan.md) before either private archive was opened. Reviewed code commit `9dfa171cbb0e85527b549eea01638365edb33921` was pushed to `origin/audit/u0` and verified against a clean working tree before the run. The private run ID is `archive-adjacent-v1-20261002T233435Z-6db0ca9ec142`.

## Observed result

| Evidence | Value |
| --- | --- |
| Version-61 strict source rows | 79,335 |
| Version-62 strict source rows | 81,567 |
| Raw 21-field tuple multiset overlap | `1000_plus` |
| Overlap after normalizing only sale-date representation | `1000_plus` |
| Certified sale labels | 0 |
| Historical as-of eligibility | false |

The fixed [public projection](public.json) contains source denominators and broad overlap buckets only. The [intent](intent.json) records code, environment, configuration and source hashes. The raw archive rows and exact aggregate counts remain in protected Git-ignored storage. Neither the source-row count difference nor the overlap bucket identifies a new, deleted or corrected *economic transfer*. Matching representations do not establish first row publication, the meaning of DOF `SALE DATE`, a single-dwelling transaction, source-specific reuse rights or historical attribute availability. No NYC label is admitted for model fitting, calibration or a temporal certification cohort.

## Execution and checks

From the project root, the frozen offline comparison command was `.\.venv\Scripts\python.exe scripts/compare_nyc_adjacent_archives_v1.py compare data/raw/nyc_dof/archive-adjacent-v1-20261002T233435Z-6db0ca9ec142` (exit 0, 4.718 seconds wall time). The same command with `replay` in place of `compare` exited 0 in 4.081 seconds and reproduced the protected aggregates. The public `& 'runs/u0-nyc-adjacent-archives-v1-20261002T233435Z/verify_artifacts.ps1'` exited 0 in 4.229 seconds after checking the private artifact hashes and replay. Its output was: `NYC adjacent archives: private hashes and offline replay verified; zero labels certified; U0, U3 and G-US pending`.

The [test gate](test_gate.json) records 22 focused tests, 86% branch-aware runner coverage, 960 full-suite tests with zero skips, Ruff, dependency checks and the initial failing synthetic replay-runtime test before the fix. The full-suite duration was 167.150 seconds. The failed RED test was a development check, not an accepted archive run; no private comparison was started until code and plan were committed and pushed.

## Remaining dependencies and next action

Seek dated publisher evidence for first availability of source rows and property attributes, clarify the DOF sale-date/close/contract relationship, verify transfer and dwelling identity against authoritative instruments, and document dataset-specific commercial/reuse rights. Complete the outstanding manual source-review rubrics independently. If any of these cannot be established, keep NYC as inventory-only and pursue another authorised US source. Do not convert the overlap into 90-day labels or open U3/G-US tests from these archives.
