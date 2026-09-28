# ADR 0013: Hillsborough All Sales manual-audit sample

Date: 2026-09-28

Owner: project implementation

Affected requirements: US02, US05, US06, US07, US08

## Evidence and alternatives

The unchanged HCPA archive identified by SHA-256
`847854d9139fe3811506991d3c41d961581a92a648bb661c4bd9d166591366c7`
contains 2,453,187 parcel-linked sale entries. The [source profile](../runs/u0-hcpa-profile-20260928T133100Z/report.md)
establishes its physical layout and aggregate codes, but no individual label has
been verified. Its embedded `allsales.doc` defines `S_DATE` only as "date of
sale". It describes a lag between Clerk receipt, assessor review and entry.
The [official download page](https://downloads.hcpafl.org/Default.aspx) does
not establish first publication for each row or a product reuse right.

A simple random sample would be easy to reproduce, but could underrepresent
unqualified sales and unusual records. Selecting only suspicious records would
not allow review of ordinary records across time. The following fixed design
balances these two aims; its proportions are deliberately not population
weights.

## Frozen selection protocol

The sampling frame is every active DBF record in the pinned ZIP, before any
residential or arm's-length eligibility filter. Divide records into five
`S_DATE` bands: before 2000; 2000–2009; 2010–2019; 2020–2023; and 2024–2026.
Cross each band with raw `QU` values `Q` and `U`. Select 20 distinct records
per cell, yielding 200 if all ten cells have enough rows. A row is marked
`edge` if `VI` is not `I`, `DOC_NUM` is blank, `S_TYPE` is not `WD`, `S_AMT`
is below USD 1,000, or `DOR_CODE` differs from `0100`. Prefer up to ten edge
records in each cell, then fill to 20 from that cell's full population.
Selection uses the smallest SHA-256 ranks of the pinned archive hash, seed 42
and one-based DBF record ordinal. Stable ordinals, cell counts, edge counts,
the selection algorithm version and the sample file hash make replay possible.
If a cell has fewer than 20 records, fail and revise the protocol before any
review; do not silently fill from another cell. Record all observed cell and
edge counts. Do not treat the sample as statistically representative of the
county or a model-ready cohort.

The private review file stays under Git-ignored `data/raw/hcpa/`. It may hold
parcel and Clerk identifiers, sale dates, raw amounts and codes needed for
source comparison. Exclude `GRANTOR`, `GRANTEE`, street/address fields and all
other personal names. The tracked manifest contains only aggregate counts,
configuration, source hash and sample hash. The sampler writes atomically and
does not overwrite an existing review file. Sample generation is not a manual
audit; review status remains pending until 200 source comparisons are recorded.

## Manual review contract

Before changing eligibility rules, examine all 200 sampled entries against
the HCPA record and, where legally accessible, the associated Clerk instrument.
For each, record whether parcel and document identity agree, the meaning of
`S_DATE` relative to execution/recording/closing evidence, price scope,
property class, `QU` and `REA_CD` interpretation, multi-parcel or repeated
consideration, missing fields, and an evidence-quality code. Preserve unknown
answers. Audit every schema anomaly discovered in the sample, including source
corrections and conflicting identifiers. Expand the review if a systematic
defect appears. A duplicate across publishers requires a second authorised
source and remains untested with HCPA alone.

## Decision and gate effect

This is a U0 source-quality sample only. `S_DATE` is not yet a verified closing
date; this ZIP alone does not provide historical `available_at`; HCPA use and
redistribution permissions remain unresolved. Therefore its rows cannot enter
a certified 90-day as-of benchmark or a releasable model. The audit can inform
a source-specific eligibility rule and the next data-access decision, but does
not by itself accept U0, U2 or G-US.
