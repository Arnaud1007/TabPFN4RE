# King historical interval checkpoint

Date: 2026-10-05  
Protocol: `king_historical_intervals_v1`  
Status: interval coverage passed; width utility gate **FAILED**; G-US **PENDING**

## Result

The fixed King XGBoost predictor was calibrated on 1,875 March 2015 saved
predictions and evaluated on 2,877 April-May 2015 saved predictions. This path
required no model retraining.

| Metric | Observed | Required | Result |
| --- | ---: | ---: | --- |
| 80% empirical coverage | 78.24% | 78%-82% | Pass |
| 90% empirical coverage | 88.53% | 88%-92% | Pass |
| Mean 90% relative width | 54.45% | <=40% | **Fail** |
| P90 90% relative width | 64.55% | <=70% | Pass |
| Nested intervals | 2,877 / 2,877 | 100% | Pass |

The average interval is too wide for the predeclared utility requirement. The
interval configuration is rejected and will not be attached to the prediction
interface. No tuning will use the consumed April-May evaluation labels.

## Evidence and verification

- The runner pins the saved manifest and prediction hashes, exact monthly row
  counts, date boundaries, checkpoint, source snapshot and split identity.
- The predictor was frozen before the March calibration period.
- 20 interval and conformal tests passed; runner branch coverage was 80%.
- Ruff format/lint and code, Python, security and TDD reviews passed.
- Private row-level intervals remain under ignored `data/raw/king-benchmark/`.

## Limits

March-May outcomes had already been opened in earlier retrospective research.
This evidence therefore cannot restore an untouched test claim. The data also
does not establish a certified 90-day prediction origin, source availability,
arm's-length scope or product-use rights. G-US remains pending.
