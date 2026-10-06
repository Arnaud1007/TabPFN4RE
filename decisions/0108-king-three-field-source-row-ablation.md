# ADR 0108: King three-field source-row ablation

## Status

Accepted for one bounded development run.

## Decision

Test `yr_renovated`, `sqft_living15`, and `sqft_lot15` together as one feature family against the frozen log absolute-error incumbent on the exact four November 2014 through February 2015 development windows. No individual feature variants are permitted.

Retain source zero values for `yr_renovated`. Replace only values later than the row's sale year with XGBoost missing (`NaN`) and report the replacement count. Preserve the existing parser, base feature constants, objective, model parameters, memberships, and incumbent predictions.

The challenger passes the development screen only if it improves MdAPE in at least three windows, reduces pooled MdAPE by at least 2%, loses no more than 0.5 percentage points of within-10% accuracy, and adds no more than 0.5 percentage points to P90 APE.

## Boundaries

The run is retrospective source-row research. Feature vintages, publication timing, transaction eligibility, and commercial-use rights are unresolved. Therefore the result is never promotion eligible and cannot change G-US from PENDING. The run performs exactly four fits and may not parse or score March through May labels.

## Compute cap

Allow two minutes of model fitting and five minutes end to end on the declared local environment. Reuse the pinned source, frozen memberships, and frozen incumbent predictions. Do not reuse challenger checkpoints.
