# ADR 0074: MyDec public declaration search as a Cook audit route

Date: 2026-10-03

Owner: project implementation

Status: verified public search access; no declaration queried

Requirements: US02, US05, US07, US24
Affected protocols: none; Cook/PTAX samples and eligibility are unchanged

## Evidence

The [Illinois Department of Revenue's MyDec guidance](https://tax.illinois.gov/localgovernments/property/property-transfer-tax-declarations-and-mydec.html)
says recorded Illinois PTAX-203/203-A/203-B and, where applicable, Cook
County and Chicago transfer declarations can be searched without a login.
The [IDOR data-file guidance](https://tax.illinois.gov/localgovernments/property/mydecdatafiles.html)
says the open declaration files cover 2013 onward, are updated weekly and
have **not** been accuracy-verified by IDOR. It also distinguishes additional
PIN and personal-property companion tables.

The [bounded public-home capture](../runs/u0-mydec-public-access-v1-20261003T142501Z/plan.md)
reached the MyDec home screen in an isolated local browser. Its protected DOM
contains one enabled link labelled “Search for Illinois, Cook County, and
City of Chicago Real Estate Transfer Declarations.” A direct navigation to
the link's internal hash returned the home view again; that failed route is
retained under the [search-entry plan](../runs/u0-mydec-search-entry-v1-20261003T142900Z/plan.md).
The subsequent [browser interaction](../runs/u0-mydec-browser-click-v1-20261003T143000Z/report.md)
clicked that public link and reached a search view with **PIN Search**,
**Document Number Search** and **Address Search** options. The captured view
includes **Primary PIN** and **County** fields. No identifier, login or query
was submitted. Private DOMs, browser profiles and manifests remain under
Git-ignored `data/raw/illinois_mydec/`; public reports contain only hashes
and non-property field names. The isolated browser profiles remain locally
because a scoped cleanup command was rejected by automatic approval review;
see the [deviation record](../runs/u0-mydec-browser-click-v1-20261003T143000Z/deviation.md).

## Decision

Use MyDec as a candidate **declaration-representation check** for an already
frozen Cook/PTAX lead. Prefer a document-number lookup to avoid submitting a
PIN or address. A future one-record query needs a separately frozen selector,
an explicit one-query cap, an authorised handling decision for its identifier
and protected capture of any result. The public search view alone is not a
matched declaration, instrument or property.

Even a matching declaration would corroborate filed fields rather than prove
the deed, closing date, arm's-length single-home scope, first publication,
historical characteristic availability or dataset-specific permitted use.
No Cook row becomes a certified sale label through this route. Keep U0 and
G-US pending and retain the Clerk instrument and custodian clarification as
the authoritative evidence targets.

## Follow-up: document-number tab access

The [bounded document-tab check](../runs/u0-mydec-document-form-v2-20261003T144507Z/report.md)
did not establish the document-number form in this headless environment. Two
different click targets returned successfully, but the saved DOMs still
marked that tab not selected. No identifier was submitted. This does not
disprove IDOR's public search claim; it makes a document-number lookup
**not yet runnable here**. Keep the document-number preference, but require a
verified selected form or an official alternative route before querying.
