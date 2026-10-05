# 0099 — King recency rolling development comparison

Date: 2026-10-05  
Status: accepted experiment protocol

## Decision

Run one bounded historical King County comparison across November 2014 through
February 2015. Each monthly validation window trains only on earlier sale dates.
Compare the ZIP median, the existing fixed log-price XGBoost configuration, and
the same XGBoost configuration fitted with exponential sample weights having a
180-day half-life.

The March–May 2015 later cohort remains outside this experiment. No parameter
search is authorized. The recency challenger is promoted only if it improves
MdAPE in at least three of four windows, reduces pooled MdAPE by at least 2%
relative, and degrades neither within-10 accuracy nor P90 APE by more than 0.5
percentage point.

## Reason

This is the shortest measured experiment that can test a plausible current
error mechanism, market drift, while preserving chronological development
evaluation and the existing model configuration. It is expected to finish in
seconds rather than launching a multi-family tuning programme.

## Limits

The source still lacks certified 90-day feature availability, arm's-length and
single-property label proof, and cleared product-use rights. Results are
retrospective sale-date development evidence. They cannot pass G-US or support
a current valuation claim.
