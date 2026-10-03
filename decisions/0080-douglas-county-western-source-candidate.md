# ADR 0080: Keep Douglas County downloads at metadata-only qualification

Date: 2026-10-03
Owner: project implementation
Status: source candidate recorded; acquisition and admission pending
Affected requirements: US02, US05, US06, US08, US24
Affected protocols: none

## Evidence

The [Douglas County Assessor download page](https://www.douglasco.gov/assessor/data-downloads/)
lists current Property Sales and Property Improvements text files. It calls
them database records for **active accounts only**, gives an update date, and
disclaims their accuracy and timeliness. The sales field list includes
`Account_No`, `Sale_Date`, `Sale_Price`, `Deed_Type` and recording references.
The improvement list includes `Account_No`, `Building_ID`, area and age fields.
The [metadata-only run](../runs/u0-douglas-co-source-feasibility-v1-20261003T172000Z/report.md)
records the exact file URLs and HTTP HEAD responses without downloading rows.

The [Assessor FAQ](https://www.douglasco.gov/assessor/about/assessor-faqs/)
explains that its valuation study uses a contractual price adjusted for
personal property and financing before time adjustment. It does not define
the downloadable `Sale_Price` field. The page offers files for public
reporting. The [County Open Data Guidelines](https://www.douglasco.gov/documents/open-data-guidelines.pdf/)
allow use without licence restrictions for data **on its Open Data Portal**,
but the assessor's direct text-file route is not identified there as a portal
dataset. Whether that rule covers these files and commercial AVM use is
unconfirmed. File update and Last-Modified times do not prove
first publication of a particular sale or historical property attribute.

## Alternatives and decision

1. Download full sales and improvement files now. This could expose row
   structure, but the two files together exceed 140 MB, include party names
   in the sales schema, and still would not resolve historical availability,
   label semantics or rights. Deferred.
2. Treat the monthly update and current attributes as historical vintages.
   This would introduce look-ahead and active-account survival bias. Rejected.
3. Record the source and metadata, then seek a minimized rights-cleared route
   and dated historical files. Chosen.

Rank this candidate as a Western alternative ahead of the more restricted
King County download route in the acquisition backlog. The rank is a
feasibility judgment, not source admission. Before any row-level acquisition,
verify commercial and redistribution permissions, `Sale_Date` versus close
and recording, gross versus adjusted `Sale_Price`, transfer scope, account
stability, deletion of inactive accounts, historic extract availability and
improvement vintages. A bounded 200-record manual audit and cardinality check
must precede model training. No sale labels are certified by this decision.
