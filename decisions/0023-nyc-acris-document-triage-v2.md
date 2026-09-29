# ADR 0023: versioned NYC ACRIS document triage pilot

Date: 2026-09-29
Owner: project implementation
Affected requirements: US04, US05, US06, US07, US08, US22, US24
Protocol version: `nyc-acris-pilot-v2`
Status: accepted for a bounded internal source-qualification pilot only

## Evidence and alternatives

[ADR 0022](0022-nyc-acris-linkage-pilot.md) froze four sampled rolling-sales
rows and a 50-request pilot. Its [v1 run](../runs/u0-nyc-acris-pilot-20260929T003102Z/report.md)
stopped after three requests: the first BBL produced 27 Legals rows referring
to 24 documents, and the first linked-document Legals response reached the
registered 100-row cap. That response body was not saved. The first Master
record had code `CDEC`. The [official 126-code inventory](../runs/u0-nyc-acris-codes-20260929T004355Z/report.md)
and [NYC ACRIS daily-file guide](https://a836-acris.nyc.gov/EDS/Overview/How%20To%20Process%20ACRIS%20Daily%20File%20v1%207.htm)
describe `CDEC` as CONDO DECLARATION, despite placing it in the broad DEEDS
AND OTHER CONVEYANCES class. A class-only filter would repeat the failure.

The options were to widen every linked-Legals cap, replace the difficult
sampled property, or inspect document types before fetching all linked lots.
Choose the third option. Preserve v1, its two saved responses and failure
status unchanged. Do not edit its hashed collector, tests or ADR. The same
four rows remain selected by the v1 pinned CSV and sample-ledger hashes;
Staten Island remains outside ACRIS deed-search coverage. No replacement row
may be chosen after seeing the v1 failure.

## Frozen retrieval and triage rules

Use the pinned code-table rows SHA-256
`518363532df753ac364ce47c5d62dfbdbaf609b598845bfcfe2ec83b9739c625`.
Verify all three private input hashes before any request. For each selected
row, retain the original source values privately. Never use sale-price
closeness, `document_amt`, or a later outcome to retrieve or rank a document.

1. Query exact numeric borough, block and lot in Legals for **all four**
   selected boroughs before fetching any Master row. Request 251 rows per
   BBL; more than 250 means `saturated_bbl`, not an empty match. Preserve
   every returned document ID, including duplicate Legals rows, privately.
   If a pinned selected row has missing or invalid BBL components, record
   `missing_identity` as unresolved without making a fabricated request;
   the overall run is `INCOMPLETE_ERROR`.
   Validate each ID against `[A-Za-z0-9_-]{1,64}` before building an encoded
   query; a malformed ID produces a private unresolved failure, never a
   constructed SoQL expression or a printed diagnostic containing that ID.
2. For each nonsaturated BBL, retrieve Master records for **every** distinct
   returned document ID where the budget permits, in sorted batches of at
   most 10 IDs. Schedule batches round-robin starting with boroughs 1, 2, 3,
   4 and repeat. If one ID appears under several selected BBLs, assign its
   request to the lowest numbered borough, fetch it once, then attach the
   saved Master result to every referring BBL. A batch asks for at most 31
   rows and treats more than 30 as saturated. Validate every
   returned document ID against the requested set; missing, duplicate,
   malformed or conflicting records remain unresolved. Unvisited IDs remain
   `not_inspected_budget` in private state, rather than silently classified.
   The v2 Master `$select` excludes `document_amt`; it retains document ID,
   record type, exact document code, document/recording dates, transfer
   percentage and correction fields needed for this route audit. A BBL HTTP or
   schema failure does not prevent attempts for the other selected BBLs,
   but makes the whole run incomplete.
3. Compare the exact uppercased, trimmed `doc_type` with this **primary
   inspection queue**: `DEED`, `DEEDP`, `DEEDO`, `DEED, RC`. The official code
   table describes these as deed variants. A queued record is a document for
   manual inspection, not a certified sale. Other and unknown codes, including
   `CDEC`, remain uninspected unresolved context, never negative matches.
   A primary document stays provisional when another conveyance code on
   its BBL remains unresolved. Broad class membership is never used to
   certify a transfer or to infer an empty result.
4. Fetch all linked Legals for primary-queue documents only. Schedule one
   document at a time round-robin through boroughs 1, 2, 3, 4. Within each
   borough deduplicate a document already scheduled from another selected
   BBL, then attach its one saved linked-Legals result to every referring
   BBL. Sort each borough's queue by (date bucket, absolute day distance,
   document ID): bucket
   0 is one valid Master `document_date` within 365 days of the rolling
   `SALE DATE`, bucket 1 is a valid date farther away, and bucket 2 is
   missing or malformed date. Parse rolling dates as MM/DD/YYYY and Master
   dates as ISO YYYY-MM-DD. Conflicting or duplicate Master rows stay
   unresolved and do not enter the primary queue automatically. Use date
   proximity only to prioritize inspection.
   Never exclude a candidate because its document date is outside 365 days.
   Request 101 linked rows per document; more than 100 is `saturated_document`
   and the response is retained privately. Record additional lots, partial
   interests, blank/conflicting units and multiple deed candidates as
   ambiguity. No primary deed or an exhausted request budget means
   `needs_manual_review` or `unfinished`, never `no sale` or `no match`.

