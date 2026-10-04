# 0092 — Indiana assessment-snapshot error slices

Date: 2026-10-05. Owner: project team. Status: accepted for development diagnosis.
Protocol: `indiana_sdf_snapshot_assessment_posthoc_slices_v1`.

## Decision

Inspect the already saved Indiana 2025 prediction rows without fitting another
model. Score all 71,054 eligible rows, five price bands defined by nearest-rank
cutoffs from 2024 training prices, assessment-value states (both positive, any
zero, missing), and counties with at least 200 rows. Report the number of
smaller counties and their total sales separately. Groups with fewer than 200
sales retain only their count; their metrics and paired comparison are
suppressed. Each scored slice uses the shared metric engine for the fixed
county/ZIP median, three-input XGBoost and
assessment-snapshot XGBoost. Also count paired homes where assessment XGBoost
has lower absolute dollar error than the three-input XGBoost.

This is a **post-hoc development diagnostic**: the 2025 cohort was consumed
before these slices were chosen. Comparisons describe error structure and
prioritise a data investigation; they do not select or promote a model, test a
new hypothesis independently, or satisfy the 90-day origin or G-US gate.

## Alternatives and evidence

The aggregate [assessment diagnostic](../runs/indiana-assessment-diagnostic-v1/report.md)
showed a large median-error gain but could hide county, price and missing-data
failures. A new model search would answer a different question and reuse the
consumed cohort for tuning. The source archives and private saved predictions
are hash-pinned; the diagnostic checks both before making an aggregate report.

## Constraints and adoption rule

Keep row IDs, sale prices and row-level predictions in ignored private
artifacts. The public JSON contains only aggregate scores and counts. Any
county below 200 rows remains in the overall denominator but receives no
county scorecard. Empty price bands remain visible with zero count. No slice
result can establish that assessment values were available before sale;
verify vintage and first publication separately before an as-of experiment.
Price bands use each sale's realised price, so they are retrospective error
diagnostics and cannot route a prediction before sale.

The next data task is selected from observed failures and source feasibility,
not from the lowest subgroup score alone. Future certification requires an
untouched period and a frozen policy.
