# 0093 — Indiana low-price source-audit sample

Date: 2026-10-05. Owner: project team. Status: adopted before sample selection.
Scope: **source audit of the consumed 2025 research cohort**, not a model
training or certification cohort.

## Evidence and decision

The [fixed slice report](../runs/indiana-assessment-diagnostic-v1/slice_report.md)
shows 51.62% MdAPE on 12,737 sales at or below the $117,000 cutoff defined
from 2024 training prices. A hash-checked exploratory join to the 2025
SALEDISC records found 7,354 of these lower-price sales marked `N` for
`P2_16_Valid_Trending` and 5,383 marked `Y`; among 58,317 higher-price sales,
10,496 were `N` and 47,821 `Y`. This is a post-sale validation field. It is
useful for audit stratification and **forbidden as a pre-sale predictor or a
post-hoc filter for the published score**.

Select exactly 200 distinct eligible 2025 transactions from four cells:
realised price up to $117,000 versus above, crossed with `P2_16` `Y` versus
`N`. Take 50 from each cell. Within each cell select the 10 smallest prices,
the 10 largest remaining prices, and 30 of the remainder ranked by SHA-256 of
seed 42 and the existing pseudonymous row ID. Sort ties by row ID. Fail if a
cell lacks enough records or if the source join is incomplete or duplicated.
The selected queue is deliberately edge-enriched and is **not** a population
sample for prevalence estimates. It contains only the existing eligible
one-family cohort; it cannot by itself satisfy US07's wider source audit of
excluded transfers, duplicate identities, uncertain matches and geographic
coverage. That audit remains a separate gate.

The private queue keeps only the source lookup fields and audit rubric needed
for manual review. Public evidence may contain aggregate cell counts, source
and membership hashes, code commit, queue hash and review status, but no
transaction ID, parcel, address, person or row-level price. Reviewers must
record a source-evidence reference, decision and reason for each of the 200;
selection alone does not satisfy the manual-audit requirement.

## Review rubric and limitations

For each selected transfer, compare the original disclosure and parcel rows
to the [DLGF form instructions](https://www.in.gov/dlgf/files/Sales-Disclosure-Form-Instructions.pdf):
price and consideration scope, single economic transfer, parcel count and
class, valuable-consideration and special-transfer flags, physical changes,
assessor receipt and trending status. Where possible, cross-check a separate
official conveyance or assessment record with its own timestamp. Mark
unresolved facts unknown rather than assigning arm's-length status from price
or trending alone.

The DLGF instructions call `P2_13_Date_Sale` a conveyance date and describe
land/improvement AV as the assessor's most recent values when processing the
form. The assessor may validate the sale after receipt. [STATS Indiana](https://www.stats.indiana.edu/about/sdf.asp)
says historical files can be corrected. Neither source establishes that the
retrieved assessment values were available 90 days before an individual sale.
The local Marion 2023-assessment PARCEL extract [audited in ADR
0091](0091-indiana-assessment-snapshot-diagnostic.md) declares a file
creation date of **19 April 2025** and pay year 2024; its nominal
assessment year alone cannot certify an
earlier feature snapshot. Preserve the OFF as-of blocker pending an actually
dated prior source or independent availability evidence.

## Alternatives

Automatically removing `P2_16=N` sales would make the retrospective score
look better while changing its denominator after seeing errors. It would not
prove those transfers were invalid for the product target. Blind model tuning
would not resolve a label or vintage defect. Audit the records first, correct
only evidenced source rules, and use a new untouched period for any revised
model's acceptance.
