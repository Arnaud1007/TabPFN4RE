# Local Ames prediction form checkpoint

Date: 2026-10-04. Status: **implemented and verified**.
Scope: historical Ames development prototype. U0 and G-US remain **PENDING**.
The executable check ledger is [test_gate.json](test_gate.json).

## Delivered

- `scripts/ames_manual12_form.py` opens a local 12-field Tkinter form and
  calls the same guarded prediction service as the CLI.
- The form shows the historical scope and lack of a calibrated interval,
  rejects incompatible bundles before opening, validates input, and clears
  stale results on errors.
- `README.md` contains the exact workstation launch command. The bundle and
  raw data remain Git-ignored private artifacts.

## Observed checks

| Check | Result |
| --- | --- |
| Six form contract unit tests | PASS |
| Native Tkinter form/CLI parity flow | PASS; one integration test |
| Ruff lint and format checks on the three new Python files | PASS |
| Synthetic example CLI request | $147,843.96875 USD; `schema_supported` |
| Project suite with pinned Ames ARFF available | PASS; 1,302 tests, zero skips, 92% package coverage |
| Prototype dependency audit | PASS; no known vulnerabilities found |

The parity test trains a fresh private 12-field bundle, loads the synthetic
example in a withdrawn Tkinter window, and compares the form output with both
direct service and CLI responses. It also verifies invalid lot area clears
the prior result and a missing demo file displays an error. It does not
assert screen-reader behavior or current-market prediction quality.

The existing 12-field model's development score is in the
[model checkpoint](../ames-manual12-20261004-v1/report.md): 6.81% MdAPE on
1,168 historical development folds. It is not an independent future-sale
result. The 292 legacy holdout rows remain unopened.

## Commands

From the repository root:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_ames_manual12_form -q
$env:PYTHONPATH = (Resolve-Path -LiteralPath 'src').Path
& 'data/raw/legacy-replay/.venv/Scripts/python.exe' -m unittest prototype_tests.test_ames_manual12_form_flow -q
.\.venv\Scripts\ruff.exe check scripts/ames_manual12_form.py tests/test_ames_manual12_form.py prototype_tests/test_ames_manual12_form_flow.py
.\.venv\Scripts\ruff.exe format --check scripts/ames_manual12_form.py tests/test_ames_manual12_form.py prototype_tests/test_ames_manual12_form_flow.py
$env:AMES_ARFF_PATH = (Resolve-Path -LiteralPath 'data/raw/openml/house_prices-42165.arff').Path
.\.venv\Scripts\python.exe -m coverage run --source=tabpfn4realestate -m unittest discover -s tests -q
.\.venv\Scripts\python.exe -m coverage report --skip-covered
.\.venv\Scripts\python.exe -m pip_audit -r locks/ames-prototype-requirements.txt --progress-spinner off
```

The full-suite output is retained at
`data/raw/ames-prototype/manual12-form-full-suite.log` (Git-ignored), SHA-256
`754cfdf48d5515a482a8bd4caad2d93f809bb223f4399af2523732d828f7f972`.

## Next action

Use the form to try individual historical Ames-style examples. Continue U0
source qualification before training on real US transactions. The local
window still needs a manual keyboard and screen-reader review before an
accessibility claim. No prospective cohort, current US accuracy, calibrated
interval or accepted application release is claimed here.
