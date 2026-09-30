# One-home NYC source-lookup capture plan

Run ID: `u0-nyc-source-lookup-live-v1-20260930T193830Z`  
Frozen before the first live GET: 2026-09-30 19:38:30 UTC  
Status: **planned, internal U0 source qualification only**  
Protocol: `nyc-source-lookup-v1`, [ADR 0037](../../decisions/0037-nyc-bounded-review-lookups.md)  
Collector code commit: `9aa6f5d3f6eeab299d68dd16042edf5dceb258d9`

## Cohort and operation

Use the pinned NYC rolling CSV, frozen 200-entry review sample, live protected
review ledger and pinned ACRIS code table. The checked-in collector validates
their hashes and selects exactly one lowest-ranked untouched row in ACRIS
boroughs 1–4. No ordinal, address, BBL, price, unit or document identifier is
chosen or written in this public plan. Save the selected row and every request
or response only under an opaque, Git-ignored, ACL-protected private run ID.

Make only official ACRIS index GETs via the exact Legals → Master → linked
Legals route. A single capture invocation is permitted. If an intent or body
is left pending, preserve it; replay without network and reconcile it before
any new capture. No automatic retry, hidden fallback or parallel capture.

## Limits and adoption rule

Maximum 50 GETs total, with phase caps of 1 BBL, 30 Master and 16 linked
requests; 30-second timeout, one-second pacing including before first GET,
4,096-character URL limit and at most 1 MiB plus one byte of each response.
The private global lock serializes captures. Abort if available disk drops
below 50 MiB before the invocation. No paid service or credential is used.

Capture and offline replay must agree on the private aggregate and verified
response hashes. Public output remains `private_only_v1`, with zero appended
review forms and zero certified sale labels. Even a complete index route is
only a review lead. The next manual rubric remains subject to ADR 0027;
transaction identity, consideration scope, closing date, first publication
and dataset-specific rights cannot be inferred from this index lookup.

G-US and U0 stay **PENDING**. Failure is retained as a result. A later
protocol correction requires a new run ID and cannot overwrite this attempt.
