# U1 synthetic listing lifecycle increment

Run ID: `u1-lifecycle-20261003T000805Z`
Reviewed code commit: `286273dd0afde6621b78f3e70dfaf2bd24b11b2b`
Protocol: `us_listing_lifecycle_v1`
Requirements touched: US04, US06, US08, US23, US24
Status: synthetic increment **verified**; U1 and G-US **PENDING**

## Objective and completed changes

Added an immutable, in-memory resolver for dated property identity and
listing episodes. It conservatively matches parcel/address and unit facts,
uses only reviewed cross-feed aliases available by the valuation origin,
retains source observations, flags overlapping advertisements, and
reason-codes unresolved events. Withdrawals and relists remain separate.
The existing OFF path and ON restriction were not changed. [ADR 0050](../../decisions/0050-synthetic-listing-lifecycle-v1.md)
records the fixed synthetic expectations and boundaries.

## Commands and observed results

`test_gate.json` records the exact command arrays, exit codes, durations,
Python version, commit, source/test hashes, environment-lock hash and SHA-256
of every output log. All seven gate commands exited 0:

| Check | Observed result |
| --- | --- |
| Focused lifecycle tests | 17 passed, zero skipped |
| Lifecycle branch-aware coverage | 89% (240 statements, 96 branches) |
| Full repository suite | 977 passed, zero skipped, 169.849 seconds reported by unittest |
| Ruff check and format | Both passed |
| Dependency consistency | `pip check` passed |
| Dependency audit | No known vulnerabilities found; the editable local package was not found on PyPI and was skipped by pip-audit |

The full-suite log includes expected stderr from negative-path tests, followed
by `OK`. Test fixtures contain synthetic address, parcel, unit and price
values. No private source row or real listing event was used by this resolver
gate. Initial RED execution failed because the module was absent; a later
RED execution caught an alias-availability contract before implementation.
Code, Python and security reviews identified and then verified fixes for
future alias leakage, reingestion handling, deterministic conflict output
and identifier namespace collisions.

## Residual limits and next action

This is not complete US04: source corrections and supersession, evidence
quality, match confidence, historical listing rights and first publication,
production-scale indexing, and transaction-to-episode linkage remain open.
The `sold` listing status is not a certified gross sale label. No real NYC,
HCPA, Cook or other US source has entered the resolver. U1 is not accepted
and G-US remains pending. Continue U0 source qualification and manual audits
before any real listing-feature or ON claim.

To re-run the focused synthetic check from the project root:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_listing_lifecycle -q
```
