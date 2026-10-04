# TabPFN4RealEstate

Evidence-first research workspace for residential sale-price prediction. U0, the legacy-project and data audit, remains open. A fast Ames development-only prototype now produces historical predictions while US source qualification continues. Ames results are engineering evidence, not a US release or future-sale accuracy claim.

In Visual Studio 2022, choose **File > Open > Folder** and select this directory.

## Fast Ames prediction prototype

Use Python 3.11 and the pins in [ames-prototype-requirements.txt](locks/ames-prototype-requirements.txt). On this workstation the isolated interpreter is `data/raw/legacy-replay/.venv/Scripts/python.exe`. A fresh clone can create an environment with `py -3.11 -m venv data/raw/ames-prototype/.venv` after creating the ignored `data/raw/ames-prototype` directory, then install with `python -m pip install -r locks/ames-prototype-requirements.txt`. Set `PYTHONPATH` to the repository's `src` directory because the isolated interpreter does not install this package.

From the project root in PowerShell, after obtaining the checksum-pinned OpenML 42165 ARFF named in [migration_report.md](migration_report.md):

```powershell
$env:PYTHONPATH = (Resolve-Path -LiteralPath 'src').Path
& 'data/raw/legacy-replay/.venv/Scripts/python.exe' -m scripts.ames_dev_prototype train-evaluate --source data/raw/openml/house_prices-42165.arff --holdout data/legacy/holdout_ids.csv --output data/raw/ames-prototype/my-unique-run
```

The command skips the 292 frozen holdout data lines before parsing prices. It saves private row-level development predictions and a data-only model bundle under ignored `data/raw/ames-prototype/`. To predict, pass the bundle SHA-256 recorded in a **trusted, committed** run report; a digest copied from an untrusted bundle does not establish its provenance:

```powershell
& 'data/raw/legacy-replay/.venv/Scripts/python.exe' -m scripts.ames_dev_prototype predict --bundle data/raw/ames-prototype/my-unique-run --request examples/ames-prototype-request.json --bundle-sha256 <committed-bundle-sha256>
```

The example includes all 75 expected feature keys and comes from a development training row, with its sale price and ID removed. Its output demonstrates serving consistency. Use the saved out-of-fold scorecard for historical development accuracy. The CLI requires the full feature schema; it does not provide calibrated intervals or a current-market valuation.

## Current evidence

- [migration_report.md](migration_report.md) records recovered and missing legacy inputs, the replay outcome, and the hardware audit.
- [U0 legacy replay report](runs/u0-legacy-replay-20260928T145000Z/report.md) records the original split, repeatability, archived-score mismatch and verification evidence.
- [requirements.yaml](requirements.yaml) tracks requirement IDs and evidence status.
- [next_action.md](next_action.md) gives the current runnable task and blockers.

Use Python 3.11.6 for the U0 smoke package. Raw source files, row-level predictions, derived data and model checkpoints stay outside Git. The application, real-world US evaluation and international stages remain gated by the supplied specification.
