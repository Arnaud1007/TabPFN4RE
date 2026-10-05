# ADR 0101: King comparable residual development experiment

## Status

Accepted for one bounded, private, retrospective exploratory screen.

## Context

The fixed King XGBoost model remains the development champion after the 180-day
recency challenger failed its adoption rule. US10 requires an auditable
comparable baseline and permits a residual correction in which strictly prior
observed comparable residuals adjust a base prediction. The archived OpenML
King source can support a fast sale-date screen, but it does not establish row
publication times, historical property-attribute vintages, arm's-length
status, commercial use rights, or a duplicate-economic-transfer key across
different property identifiers. Consequently this partial screen cannot
satisfy US10 and is never eligible for promotion.

## Decision

Use the exact November 2014 through February 2015 rolling membership frozen in
`runs/king-rolling-development-20261005-v1/manifest.json`. For every window,
fit the existing XGBoost configuration once on sales strictly before the
window. Candidate residuals are precomputed once with deterministic monthly
out-of-fold prediction: the model for a candidate sale uses only sales from
calendar months strictly before that candidate's sale month. The source reader
validates the complete pinned file but parses sale prices only for rows before
1 March 2015. March through May labels are neither parsed nor scored.

Candidates are prior sales in the preceding 12 months, from a different
property, with valid coordinates and positive living area. Only the latest
sale per candidate property remains. Search radii are 2, 10, and 30 kilometres;
the first radius with at least three candidates is used, with at most ten
neighbours. Ranking is target blind:

```text
distance_km
+ age_days / 365
+ abs(log(candidate_area / subject_area)) / 0.25
```

The candidate residual is `log(observed price / base prediction)`. The subject
base log prediction receives the weighted median residual, using
`1 / (1 + score)` weights. Fewer than three candidates produces the unchanged
base prediction and a `low_support` status.

The development screen favours the challenger only when it improves at
least three of four windows, reduces pooled MdAPE by at least 2% relative, and
degrades neither within-10 accuracy nor P90 APE by more than 0.5 percentage
point. Every row must receive a finite positive prediction through the
registered fallback. This is a screening outcome, not model selection or an
adoption decision.

The manifest records actual Python, NumPy, SciPy, and XGBoost versions. The
requirements-file digest is named `declared_lock_sha256`; it does not claim the
runtime was reconstructed from that lock. Membership is checked against the
prior manifest before fitting. Monthly residual fold membership and hashes are
persisted. The so-called challenger identities are explicitly run-artifact
identities rather than deployable checkpoint identities. Replaying the
challenger requires rebuilding each comparable index from the pinned source,
the chronological residual artifact, and the frozen configuration.

## Evidence boundary

This experiment is private, retrospective exploratory evidence. It is never
eligible for product promotion because duplicate-transfer reconciliation,
publication timing, and feature vintages are unverified. It cannot satisfy
US10, certify a 90-day origin, establish King County service, pass G-US, or
support any current accuracy claim. The March through May cohort remains
outside this experiment. A favourable screen would only justify a future
experiment with resolvable economic transfers, qualified point-in-time data,
and a new untouched cohort.
