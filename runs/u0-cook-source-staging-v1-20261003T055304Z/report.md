# U0 Cook parcel-source observation staging, v1

- Date: 2026-10-03 UTC
- Requirements: US02, US03, US05, US06, US07, US08, US22, US23, US24
- Protocol: `cook-parcel-source-staging-v1`
- Status: **verified source-schema staging; U0 PENDING; G-US PENDING**

## Objective and changes

[ADR 0064](../../decisions/0064-cook-parcel-source-staging.md) and the [frozen plan](plan.md) govern a local-only round trip of the already captured 200 Cook Assessor parcel-sale rows. The new immutable source-observation type preserves the 18 requested raw scalar fields, missing versus null states, source row identity, exact Decimal price state, PIN state, source-local recorded date, capture time and lineage hashes. It has no conversion to the canonical `Transaction` or historical as-of feature. The offline runner checks the pinned source replay, writes an ACL-restricted private file and completion manifest once, and publishes only a fixed nine-field [aggregate](aggregate.json). No new HTTP request was made.

## Observed evidence

The one-shot staging command exited 0 in 4.132 seconds. It wrote 200 source observations to the Git-ignored private directory `data/raw/cook_county/parcel-staging-v1-130b5169ff81ccbc/`. Its observation file is 205,419 bytes with SHA-256 `7b315b4b001d3b14ffc64ab0277f486738e53b83b120da592a952f94a175c167`. The public aggregate SHA-256 is `07dfa3b0b038e8d4bbac50a54b365c1cd93a397127ae94ed0b7fbd6b8c490488`. Exact-byte private/public [replay](verify_artifacts.ps1) exited 0 with `cook_source_staging_private_and_public_replay_pass`; the public field allowlist and zero-label state also passed.

Eighteen focused synthetic tests passed at 91% branch-aware coverage. The first full-suite attempt stopped during a fixture write when C: ran out of space; its partial [log](full_tests.log) remains a failed/incomplete attempt, not a valid test result. After disk space was restored, the complete repository suite passed **1,115 tests with zero skips** in 196.177 seconds; its [log](full_tests_retry.log) and hash are recorded in the [test gate](test_gate.json). Ruff check, Ruff format, `pip check` and `pip-audit` exited 0. The dependency audit found no known vulnerabilities among auditable packages; it could not audit the local editable package on PyPI. Code, Python and security reviews found no critical or high issue before the real run.

The four public command logs were converted from PowerShell UTF-16 to UTF-8. Local home paths were replaced with `%USERPROFILE%`; the test and failure text remains. The test gate records original and published log hashes. Final code and security reviews of the publishable artifacts found no critical, high or medium issue.

## Interpretation and next action

These are **parcel-source observations, not 200 certified sale labels**. A repeated deed number may describe one economic transfer across multiple parcels. `sale_date` is a recorded date; true close date, first row availability, transaction scope, arm's-length status, property identity and dataset-specific commercial rights remain unresolved. The published price is preserved for audit, never promoted to a model target or comparable. **Zero sale labels are certified; historical as-of eligibility is false; U0 and G-US remain PENDING.**

Continue the private 200-record review against independent deed and parcel instruments and obtain authoritative date, publication and rights evidence. The custodian inquiry remains an unsent draft. Do not start real US training or international implementation from this staging result. Replay from the project root with `& 'runs/u0-cook-source-staging-v1-20261003T055304Z/verify_artifacts.ps1'`.