Reserve up to 4 requests for the four BBL queries, up to 30 for Master
batches and up to 16 for linked Legals. Unused capacity in a phase is not
borrowed by an earlier phase; this protects a linked-Legals inspection window
from one dense BBL. The whole run permits at most 50 HTTP GET requests, a
1 MiB response-read cap, a 30-second timeout per request, a maximum
4,096-character URL and at least
one second between requests. Use only the official NYC Open Data Master and
Legals HTTPS endpoints. Reject redirects. A 1 MiB read limit is checked
before parsing; an oversized response is a recorded bounded truncation and
unresolved. Do not widen these caps or fetch images/party tables in this run.

## Crash recovery, privacy and acceptance

Before each request, atomically save a private intent with its exact query,
phase and sequence. Atomically save bounded response bytes and SHA-256 **before**
JSON, schema or saturation validation. Save bounded HTTP error bodies when
available; a timeout has no invented body. Verify that the local private
directory has restricted access before saving a response; unexpected fields
or personal data in a failed response are forensic bytes only and rejected
for downstream use. Logs expose only a fixed error category and response
hash, never an error body or query. An intent with no durable response after
a crash is `attempt_outcome_unknown_no_body`, not a request to retry
automatically. Preserve an orphan response file for private reconciliation;
never attach it to an intent by guessing.
A crash, timeout, HTTP error, malformed response or failed validation leaves
the run `INCOMPLETE_ERROR`; other BBLs may still be inspected within the
registered budget. Offline replay recomputes statuses and aggregates from
the ordered intents and saved bytes, and verifies hashes; it never trusts a
saved summary or automatically retries a failed request. A new source
snapshot or configuration requires a new run ID.

All BBLs, sample ordinals/ranks, document IDs, dates, prices, units, query
URLs, response bytes, per-borough outcomes and review notes stay in
Git-ignored `data/raw/nyc_dof/`. The four deterministic selected rows are
potentially re-identifiable from the public selection rule. Tracked results
therefore contain hashes, total requests, overall completion/failure status,
tests and protocol identity, but **no property-linked counts or document-type
breakdowns** from this four-row pilot. A later larger audit may publish a
fixed-category cell only when at least five distinct properties contribute,
under a separately frozen disclosure rule. Do not print an arbitrary API
value in an exception, log or aggregate. The four rows are a route/ambiguity pilot,
not a representative audit. The separate 200-record manual rubric remains
at zero completed reviews until people actually inspect those records.

Write synthetic tests before implementation for the same-row selection,
four-BBL-first order, batch completeness and duplicate detection, `CDEC`
triage, other-code unresolved status, multi-lot deed, blank unit, saturation,
redirect, failure-body preservation, request cap, crash recovery and offline
replay. Commit and push the new v2 collector and tests before any v2 sampled
lookup. Use `COMPLETE_ROUTE_ONLY` only when all four BBL requests, every
scheduled Master batch and every primary linked-Legals request have completed
without transport or schema failure, and every attempted response has a
private body or explicit no-body reason. A valid saturated response remains
unresolved and retained; it does not certify a transaction. A request-budget
stop with pending IDs or primary documents is `PARTIAL_BUDGET`. Any failed
validation or transport request is `INCOMPLETE_ERROR` regardless of other
completed requests. Store separate private flags
`four_bbl_queries_finished`, `document_triage_finished` and
`manual_review_pending`; a finished bounded request schedule is not a
completed manual audit. Set `document_triage_finished=false` when any BBL,
Master batch or linked document is saturated or remains uninspected, even
if all bounded requests were attempted. All terminal states keep manual
reviews and
certified sale labels at zero until separately evidenced.

This source qualification cannot establish a verified sale price, closing
date, first public availability, historical as-of correctness or commercial
reuse. The official daily-file guide says a record can be recorded **or
updated** on a business day; its current presence does not prove first
availability. U0 and G-US remain pending regardless of the v2 route result.
