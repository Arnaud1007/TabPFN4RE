# ADR 0066: New York State Sales Web is a separate US source candidate

Date: 2026-10-03
Owner: project implementation
Status: approved for U0 documentation review only
Requirements: US03, US05, US07, US08, US11, US24
Affected protocols: none; no source rows, splits or model results change

## Evidence and scope

The [current Municipal Data Portal description](https://www.tax.ny.gov/pit/property/munidataportal.htm)
states that Sales Web contains ten years of New York State property transfers
**outside New York City**. It describes weekly updates, a lag of several weeks,
corrections after local review, and an Excel download of search results. Its
source is a deed and the RP-5217 transfer report forwarded through county and
state offices. An [older SalesWeb FAQ](https://www.tax.ny.gov/research/property/assess/sales/salesweb.htm)
describes CSV bulk periods and a 3,000-result search limit, but the current
portal may differ. No export or property row was acquired for this decision.

The official [RP-5217 instructions](https://www.tax.ny.gov/pdf/current_forms/orpts/rp5217pdfins.pdf)
distinguish contract date from title-conveyance date, which is generally the
closing date, and define full sale price, personal property and transfer
conditions. Search-indexed text of an official but older
[SalesWeb field dictionary](https://swcf.orpts.ny.gov/cfapps/salesWebProd/salesWeb/datadict.pdf)
describes a sale-price field net of personal property and date, parcel,
arm's-length and update fields. Direct PDF retrieval failed in this audit;
these field claims remain provisional until the actual current export or a
publisher-confirmed dictionary is archived. Whether a price net of personal
property matches the primary target also needs an explicit cohort decision.
The later [ADR 0071](0071-nys-orpts-report-date-price-boundary.md) adds direct
official quarterly-report date, price and correction guidance, while keeping
the current Sales Web Excel mapping unverified.
The indexed dictionary calls the recorded-deed field `deed_date`, uses
`1950-01-01` for a missing contract date, and separates property class at
sale from class on the last roll. The sentinel cannot be treated as a real
contract date, and last-roll class cannot be assumed available at an earlier
origin.
The state's [sales usability rules](https://www.tax.ny.gov/research/property/assess/sales/salescriteria.htm)
distinguish arm's-length exclusions from ratio-program exclusions; neither is
an automatic eligibility policy for this product.

This source could add Northeast metropolitan and nonmetropolitan cohorts. It
cannot provide NYC sales or alone satisfy G-US coverage across four Census
regions. Its current exported schema, transaction-to-dwelling cardinality,
historical attribute vintages, exact first public availability and
dataset-specific commercial or redistribution rights remain unresolved. A
legacy dictionary `load_date` is not evidence of the first date the public
could see a row. The general [website disclaimer](https://www.tax.ny.gov/help/tech/disclaimer.htm)
does not establish a reuse grant.

## Decision

Add Sales Web to the US acquisition backlog as a distinct candidate. Do not
admit it as a canonical transaction source, train on it, or include it in a
frozen service area yet. Keep NYC and Staten Island outside its scope.
Exclude party and preparer identities from any later bounded research extract.

The next source decision requires a verified current export schema, access
and reuse terms, a bounded acquisition protocol, source-date and
first-availability evidence, and a 200-record stratified audit. If only
current snapshots can be obtained, record their capture times and evaluate a
prospective or separately named monthly-origin benchmark; do not reconstruct
earlier public availability from a present-day download.
The [source inquiry](../data/requests/nys_salesweb_inquiry_draft.md) is ready
for owner review but remains unsent.

**Zero new sale labels are certified. U0 and G-US remain PENDING.**

## Current static UI asset check, 3 October 2026

The live portal served a 1,378,915-byte
[JavaScript asset](https://pad.tax.ny.gov/base/js/spa.js) with SHA-256
`36af85aa06fce5839eec5a0adb354548cafd8adc2e2db410dd40bc810773627c`.
The [bounded label inventory](../runs/u0-nys-salesweb-ui-v1-20261003T115547Z/observation.json)
records current static strings for sale, contract and deed dates; sale price;
property class at sale; part of parcel; an arm's-length indicator; sale loaded
to database; and last update to sale. The bundled help text describes the
sale-loaded date as the date New York State initially entered or loaded a sale.
This is a portal-side ingestion timestamp candidate, but the asset does not say
when a row first became public. It does not prove the current Excel export
includes those columns or that their values retain the older dictionary's
semantics. No property row, export, or API response was acquired, and the
documentation-only source decision above is unchanged.
