# U0 Illinois PTAX-203 exact-document linkage probe, v1

Frozen before any row-level PTAX request on 2026-10-03 UTC.

## Inputs and question

Use only the immutable 200-row private Cook sale sample with manifest SHA-256
`130b5169ff81ccbc0a729cba98400f2fb377ff9a25999316aaac1960e38a3cf7`.
Select all rows whose frozen `year` is `2024` or `2025` and whose `doc_no` is a
nonempty string. The prior sample inventory shows 100 such rows. Deduplicate
the exact document strings, preserving their association to the Cook rows in
private storage. Sort document strings by Unicode code point and split them
into consecutive batches of ten. Do not normalize punctuation, leading zeros
or whitespace to manufacture a match.

The question is whether an independently published IDOR declaration has a
matching document number and what linkage conflicts it reveals. This is a
source audit, not a label-eligibility or model-training run.

## Official endpoint and field allowlist

Fetch metadata immediately before and after the row queries from
`https://illinois-edp.data.socrata.com/api/views/it54-y4c6.json`. Require
published stage, official provenance, `PUBLIC_DOMAIN` licence and
`declaration_id` as the documented row identifier. Compare the two captures'
`rowsUpdatedAt`, `viewLastModified`, schema field names and licence identity.
Keep the exact metadata bytes privately, even if version stability fails.

For each batch, query only
`https://illinois-edp.data.socrata.com/resource/it54-y4c6.json` with an
exact `document_number IN (...)` predicate. First request `count(*)`; then
request the selected rows with `$order=declaration_id` and `$limit=100` only
if the count is at most 100. An excessive count stops the run as incomplete.
The row `$select` allowlist is:

`declaration_id,status,document_number,date_recorded,line_1_county,line_1_primary_pin,line_1_unit,line_2_total_parcels,line_3_additional_pins,line_4_instrument_date,line_5_instrument_type,line_8_current_use,line_10b_sale_between_related,line_11_full_consideration,line_12a_total_personal,line_13_net_consideration`

No buyer, seller, preparer, address, legal-description or free-text fields may
be requested or saved. A row response must contain only allowlisted fields and
each document number must equal one of the exact requested strings. County,
PIN, parcel count, dates and consideration are private diagnostics, not
automatic acceptance rules. Preserve zero, one and multiple candidates.

## Resource and failure limits

- At most 100 selected Cook rows, ten document strings per batch, ten batches,
  22 read-only GET requests including metadata, and 100 returned declaration
  rows per batch.
- HTTPS only, exact official host, no cross-host redirects, no credentials,
  no writes to the publisher, at most 15 seconds per request.
- At most 512 KiB per metadata response, 8 KiB per count response and 64 KiB
  per row response. Save exact response bytes, UTC request times, HTTP status,
  duration, URL hash and SHA-256 under ACL-restricted,
  Git-ignored `data/raw/illinois_ptax203/`.
- Claim a create-only private run directory before the first GET. Preserve
  incomplete state and every failed request's status, timing and body hash;
  save the exact body only when it is valid JSON with the expected schema and
  contains no unrequested fields. An error body or unexpectedly broad row
  payload is discarded after hashing, so an accidental PII response is never
  retained. Do not silently retry or alter the frozen selection or query after
  seeing matches.

## Evidence and publication

Offline replay verifies exact selection, request text, byte hashes, metadata
stability, row/count agreement, unique declaration IDs, private ACL and
bounded output. Public files contain protocol identity, hashes and aggregate
denominators only; cells below five are suppressed. No document number, PIN,
declaration ID, row timestamp, price, query URL, party or free-text note may be
committed. Report zero certified sale labels, false historical as-of
eligibility, and U0/G-US PENDING regardless of candidate links.

Failed or saturated requests produce an incomplete run rather than a valid
score. A later request change needs a versioned protocol. The official
[PTAX-203 instructions](https://tax.illinois.gov/localgovernments/property/general-information/ptax-203_instructions.html)
and [ADR 0057](../../decisions/0057-illinois-ptax203-bounded-linkage-audit.md)
govern interpretation; this plan does not equate recorded or instrument dates
with close date.
