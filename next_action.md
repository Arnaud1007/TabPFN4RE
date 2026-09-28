# Next action

Active milestone: U0 audit. Status: engineering smoke is ready to run; legacy recovery remains pending.

## Next runnable command

From the project root in PowerShell, with the local Python 3.11 environment installed:

```powershell
.\.venv\Scripts\python.exe -m tabpfn4realestate.ames_smoke data/raw/openml/house_prices-42165.arff --sha256 10db9fe72ed693212a222e39981133ec1b3ee5090d7f2caf2461190a4ad51279 --output runs
```

Inspect the printed run directory's `manifest.json`, `metrics.json`, `split.json` and `predictions.csv`. A completed engineering run is not a recovered legacy result or a release gate. Record its run ID and observed metrics in `migration_report.md` and preserve the files. If the raw file is absent on a fresh clone, re-download it from the URL in `data/source_cards/openml_42165.yaml` and verify SHA-256 before this command.

## Unresolved dependencies

- Accessible legacy repository or local path, original Word specification, original split membership, XGBoost configuration/predictions and `feature_catalog.csv`.
- Rights decision for any releasable use of the Ames file; its OpenML licence field is `NA`.
- Multi-market time-stamped US transactions and prospective labels for G-US.

These dependencies do not prevent the smoke command. They prevent legacy reproduction, a real-world US gate and international work.
