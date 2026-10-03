# Synthetic local-date feature publication v2

Run ID: `u3-synthetic-local-date-publication-v2-20261003`
Code commit: `6fcd549f11f97bca5335924f5e04003b776c92db`
Requirements addressed: US03, US06, US08, US11, US14, US23, US24
Status: **verified engineering fixture; U0, U3 and G-US PENDING**

## Objective and changes

Add a separate OFF feature policy for sources that publish property, attribute
or prior-sale facts to a source-local date without an evidenced hour. The
assembler waits until that source-local day has ended and respects an earlier
source-snapshot cap. It retains original date precision and IANA zone in
lineage and the v2 snapshot hash. Exact-UTC and local-date v1 entry points
reject these facts and preserve their existing snapshot identity. The guarded
synthetic median opts into v2 explicitly. [ADR 0082](../../decisions/0082-source-local-feature-publication-v2.md)
records the choice.

A later date-only correction may close an earlier exact-time property or
attribute version without inventing a timestamp. Cross-precision raw deed
and economic-transfer collisions are rejected. ON remains unavailable.

## Executed checks and observed results

| Check | Actual result | Evidence |
| --- | --- | --- |
| Full Python 3.11 suite with local OpenML ARFF enabled | Exit 0; **1,255 tests, zero skips**, 204.448 s test time | [gate](test_gate.json), [log](full_suite.log) |
| Branch-aware coverage across seven touched production modules | **90% combined**; each module at least 81% | [coverage](coverage.log) |
| Ruff check and format check on nine changed Python files | Exit 0 for both | [lint](ruff_check.log), [format](ruff_format.log) |
| Installed-dependency audit | Exit 0; no known third-party vulnerabilities; editable local package skipped | [audit](pip_audit.log) |
| Code, Python and security reviews | No remaining high/medium correctness or leakage finding after corrections | [review record](review_evidence.md) |

The full command was `.venv/Scripts/python.exe -m coverage run --branch
--source=tabpfn4realestate -m unittest discover -s tests -p test_*.py -q`
with `AMES_ARFF_PATH` set to the existing hash-verified ARFF
(`10db9fe72ed693212a222e39981133ec1b3ee5090d7f2caf2461190a4ad51279`).
Its presence prevents the OpenML fixture test from skipping. The initial
full gate passed 1,253 tests before two additional invalid-input tests were
added; its [log](full_suite_before_boundary_tests.log) is preserved. The
final suite above includes both.

Tests were written first: the initial v2 import failed; the median integration
first rejected the new dated property contract; and the mixed exact/date
version-correction regression reproduced an invalid class conversion. The
corrected paths and cross-precision identity tests pass. Expected error text
from deliberately failing private-source fixtures appears in the successful
full-suite log; the suite ends in `OK`.

## Evidence boundary and next action

The source hash used in the synthetic fit remains a fixture declaration, not
an independently verified raw-source digest. The OpenML ARFF is only an
engineering fixture for another test. This run creates **zero certified
modern US sale labels**, no trained real-market checkpoint, no calibrated
interval and no performance score. It does not accept U0, U3 or G-US.

Continue the [U0 source audit](../../next_action.md). Before real training,
verify a source-specific first-publication rule, recorded sale semantics,
rights, historical attributes and the raw-artifact hash; then exercise this
policy on manually audited source fixtures. Do not open final labels or begin
Part II.
