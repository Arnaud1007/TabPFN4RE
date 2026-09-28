# ADR 0002: Synthetic US point-in-time contract

Date: 2026-09-28
Owner: Arnaud (project); implementation decision recorded by coding agent
Affected protocol: `u1_foundation_v1`; no change to `ames_engineering_v1`

## Context and alternatives

The legacy project and real US transaction vintages are not yet accessible. U1 still needs executable schema and leakage guards. Alternatives considered were to extend the Ames fixture, choose a database schema before source inspection, or build a small in-memory contract from synthetic dated records. Ames has no verified historical availability data, and a database choice would add an unsupported assumption.

## Decision

Use frozen Python 3.11 records for US property, transaction, attribute, listing event and source snapshot facts. Require timezone-aware event and availability instants, Decimal monetary values, explicit missing states, source-qualified raw transaction IDs and canonical economic-transfer IDs. An OFF feature snapshot admits only registered attributes and records visible by both valuation origin and source snapshot cutoff. Its immutable values carry lineage and a content hash. ON remains unavailable until an authorised historical listing feed exists.

For prior-sale features, resolve and exclude the entire subject economic transfer, reconcile duplicate feeds before filtering, and admit only unflagged single-property gross recorded sales with confirmed arm's-length status. A conflicting duplicate is quarantined through an explicit exception. The empty adjustment-flag rule is conservative; later source adapters may propose a documented flag policy with new tests and a protocol version.

## Evidence and consequences

The RED fixtures exposed cross-feed and cross-property subject leakage, source-local ID collisions, later source observations, nonstandard transfers and disagreement on eligibility. The fixed implementation passes the 34 U1 foundation tests. The full 67-test run and coverage are in `runs/u1-foundation-20260928T091610Z/` at code commit `c85abb2` (full hash in its gate manifest). This proves synthetic behaviour only; it does not establish factual correctness, source rights or US model accuracy. U1, US06 and US08 remain pending their broader source and pipeline evidence.
