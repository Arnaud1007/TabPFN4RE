# TabPFN4RealEstate

Evidence-first research workspace for residential sale-price prediction. U0, the legacy-project and data audit, remains open. Ames and King County historical prototypes produce local research predictions. An Indiana 2024-to-2025 development diagnostic reached 15.19% median error after adding assessed values from later sale-disclosure snapshots; their pre-sale timing is unverified, and a targeted source review found nominal/nonmarket label concerns. None of these results is a US release or future-sale accuracy claim.

In Visual Studio 2022, choose **File > Open > Folder** and select this directory.

## Fastest working prediction: King County

On the prepared workstation, double-click `Launch-KingResearchForm.cmd`. Wait
for **Historical model ready**, choose **Load synthetic example**, then choose
**Predict**.
The saved model returns a point estimate without retraining. To preserve a real
pre-outcome prediction for later evaluation, enter an opaque enrollment
reference that contains no address or parcel information and choose
**Predict + record**. That one action creates the prediction, a private local
receipt and a privacy-safe commitment.

If commitment publication is interrupted, the private receipt is retained.
The form restores pending receipts after restart and enables **Retry
commitment**, which publishes the existing receipt without running the model a
second time. Keep private receipts under the ignored `data/raw/` area.

The model was trained and evaluated on historical King County sales through
2015. Its output is a historical research estimate, with no calibrated
interval, current-market validity or certified 90-day accuracy. **G-US is
PENDING.**

## Fast Ames prediction prototype

Use Python 3.11 and the pins in [ames-prototype-requirements.txt](locks/ames-prototype-requirements.txt). On this workstation the isolated interpreter is `data/raw/legacy-replay/.venv/Scripts/python.exe`. A fresh clone can create an environment with `py -3.11 -m venv data/raw/ames-prototype/.venv` after creating the ignored `data/raw/ames-prototype` directory, then install with `& 'data/raw/ames-prototype/.venv/Scripts/python.exe' -m pip install -r locks/ames-prototype-requirements.txt`. Set `PYTHONPATH` to the repository's `src` directory because the isolated interpreter does not install this package.

### Twelve-field quick prediction

For a local entry form on this workstation, run from the project root:

```powershell
$env:PYTHONPATH = (Resolve-Path -LiteralPath 'src').Path
& 'data/raw/legacy-replay/.venv/Scripts/python.exe' -m scripts.ames_manual12_form --bundle data/raw/ames-prototype/manual12-20261004-v1 --bundle-sha256 1505ab1806202b9ca9626bbe5c92c4ef4f7393ef90680994ba8113b0f392a4f4
```

Choose **Load synthetic demo** for an example or enter the 12 fields and choose
**Predict**. Living area, overall quality and Ames neighborhood code are
required. The result is a historical Ames point estimate; it has no calibrated
interval and is not a current US valuation. The form and CLI use the same
prediction service. The private model bundle stays outside Git; a fresh clone
must train its own bundle as described below.

For a JSON request or automation, use the CLI:

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

### King County historical prediction form

The local [15-field King County form](runs/king-absolute-error-serving-20261006-v1/report.md)
uses the selected absolute-error historical model. From the project root on
this workstation:

Double-click `Launch-KingResearchForm.cmd` for the pinned local setup, or run
the equivalent command below. The launcher verifies that the private Python
environment and selected model bundle exist before opening the form.

```powershell
$env:PYTHONPATH = "$(Resolve-Path -LiteralPath '.');$(Resolve-Path -LiteralPath 'src')"
& 'data/raw/legacy-replay/.venv/Scripts/python.exe' -m scripts.king_research_form --bundle data/raw/king-benchmark/king-absolute-error-serving-20261006-v1 --manifest-sha256 50ca467e61a52752e5ff9082297eeff1b294ef761aec383c8c7d2537c027941d
```

For the quickest demonstration, choose **Load synthetic example** and then
**Predict**. You can instead load an edited copy of
[`examples/king-research-request.json`](examples/king-research-request.json)
with **Load request JSON...**, or enter the 15 physical and location fields,
then choose **Predict**. Loaded files pass the same validation as typed values;
an invalid file leaves the existing form values unchanged. The synthetic
example displays **$553,847** rounded from the saved machine output. The form
keeps the window responsive during model
inference, loads the verified checkpoint only once per application session,
and clears an old estimate when inputs change. The current checkpoint verifies
the equivalent saved-model prediction through the shared service; it does not
reuse the older bundle's GUI timing measurements. This is a 2015 research
estimate, with no calibrated interval or current-market validity. The private
bundle stays outside Git; a fresh clone must build and verify its own bundle.

For a real observation made before its outcome is known, enter an opaque
enrollment reference that does not contain an address, parcel number or owner
name, then choose **Predict + record**. The form reuses its loaded model and, in
one action, saves an access-restricted private receipt under `data/raw/` and a
privacy-safe commitment under `runs/`. If commitment publication fails after
the receipt is saved, the form blocks another capture and offers **Retry
commitment**. Pending receipts are restored after restart; retrying creates the
commitment from the saved receipt and does not make a second prediction. See
the [prospective enrollment report](runs/king-prospective-enrollment-20261005-v1/report.md)
for the verified behavior and privacy boundary.

