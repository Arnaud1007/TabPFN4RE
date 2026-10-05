# King comparable residual development screen

Date: 2026-10-06  
Protocol: `king_exploratory_partial_comparable_residual_screen_v1`  
Status: execution passed; challenger **rejected**; G-US **PENDING**

## Result

One frozen comparable residual correction was evaluated on the same 5,108
November 2014 through February 2015 rolling development sales as the incumbent.
Comparable residuals were generated with chronological monthly out of fold
models, and candidate labels were always earlier than the subject window.

| Pooled metric | Fixed XGBoost | Comparable residual |
| --- | ---: | ---: |
| MdAPE | **8.56%** | 9.10% |
| Within 10% | **56.25%** | 54.05% |
| P90 APE | **26.86%** | 27.71% |
| Median signed error | -1.35% | -0.78% |

The challenger improved MdAPE in **0 of 4** windows and was 6.29% worse
relative on pooled MdAPE. The fixed XGBoost remains the development screening
candidate. This comparable configuration should not receive further tuning
without a new error mechanism.

## Integrity evidence

- Exact rolling membership matched the frozen split hash `47571792…`.
- March-May prices were neither parsed nor scored.
- All 5,108 rows received finite positive predictions; all had at least three
  retrieved comparables under the frozen radius policy.
- Chronological residual fold memberships, candidate indexes, model files,
  predictions and configuration are hash bound in the private manifest.
- Ten focused tests passed with 91% runner branch coverage. Ruff and code,
  Python, security and ML reviews passed.

## Limits

The source cannot identify duplicate economic transfers across different
property IDs and lacks row publication times and historical feature vintages.
This is therefore a partial exploratory screen: `us10_satisfied=false` and
`promotion_eligible=false`. It cannot establish a 90-day origin, current King
County accuracy, product readiness or G-US.
