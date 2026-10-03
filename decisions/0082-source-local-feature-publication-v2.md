# ADR 0082: Typed source-local publication dates in OFF features

Date: 2026-10-03
Owner: project implementation
Status: implemented synthetic engineering contract; source certification pending
Requirements: US03, US06, US08, US11, US14, US23, US24
Affected protocol: `synthetic_off_local_date_asof_v2`; the exact-UTC and local-date v1 policies are unchanged

## Problem and alternatives

Some source facts are published with a source-local calendar date but no evidenced
hour. Assigning midnight or another invented hour can leak property, attribute or
prior-sale information into a historical prediction. Excluding every date-only
fact would prevent a potentially useful source from entering the local-date OFF
research path. Reinterpreting the existing exact or local-date v1 policy would
change its snapshot identity and break frozen engineering replay.

## Decision

Use separate immutable `DatePublishedProperty` and `DatePublishedAttribute`
contracts for property and attribute publication dates. Preserve
`LocalDateSale` for prior transactions. Keep source-local date and IANA zone in
lineage. A date-only event or publication becomes visible only after its
source-local day has ended in UTC, and only if the source snapshot is at least
that recent. Exact timestamps retain their original instant comparison. The
v2 snapshot hash records typed precision and zone and pins a distinct policy
version.

An exact-time source fact may receive a date-only version-end disclosure. An
immutable internal reconciliation overlay preserves its exact initial
publication and typed later disclosure without converting either to an
invented time. Conflicting cross-precision deed and economic-transfer IDs are
quarantined. The exact-UTC and local-date v1 entry points explicitly reject
date-only facts.

The guarded synthetic OFF median may opt into v2 by an explicit feature-policy
version. Training uses only matured labels in the frozen chronological plan;
prediction keeps the chosen policy. The accepted training digest includes the
typed feature snapshots. ON remains unavailable.

## Evidence boundary

The synthetic run under
`runs/u3-synthetic-local-date-publication-v2-20261003/` records executable
checks and reviews. No county adapter has established actual first publication,
source rights or historical attribute vintages. No modern US labels have been
certified or used for this experiment. U0, U3 and G-US remain pending. A real
adapter must bind independently hashed raw source artifacts and its source card
to these typed fields before any real-data fit.
