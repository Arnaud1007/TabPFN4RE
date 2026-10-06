# King three-field source-row ablation

Date: 2026-10-06  
Protocol: `king_three_field_feature_family_development_v1`  
Status: development challenger **REJECTED**; product promotion ineligible; G-US **PENDING**

## Result

One predeclared feature family containing `yr_renovated`, `sqft_living15`, and
`sqft_lot15` was added to the frozen log absolute-error candidate. Exactly four
models were fitted on the unchanged November 2014 through February 2015 rolling
windows. The incumbent predictions were hash verified and reused.

| Pooled metric (5,108 sales) | Incumbent | Three-field challenger |
| --- | ---: | ---: |
| MdAPE | **8.2750%** | 8.3664% |
| Within 10% | 57.341% | **57.498%** |
| P90 APE | 26.950% | **26.756%** |
| Median signed error | **-0.808%** | -0.937% |
| MAE | $63,246 | **$62,749** |

The challenger improved window MdAPE in only **1 of 4** windows and increased
pooled MdAPE by 1.10% relative. It therefore fails both primary adoption
conditions: improvement in at least three windows and at least a 2% relative
pooled MdAPE reduction. The small improvements in within-10 accuracy, P90 APE,
and MAE do not override those predeclared conditions. Keep the incumbent and do
not tune these fields individually on the same windows.

## Integrity and timing

- The runner parsed 16,861 source rows before March and selected 16,849 eligible
  rows after the existing future-year-built quarantine.
- March through May prices were never parsed or scored.
- Six `yr_renovated` values later than their row sale year were replaced with
  XGBoost missing values. Source zero values were retained.
- The three fields were tested jointly; no individual variants were run.
- Source, split, incumbent manifest, incumbent predictions, configuration,
  checkpoints, predictions, and scorecards are bound by SHA-256 identities in
  `manifest.json`.
- The bounded run completed in **22.94 seconds**, within its two-minute fitting
  and five-minute end-to-end caps.

The executed experiment command was:

```powershell
$env:PYTHONPATH='.;src'
py -3.11 scripts/run_king_feature_family_development.py --source data/raw/openml-king-42092/house_sales.arff --incumbent-predictions data/raw/king-benchmark/king-log-absolute-error-20261006-v1/predictions.csv --output data/raw/king-benchmark/king-three-field-ablation-20261006-v1
```

The focused branch-coverage commands were:

```powershell
$env:PYTHONPATH='.;src'
py -3.11 -m coverage erase
py -3.11 -m coverage run --branch -m unittest tests.test_king_feature_family_development -q
py -3.11 -m coverage report -m scripts/run_king_feature_family_development.py
```

Thirteen tests and three subtests passed. The Windows symlink test was skipped
because this account cannot create a test symlink. The production path still
rejects detected reparse points, and the focused branch-aware coverage
measurement was 85%.

## Limits

This is retrospective source-row development evidence. Historical feature
vintages, publication timing, arm's-length and single-property eligibility, and
commercial-use rights remain unresolved. The challenger is rejected,
`promotion_eligible=false`, no serving bundle changes, and G-US remains
PENDING.
