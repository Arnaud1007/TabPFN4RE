# ADR 0040: NYC instrument and date evidence boundary

Date: 2026-09-30
Owner: project implementation
Status: approved for U0 source qualification
Requirements: US03, US04, US05, US07, US08, US24
Affected protocols: none; `nyc-source-review-v1` and its ten entries remain unchanged

## Evidence checked

The [DOF property-sales glossary](https://www.nyc.gov/site/finance/property/glossary-property-sales.page)
defines `SALE PRICE` as the price paid and `SALE DATE` only as the date the
property sold. It does not identify that date as contract signing, closing,
deed execution, recording or first publication. Its address definition says
cooperative apartment numbers can appear in the address field. Its borough,
block and lot definitions identify tax property, not necessarily a unique
dwelling or one economic transfer.

The [official ACRIS detail-view guide](https://a836-acris.nyc.gov/AcrisHelp/docsearch/Documents/detailview.htm)
distinguishes `Document Date` (document execution) from `Recorded/Filed`
(recording time). It describes parcel, unit, partial-lot, correction and
cross-reference fields, and a separate `View Document` action when an image
exists. Neither indexed field is defined there as the sale closing date. The
[ACRIS service page](https://www.nyc.gov/site/finance/property/acris.page)
provides public document-image search in four boroughs and restricts
excessive automated downloading; Staten Island needs a different recorded
document route.

The existing one-home `nyc-source-lookup-v1` capture has hash-checked ACRIS
index responses and an offline replay, but no instrument image. The capture
ended `COMPLETE_ROUTE_ONLY` with document triage unfinished. It appended no
review and certified no sale label. Two attempts to open the ACRIS search
through the available browser tools failed before reaching the page (computer
use kernel-asset error and missing Playwright extension). These are access
failures, not evidence that the instrument is absent from ACRIS.

## Decision

Keep all NYC date, transfer-scope, unit-identity and first-availability
rubric dimensions `unknown` under ADR 0027. An ACRIS Master/Legals index lead
may identify a document for inspection and may independently identify its
indexed execution or recording event, but cannot by itself prove a matching
dwelling sale, gross consideration, arm's-length status, closing date or the
first publication of a DOF rolling row. Do not map `SALE DATE` to a 90-day
pre-close origin from the glossary alone. Do not use a deed execution date as
a substitute close date.

Do not create a generic affirmative v2 verifier from a user-supplied sidecar
and hash alone. A hash proves byte integrity after capture, not official
provenance or the truth of transcribed deed facts. Before any v2 promotion,
freeze the supported instrument format and capture route, retain immutable
official bytes and retrieval time in protected storage, inspect the actual
document, compare every linked property and unit with the pinned row, handle
multiple or partial interests and corrections, and use a specific parser or
independently checked page-referenced attestation. Preserve ambiguous and
missing cases as unresolved. A dated row-containing DOF release gives only an
availability upper bound; a first-publication claim needs evidence excluding
earlier releases. A close-date claim needs a source that actually defines or
records closing.

## Next dependency-ready work

Obtain one official instrument for the already frozen sample lead through a
permitted single-document route, or retain a bounded access-failure record.
Only then freeze and test an attested v2 comparison for that artifact type.
Pursue the existing DOF inquiry for sale-date meaning, historic row
publication, corrections, transfer grain and intended-use rights once an
authorized delivery route is available. In the meantime, v1 review forms can
document effort but cannot certify labels; prioritise evidence acquisition
before scaling the remaining 190 forms.

No U0 or G-US gate is accepted by this decision.
