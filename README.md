# TabPFN4RealEstate

Evidence-first research workspace for residential sale-price prediction. U0, the legacy-project and data audit, remains open. A fast Ames development-only prototype now produces historical predictions while US source qualification continues. Ames results are engineering evidence, not a US release or future-sale accuracy claim.

In Visual Studio 2022, choose **File > Open > Folder** and select this directory.

## Fast Ames prediction prototype

Use Python 3.11 and the pins in [ames-prototype-requirements.txt](locks/ames-prototype-requirements.txt). On this workstation the isolated interpreter is `data/raw/legacy-replay/.venv/Scripts/python.exe`. A fresh clone can create an environment with `py -3.11 -m venv data/raw/ames-prototype/.venv` after creating the ignored `data/raw/ames-prototype` directory, then install with `& 'data/raw/ames-prototype/.venv/Scripts/python.exe' -m pip install -r locks/ames-prototype-requirements.txt`. Set `PYTHONPATH` to the repository's `src` directory because the isolated interpreter does not install this package.

### Twelve-field quick prediction

Edit the [12-field example request](examples/ames-manual12-request.json), then run this command from the project root on this workstation:

```powershell
$env:PYTHONPATH = (Resolve-Path -LiteralPath 'src').Path
& 'data/raw/legacy-replay/.venv/Scripts/python.exe' -m scripts.ames_dev_prototype predict --bundle data/raw/ames-prototype/manual12-20261004-v1 --request examples/ames-manual12-request.json --bundle-sha256 1505ab1806202b9ca9626bbe5c92c4ef4f7393ef90680994ba8113b0f392a4f4
```

The [12-field report](runs/ames-manual12-20261004-v1/report.md) records 6.81% MdAPE and 66.78% within 10% on 1,168 historical development sales. The example output is $147,843.96875 for a synthetic house. These are Ames engineering results, not a current US market validation. `OverallQual` and `OverallCond` use Ames 1-10 ratings; `Neighborhood` uses Ames codes. The private bundle is not in Git. A fresh clone must train it first using the source and holdout membership below, adding `--profile manual12` and a new output path, then use its bundle digest.

### Full-feature comparison

From the project root in PowerShell, after obtaining the checksum-pinned OpenML 42165 ARFF named in [migration_report.md](migration_report.md):

```powershell
$env:PYTHONPATH = (Resolve-Path -LiteralPath 'src').Path
& 'data/raw/legacy-replay/.venv/Scripts/python.exe' -m scripts.ames_dev_prototype train-evaluate --source data/raw/openml/house_prices-42165.arff --holdout data/legacy/holdout_ids.csv --output data/raw/ames-prototype/my-unique-run
```

The command skips the 292 frozen holdout data lines before parsing prices. It saves private row-level development predictions and a data-only model bundle under ignored `data/raw/ames-prototype/`. The prediction command below replays the existing bundle **on this workstation**. A fresh clone must train its own bundle first, then use that run's path and verified bundle digest. A digest copied from an untrusted bundle does not establish its provenance:

```powershell
& 'data/raw/legacy-replay/.venv/Scripts/python.exe' -m scripts.ames_dev_prototype predict --bundle data/raw/ames-prototype/dev-only-20261004-v3 --request examples/ames-prototype-request.json --bundle-sha256 c4da912facd6025145b31725ad5e25918e3eb8fa95463e6a8205513f3208f121
```

The example includes all 75 expected feature keys. It is a synthetic vector seeded from development-feature medians and modes, then adjusted for physical consistency; it is not an observed property. Its output demonstrates serving consistency. Use the saved out-of-fold scorecard for historical development accuracy. The CLI requires the full feature schema; it does not provide calibrated intervals or a current-market valuation.

The [Ames prototype report](runs/ames-dev-prototype-20261004-v1/report.md) records 1,168 paired development predictions: XGBoost reached 5.64% MdAPE and 71.32% within 10%, versus 24.83% and 21.32% for the median baseline. These are historical development-fold results only; U0 and G-US remain pending.

## Current evidence

- [migration_report.md](migration_report.md) records recovered and missing legacy inputs, the replay outcome, and the hardware audit.
- [U0 legacy replay report](runs/u0-legacy-replay-20260928T145000Z/report.md) records the original split, repeatability, archived-score mismatch and verification evidence.
- [requirements.yaml](requirements.yaml) tracks requirement IDs and evidence status.
- [next_action.md](next_action.md) gives the current runnable task and blockers.

Use Python 3.11.6 for the U0 smoke package. Raw source files, row-level predictions, derived data and model checkpoints stay outside Git. The application, real-world US evaluation and international stages remain gated by the supplied specification.
