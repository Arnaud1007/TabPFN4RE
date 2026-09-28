# ADR 0018: Diagnose frozen HCPA crosswalk gaps

Date: 2026-09-29

Owner: project implementation

Affected requirements: US05, US06, US07 and US24

## Context and choice

ADR 0017 froze the sampling rule and PIN-format hypothesis; the 1,000
disjoint All Sales rows were then selected and frozen before the crosswalk
audit. That audit found 16 sale rows without an exact 2025 PIN+FOLIO
control and six rows whose unique 2026 FOLIO lead has a blank PIN. Five rows
overlap. These are source-quality questions, not a reason to admit a one-key
parcel join. Diagnose the gaps using the *same* frozen rows and archives, with
no sample replacement, model training or change to the accepted matching rule.

## Preregistered checks

Recompute, from the pinned private sample and raw DBF fields, the full 1,000-row
intersection of exact 2025 two-key match and current unique-FOLIO blank-PIN
status. Reconcile its four cells against the prior frozen audit: 983 exact and
nonblank, one exact and blank, 11 no exact and nonblank, and five no exact and
blank. Also reconcile the 16 missing exact 2025 controls, six current blank
PINs and five-row overlap. These are prior observed counts to *check*, not
values to insert into a new report by hand. Fail the diagnostic if counts or
source hashes differ.

For each of the 16 no-exact-2025 rows, distinguish a unique FOLIO-only lead
from no one-key lead; the prior audit recorded six and ten respectively. On
each FOLIO-only lead inspect raw 2025 PIN and STRAP state, and whether a
nonblank STRAP agrees with the frozen transform. Record conflicting or
multiply matched candidates explicitly. A FOLIO-only lead never becomes an
accepted match. Classify the sale date before, on or after the 2025 DBF header
date if both dates parse. The header date describes file metadata and does not
establish publication or historical availability.

For each of the six unique-2026-FOLIO rows with blank PIN, inspect the raw
fixed-width DBF bytes, field descriptor, active-record marker and candidate
cardinality. Separate genuinely all-space PIN bytes from any other unexpected
encoding. Cross-tabulate against exact 2025 two-key controls and the 2025
one-key leads. If a source field is malformed, a candidate is duplicated or
conflicting, or a category cannot be reconciled, fail closed with no promotion.

## Evidence and limits

The diagnostic must hash the pinned sample and both source ZIPs, preserve
vintage-specific schema fingerprints, generate counts from source rows, and
replay the aggregate byte-identically. Keep identifiers, prices, addresses,
sample ordinals and private flags only in ignored `data/raw/hcpa/`. Tracked
evidence contains aggregate counts and hashes only, with denominators and a
command for replay. Synthetic tests must cover overlap, one-key nonpromotion,
blank raw bytes, duplicate/conflicting candidates, date boundaries, and
hash/schema failures. An explicit privacy test must reject row identifiers,
sample ordinals, prices, addresses, raw PIN/FOLIO values and private flags in
tracked output, and must reject private output paths outside ignored raw
storage. Run the real diagnostic only after this decision is committed.

No result of this diagnostic establishes the publisher's exact permutation,
transaction identity, dwelling-level price scope, first availability, sale
date meaning or permitted use. Automatic parcel joining remains **BLOCKED**
until those separate controls pass. U0 and G-US remain pending.
