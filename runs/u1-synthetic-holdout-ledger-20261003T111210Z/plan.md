# Synthetic holdout opening ledger verification plan

Run ID: `u1-synthetic-holdout-ledger-20261003T111210Z`
Code commit before verification: `595256a51f1de4fb5de72943f60b6900fc41454d`
Requirements: US11, US22, US23 T12 (synthetic engineering only)

## Hypothesis and acceptance

An evaluator-owned, on-disk SQLite ledger can commit outcome-free predictions
and a one-use opening intent before the reserved-label loader runs. A failed
or interrupted opening must remain consumed, and replay must use an already
completed scorecard without reopening labels. Callers cannot substitute
mutable predictions after the intent. In-memory SQLite paths must fail before
label access.

Pass only if the focused tests, full `unittest` discovery, Ruff checks and
focused branch coverage at or above 80% pass. Record the exact outputs.
This run contains synthetic IDs and labels; it cannot certify a real sale
source, holdout protocol, model or US gate.

## Commands

From the repository root in PowerShell, with the pinned local `.venv`:

```powershell
& .\.venv\Scripts\python.exe -m unittest tests.test_holdout_ledger -q
& .\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_*.py' -q
& .\.venv\Scripts\python.exe -m coverage run --branch --source=tabpfn4realestate.evaluation.holdout_ledger -m unittest tests.test_holdout_ledger -q
& .\.venv\Scripts\python.exe -m coverage report -m src\tabpfn4realestate\evaluation\holdout_ledger.py
& .\.venv\Scripts\ruff.exe check src\tabpfn4realestate\evaluation\holdout_ledger.py tests\test_holdout_ledger.py
& .\.venv\Scripts\ruff.exe format --check src\tabpfn4realestate\evaluation\holdout_ledger.py tests\test_holdout_ledger.py
& .\.venv\Scripts\pip-audit.exe --local --progress-spinner off
```
