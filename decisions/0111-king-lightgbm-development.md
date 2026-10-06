# ADR 0111: One bounded King LightGBM development candidate

**Status:** Accepted for implementation; real run not opened by this change
**Date:** 2026-10-06
**Owner:** Arnaud

## Context

The retrospective King County development champion is the fixed XGBoost
log-price absolute-error candidate. Its pooled development MdAPE is 8.27%, so
it does not meet the proposed 5% US release requirement. LightGBM is a mandatory
US candidate under US14, but an unconstrained search would delay the first useful
comparison and increase selection bias.

The King source remains research-only. Historical publication timing, attribute
vintages, arm's-length and single-property label semantics, and commercial-use
rights are unresolved. No King result can certify the 90-day product or pass
G-US.

## Decision

Run at most one LightGBM 4.7.0 configuration on the existing four frozen
November 2014 through February 2015 development windows. Use the incumbent's 14
numeric fields plus training-only ZIP one-hot encoding, train on log price, and
exponentiate predictions. The exact parameters and runtime are code and lock
artifacts; there is no search, early stopping, retry, refit, ensemble, or access
to March-May labels.

The runner must:

- verify the committed incumbent manifest, predictions, split, source, feature
  policy, experiment lock, and runtime before reading source labels;
- parse only rows with a date prefix before March 2015;
- fit exactly four models with a 120-second measured per-fit rejection cap and
  a 300-second measured whole-run rejection cap;
- store native LightGBM text boosters plus each window's exact ordered feature
  names and training-only ZIP vocabulary; reload every staged booster and
  reproduce its validation predictions from those persisted artifacts within
  `rtol=1e-12` and an absolute tolerance of `0.000001` USD before marking the
  run complete;
- write atomically under the private ACL-protected King benchmark directory;
- retain the incumbent unless LightGBM improves MdAPE in at least three windows,
  reduces pooled MdAPE by at least 2% relative, loses no more than 0.5 percentage
  points of within-10 accuracy, and adds no more than 0.5 percentage points to
  P90 APE.
  The challenger must also keep absolute median signed percentage error at or
  below the product threshold of 1%.

These caps reject an over-budget completed fit; they do not claim to interrupt a
hung native fit. The experiment must always record `promotion_eligible=false`
and `g_us_gate=PENDING`, even if it passes the development screen.

## Consequences

This creates a fast, falsifiable comparison against the strongest current King
candidate while preserving the frozen development protocol. A positive screen
would justify later protocol work; it would not create a deployable release.
The existing XGBoost bundle remains the only local research prediction bundle
until a separately reviewed decision changes that status.

The dependency lock supports a same-device, same-installed-build development
replay. It is not a cross-platform binary environment lock: wheel identity,
OpenMP implementation and every transitive package are not pinned here.
