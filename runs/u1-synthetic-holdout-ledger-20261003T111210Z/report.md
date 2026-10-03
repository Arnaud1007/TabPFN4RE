# Synthetic holdout opening ledger: verification report

Run ID: `u1-synthetic-holdout-ledger-20261003T111210Z`
Code commit: `595256a51f1de4fb5de72943f60b6900fc41454d`
Requirements: US11, US22, US23 T12 (synthetic engineering scope)
Status: **verified synthetic fixture; U0 and G-US PENDING**

## Changes and observed results

The [ledger module](../../src/tabpfn4realestate/evaluation/holdout_ledger.py)
persists outcome-free predictions and an opening intent in one SQLite
transaction before loading reserved labels. A failed opening cannot be retried
on the same ledger, including with a changed model or overlapping row IDs.
Replay is read-only and requires matching identity and digests. The evaluator
rejects an in-memory database path before label access.

The [test fixture](../../tests/test_holdout_ledger.py) contains 11 tests. Its
RED checkpoints exposed the missing module, mutable prediction-list scoring,
replay that wrote schema tables, and the SQLite `:memory:` bypass. The GREEN
implementation passed the focused tests after each fix. Code and security
reviews found the mutable-list and in-memory-path bugs; both were fixed and
re-reviewed with no remaining high or medium finding within synthetic scope.

| Check | Actual command or artifact | Observed result |
| --- | --- | --- |
| Focused T12 fixture | `python -m coverage run --branch --source=tabpfn4realestate.evaluation.holdout_ledger -m unittest tests.test_holdout_ledger -q` | 11 passed, exit 0; [log](focused_tests.log) |
| Full suite after final path fix | `python -m unittest discover -s tests -p 'test_*.py' -q` | 1,126 tests, 1 skipped, exit 0 in 242.909 s (test runner time); [log](full_tests.log) |
| Focused branch coverage | `python -m coverage report -m src/tabpfn4realestate/evaluation/holdout_ledger.py` | 84%; [log](coverage.log) |
| Ruff check and format | Commands in [plan](plan.md) | Both exit 0; [check](ruff_check.log), [format](ruff_format.log) |
| Local dependency audit | `pip-audit --local --progress-spinner off` | Exit 0, no known vulnerabilities in auditable packages; editable project itself was skipped as not on PyPI; [log](pip_audit.log) |

The full suite emits expected failure messages from negative source-audit
fixtures, then reports `OK`. No private transaction rows or actual sale-price
metrics are reported. Logs were transcoded from PowerShell UTF-16 output to
UTF-8 without changing their text. The [manifest](manifest.json) records the
environment, fixture and plan hashes; model/data/split fields are not applicable to this
software-only run.

## Limits and next action

The ledger must be owned by a future evaluation process at a single controlled
path. Its local hashes do not resist an operator who can rewrite the database.
The interface currently scores one frozen model bundle; certification must
persist every predeclared comparison model's outputs before one label opening.
There is no real source label, frozen final cohort or release bundle to open.
Continue the U0 source rights, identity, close-date and historical-availability
audits in [next_action.md](../../next_action.md). Do not treat this test as a
PASS for U3, U6, U8 or G-US.