- [King historical prediction command](runs/king-absolute-error-serving-20261006-v1/report.md) reuses the selected saved model without retraining. Edit [the 15-field synthetic request](examples/king-research-request.json) and run the command below on this workstation. The example returns **$553,846.97** in historical 2015 USD terms; it is not a current-market estimate or a certified 90-day valuation. The private model is not committed to Git.

  ```powershell
  $env:PYTHONPATH = (Resolve-Path -LiteralPath 'src').Path
  & 'data/raw/legacy-replay/.venv/Scripts/python.exe' -m scripts.king_research_predict --bundle data/raw/king-benchmark/king-absolute-error-serving-20261006-v1 --manifest-sha256 50ca467e61a52752e5ff9082297eeff1b294ef761aec383c8c7d2537c027941d --request examples/king-research-request.json
  ```

- The form's **Predict + record** action is the preferred prospective capture
  path. For automation or recovery without the form, the lower-level CLI can
  create a private receipt. Replace the opaque enrollment reference for each
  property; do not put an address, parcel number or owner name in it. The
  receipt retains the exact validated request under `data/raw/`, which is
  excluded from Git and access restricted. Terminal output omits those
  property inputs.

  ```powershell
  $env:PYTHONPATH = "$(Resolve-Path -LiteralPath '.');$(Resolve-Path -LiteralPath 'src')"
  & 'data/raw/legacy-replay/.venv/Scripts/python.exe' -m scripts.capture_king_prediction --bundle data/raw/king-benchmark/king-absolute-error-serving-20261006-v1 --manifest-sha256 50ca467e61a52752e5ff9082297eeff1b294ef761aec383c8c7d2537c027941d --request examples/king-research-request.json --enrollment-reference demo-20261005
  ```

  This lower-level command creates only the private receipt. It uses an
  untrusted workstation clock, and the local owner can still modify or delete
  it. Use the form for the normal one-action receipt-and-commitment workflow.
  A matured qualifying sale is still required before any captured prediction
  can contribute to prospective evaluation; G-US remains pending.

  Receipt format v2 includes a private random nonce and retains the exact raw
  JSON only inside the ignored, access-restricted receipt. If an older receipt
  was created with the lower-level CLI, prepare its public commitment without
  publishing the property inputs, price, request hashes, response hash,
  receipt ID or local prediction time by creating an output directory under
  `runs/` and running:

  ```powershell
  New-Item -ItemType Directory -Force runs/king-prospective-commitments-v1 | Out-Null
  & '.venv/Scripts/python.exe' -m scripts.prepare_king_receipt_commitment --receipt data/raw/king/prospective-predictions/<private-receipt>.json --output-dir runs/king-prospective-commitments-v1
  ```

  Commit and push the resulting JSON before outcomes are inspected. The Git
  artifact commits the private receipt bytes, but it still does not authenticate
  the workstation clock, prove that an outcome was unknown, or certify accuracy.

- [King historical validation report](runs/king-historical-20261004-v1/report.md) records a fixed two-model comparison on 2,228 sale-date validation rows: XGBoost 8.90% MdAPE and 55.25% within 10%, versus ZIP-code median 21.20% and 25.18%. A separate [later-period research check](runs/king-later-2015-v1/report.md) scored the frozen model on 4,752 March-May 2015 sales: 10.52% MdAPE and 47.94% within 10%, versus 20.00% and 25.38% for the ZIP median. The source lacks verified pre-sale feature availability, so neither result is a current or 90-day valuation claim.
- [Indiana 2024-to-2025 research report](runs/indiana-sdf-20261004-v1/report.md) records 71,054 later sales scored in 24.46 seconds: the county/ZIP median achieved 28.68% MdAPE, while a fixed XGBoost model using the same county, ZIP and acreage information reached 30.79%. The simpler reference remains stronger on typical error; neither is a current-home valuation.
- [Indiana assessment-snapshot diagnostic](runs/indiana-assessment-diagnostic-v1/report.md) compares the exact same 71,054 development sales with two fixed tree models. Adding assessed land/improvement values and neighborhood code reduced MdAPE from 30.79% to 15.19% in a 36.32-second full run. The fields' availability 90 days before sale is unknown, so this is not a deployable predictor.
- [Indiana post-hoc slice report](runs/indiana-assessment-diagnostic-v1/slice_report.md) shows the gain across 56 sufficiently sized counties but 51.62% median error for sales in the lowest realised-price band. This is development error analysis, not a current-home or 90-day valuation result.
- [Indiana targeted source review](runs/indiana-assessment-diagnostic-v1/audit_source_report.md) selected 200 transactions and inspected the first 20 extreme low-price records. Ten have source notes indicating nonmarket consideration or invalidity; none of the 20 has a final arm's-length determination. [ADR 0094](decisions/0094-indiana-assessment-asof-no-go.md) blocks the assessed-value challenger from 90-day or current serving until historical availability and label quality are established.
- [migration_report.md](migration_report.md) records recovered and missing legacy inputs, the replay outcome, and the hardware audit.
- [U0 legacy replay report](runs/u0-legacy-replay-20260928T145000Z/report.md) records the original split, repeatability, archived-score mismatch and verification evidence.
- [requirements.yaml](requirements.yaml) tracks requirement IDs and evidence status.
- [next_action.md](next_action.md) gives the current runnable task and blockers.

Use Python 3.11.6 for the U0 smoke package. Raw source files, row-level predictions, derived data and model checkpoints stay outside Git. The application, real-world US evaluation and international stages remain gated by the supplied specification.
