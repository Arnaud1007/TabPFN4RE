# King absolute-error serving bundle

Date: 2026-10-06  
Protocol: `king_log_absolute_error_serving_refit_v1`  
Status: runnable historical research predictor; G-US **PENDING**

## Result

The selected log absolute-error XGBoost candidate was refitted once on 16,849
eligible King County sales before 1 March 2015. Staging parsed no March through
May labels. Building the model took about 14 seconds on this workstation,
including artifact validation and a real save/reload equivalence check.

The existing prediction CLI loaded the saved bundle and returned
**$553,846.97** for `examples/king-research-request.json`. The same prediction
service is used by the local form. The response declares median-like point
semantics, a 90-day conditional-sale target, its training and selection
periods, and `historical_research_only` status.

## Why this is faster

- Model selection was already completed on four rolling development windows.
- The build performs one fixed fit instead of another tuning search.
- Later reserved labels are neither parsed nor scored.
- Future predictions load the saved checkpoint and require no retraining.

The earlier development screen measured 8.27% MdAPE on 5,108 November 2014
through February 2015 rows, a 3.29% relative improvement over the frozen
squared-error candidate, with improvement in all four windows. Those metrics
describe selection evidence; they are not a score for this final refit.

## Integrity evidence

- Public and private bundle manifests have SHA-256
  `50ca467e61a52752e5ff9082297eeff1b294ef761aec383c8c7d2537c027941d`.
- The model checkpoint SHA-256 is
  `de9a7e8b1b6261a689070af200e4c4d1eb51a4fb5d77d8977341875bbf7d7357`.
- Reloaded predictions matched the in-memory model exactly on eight fixed
  training-only probes: maximum absolute and relative difference were zero.
- The builder recorded one fit, 16,849 training rows, 12 quarantined rows and
  zero March-May labels parsed or scored.
- Fifty-four focused tests passed with 80% combined branch coverage; Ruff and
  code, Python, security and ML reviews passed.

## Run

From the project root in PowerShell:

```powershell
$env:PYTHONPATH = "$(Resolve-Path '.');$(Resolve-Path 'src')"
& 'data/raw/legacy-replay/.venv/Scripts/python.exe' -m scripts.king_research_predict `
  --bundle 'data/raw/king-benchmark/king-absolute-error-serving-20261006-v1' `
  --manifest-sha256 '50ca467e61a52752e5ff9082297eeff1b294ef761aec383c8c7d2537c027941d' `
  --request 'examples/king-research-request.json'
```

## Limits

This model does not have a disjoint final-refit score. The source lacks proven
historical publication times, attribute vintages, arm's-length flags and
commercial-use clearance. The output is a 2015 historical research estimate,
not a current valuation or certified 90-day service. No G-US condition is
claimed as passed.
