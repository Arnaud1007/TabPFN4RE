# ADR 0016: Synthetic split-conformal interval contract

Date: 2026-09-28

Owner: project implementation

Affected requirements: US19, US22, US23, US24

Affected protocol: synthetic US 90-day OFF engineering only; no G-US or U5
certification protocol is changed.

## Question and evidence

The current point-error engine counts failures and abstentions, but cannot
produce or evaluate a prediction interval. The specification requires 80% and
90% intervals for a frozen point predictor, using absolute log-price
calibration residuals and the one-based rank
`ceil((n + 1) * (1 - alpha))`. This rank differs from an ordinary percentile,
especially for small cohorts. The [conformal prediction tutorial](https://arxiv.org/abs/2107.07511)
motivates separate calibration under exchangeability; the
[conformalized quantile regression paper](https://arxiv.org/abs/1905.03222)
motivates a later adaptive-width comparison. Neither establishes coverage in
this project's shifted housing markets.

## Decision

Keep the point-metric implementation unchanged. Add a separate synthetic
calibration module with a pure finite-sample rank helper and an immutable
fitted log-residual calibrator. The pure helper handles small `n` for T09 and
fails explicitly if the required rank exceeds the number of residuals. The
fitted overall calibrator requires at least 1,000 valid, successful, disjoint
calibration predictions. A future separately fitted local calibrator must
apply the specified 200-row minimum under its own frozen policy.

The calibration plan identifies training, calibration and reserved evaluation
rows without overlap, a frozen predictor identity and chronological cutoffs.
Calibration uses saved point predictions and matured labels only. Every
declared successful calibration row must be accounted for. A future source
pipeline must independently freeze the entire eligible calibration population
and report calibration prediction failures before selecting the successful
rows passed here. The predictor was fitted before calibration origins and
is not refitted after calibration. Synthetic rows use the registered 90-day
close-origin rule. A later real source must supply its own date and publication
semantics before this workflow can support a release.

The interval constructor uses exact multiplicative residual factors, whose
ordering equals the ordering of absolute log residuals. It converts rational
endpoints to Decimal with outward rounding, checks positive finite endpoints
and 80%-within-90% nesting, and rejects an incompatible predictor identity.
Bounds outside the numeric representation budget fail explicitly; an upstream
service must count that request as a failed estimate. A separate scorer retains
failures and abstentions in the service-coverage denominator and reports
empirical interval coverage and relative width on successful estimates. It never
recalibrates from evaluation outcomes.

## Interpretation and promotion

Synthetic arithmetic and guard tests may verify the code; they cannot prove
calibration on future transactions. Ordinary split-conformal marginal
coverage relies on exchangeability, which may fail under geographic or
temporal housing shifts. A release still needs a disjoint, time-valid
calibration cohort, at least 1,000 real labels, the locked 12-month test,
overall and subgroup coverage, width checks, uncertainty estimates and a
frozen bundle. The current in-memory frozen dataclass is not a trusted signed
release artifact; real deployment also needs a hashed compatible model,
preprocessor, feature snapshot and calibration bundle. U5, US19 acceptance
and G-US remain pending until those files
contain actual eligible transaction results.
