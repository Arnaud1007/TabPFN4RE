# King log absolute-error development screen

Date: 2026-10-06  
Protocol: `king_log_absolute_error_development_screen_v1`  
Status: development screen **PASS**; product promotion ineligible; G-US **PENDING**

## Result

Exactly four XGBoost challengers were trained on the frozen November 2014
through February 2015 rolling windows. Every parameter and input matched the
incumbent; only the log-price objective changed from squared error to absolute
error. Frozen incumbent predictions were reused rather than retrained.

| Pooled metric (5,108 sales) | Squared error | Absolute error |
| --- | ---: | ---: |
| MdAPE | 8.56% | **8.27%** |
| Within 10% | 56.25% | **57.34%** |
| P90 APE | **26.86%** | 26.95% |
| Median signed error | -1.35% | **-0.81%** |
| MAE | $63,740 | **$63,246** |

The challenger reduced pooled MdAPE by **3.29% relative**, improved MdAPE in
all four windows, improved within-10 accuracy by 1.10 percentage points, and
kept P90 degradation to 0.09 percentage point. It passes the predeclared fast
development screen and becomes the preferred candidate for the next qualified
experiment.

## Integrity evidence

- Frozen incumbent manifest, predictions, split, configuration and feature
  policy are independently hash verified before labels or fitting.
- Bounded single-snapshot reads ensure the hashed bytes are the parsed bytes.
- March-May rows are counted from their `id,date` prefix only; their prices are
  neither parsed nor scored.
- Four challenger fits were performed with no search or extra variant.
- Eleven focused tests passed with 81% runner branch coverage. Ruff and code,
  Python, security and ML reviews passed.

## Limits

The result is retrospective sale-date development evidence. Historical
publication timing, feature vintages, arm's-length status, property scope and
commercial-use rights remain unresolved. The challenger is therefore not
attached to serving, `promotion_eligible=false`, and G-US remains pending. A
strong comparative claim requires qualified point-in-time data, dependence
aware uncertainty and a new untouched future cohort.
