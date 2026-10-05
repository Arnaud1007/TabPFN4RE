# King rolling recency development checkpoint

Date: 2026-10-05  
Protocol: `king_rolling_development_v1`  
Status: verified historical development evidence; G-US **PENDING**

## Result

One predeclared 180-day recency-weighted XGBoost challenger was compared with
the fixed XGBoost incumbent and ZIP-code median on four expanding monthly
windows from November 2014 through February 2015. Every validation sale was
strictly later than its training cohort. The March-May later cohort was not
scored.

| Pooled metric (5,108 sales) | ZIP median | Fixed XGBoost | Recency XGBoost |
| --- | ---: | ---: | ---: |
| MdAPE | 20.98% | **8.56%** | 8.63% |
| Within 10% | 25.74% | 56.25% | 56.40% |
| P90 APE | 56.90% | **26.86%** | 26.89% |
| Median signed error | 0.35% | -1.35% | -1.50% |

The recency challenger improved MdAPE in only **1 of 4**
windows and its pooled MdAPE was **0.81% worse relative**. It failed the
predeclared promotion rule. The fixed XGBoost model remains champion. No further
recency tuning is justified by this result.

## Evidence and verification

- All 5,108 pooled evaluation rows received all three predictions.
- The manifest binds the code commit, pinned source, dependency lock, feature
  policy, configuration, every window membership, eight model checkpoints and
  row-level prediction artifact.
- Private row-level predictions and model checkpoints remain under ignored
  `data/raw/king-benchmark/`.
- 14 related tests passed; the new runner achieved 85% branch coverage.
- Ruff format/lint and code, Python, and security reviews passed.

## Limits

This source does not establish 90-day feature availability, arm's-length and
single-property label status, or cleared product-use rights. The score is
retrospective sale-date development evidence, not current valuation accuracy.
It cannot pass G-US.
