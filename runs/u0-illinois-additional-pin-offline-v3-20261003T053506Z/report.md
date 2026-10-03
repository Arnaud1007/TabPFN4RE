# U0 Illinois Additional PIN offline identity triage, v3

- Date: 2026-10-03 UTC
- Requirements: US02, US03, US05, US06, US07, US08, US24
- Protocol: `illinois-additional-pin-offline-v3`
- Status: **verified offline diagnostic; U0 PENDING; G-US PENDING**

## Objective and changes

This run compares the frozen 100 Cook sample rows, 80 PTAX declarations and their previously captured Additional PIN observations **offline**. [ADR 0061](../../decisions/0061-illinois-additional-pin-offline-triage.md) fixes the strict PIN states, exact declaration-ID join, duplicate retention and private/public boundary. The v1 plan was rejected before execution for a mistyped prior-worklist hash. The one real v2 run [failed](../u0-illinois-additional-pin-offline-v2-20261003T051910Z/failed_report.md) under a separate 500 observation-reference cap. [ADR 0063](../../decisions/0063-illinois-additional-pin-reference-cap-v3.md) and the [v3 plan](plan.md) raised only that resource cap to 5,000 before this real run. The candidate-pair cap remained 500 and the worklist cap remained 1 MiB.

The implementation preserves one review item per Cook row and references captured Additional observations by ordinal and row hash. Primary and Additional comparisons remain separate. Repeated Cook rows do not multiply a declaration-level consideration into labels. No new source request was made.

## Observed evidence

The one-shot v3 command exited 0 in 54.757 seconds. It created a private ACL-restricted, Git-ignored worklist and completion manifest, then wrote the fixed-allowlist [public aggregate](aggregate.json). Its SHA-256 is `1dc56626f3aaa0823a313ede5ce1b8d807c99865dcb899ea45324eafae39661d`; the private worklist hash recorded there is `cd9e86a4888dee74eb8c6d9a0c5e4b1349dca2c2561284d2a223f2c37e8a2c3d`. The exact-byte [replay](verify_artifacts.ps1) exited 0 with `offline_private_and_public_replay_pass`.

Eleven focused synthetic tests passed at 91% branch-aware coverage, including the exact 501, 5,000 and 5,001 reference boundaries. Ruff check and format passed. The full repository suite passed 1,097 tests with zero skips in 176.980 seconds, with the verified local Ames ARFF configured. `pip check` passed; `pip-audit` found no known vulnerabilities among auditable installed packages and could not audit the local editable package on PyPI. Code, Python and security reviews found no critical or high issue. Exact commands, versions and outputs are in the [test gate](test_gate.json); the full suite output is in [full_tests.log](full_tests.log).

## Interpretation and next action

The worklist is a **private identity-review aid**, not a factual determination of parcel scope. No match count, conflict cell, PIN, declaration ID, price or row-level date is published. **Zero sale labels are certified**; historical as-of eligibility is false. A matching or additional PIN does not allocate consideration to a single home or establish arm's-length status, closing date, first availability or source-specific commercial rights.

Continue manual review of the private candidate queue and obtain independent deed/parcel, date and rights evidence. The Cook custodian inquiry is drafted but remains unsent in this environment. No real US training, US release claim or international implementation is unlocked. Replay from the project root with `& 'runs/u0-illinois-additional-pin-offline-v3-20261003T053506Z/verify_artifacts.ps1'`.
