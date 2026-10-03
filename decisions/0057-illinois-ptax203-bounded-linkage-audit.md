# ADR 0057: bounded Illinois PTAX-203 linkage audit

- Date: 2026-10-03
- Owner: project implementation
- Affected requirements: US02, US03, US05, US06, US07, US08, US24
- Protocol: `illinois-ptax203-link-v1`

## Context and alternatives

The public Illinois Department of Revenue `PTAX-203, 203-A, and 203-B`
dataset (`it54-y4c6`) exposes declaration-level fields missing from the Cook
Assessor sale feed: a declaration ID, recording and instrument dates, document
number, primary PIN, parcel count, transfer flags and consideration. The
official metadata says it is updated weekly, covers records filed since 2013,
is published, and has `licenseId: PUBLIC_DOMAIN`. It also has party names,
addresses and preparer fields that are unnecessary for this audit.

The options are to ignore the source, ingest the entire 183-column table, or
test a restricted link against the existing Cook sample. The last option
tests whether the independent declaration can improve source qualification
while limiting data retained. The [frozen plan](../runs/u0-illinois-ptax203-link-v1-20261003T032248Z/plan.md)
defines the read-only request and review caps before capture.

## Permitted-use and data decision

Permit a bounded private research audit of exact document-number matches for
the 100 already captured Cook sample rows from 2024 and 2025. The selected
PTAX fields exclude parties, full address, legal description and preparer
details. Retain row values and request URLs only under ACL-restricted,
Git-ignored `data/raw/illinois_ptax203/`. No raw declaration or matched Cook
row may enter Git or a public report. The explicit Public Domain metadata
supports this restricted source audit; commercial deployment still requires a
release-specific source and privacy decision. The Cook Assessor dataset keeps
its separate unresolved rights status.

## Interpretation boundary

IDOR's [PTAX-203 instructions](https://tax.illinois.gov/localgovernments/property/general-information/ptax-203_instructions.html)
describe Line 11 as full actual consideration, including specified exchanges
and outstanding mortgages and excluding certain buyer credits for repairs.
It is a **declaration-level** amount. Multiple parcels or interests cannot be
allocated to an individual home without evidence. `date_recorded` is a
recording date. Line 4 is the instrument's month/year, even if the data schema
renders it as a date. Neither establishes a closing date. Dataset publication
and system timestamps do not prove each row's first public availability at a
past 90-day origin.

Exact document-number agreement is a candidate link, not an identity proof.
County, PIN, date, price and parcel-count diagnostics may reject or quarantine
candidate links, but cannot automatically certify labels in v1. Preserve
source values and counts even if matching fails. The public result always
reports zero certified sale labels and no historical as-of eligibility.

## Acceptance and next decision

Tests and offline replay must verify the frozen Cook sample, exact selection,
query allowlist and caps, metadata stability, source response hashes, private
ACL, join cardinality and aggregate privacy. Failure stays incomplete; a
revised request needs a new protocol. After the probe, decide whether a
record-by-record manual PTAX/Cook review and Additional PIN linkage is
worthwhile. Do not start model training from this audit.
