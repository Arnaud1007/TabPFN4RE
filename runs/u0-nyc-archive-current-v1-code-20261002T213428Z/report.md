# NYC archive/current comparison: code gate

Run ID: `u0-nyc-archive-current-v1-code-20261002T213428Z`  
Protocol: [ADR 0044](../../decisions/0044-nyc-archive-current-concordance-v1.md)  
Status: **code verified, private source comparison not yet run**  
Requirements: US05, US06, US08, US22, US23, US24

## Implemented

The offline comparator pins the version-62 archive and the September 2026
current snapshot, maps the 21 exact source fields, validates each CSV and
compares complete rows with duplicate-aware multisets. Its second tier
normalizes only a strictly parsed calendar date. It emits aggregate counts
privately and broad overlap buckets publicly. A create-only intent precedes
CSV access, and offline replay checks saved outputs. Neither tier establishes
transaction identity, first publication, sale-label eligibility or rights.

The comparator is in
[`scripts/compare_nyc_archive_snapshot_v1.py`](../../scripts/compare_nyc_archive_snapshot_v1.py),
with synthetic tests in
[`tests/test_compare_nyc_archive_snapshot_v1.py`](../../tests/test_compare_nyc_archive_snapshot_v1.py).
The final formatted comparator SHA-256 is
`b1e339fe7e2c5482ae72431d370fc3d5cd90bed249340a402529e527c234a2be`.
The new comparator tests use only synthetic CSV rows; the comparator's
private comparison command has not been run.

## Actual checks

| Check | Observed result | Evidence |
| --- | --- | --- |
| Full repository suite, with verified Ames ARFF path | 919 tests passed, zero skips, exit 0, 186.696 s | [final gate](full_tests_final_gate.json), [log](full_tests_final.log) |
| Focused synthetic suite | 17 passed, exit 0 | [gate](focused_checks_gate.json), [log](focused_tests.log) |
| Branch-aware comparator coverage | 83%, 297 statements and 98 branches | [coverage](coverage.log) |
| Ruff check and format | both exit 0 | [lint](lint.log) |
| `pip check` and pinned scoped `pip-audit` | both exit 0, no known vulnerabilities | [dependency](dependency.log) |
| Code and security review | approved; no remaining Critical, High or Medium finding | reviewer findings recorded in development session |

The first full-suite wrapper attempt stopped before a test verdict because
PowerShell treated an expected adversarial ZIP warning as terminating. Its
[failure record](full_tests_attempt1_failure.json) is retained. A corrected
wrapper completed a 919-test run, then a formatting-only code change was made.
The final full-suite run above used the final formatted code bytes. Its
expected synthetic failure-path messages are test output, not gate failures.

## Next action

Commit and push this reviewed code and gate evidence to `audit/u0`. Confirm
the remote branch hash with `git ls-remote` and a clean tree. Only then run
the fixed offline comparison against the private pinned files and preserve
its redacted public evidence. U0 and G-US remain **PENDING**; NYC certified
sale labels remain **0**.
