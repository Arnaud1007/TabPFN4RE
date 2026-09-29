# ADR 0022: bounded NYC ACRIS linkage pilot

Date: 2026-09-29
Owner: project implementation
Affected requirements: US04, US05, US06, US07, US08 and US24
Protocol version: `nyc-acris-pilot-v1`

## Evidence and decision

The NYC rolling source's [200-row private audit sample](../runs/u0-nyc-review-sample-20260928T234700Z/report.md)
has no completed manual rubrics. The official [ACRIS service](https://www.nyc.gov/site/finance/property/acris.page)
offers property records and document images for Manhattan, Bronx, Brooklyn
and Queens. Its public [Master](https://data.cityofnewyork.us/City-Government/ACRIS-Real-Property-Master/bnx9-e6tj)
and [Legals](https://data.cityofnewyork.us/City-Government/ACRIS-Real-Property-Legals/8h5j-fqxa)
datasets provide a document ID, legal parcel rows, document date and recorded
date. The portal describes Master `document_amt` as *principal debt or
obligation*, not verified sale consideration. Legals may link several lots to
one document. No field gives each row's first public availability. ACRIS
records here do not cover Staten Island deed search; an empty result there
must never become evidence of no transaction.

Metadata and count-only API responses were saved privately and hashed on
2026-09-29. At this inventory, Master had 17,090,001 portal rows and Legals
22,761,783. These are mutable counts, not eligible transfers. Both portal
metadata records have a null licence field. Under [ADR 0020](0020-nyc-source-semantics-and-profile.md),
the permissible project action is a small internal source-qualification pilot;
releasable model use and redistribution still need a specific decision.

## Frozen pilot before sampled lookups

Use only the pinned rolling CSV SHA-256
`84c06057c52a2822f982cd98fb77ef7edf2c14134d00f46b073d2e4b762b2ef2`
and the private sample ledger SHA-256
`e137de2cf73aa4a9fea6d024e4564ef6e907020e73fc8dbec3e4026786b189ca`.
For each borough 1–4, choose the sampled row with the smallest stored sample
rank. This fixes **four pilot rows** before any ACRIS candidate is viewed.
If a chosen row lacks a complete numeric borough/block/lot, mark
`missing_identity` and issue no replacement query. Selected borough 5 rows
remain `acris_out_of_scope`; assess a Richmond County Clerk route separately.
The pilot is a route and ambiguity test, not a representative audit.

Use only the official NYC Open Data API, not automated document-image scraping
from the ACRIS application. For each eligible BBL, query Legals by exact
numeric borough, block and lot; request at most 251 rows so a 250-row cap is
detectable. Sort by document ID and retain selected fields only. A count above
250, incomplete page, malformed response or timeout is `unresolved`, not an
empty match. Fetch Master rows for candidate document IDs, retaining all
plausible document types and dates; never retrieve or select by closeness of
`document_amt` to the rolling `SALE PRICE`. Fetch every Legals row for each
candidate document ID to identify other lots and units; a 100-row cap must
likewise be detected. Bound the pilot to 50 HTTP requests, 1 MiB per response,
30 seconds per request and at least one second between requests. Stop at a
limit and record the unfinished state. Do not silently widen limits, paginate
away a saturated result or discard ambiguous candidates.

The review window is document dates from 365 days before to 365 days after the
rolling `SALE DATE`, used only to order *inspection*, not to exclude a later
deed or declare a match. Preserve all BBL-linked documents and their recorded
dates in private evidence. A later investigation may register a narrower
window after actual lag is measured. Treat mortgages, partial interests,
additional legal lots, blank or conflicting units and multiple plausible
deeds as ambiguity, not automatic price labels. A document date, recording
date and rolling sale date may all differ from the closing date.

## Privacy, output and stop rules

Store query URLs, BBLs, document IDs, selected rows and full bounded API
responses only under Git-ignored `data/raw/nyc_dof/`. Keep party names and
images out of this pilot. Tracked output may contain only counts by borough,
resolution status, document type and ambiguity reason, along with source,
query and private-artifact hashes, test results and failures. Never commit
individual ordinal, rank, address, price, date, BBL, unit or document ID.
Verify source and sample hashes before querying. Save responses atomically;
an incomplete request has a failed status, not a valid match. Replaying a
completed pilot must use the saved responses unless a new run ID declares a
new source snapshot.

The pilot can establish whether ACRIS is a feasible corroboration route.
It cannot complete the 200 manual rubrics, certify consideration or close
dates, supply first availability, establish commercial rights, accept U0 or
unlock real-data training. Any automated candidate link remains provisional
until a reviewer checks instrument and unit evidence. Record new access or
schema problems before expanding beyond these four pilot rows.
