# King County historical validation checkpoint

Date: 2026-10-04. Status: **implemented and verified for historical research**.
Requirements informed: US05, US11, US12, US14. U0 and G-US remain **PENDING**.
This run is not a release milestone or an accepted US valuation model.

## Purpose and scope

Provide a quick, reproducible comparison on real historical sale rows while
the official US source audit continues. The source is OpenML `house_sales`
version 2 ([source card](../../data/source_cards/openml_king_42092.yaml)). Its
21,613 rows span May 2014 to May 2015. Twelve rows with `yr_built` after their
sale year were quarantined by a rule fixed before scoring. The frozen
[split manifest](split_manifest.json) assigns 14,621 sales through December
2014 to training, 2,228 January–February 2015 sales to validation, and 4,752
March–May 2015 sales to a later cohort. The runner computed no score for that
later cohort. It does parse the full source, including later prices, when it
verifies the source and split, so those labels are **not process-inaccessible**.

The comparison used a ZIP-code median trained on the earlier rows and a single
fixed XGBoost log-price configuration. Both predicted the same validation rows.
The candidate rule selected XGBoost using these validation results, so the
selected score is development evidence, not an independent final estimate.

## Observed validation results

Values below are generated from saved private row-level predictions; the
aggregate [summary](validation_summary.json) and [run manifest](validation_manifest.json)
are committed. Percentages use actual sale price as the denominator.

| Metric | ZIP-code median | XGBoost |
| --- | ---: | ---: |
| Median absolute percentage error | 21.20% | **8.90%** |
| Within 10% | 25.18% | **55.25%** |
| P90 absolute percentage error | 55.94% | **29.28%** |
| Median signed percentage error | -0.01% | -2.46% |
| Successful estimates | 2,228 / 2,228 | 2,228 / 2,228 |

The full validation command took 6.46 seconds on this workstation, including
source parsing, fitting, scoring and private artifact writing. It is not an
isolated training-time benchmark. The selected checkpoint SHA-256 is
`cead625a3b87d73f46fdf740bfb366b9ff3b17d52434011a63e0ca91849f0033`.
The code commit was `3df798b6689a2aa2f6732cb93b065ad5493eda41`.

## Verification and limitations

- Nine focused tests and Ruff lint/format checks passed. The dependency audit
  found no known vulnerabilities in the pinned prototype requirements.
- The private output manifest's six file hashes matched. Recomputing MdAPE,
  within-10%, P90 error and bias from all 2,228 saved rows matched the saved
  scorecards. Reloading the saved XGBoost model reproduced all validation
  predictions with maximum observed difference of $0.00.
- A full project test-suite result is in [test_gate.json](test_gate.json).
- The uploader's sale-date field is not a verified pre-contract valuation
  origin. First availability and historical vintages of property attributes,
  arm's-length status, exact transfer scope and original source rights are
  unresolved. The dataset supplies only about one year of dates. No interval
  calibration or prospective evidence exists. The source remains private
  research only under its source card.
- XGBoost's 8.90% development MdAPE does not meet the proposed 5% US gate
  threshold. Its 55.25% within-10% rate also falls short of the proposed 85%
  threshold. These gate comparisons are descriptive; this cohort cannot
  certify or fail G-US because its information timing and coverage differ.

## Reproduction

From the project root, after obtaining and hash-checking the source named in
the source card, use a **new** private run directory:

```powershell
$env:PYTHONPATH = (Resolve-Path -LiteralPath 'src').Path
& 'data/raw/legacy-replay/.venv/Scripts/python.exe' -m scripts.run_king_historical_benchmark --source data/raw/openml-king-42092/house_sales.arff --split-manifest runs/king-historical-20261004-v1/split_manifest.json --output data/raw/king-benchmark/my-unique-validation-run
```

The exact original output is Git-ignored at
`data/raw/king-benchmark/king-validation-20261004-v1/`. It contains row-level
validation predictions, model files, the scorecards and their hashes. The
runner requires a clean committed tree and refuses an existing output path.

## Next action

Keep the usable Ames entry form available for local historical examples.
Qualify an official US transaction source's close-date, first-publication,
attribute-vintage, transfer-scope and rights rules before claiming a current
90-day prediction result. Do not score the King March–May cohort as a shortcut
to G-US; a certification evaluator needs genuinely isolated labels and an
as-of feature source.
