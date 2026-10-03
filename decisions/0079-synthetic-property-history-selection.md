# ADR 0079: Synthetic property-history selection at two times

Date: 2026-10-03
Owner: project implementation
Status: implemented engineering contract; source certification pending
Affected requirements: US06, US08, US10, US23, US24
Affected protocol: `synthetic_off_asof_v2`; no frozen real-market split changed

## Problem and alternatives

[ADR 0078](0078-synthetic-asof-validity-and-corrections.md) gave property
records effective intervals, but the OFF assembler accepted one preselected
property version. Comparable retrieval also accepted one candidate record, so
an adapter could choose a later area or silently miss a correction. Selecting
the candidate only with information available on its sale date is too strict:
a correction published before valuation can identify the state that was
already effective at the earlier sale. Using valuation time as the effective
date is wrong for the opposite reason. A first observation made after the
sale cannot be backdated into that sale without source-specific proof.

## Decision

The synthetic assembler now accepts a property history and selects exactly
one version effective at the valuation origin, using only records and ends
known by that origin and the pinned source snapshot. Ambiguous overlap,
conflicting ends and unlisted visible sources fail closed. Identical source
copies are reconciled deterministically; equivalent end instants are returned
in UTC. End dates not yet published are removed from returned property
objects as well as from feature hashes.

Comparable retrieval selects each candidate version effective at its sale
date, using corrections known by the valuation origin. The selected version's
observation must have occurred no later than that sale. Later publication of
an earlier observation is allowed. Later observation, invalidated state and
unlisted visible candidate sources are excluded or rejected as appropriate.
The retrieval result returns only end metadata known by the query cutoff.

The selector's optional `known_at` parameter expresses this distinction.
Normal OFF snapshots omit it, so their effective date and information cutoff
remain the valuation origin. This change does not alter the legacy Ames split
or any final-test protocol.

## Evidence and limits

The [synthetic run report](../runs/u1-synthetic-property-history-v1-20261003T164855Z/report.md)
contains RED/GREEN cases for late publication, post-sale observation,
expired candidates, equivalent copies, source manifests and overlap. It
reports the full test and review results. These fixtures show code behavior,
not completeness or correctness of a real assessor's version history.
Before certification, each adapter must demonstrate that its observation,
effective and first-publication timestamps have the documented meanings and
that corrections do not erase earlier recoverable vintages. Until then this
contract cannot supply certified modern US labels or a G-US score.
