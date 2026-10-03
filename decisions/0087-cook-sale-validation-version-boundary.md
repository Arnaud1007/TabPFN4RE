# ADR 0087: Keep Cook validation flags and late sales versioned

Date: 2026-10-04
Owner: project implementation
Status: source-qualification evidence; no sale-label admission
Requirements: US05, US07, US08, US24
Affected protocol: U0 Cook source audit only; no frozen evaluation changed

## Pinned publisher evidence

The Cook County Assessor's [sales-validation repository](https://github.com/ccao-data/model-sales-val/blob/44da5d6bb143ab5f0e09a6374bfb738beed0446c/README.md)
describes a separate flagging process for suspected non-arm's-length and
outlier sales. It says flags are updated as sales arrive, historical flag
versions are stored internally, and the current view resolves to the latest
version by document number. Its published residential input excludes
multi-PIN sales, among other categories. The public README describes internal
Athena tables; it does not grant this project access to row-level historical
flags or demonstrate that a flag was public at any valuation origin.

The Assessor's [residential AVM repository](https://github.com/ccao-data/model-res-avm/blob/feec9b79229e5ea9cfcbe042184855c2e047ae14/README.md)
reports a 2026 rerun after the Illinois Department of Revenue identified
relevant 2025 sales missing from the Assessor's database. This is concrete
publisher evidence that historical sale populations can be revised. It does
not identify which, if any, rows in our protected 200-row sample were affected
or when those rows first became public.

## Decision

Add two questions to the unsent Cook custodian inquiry: whether a permitted,
historically versioned sale-validation status can be linked to public parcel
sales, and whether dated source snapshots or correction logs capture late
sales such as those acknowledged in the 2026 rerun. Keep the current source
card's `historical_asof_eligible: false` and `certified_sale_labels: 0`.

The Assessor's internal exclusion rules are evidence for audit design, not an
automatic eligibility policy for this project. In particular, price-outlier
flags and fixed price cutoffs cannot be copied into a final-test filter after
seeing sale prices. If historical flags become available under suitable terms,
register their meaning and timing before using them, retain original versions,
and assess their effect on the full eligible denominator. Buyer and seller
identities are outside the project's necessary input contract.

No public dataset, model training, test population or service-area status
changed in this decision.
