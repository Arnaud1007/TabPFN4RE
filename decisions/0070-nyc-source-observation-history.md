# ADR 0070: Bounded NYC source observation history

Date: 2026-10-03
Owner: project implementation
Status: verified source-inventory method; no certified labels
Affected requirements: US05, US08, US22, US24
Affected protocol: `nyc-observation-v1`; no change to a frozen model evaluation

## Context and alternatives

The NYC rolling CSV was captured on 28 September and 3 October 2026. Their
bytes are equal, but two capture manifests represent two observations at
different project-known-by times. Treating the later file as an earlier
historical vintage would be unsound. Comparing only byte hashes would miss
whether a later, differently ordered file held the same row representations.

We considered persisting per-row hashes to make later comparisons cheaper.
That would retain address-and-price-derived fingerprints and risk exposing
small changes in a portable artifact. We instead retain only private,
capture-level entries and recompute full-row multisets in memory from the
original private files on each append. An append fails if any prior manifest,
raw file or observation entry no longer verifies.

## Decision

The ledger uses the capture completion time as a conservative time by which
this project knew the file. It permits chronological, create-only observations
for the pinned `usep-8jbt` source and v1 CSV schema. Comparisons are multisets
of complete source-row representations, so order changes do not create a
delta and duplicated rows retain their multiplicity. An unmatched
representation is a source change, never an inferred transaction correction,
new sale, property identity or publication timestamp.

The private ledger lives under Git-ignored `data/derived/nyc_dof/`. Public
outputs contain capture-level hashes and times, exact total row counts, and
suppressed buckets for added and removed representation occurrences. They
contain no addresses, prices, source row ordinals or per-row fingerprints.
The current run pins exactly two existing manifests and uses no network.

The code caps file size and row count, validates UTC chronology and source
status, takes an exclusive local write lock and publishes entries without
overwriting. Replay is idempotent. The ledger references local absolute
manifest paths, so moving it to another machine requires a separately
verified reconstruction from the source files. Each append re-reads the
private history, which is acceptable for this bounded run but requires a
scaling review before a long capture programme. A stale lock needs manual
inspection rather than automatic removal. The generic CLI accepts a ledger
path supplied by its local operator; this run's verified script pins the
private root and both manifests.

## Evidence and boundary

The [plan](../runs/u0-nyc-observation-history-v1-20261003T125727Z/plan.md),
[executable verifier](../runs/u0-nyc-observation-history-v1-20261003T125727Z/verify_artifacts.ps1)
and [report](../runs/u0-nyc-observation-history-v1-20261003T125727Z/report.md)
show the two replayed captures and test evidence. The later file has zero
added and zero removed row-representation occurrences relative to the first.

First public availability, `SALE DATE` semantics, single-home transfer
eligibility, source rights and historical attribute vintages remain
unverified. Both observations remain inventory-only with zero certified sale
labels. U0 and G-US remain PENDING; no model training follows from this ADR.
