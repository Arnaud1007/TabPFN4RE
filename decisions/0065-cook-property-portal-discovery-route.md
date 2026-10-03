# ADR 0065: Cook property portal as a manual document-discovery lead

Date: 2026-10-03
Owner: project implementation
Status: source-route decision; no row query or sale-label admission
Affected requirements: US02, US05, US07, US08, US24

## Context and evidence

The direct Cook Clerk recordings search returned HTTP 403 from this environment,
and the Clerk transfer list and instrument copies have documented prices; see
[ADR 0053](0053-cook-clerk-date-and-access-route.md). The private Cook/PTAX/
Additional PIN review queue remains unverified against a deed instrument.

The [county service page](https://www.cookcountyil.gov/service/property-tax-portal)
identifies the Cook County Property Tax Portal as a county collaboration. The
[Treasurer-maintained landing page](https://cookcountypropertyinfo.com/default.aspx)
accepts a 14-digit PIN or address and says its Documents, Deeds & Liens section
shows a summary of the most recent recorded documents and links to Clerk copies
available for purchase. Its [disclaimer](https://cookcountypropertyinfo.com/Disclaimer.aspx)
explicitly says displayed information is **not an official record**, is only
periodically updated and can be revised after audit or later events. The page
does not specify which document-summary fields appear for a particular PIN.

This inspection read only public landing, county-service and disclaimer pages.
No private PIN, address or document number was submitted; no result page or
instrument was accessed, and no purchase was made. The in-app browser was
unavailable in this environment, so this decision does not claim a working
interactive lookup here.

## Alternatives and choice

| Route | Current evidence | Decision |
| --- | --- | --- |
| Direct Clerk search/instrument | Read-only HTTP route blocked here; official copies may cost money | Retain as the authoritative-record target, pending access and budget |
| PTAX-203 and Additional PIN open data | Private bounded captures and an offline identity worklist exist; dates and scope remain unresolved | Continue separate source audit; do not treat a match as a deed |
| Treasurer property portal | County-endorsed recent-document summary, but not an official record | Use only as a possible **manual discovery lead** after an approved PIN query; never as a certified transaction or historical feature source |

The portal may help find a Clerk document reference for a specific sample row.
Even an apparent match cannot verify recorded versus closing date, gross
single-home consideration, first publication, arm's-length status or rights.
The v1 Cook review rubric stays unchanged and all 200 sampled rows remain
uncertified. No automatic scraper or bulk query is authorised by this decision.

## Next evidence

If the owner permits transmission of one private sample PIN to the official
portal, perform one bounded read-only lookup and preserve any returned row
details solely under ignored private storage. Record the exact fields observed,
access time, failure or result, and whether the page points to an official
Clerk instrument. Do not purchase a copy without a monetary budget. If no
usable route exists, ask the custodian for an authorised instrument-access
method. Independently obtain close-date, publication and dataset-rights
evidence before any sale-label construction.
