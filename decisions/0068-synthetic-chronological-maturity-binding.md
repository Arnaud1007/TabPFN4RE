# ADR 0068: Bind calendar folds to training-side label maturity

Date: 2026-10-03
Owner: project implementation
Status: verified synthetic engineering; no real sale labels opened
Affected requirements: US11, US22, US23, US24
Protocol: `us_synthetic_chronological_plan_v1`

## Context and alternatives

The existing calendar schedule freezes four development quarters, calibration,
and a 12-month test using source-local dates. It identifies training candidates
without proving their labels were published by model-fit time. The older
synthetic splitter uses an exact 90-day UTC duration, which is unsuitable
for source-local 90-calendar-day origins across daylight-saving changes.

## Decision

The [chronological plan](../src/tabpfn4realestate/evaluation/chronological_plan.py)
rebuilds and verifies the calendar schedule and its per-row pinned time-zone
policy. It accepts close dates and first-availability metadata only for rows
before calibration. Calibration and final-test rows stay reserved. Each of four
development folds and the final pre-calibration fit has one explicit UTC
cutoff, included in the plan hash. The cutoff must precede the local start of
the relevant window in every declared source zone. Training admits a label
only when its availability instant is no later than that single cutoff.

Date-only availability is conservatively placed at the end of its source-local
day. Because close time is unknown for a date-only closing record, an exact
publication timestamp earlier than the end of the local close date is rejected.
This can exclude a valid same-day publication; an audited source-specific
close timestamp would require a new protocol version. A different publication
zone is respected: December 31 availability in UTC and New York can have
different maturity at January 1 00:00 UTC.

The plan contains no prices. It hashes source and schedule fingerprints,
per-row origin policies, maturity metadata, cutoffs and bound membership.
Hashes detect changed declared inputs but do not authenticate publisher facts.

## Verification and limits

The [synthetic tests](../tests/test_chronological_plan.py) exercise delayed
publication, DST and leap dates, cross-zone date-only availability, exact
cutoffs, reserved-row injection, forged schedules and hash stability. The
[run report](../runs/u3-synthetic-chronological-plan-20261003T113906Z/report.md)
records the observed commands and results.

This does not certify U3 or G-US. The declared 24-month history is not yet
shown to be usable, and no source currently has verified target semantics,
row-level first availability, rights and sufficient matured cohorts. The
spatial dependence plan, calibration and prospective test remain separate
requirements. Use this bridge on real sources only after those facts pass U0/U2.
