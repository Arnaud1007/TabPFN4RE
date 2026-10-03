# ADR 0071: ORPTS report definitions narrow, but do not qualify, Sales Web

Date: 2026-10-03
Owner: project implementation
Status: verified official documentation; current export unverified
Affected requirements: US03, US05, US07, US08
Affected protocols: none; no source row, label, split or model result changes

## Evidence and alternatives

The New York State Department of Taxation and Finance's
[List of Arm's Length Sales quarterly-report guidance](https://www.tax.ny.gov/research/property/assess/sales/qr1.htm),
updated 4 March 2026, provides a direct official definition that the older
SalesWeb dictionary could not yet supply by accessible download. Item 7 maps
the report's Sale Date to RP-5217 item 12, date of transfer, and Deed Date to
item C2, county-clerk recording. The
[RP-5217 instructions](https://www.tax.ny.gov/pdf/current_forms/orpts/rp5217pdfins.pdf)
define item 11 as contract date and item 12 as title conveyance, generally
the closing date. These are distinct dates.

The same report guidance says book/page is used to match local corrections to
ORPTS sales and warns that an incorrect value can misapply a correction. It
also describes a failure mode in which a part-of-parcel flag is overwritten
by an incorrect one-parcel update. The report's property-use code 210 means a
one-family year-round residence at the time of sale. These definitions make identity,
transfer scope and source corrections explicit audit questions rather than
assumptions based on a column name.

RP-5217 item 13 defines full sale price and instructs filers to exclude seller
concessions. The quarterly guidance says some 100%-financed transactions have
included concessions and that a discovered error should be corrected for
ORPTS ratio work. Therefore the form instruction alone does not prove every
stored price is concession-correct. Personal property is reported separately
on RP-5217 item 14, but the current Sales Web export's adjustment semantics
remain unverified.

One option was to treat these official form and report definitions as the
current Sales Web Excel column contract. That is unsupported: no current
export, schema or row has been inspected, and Sales Web may present corrected
values or different field names. The chosen interpretation is narrower.

## Decision and required checks

Use the report and form to define the *candidate* date and price checks for a
bounded Sales Web sample. Before source admission, verify on actual exported
rows and, where possible, underlying instruments:

1. Whether current `sale_date`, contract date and deed date map to the form and
   report fields after corrections, with missing and changed values preserved.
2. Whether current sale price includes or excludes seller concessions and
   personal property, and whether correction history is recoverable.
3. Whether book/page, SWIS and parcel identifiers identify one economic
   transfer and one eligible home, including multi-parcel and part-parcel
   cases; do not use a one-parcel flag as proof by itself.
4. Whether class-at-sale and arm's-length fields can define the existing
   one-family cohort without relying on a later assessment-roll class.
5. First public availability, rights and historical attribute vintages.

This documentation establishes no record-level first-publication time, no
dataset-specific reuse right and no verified current export mapping. No
property row was requested or acquired for this decision. Sales Web remains
inventory-only, with zero certified sale labels and U0/G-US PENDING. The
[source card](../data/source_cards/nys_salesweb.yaml) and
[ADR 0066](0066-nys-salesweb-source-feasibility.md) retain its other limits.
