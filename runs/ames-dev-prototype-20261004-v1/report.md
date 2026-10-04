# Ames development-only prediction checkpoint

Date: 2026-10-04. Private run ID: `dev-only-20261004-v3`.
Code commit: `cd2f4221d0581a7a16c13d9d088d7130d5a79d31` (clean tree).
Evidence class: **historical Ames engineering prototype**. U0 **PENDING**;
G-US **PENDING**. Requirements touched: US02, US12, US14, US22, US23, US24.

## Objective and observed result

Produce a useful prediction result quickly without opening the legacy 292-row
holdout. The frozen OpenML 42165 ARFF (`10db9fe72ed693212a222e39981133ec1b3ee5090d7f2caf2461190a4ad51279`)
and saved holdout membership were checksum verified. The guarded loader skipped
all 292 reserved physical data rows before parsing their prices. One seeded
five-fold comparison scored 1,168 development rows once per model. Raw `Id`,
the target and recorded sale timing/type/condition fields were excluded. Each
fold fitted imputation and one-hot encoding on its training partition.

The following values come from [scorecards.json](scorecards.json), computed
from the private row-level predictions:

| Development metric | Fold median | XGBoost |
| --- | ---: | ---: |
| Predictions | 1,168 | 1,168 |
| Median absolute percentage error | 24.83% | 5.64% |
| Within 10% of sale price | 21.32% | 71.32% |
| P90 absolute percentage error | 60.22% | 18.41% |
| Median signed percentage error | -0.003% | -0.389% |
| Mean absolute error | $54,591 | $15,497 |

The XGBoost configuration was selected from these development results, then
fitted on all 1,168 development rows for the local prototype bundle. Its
reported score measures the fixed candidate on development folds. It is not an
independent estimate of the selection procedure, a test-set result or a
future-sale US result. There is no calibrated interval. The locked legacy
holdout remains unopened by this run.

The full run took **4.729 seconds** on the recorded local environment. The
five fold fits plus their validation predictions took 1.929 seconds for
XGBoost and 0.298 seconds for the median. These measured durations exclude
source acquisition and a fresh environment installation.

## Local serving demonstration

[example_prediction.json](example_prediction.json) records a prototype
estimate from the saved bundle and
[example request](../../examples/ames-prototype-request.json). The 75-field
request is a **synthetic** vector seeded from development-feature medians and
category modes, then adjusted for physical consistency. It is not copied from a source property record and includes no sale price
or ID. The area totals and conditional pool fields are internally consistent.
Its saved point estimate is **$145,196.03125**; `PoolQC` is intentionally
missing because the example has no pool. The `schema_supported` flag verifies
the input contract, not market or property support. This output checks the CLI
and bundle, not prediction accuracy.
The CLI reports unknown categorical values separately and requires the full
evaluated feature schema.

The SHA-256 of the trusted, committed [bundle metadata](bundle.json) is
`c4da912facd6025145b31725ad5e25918e3eb8fa95463e6a8205513f3208f121`.
The model uses native XGBoost JSON and a bounded JSON preprocessing snapshot.
The model file, preprocessing snapshot, split and row-level predictions remain
under ignored `data/raw/ames-prototype/dev-only-20261004-v3/`. The public
[manifest](manifest.json) retains their hashes without publishing them.

## Replay and checks

From the project root in PowerShell, with the local pinned ARFF present. The
second command replays the existing ignored bundle on this workstation; a
fresh clone must substitute its newly trained bundle path and verified digest:

```powershell
$env:PYTHONPATH = (Resolve-Path -LiteralPath 'src').Path
& 'data/raw/legacy-replay/.venv/Scripts/python.exe' -m scripts.ames_dev_prototype train-evaluate --source data/raw/openml/house_prices-42165.arff --holdout data/legacy/holdout_ids.csv --output data/raw/ames-prototype/a-new-unique-run
& 'data/raw/legacy-replay/.venv/Scripts/python.exe' -m scripts.ames_dev_prototype predict --bundle data/raw/ames-prototype/dev-only-20261004-v3 --request examples/ames-prototype-request.json --bundle-sha256 c4da912facd6025145b31725ad5e25918e3eb8fa95463e6a8205513f3208f121
```

Actual verification observations:

- Private manifest: `complete`, `dirty_tree: false`, code commit above; every
  listed output matched its SHA-256. Private predictions: 2,336 paired rows,
  no overlap with 292 reserved indices.
- Main suite: 1,294 tests passed, no skips, exit 0; package coverage 92%.
  Local log: `data/raw/ames-prototype/full_suite_20261004.log`, SHA-256
  `7102129f35ff3bd72325f5ae442b0586825c6d95c441ed7f91dd7260e566bcfb`.
- Prototype policy tests: 7 passed; isolated-environment integration tests:
  4 passed. Integration checked fold-only preprocessing, full development
  prediction coverage, six in-memory/native-bundle prediction pairs including
  missing fields, unknown-category parity, CLI/direct output identity, and
  physical consistency of the synthetic example.
- The executable [test gate](test_gate.json) records each check's command,
  exit code, duration and output hash. Ruff check and format check passed for all new Python files. The prototype
  requirements audit and the main environment audit found no known published
  vulnerabilities in the checked dependencies. Security, Python, code and ML
  reviews found no remaining high-severity prototype issue.

Initial private v1/v2 runs were development attempts made from a dirty tree;
they remain local and are not substituted for this clean run. The v1 joblib
serving path was rejected after security review. The first JSON serving test
exposed a missing-value parity difference; the implementation now matches the
training transform, and the integration test covers it.

## Limits and next action

This result is a historical Ames engineering benchmark with no 90-day
valuation origin, temporal test, calibrated uncertainty or modern multi-market
coverage. The current CLI requires 75 feature keys, so it is a runnable
prototype rather than a practical property-entry application. Continue U0
source qualification for real transaction labels and as-of histories. A
smaller-input model requires its own matched out-of-fold evaluation before its
scores can be presented beside this full-feature result. The exact next task
and unresolved US release blockers are in [next_action.md](../../next_action.md).
