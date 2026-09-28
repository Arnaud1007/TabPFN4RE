# U0 Ames engineering smoke report

Run ID: `u0-smoke-20260928T082634Z-ef55636ed896`
Date: 2026-09-28
Code commit: `7d224e711ef52fa7adbf0a4cfd52a5dd9e0afa11`
Requirements touched: US02, US09, US12, US22, US23, US24
Gate status: U0 **PENDING**; G-US **PENDING**

## Objective and changes

Verify a minimal, reproducible Ames ingestion-to-prediction path after the source schema check. The run used the official OpenML 42165 ARFF checksum `10db9fe72ed693212a222e39981133ec1b3ee5090d7f2caf2461190a4ad51279`. Its distinct `ames_engineering_v1` protocol selected the first 200 rows and reserved 40 via a seeded split. This does not reproduce the missing legacy split.

## Actual commands and outputs

From the project root:

```powershell
.\.venv\Scripts\python.exe -m tabpfn4realestate.ames_smoke data/raw/openml/house_prices-42165.arff --sha256 10db9fe72ed693212a222e39981133ec1b3ee5090d7f2caf2461190a4ad51279 --output runs
$env:AMES_ARFF_PATH = (Resolve-Path 'data/raw/openml/house_prices-42165.arff').Path
.\.venv\Scripts\python.exe -m coverage run --source=tabpfn4realestate -m unittest discover -s tests -q
.\.venv\Scripts\python.exe -m coverage report --show-missing
.\.venv\Scripts\python.exe -m coverage json -o runs/u0-smoke-20260928T082634Z-ef55636ed896/coverage.json
python -m ruff check src tests
```

The smoke command exited 0 and wrote a `complete`, `replayable` manifest. The test command exited 0: 33 tests, no skips; total statement coverage 90%. Coverage commands and lint exited 0. The test gate's measured duration and environment appear in `test_gate.json`; stdout and coverage detail are retained alongside it. Independent code, Python and security reviews reported no remaining high or medium findings.

An earlier completed run, `u0-smoke-20260928T080901Z-9c7ea074b1ae`, used the same source, split and baseline at commit `3e90391`. It yielded the same saved metrics and is retained as an earlier engineering run, not as a separate accuracy observation.

## Measured engineering result

| Metric | Saved result |
| --- | ---: |
| Selected rows | 200 |
| Development / reserved | 160 / 40 |
| Predictions | 40 |
| Median absolute percentage error | 23.9331% |
| Within 10% of sale price | 17.5% |

`manifest.json`, `config.json`, `split.json`, `baseline.json`, `metrics.json`, `feature_policy.json` and `environment.lock.json` record the run. `source.arff` and `predictions.csv` remain local ignored files, with their hashes retained in the manifest. The score is a small historical engineering baseline and cannot satisfy US performance or calibration requirements.

## Failed attempts, limitations and next task

The named legacy GitHub URL returned `Repository not found`/exit 128 without credentials, and the original split, predictions, catalogue and Word artifact were absent from the targeted local inventory. No legacy reproduction was attempted. Source rights for a releasable Ames product remain unresolved. The next dependency-ready task is the U1 core OFF schema and synthetic as-of tests; recover legacy artifacts when an accessible path arrives. The exact resume command and remaining blockers are in `next_action.md`.
