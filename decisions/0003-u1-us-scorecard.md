# ADR 0003: Initial US scorecard and split guard

Date: 2026-09-28
Owner: Arnaud (project); implementation decision recorded by coding agent
Affected protocol: `u1_integrity_v1`; no change to the Ames engineering protocol

## Context and alternatives

U1 requires shared point-error definitions and explicit accounting of failed predictions. The alternatives were to reuse the small Ames metric helpers, adopt a third-party metric library before freezing conventions, or implement a small standard-library scorecard with hand-computed tests. The Ames helpers do not carry currency or service-coverage counts.

## Decision

For the US foundation, accept USD only; country adapters must extend the currency contract before international use. Score estimated rows while retaining eligible, failed and abstained counts and a success-coverage fraction. Store signed percentage error as `(predicted - actual) / actual`; positive means overvaluation. Use inclusive 5%, 10% and 20% thresholds compared with exact decimal price values. Use type-7 linear interpolation for P90 and P95 APE. Report R-squared as undefined when all actual prices are identical. Bound Decimal representation to at most 64 coefficient digits and absolute exponent 64 to keep exact threshold calculations bounded; this is a numeric resource limit, not a sale-price eligibility rule.

Require immutable, disjoint training/reserved ID sets. The category encoder fits only declared training IDs and maps unseen categories to a disjoint negative code. The unseen-property split rejects property overlap, while the operational future-sales protocol permits a previously known property. These protocols remain separate.

## Evidence and limits

The 21 focused T05-T08 tests cover reserved IDs, validation-only categories, property overlap, arithmetic sign and boundaries, R-squared, invalid prices/currencies, failures and abstentions. The full suite passes 88 tests at 90% coverage in `runs/u1-integrity-20260928T093259Z/` on commit `08b2b55` (full hash in `test_gate.json`). The scorecard does not establish pre-abstention price accuracy for rows without an estimate; that requires a frozen fallback prediction policy and a real evaluation cohort. U1 remains pending its remaining integration and feature/comparable canaries.
