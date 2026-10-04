# Twelve-input Ames prediction checkpoint

Date: 2026-10-04. Private run ID: `manual12-20261004-v1`.
Code commit: `104d571e576893f6d9005c76ee4fd6b24bcb6d79` (clean tree).
Evidence class: **historical Ames development only**. U0 **PENDING** and
G-US **PENDING**. Protocol: `ames_manual12_prototype_v1`.

## Result

The fixed 12-field profile in [ADR 0089](../../decisions/0089-manual12-ames-prototype.md)
was trained and scored on the same 1,168 development sales and five folds as
the [75-field checkpoint](../ames-dev-prototype-20261004-v1/report.md). The
split SHA-256 matches exactly:
`3f5e0f96e2c5beea3da436a780acda8c9e244c3260b08645a4c84490f6e3db6c`.
The saved private predictions for both profiles have identical row IDs, folds
and actual prices; all 2,336 row/model pairs were compared. The guarded loader
skipped the 292 reserved holdout rows before parsing their sale prices.

| Development metric | Median baseline | 12-field XGBoost | 75-field XGBoost |
| --- | ---: | ---: | ---: |
| Predictions | 1,168 | 1,168 | 1,168 |
| Median absolute percentage error | 24.83% | **6.81%** | 5.64% |
| Within 10% of sale price | 21.32% | **66.78%** | 71.32% |
| P90 absolute percentage error | 60.22% | 19.76% | 18.41% |
| Median signed percentage error | -0.003% | +0.363% | -0.389% |
| Mean absolute error | $54,591 | $17,224 | $15,497 |

The 12-field profile gives up 1.17 percentage points of MdAPE and 4.54
percentage points of within-10% accuracy relative to the 75-field profile.
These are descriptive development comparisons; this cohort was used in
prototype design and does not provide an independent performance claim.
The [manual scorecards](scorecards.json) and
[full-profile scorecards](../ames-dev-prototype-20261004-v1/scorecards.json)
contain the exact values. There is no calibrated prediction interval.

The recorded 12-field run took **2.923 seconds** end to end, with **0.642
seconds** spent on five XGBoost fits and validation predictions. The earlier
75-field run took 4.729 and 1.929 seconds, respectively. These are single
local run measurements, not a latency guarantee.

## Prediction command

The saved [synthetic request](../../examples/ames-manual12-request.json) has
12 editable fields and produces a point estimate of **$147,843.96875** in
[example_prediction.json](example_prediction.json). It is not a real property
or an accuracy observation. `schema_supported` means the request passed this
prototype's schema checks; it does not establish market coverage.

From the repository root in PowerShell, on this workstation:

```powershell
$env:PYTHONPATH = (Resolve-Path -LiteralPath 'src').Path
& 'data/raw/legacy-replay/.venv/Scripts/python.exe' -m scripts.ames_dev_prototype predict --bundle data/raw/ames-prototype/manual12-20261004-v1 --request examples/ames-manual12-request.json --bundle-sha256 1505ab1806202b9ca9626bbe5c92c4ef4f7393ef90680994ba8113b0f392a4f4
```

The private bundle is intentionally absent from Git. A fresh clone must
obtain the pinned source and recovered holdout membership, create its own
Python 3.11 environment from `locks/ames-prototype-requirements.txt`, train
with `--profile manual12` and use its new bundle path and digest. From the
project root, after setting `PYTHONPATH` as above, the training command is:

```powershell
& 'data/raw/ames-prototype/.venv/Scripts/python.exe' -m scripts.ames_dev_prototype train-evaluate --source data/raw/openml/house_prices-42165.arff --holdout data/legacy/holdout_ids.csv --output data/raw/ames-prototype/my-manual12-run --profile manual12
$bundleSha = (Get-FileHash -LiteralPath 'data/raw/ames-prototype/my-manual12-run/bundle.json' -Algorithm SHA256).Hash.ToLowerInvariant()
& 'data/raw/ames-prototype/.venv/Scripts/python.exe' -m scripts.ames_dev_prototype predict --bundle data/raw/ames-prototype/my-manual12-run --request examples/ames-manual12-request.json --bundle-sha256 $bundleSha
```

The digest is meaningful for a bundle produced by the verified local training
run; copying a digest from an untrusted bundle does not establish provenance.

`GrLivArea`, `TotalBsmtSF` and `LotArea` are square feet; rooms, baths,
fireplaces and garage capacity are counts. `OverallQual` and `OverallCond`
use the Ames 1-10 ratings. `Neighborhood` uses Ames-specific codes such as
`NAmes`. The command requires the exact 12 field names; optional unknown
values may be `null`, while area, quality and neighborhood are required.
Invalid physical values are rejected. The model was trained on historical
Ames sales, so a present-day house elsewhere is outside its validated scope.

## Integrity and next action

The [run manifest](manifest.json) records source, holdout, split, policy,
configuration, environment and checkpoint hashes. Every listed private
artifact matches its hash. The private model, preprocessing snapshot, split
and row-level predictions remain under ignored
`data/raw/ames-prototype/manual12-20261004-v1/`.

The [test gate](test_gate.json) records executable checks and logs. This
checkpoint demonstrates fast training and a smaller input contract; it does
not meet a 90-day prediction-origin, modern multi-market or prospective US
gate. Continue real transaction source qualification and as-of evaluation as
tracked in [next_action.md](../../next_action.md).

Actual checks: 1,296 main-suite tests passed with zero skips and 92% package
coverage; nine focused unit tests and six isolated-environment integration
tests passed. Ruff check/format and the pinned dependency audit passed. The
old 75-field bundle still returned its recorded synthetic example prediction
under the new code. The full-suite log is private at
`data/raw/ames-prototype/manual12-checks-20261004/full_suite_no_skip.log`;
its SHA-256 is
`a245d4d7d88d0f1c137ba9a4db4f51d6cc9e9f1286529c253a2b20456f173731`.
The gate links each public check log with its exit code, duration and hash.
