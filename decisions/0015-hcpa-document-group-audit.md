# ADR 0015: HCPA document-group source audit

Date: 2026-09-28

Owner: project implementation

Affected requirements: US02, US05, US07, US22, US23, US24

## Question and alternatives

The pinned HCPA All Sales profile counts 269,947 blank `DOC_NUM` fields among
2,453,187 parcel-linked rows, but it does not show whether populated Clerk
instrument numbers recur. A repeated instrument may represent several parcels
in one transfer, repeated consideration, a correction, or identifier reuse.
It cannot be interpreted as a duplicate economic sale without source review.

The 200-row manual-review sample deliberately favours edge cases and is not a
county prevalence estimate. An in-memory scan would be fast but make memory
use depend on the number of distinct instruments. A disposable local SQLite
spool and ordered aggregate scan provide exact grouping with bounded process
memory. The spool is private and must be removed after a successful run.

## Decision

Verify the exact archived ZIP hash and DBF layout before processing. Group
active records by the **exact trimmed, nonblank** `DOC_NUM` text. Do not
normalize leading zeros or infer that two blank numbers match. Parse finite
`S_AMT` values as decimal amounts for equality; malformed amounts are unknown.
Compare nonblank `PIN` and `FOLIO` within each instrument group and retain
missing identifier states. Compare `S_DATE` values to flag date disagreement.

Report county aggregate counts: blank document rows, nonblank rows, distinct
groups, singleton and repeated groups, rows in repeated groups, group-size
buckets, maximum size, repeated-amount candidate groups, conflicting valid
amount groups, differing nonblank parcel-identifier groups and differing date
groups. Reconcile to the previous source profile. Verify the frozen sample
SHA-256, then report only how many sampled rows have blank, singleton or
repeated instrument numbers and candidate group flags. Never publish document
numbers, parcel identifiers, row ordinals, raw amounts, row dates or per-group
hashes. The sample is for review priority, not prevalence inference.

Use resource limits for the disposable spool, disk availability and execution
time. Test the grouping rules on synthetic DBF fixtures before the full scan.
The implementation and actual measured run determine the exact technical cap
and are recorded in the run manifest. No source row enters a modelling layer.

## Interpretation and exit

Each repeated document or repeated amount is a **linkage candidate**. It is
not a verified multi-parcel sale, duplicate transaction or invalid label. The
private 200-record manual review remains necessary, as do close-date meaning,
first availability, source-specific reuse rights and a transaction-grain rule.
This audit cannot accept U0, U2 or G-US by itself.
