# U0 Hillsborough Clerk linkage feasibility check

Run ID: `u0-hcpa-clerk-spotcheck-20260928T171047Z`

Status: one partial source comparison; zero completed 200-record review rubrics.
U0 and G-US remain pending.

## Source and action

The [official Clerk public-data guide](https://hillsclerk.com/records-and-reports/public-data-files)
describes daily `D`, `P` and `M` files. The [public directory](https://publicrec.hillsclerk.com/OfficialRecords/DailyIndexes/)
displayed `D` files dated 2026-07-27 through 2026-09-17 on 2026-09-28.
The [Official Records Index](https://www.hillsclerk.com/propertyrecords-and-recording)
provides a separate instrument search. A direct lookup for one selected HCPA
instrument timed out from this environment; no record was obtained through
that route.

A second selected entry was within the daily-file window. A read-only search
of its instrument number in the appropriate official `D` file found one deed
row. The HCPA and Clerk instrument numbers and numeric amounts agreed. HCPA's
`S_DATE` was one calendar day before the Clerk's displayed recording date.
The Clerk legal description referred to a condominium, outside the initial
single-family product cohort. The row-level number, amount, date and legal
description are retained only in the Git-ignored private observation at the
path and SHA-256 recorded in [manifest.json](manifest.json).

The [aggregate checks](checks.json) record these observations without a
property identifier. A first draft private observation compared amount
strings with different decimal formatting and falsely marked them unequal.
That draft is retained as rejected; revision v2 compares `Decimal` amounts
and is the referenced evidence. The sample file itself was not modified.

## Limits

Instrument and amount agreement is a useful linkage clue, not proof that the
same unit or a single-home economic transfer was identified. No deed image,
execution date, closing date or source-specific reuse right was verified. The
official daily file was viewed but could not be downloaded and hashed locally;
its directory modification timestamp does not establish original publication.
Neither this spot check nor the remaining unreviewed sample can enter an
as-of-certified training or test cohort. The 200-record manual audit remains
at zero completed full rubrics.

## Next action

Use an accessible authorised route to review the remaining HCPA sample
entries against Clerk instruments, including book/page fallback and document
images where publicly available. Record unit/parcel scope, event-date
meanings, price basis and unresolved evidence for each. Retain row-level notes
privately and report aggregate outcomes, source hashes and exclusions.
