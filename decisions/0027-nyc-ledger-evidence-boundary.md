# ADR 0027: conservative evidence boundary for NYC source reviews

Date: 2026-09-29
Owner: project implementation
Status: approved for `nyc-source-review-v1` before its first real entry
Affected requirements: US05, US07, US08, US22 and US24
Supersedes: the permissive evidence interpretations in ADR 0025 only

## Context

[ADR 0025](0025-nyc-private-source-review-ledger.md) defines a private,
revisioned review of 200 frozen NYC DOF rows. Independent review of the
unreleased ledger implementation found that a reviewer could supply plausible
archive metadata, row values, dates or evidence-kind labels and thereby obtain
an affirmative finding without a separately verified local source artifact.
The archived-version probe contains revision metadata, not archived rows.
The frozen source row cannot independently confirm its own identity or first
publication. No real NYC review entry exists yet.

The alternative was to build a general artifact registry and row-comparison
engine before the first pilot. That would allow richer findings, but its input
formats, custody checks and first-publication rules are not yet defined or
tested. A conservative v1 ledger can record review effort and explicit unknowns
without promoting self-declared evidence into historical facts.

## Decision

For `nyc-source-review-v1`, **every rubric dimension except
`price_semantics` must be `unknown`**, with a cited evidence item and a
concrete limitation. This includes source-row and property/unit identity,
economic transfer scope, repeated consideration, sale-date comparisons,
first-row availability, attribute vintage, source correction, property class
and evidence quality. In particular, neither an asserted archive date nor a
self-declared matching row can yield even an availability upper bound. An item
labelled `archived_row_snapshot`, `publication_log`,
`independent_dof_export`, `recorded_instrument`, `closing_record` or
`recording_index` does not bypass this rule; a generic URL does not verify its
contents. The sole affirmative finding describes `price_semantics` in the
**pinned published row**: `reported_positive`, `reported_zero` or `invalid`
must match its strict decimal parser and cite the row and official field
definition. This is not a finding about arm's-length consideration.

Correction-history evidence and any checked version date must end no later
than the entry's `reviewed_at`. The v1 rubric nevertheless records
`source_correction=unknown`; its limitation may describe the versions
actually checked, but cannot assert that an unchecked or future period had no
correction. A later protocol may permit a bounded
`no_correction_in_checked_history` finding only after verifying the actual
version artifacts and interval. It must never mean that no correction exists
outside that interval.

A `complete` entry using `unavailable_attempt` in place of a recorded
instrument must include structured `attempted_at` (UTC), `target` (the
instrument or qualified source sought), and `outcome` (the concrete access
result). The attempt must precede or equal `reviewed_at`, cite an applicable
`unknown` rubric finding, and state the resulting limitation. A generic
"unavailable" note or an attempt unrelated to any unknown does not complete a
review. It never supports an affirmative finding. A completed review may
therefore retain unknowns and is not a validated label or release gate.

If `init` creates the private manifest but crashes before creating the ledger,
another `init` must not overwrite or reuse that manifest. Recovery first
inspects the orphan under the private lock and records the interruption. The
safe default is to preserve it as an abandoned history and initialize a new
manifest and empty ledger at new private paths with a new `ledger_id`; do not
claim continuity or silently recreate a missing ledger. A same-ID recovery
would require an explicit, separately tested procedure that proves the ledger
was never created and performs create-new writes only. Neither an existing
ledger nor an orphan manifest may be truncated, replaced or silently repaired.

## Promotion requirements

These v1 restrictions can be relaxed only by a later versioned decision and
executable checks. The future workflow must capture source artifacts as
immutable local bytes with hashes, provenance and publication or retrieval
dates, compare each artifact's actual row and unit keys to the pinned sample,
and establish which event each date represents. An availability upper bound
requires the matched row in a dated archived release. A **first** publication
claim additionally requires evidence ruling out earlier releases. Contract,
closing and recording comparisons require independently checked dated records;
historical attribute claims require a dated attribute artifact available by
the prediction origin. Evidence and row-comparison outputs stay private;
public reports remain suppressed aggregates.

New validators and tests must fail every non-unknown v1 finding except checked
published-row price semantics, as well as structured attempt omissions, future
correction bounds and orphan-manifest overwrite.
Any later promotion creates a new protocol and preserves old entries and
hashes. ADR 0025 and the frozen 200-row selection remain historical records;
this decision does not rewrite them or convert prior metadata into evidence.

## Consequences

The first pilot can document what was checked and why facts remain unknown,
while resisting unsupported claims. It cannot complete source qualification
or establish G-US. Richer audit findings wait for verified local artifacts, a
semantic parser and a tested row-comparison protocol.
