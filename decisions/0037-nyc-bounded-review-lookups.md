# ADR 0037: bounded NYC source lookups for the manual review sample

Date: 2026-09-30
Owner: project implementation
Status: approved for an internal U0 source-qualification run only
Protocol: `nyc-source-lookup-v1`
Requirements: US04, US05, US07, US08, US22, US23, US24

## Context and decision

The ACRIS v2 collector is fixed to one sampled property in each of four
boroughs. Its keys conflate properties if used for more than one home in a
borough. Its failed run remains immutable. Ten separate `nyc-source-review-v1`
forms now document review effort, with zero certified sale labels. The first
form batch used bounded but unretained one-off request code. A checked-in
collector is needed before further automated lookups.

Use one frozen sample ordinal per `nyc-source-lookup-v1` run. Verify the pinned
rolling CSV, the 200-entry sample and the private review ledger/manifest before
any HTTP request. Select the lowest frozen sample rank among entries without a
complete current review in ACRIS boroughs 1-4. Do not accept an ordinal, BBL,
document ID or URL on the public command line. Freeze the selected source row,
review-ledger bytes/hash and request configuration privately before networking.
If the selected row lacks a valid positive BBL, record `missing_identity` and
make no request. An invalid sale date records `missing_date` before any GET;
the date cannot be used to prioritise deed leads. A later run may select the
next row only after a valid review
entry changes the live ledger; do not skip a difficult row to improve results.

Staten Island is outside ACRIS coverage and needs a separately qualified
Richmond County adapter. This runner must neither claim to cover it nor infer
an empty deed history. The prior Richmond HTML index lookups remain private
leads, not verified instruments.

## Retrieval and budgets

For a valid BBL, query exact ACRIS Legals first with a 251-row limit. A
response above 250 rows is saturated and must not drive candidate exclusion.
For an unsaturated response, retain every returned document ID, then query all
distinct IDs in sorted batches of at most ten via Master, subject to a maximum
of 30 Master requests. Missing, conflicting or duplicate Master records remain
unresolved. Use only exact deed codes `DEED`, `DEEDP`, `DEEDO` and `DEED, RC`
to queue linked Legals requests; other codes remain unresolved context.
Prioritise queued deeds by documented date proximity to the pinned row's
published sale date, then document ID. Never retrieve or rank by price or
`document_amt`. At most 16 linked requests are allowed. A response above 100
linked rows is saturated, retained and unresolved.

The total cap is 50 GETs, each with a 30-second timeout, at least one second
between requests including across sequential runs, a 4,096-character URL cap
and at most 1 MiB plus one byte read. A private global lock prevents
concurrent captures; each run waits one second before its first GET. Permit
only the two official NYC Open Data HTTPS resource endpoints;
reject redirects. Preserve a private intent before each request and bounded
response/error bytes with a hash before parsing. A timeout or crash after an
intent with no durable body is an unknown outcome. Never retry it implicitly.
Response caps, schema errors, transport failures and unmet phase budgets are
explicit unresolved states, not negative transaction matches.
If a process dies with the global lock present, inspect the private state and
process status before manual lock removal. Never remove a lock just to force
another network request. Use an opaque run ID in commands and reports.

## Evidence and privacy

Use a protected, Git-ignored private run directory with a create-only start.
Offline replay verifies the frozen inputs, exact request sequence and every
saved response hash, derives the same status without network, and makes no
write. A later corrected run uses a new ID; a failed run is not overwritten.
The CLI's public output is a fixed `private_only_v1` projection with protocol,
zero appended reviews and zero certified labels. Route state, request count,
source/ledger hashes, ordinals, addresses, BBLs, units, document IDs, URLs,
body bytes and per-property results remain private. A zero exit means capture
or replay evidence integrity completed; private route quality and triage do
not affect the exit code. A nonzero exit means command or integrity failure,
and never asserts an absent transaction. No row-level counts or findings are
published from a one-home run.

The collector never appends a review form, asserts a matched instrument or
certifies a sale, close date or first-publication time. ADR 0027 still makes
every `nyc-source-review-v1` rubric dimension except the pinned row's reported
price state `unknown`. A reviewer may cite these index attempts in a later
attested form, with the unresolved limitation. Dataset-specific reuse rights
and historical availability remain separate U0 dependencies.

## Acceptance before the first live lookup

Write synthetic tests before implementation for pinned-input and sample-rank
checks, deterministic untouched selection, wrong BBL, saturation, duplicate
Master IDs, other document codes, multi-lot and blank-unit ambiguity, bounded
transport, intent-before-GET, body-before-parse, crash replay, hash tampering,
path/ACL checks and public redaction. Commit and push reviewed code before
reading another sampled row through this runner. Freeze a public run plan and
resource budget before the first live request; publish actual result and
failed attempts without turning route completion into U0 acceptance.
