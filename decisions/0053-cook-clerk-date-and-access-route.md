# ADR 0053: Cook Clerk date and access route

Date: 2026-10-03

Owner: project implementation

Affected requirements: US02, US05, US07, US08, US24

Affected protocols: `cook-source-review-v1` is unchanged; `cook-clerk-public-docs-v1`
adds source feasibility evidence only. No frozen split, label rule or feature
policy changes.

## Context and alternatives

The Assessor's current Parcel Sales feed describes `sale_date` as recorded
rather than executed. It has no checked row-level first-publication timestamp,
and the 200 private source rows are not certified one-dwelling sale labels.
The question is whether the Clerk offers an authoritative date and instrument
route that can clarify selected rows without silently spending money or
admitting an incompatible date as the project's closing date.

Considered: continue with Assessor rows alone; inspect individual Clerk
recording results and non-certified copies; or acquire the Clerk's monthly
deed-transfer index. The first cannot resolve execution versus recording.
Individual copies can support a small audit but have a documented fee, and
the search portal still needs a working access path. The transfer-list product
could support systematic linkage, but needs a paid license and its published
summary does not identify a closing date.

## Observed primary evidence

The [bounded source capture](../runs/u0-cook-clerk-public-docs-v1-20261003T014926Z/report.md)
saved four official public documents privately and verified their bytes. The
[Clerk search page](https://www.cookcountyclerkil.gov/recordings/search-recordings)
links to the separate recording search and describes searches by PIN, address,
party or other indexed detail. The
[transfer-list summary](https://www.cookcountyclerkil.gov/publication/transfer-list-license-agreement-summary)
lists monthly deed-transfer indexing data with document number, consideration,
PIN, execution date and recording date, among other fields. It states a USD
400 annual fee and a license agreement. The document itself does not list a
contract/closing date or row-publication timestamp. Address is specifically
described as outside the Clerk's own index.

The [Clerk fee page](https://www.cookcountyclerkil.gov/recordings/recording-fees)
lists USD 5 for a non-certified electronic document copy, plus an online
card fee. The [FAQ](https://www.cookcountyclerkil.gov/recordings/recording-faqs)
says online document purchases cover records after 1985 and corrections to a
previously recorded document can involve a separate new instrument or
affidavit. These are publication and access facts, not an inspected deed or
a tested match to an Assessor row.

The direct shell request to the Clerk's separate recording-search endpoint
returned HTTP 403 in this environment. No browser-control surface was
available in this session. Neither observation proves the portal is generally
unavailable; no row-specific Clerk lookup was completed.

## Choice and boundary

Keep the Assessor capture as a private source audit. Record the Clerk transfer
list as a **paid, unacquired candidate** and the copy service as a **fee-based
manual audit route**. Do not purchase, subscribe, accept a license, request a
document copy, join a Clerk record, complete a manual rubric from these
generic pages, or promote an Assessor sale label on this evidence.

Execution date is distinct from recording date, but neither is automatically
the closing or contract date required by US03. A future licensed sample would
need its own rights decision, exact snapshot and publication rule, audit of
document/PIN cardinality, transaction scope and date semantics. A future
individual instrument would require a row-specific, preserved comparison.
Until then, the primary 90-day close-origin benchmark remains blocked for
these rows and U0/G-US remain pending.

## Next decision

Continue the 200 private source-review rubrics without inventing instrument
facts. Ask the relevant custodians about close-date meaning, historical
publication, correction and permitted use through the prepared unsent inquiry
when a user-approved delivery route is available. If paid Clerk data would
materially resolve those questions, present the exact fields, license and
budget as a separate acquisition decision. Continue independent US pipeline
work meanwhile.
