# ADR 0009: Synthetic rolling-origin fold contract

Date: 2026-09-28

Owner: project implementation

Affected requirements: US11, US22, US23

Affected protocol: `us_synthetic_rolling_v1`; no legacy Ames or real-world certification split is changed.

## Alternatives and evidence

The existing Ames engineering split is not a forward-in-time test. A temporal fold can be built from outcome-free row IDs, property IDs and origins, with maturity dates supplied only for pre-cutoff candidate training rows. Supplying the entire labelled table to a splitter was rejected because it would expose reserved validation labels to the training process. A fixed embargo was rejected as a substitute for actual label availability.

Twelve synthetic tests cover half-open origin windows, label maturity at the cutoff, duplicate and reserved IDs, stable hashes across input order and timezone offsets, rolling reuse of a matured label, no matured training rows, and integration with the guarded OFF baseline. A Python review found that same-zone daylight-saving fallback comparisons could admit a future label. A RED regression reproduced it; UTC-normalized comparisons made it GREEN. Independent code and Python re-reviews approved this synthetic scope. The complete test gate is `runs/u3-synthetic-temporal-20260928T123500Z/`.

## Decision

`build_temporal_fold` derives training membership only from labels whose `available_at` is no later than the training cutoff. It rejects maturity metadata for reserved or unknown rows, enforces the registered synthetic horizon and requires at least one matured training row and one validation origin. All ordering and maturity comparisons use UTC instants. The split hash binds IDs, origins, training-side maturity, boundaries, membership and protocol ID.

This is a synthetic exact-timestamp protocol. Its `origin + 90 days` equality does not yet specify the source-local calendar-date rule for records without time, and Python date arithmetic can reset the `fold` bit for an ambiguous fallback hour. Such records require an explicit real-source date/origin policy before U3 certification. A caller must use the builder or validate any loaded fold manifest; directly constructing a `TemporalFold` is not a certification path.

## Promotion dependencies

Define the close-date and local-time conventions from audited sources. Persist real row IDs, property groups, origins, source cutoffs and split hashes. Add four quarterly rolling windows, training-history floors, a separate calibration cohort, a locked 12-month final cohort, unseen-property and geography tests with development-chosen buffers, and a crash-safe reserved-label ledger. No current source card proves enough historical availability or rights for those tests. U3 and G-US remain pending.
