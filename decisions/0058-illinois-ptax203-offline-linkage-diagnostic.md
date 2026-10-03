# ADR 0058: offline Cook–PTAX linkage diagnostic

- Date: 2026-10-03
- Owner: project implementation
- Requirements: US02, US03, US05, US06, US07, US08, US24
- Protocol: `illinois-ptax203-offline-link-v1`

## Decision

Analyze only the already frozen Cook sample and Illinois PTAX-203 capture. First
replay both captures and verify their recorded hashes. Join exact Cook `doc_no`
strings to PTAX `document_number` strings without punctuation, whitespace or
numeric normalization. Preserve all zero, one and multiple candidate
relationships. Report Cook-row, unique-document and declaration grains
separately; never multiply one declaration's consideration into several labels.

Write a create-only, ACL-restricted, Git-ignored private diagnostic with a
row-level reviewer queue and source-row hashes. The public output contains
protocol/source hashes, the already disclosed input denominators, review-queue
size and zero certified labels. It contains no new match, conflict or small-cell
counts, identifiers, dates, prices, URLs or free-text notes. This conservative
publication rule avoids reconstructing small cells from overlapping totals.

## Registered diagnostics

For every exact document group, retain Cook-row count, distinct PIN count and
PTAX declaration count privately. Compare county only to the declared Cook
source area; missing or unrecognized values stay unknown. Compare PIN strings
exactly and keep absent, malformed, unequal and possible nonprimary-PIN cases
separate. The Additional PIN dataset has not been captured, so a primary-PIN
mismatch cannot prove a different property.

Treat Cook `is_multisale` and `num_parcels_sale`, PTAX
`line_2_total_parcels` and `line_3_additional_pins` as scope diagnostics.
Compare Cook `sale_price` with PTAX Line 11 using `Decimal`; keep Line 12 and
Line 13 separate. An equal amount does not prove a single-home gross label.
Compare `sale_date` with `date_recorded` only as recorded-date observations;
Line 4 has month/year precision only. Neither is accepted as close date.
Related-party, status, use and instrument codes are review prompts until their
source semantics are qualified. Unknown is never converted to false or zero.

Priority order for private human review is missing/multiple links, identity or
county conflicts, multi-parcel scope, consideration or recorded-date
disagreements, and source flags. This is triage, not an eligibility rule. The
existing Cook review ledger remains unchanged; a reviewer must separately
attest evidence in a versioned protocol before any rubric is considered done.

## Boundary and alternatives

Directly merging the two feeds would create false one-home prices and apparent
independent labels for repeated deed rows. Ignoring the independent declaration
would leave useful contradictions unexamined. The offline diagnostic tests the
linkage while keeping the raw records private and the source questions open.
No new request to IDOR or Cook is authorized by this ADR. No model training,
historical `available_at` inference or G-US promotion follows from its results.

The [frozen run plan](../runs/u0-illinois-ptax203-offline-v1-20261003T035947Z/plan.md)
sets caps, fixtures, replay and failure behavior before candidate-level
inspection. A changed rule needs a new protocol and output, never a silent
revision to this frozen run.
