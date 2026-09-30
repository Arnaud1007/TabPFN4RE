# ADR 0041: bounded Socrata row-timestamp diagnostic

Date: 2026-09-30
Owner: project implementation
Status: approved for a read-only U0 diagnostic
Protocol: `nyc-row-system-timestamps-v1`
Requirements: US05, US08, US22, US24

## Question and prior observation

Could the NYC Open Data system fields establish when a rolling or annualized
sale row first became public? The [Socrata system-fields guide](https://dev.socrata.com/docs/system-fields.html)
defines `:created_at` as creation of the current portal record and
`:updated_at` as its last update. The guide warns that a full dataset replace
can update all records in a short interval. These fields do not themselves
define a property's sale, closing or first publication in an older release.

Unfrozen exploratory aggregate requests on 30 September returned 82,345
current rolling rows, all with the same creation and update timestamp on
15 September 2026. Current annualized rows had creation timestamps between
27 May and 9 June 2026, despite the view covering earlier sale years. These
observations motivate this reproducible probe; they are not an untouched
test or evidence that the provider definitely used a full-replace operation.

## Fixed capture

Query only `usep-8jbt` (rolling) and `w2pb-icbu` (annualized). For each view,
GET its official `/api/views/<id>` metadata, one `/resource/<id>.json`
aggregate, then the same metadata again. The aggregate is fixed to
`count(*)`, non-null counts and minimum/maximum of `:created_at` and
`:updated_at`. Request no row identifiers, addresses, prices or individual
timestamps. Allow only `https://data.cityofnewyork.us` and these fixed paths;
reject redirects. Limit each metadata response to 2 MiB, each aggregate to
4 KiB, apply a 30-second elapsed-time budget to each GET's socket I/O, and
limit the run to six GETs without retry. Operating-system DNS resolution or
connection setup may overrun that budget; record such a failure as incomplete.
Save every bounded raw response before parsing, with its hash
and retrieval time, only inside protected, Git-ignored `data/raw/nyc_dof/`.
An interrupted run remains incomplete; a retry uses a new run ID.

Require a matching dataset ID and positive integer `rowsUpdatedAt` and
`viewLastModified` in each metadata response. The before/after values for a
view must agree. Require one aggregate object with only the seven registered
fields, a positive total count, non-null system-field counts equal to the
total, valid UTC bounds and minimum no later than maximum. If metadata
changes or any request/validation fails, report an inconclusive diagnostic,
not a historical absence of rows. Write a create-only manifest last. An
offline replay verifies each raw hash and regenerates the public aggregate
without network access. Publish only the validated aggregate projection,
response hashes and suppressed provenance. The full metadata response can
contain example addresses, unit numbers and prices in cached column content;
it must never be committed or copied to a public run directory.

## Interpretation and limit

If all current rolling rows share one creation timestamp, the result shows
only that the *current portal row instances* were created at that timestamp.
It cannot establish each sale's first public availability in an earlier
version, nor can it prove the exact upload method. Even a varied annualized
range describes current row instances, not old publication history. Keep
`historical_asof_eligible: false`; archived row-containing releases, a
publisher publication log or prospective snapshots are still needed. This
probe does not change the price or date semantics, rights decision, review
ledger, certified label count, U0 status or G-US status.
