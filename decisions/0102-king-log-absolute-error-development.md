# ADR 0102: King log absolute-error development screen

## Status

Accepted for one bounded, private, retrospective development screen.

## Context

The fixed King XGBoost model remains the development champion. Its registered
configuration optimises squared error on log price, while the primary
development selection statistic is median absolute percentage error. A log
absolute-error objective is a cheap, specific hypothesis: reducing the
influence of large log residuals may improve typical proportional error. The
archived OpenML source does not establish historical publication times,
property-attribute vintages, arm's-length status, original-source commercial
rights, or a certified 90-day valuation origin. This experiment therefore
cannot promote a model or support a service claim.

## Decision

Reuse the exact November 2014 through February 2015 rolling membership and
incumbent predictions from `king-rolling-development-20261005-v1`. Verify the
committed rolling manifest by its pinned SHA-256, verify the private incumbent
prediction artifact against the hash recorded in that manifest, and then
verify every row identifier, date, window, observed price, and membership
order against the selectively parsed source.

Before reading any source label or fitting a model, reconstruct and verify the
frozen rolling model/window configuration hash and feature-policy hash. Verify
that the declared lock is the same lock bound by the frozen rolling manifest,
require Python 3.11.x, and reject exact NumPy or XGBoost version drift. This
makes the objective the only intended model-training change rather than merely
recording dependency differences afterward.

Read the frozen manifest and incumbent predictions as separate bounded regular
file snapshots. Reject symbolic links and non-regular or oversized inputs;
hash and parse the same in-memory bytes. The pinned source decoder likewise
uses one bounded, hash-verified snapshot. For each data row, inspect only the
`id,date,` prefix first. Full CSV and sale parsing occurs only for pre-March
rows, while the total 21,613-row count is still enforced.

The challenger changes exactly one model parameter:

```text
objective: reg:squarederror -> reg:absoluteerror
```

All other XGBoost parameters, feature encoding, expanding monthly training
sets, target transformation, and scoring rules remain fixed. Fit exactly one
challenger in each of the four development windows. Read sale prices only for
source rows before 1 March 2015. Do not refit the incumbent and do not parse or
score March through May labels.

The screen favours the challenger only when it improves at least three of four
windows, reduces pooled MdAPE by at least 2% relative, and degrades neither
within-10 accuracy nor P90 APE by more than 0.5 percentage point. This outcome
is named a `development_screening_candidate`; it is not an adoption or model
selection decision.

Write prediction rows, four challenger checkpoints, scorecards, and a run
manifest atomically below the private benchmark root. The manifest records the
actual Python, NumPy, and XGBoost versions, the complete resolved
configuration and its hash, source and membership hashes, the exact incumbent
prediction hash, and the four challenger checkpoint identities. The declared
requirements-file hash does not claim that the runtime was reconstructed from
that file.

## Evidence boundary

The result is development screening only and `promotion_eligible` is always
false. A favourable result can justify later evaluation with qualified
point-in-time data and a new untouched cohort. It cannot satisfy US11 through
US15, certify a 90-day origin, establish King County service, pass G-US, or
support a present-day accuracy or commercial-use claim.
