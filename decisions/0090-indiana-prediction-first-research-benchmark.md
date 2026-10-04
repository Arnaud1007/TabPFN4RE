# ADR 0090: One fast Indiana retrospective prediction comparison

Date: 2026-10-04
Owner: Arnaud
Status: adopted before scoring 2025 labels
Protocol: `indiana_sdf_2024_2025_retrospective_research_v1`

## Decision

Run one fixed, research-only Indiana comparison now. Train on eligible 2024
sale disclosures and evaluate all eligible 2025 disclosures. Compare a
county/property-ZIP median with a fixed 180-tree XGBoost log-price model.
Use only county ID, property ZIP and acreage as raw predictors. Score MdAPE,
within-10%, P90 APE and signed bias from saved private row-level predictions.
Record the full eligibility funnel, runtime, source hashes and split membership.
The archive stores money as integer hundredths (`12.2`) and acreage as integer
ten-thousandths (`8.4`); decode those source units before modelling or scoring.
Reject a decimal-formatted value in these integer fields rather than guessing
whether it has already been converted.

The source metadata defines `Unique_Sales_ID` as the economic transaction
group; several `SDF_ID` forms may share it. Require exactly one disclosure row,
one form and one parcel row per economic sale. Require positive consideration,
one declared parcel, residential status, valuable consideration, no indicated
special transfer, no personal-property amount or relationship discount,
property class 510–515, an improvement and a property ZIP. The official 2025
class manual identifies 510–515 as one-family classes. Keep `A3_Land` diagnostic:
most one-family parcel rows have both `A3_Land=Y` and `A4_Improvement=Y`, so
interpreting `A3_Land=Y` as vacant would discard most houses.

The fixed XGBoost configuration is 180 hist trees, depth 5, learning rate
0.08, minimum child weight 20, subsample 0.8, column sample 0.8, four jobs,
seed 42 and squared-error loss on log price. ZIP/category vocabulary fits on
2024 rows only. The median baseline requires 20 past sales in a county/ZIP,
then backs off to county and statewide medians.

## Evidence and limits

The unchanged official ZIPs are pinned at
`a208f5b7230c0e5a0a5b74217a8b37e7d175e12cce59f122ffe2369a548bf6bd`
(2024) and
`f574f75604c953a1c0e498550ea05a20ebf705e8dfaca9aa1090d7a358ee4e12`
(2025). A read-only parser check found 65,490 and 71,054 eligible rows,
respectively, under this rule. These counts are parser observations, not an
audited source-quality conclusion. The publisher says prior-year data can be
revised; the downloaded files do not reconstruct what was available before
each sale. The source describes research use, while commercial/redistribution
rights remain unresolved. This run cannot certify a 90-day origin, present-day
valuation, G-US or a deployment release. The required 200-record manual source
audit has not occurred.

## Alternatives and next gate

Continuing a broad search across Cook, NYC and Florida before another score
delays prediction feedback. The already usable historical King predictor
remains available. This Indiana run adds a larger and newer transaction
comparison with a narrow, explicit feature set. If identity or price scope
fails review, retain the result as exploratory and correct the source rule
before any certification. Do not tune repeatedly on this 2025 cohort and call
it untouched. A separate as-of source and future outcomes are required for
the US release gate.

Primary source notes: [STATS Indiana description](https://www.stats.indiana.edu/about/sdf.asp),
[official downloads](https://www.stats.indiana.edu/topic/sdf.asp), and
[DLGF property-class manual](https://www.in.gov/dlgf/files/Property-Tax-Management-System-Code-List-Manual-250610.pdf).
