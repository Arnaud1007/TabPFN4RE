# ADR 0100: King historical interval calibration

Status: accepted for retrospective research

Date: 2026-10-05

Owner: Arnaud

## Context

The saved King County predictor has point predictions but no calibrated
prediction intervals. Retraining would delay a usable result, while existing
saved predictions contain a disjoint calibration period and a later evaluation
period. The later evaluation labels have already been inspected, so they cannot
support certification or model selection.

## Decision

Calibrate fixed 80% and 90% split-conformal log-residual intervals on all 1,875
saved predictions from March 2015. Evaluate them once on all 2,877 saved
predictions from April and May 2015. The model was frozen before this later
period. Bind the source file and manifest to their recorded hashes, checkpoint,
source snapshot and split manifest. Require exact cohort membership, disjoint
row identifiers and nested intervals.

The descriptive targets are 78%-82% empirical coverage for the 80% interval,
88%-92% for the 90% interval, mean 90% relative width no greater than 40%, and
P90 width no greater than 70%. A failure is preserved and does not trigger
tuning against these consumed labels.

## Consequences

This produces a fast, reproducible reliability result without model training.
The result is historical research only because the March-May outcomes were
previously consumed and the underlying data does not establish the required
90-day origin or source availability. The split therefore measures empirical
retrospective coverage and cannot restore an untouched certification claim. It
cannot pass G-US or certify a current prediction service. Row-level outputs
remain under the ignored private data root; only aggregate evidence may enter
Git.
