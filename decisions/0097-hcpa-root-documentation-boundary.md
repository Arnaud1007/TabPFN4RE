# ADR 0097: HCPA root documentation narrows the source boundary

Date: 2026-10-05
Status: accepted
Requirements: US05, US07, US08

## Context

The HCPA public-download root lists `_Documentation.doc`, but the All Sales
source card previously relied mainly on the documentation embedded in the
All Sales ZIP. The root document was downloaded through the publisher's
ASP.NET postback and inspected without changing the raw source.

## Evidence

The exact 612,352-byte document has SHA-256
`207fab6385b9be0a48eab5fe4f0960d0f99ec08d8db83f18474dfa280db37253`.
Its text says:

- HCPA receives sales data from the Clerk and reviews it before acceptance;
  title-company, Clerk and HCPA verification delays can affect timeliness.
- `allsales.dbf` contains qualified and unqualified sales, including examples
  such as multi-parcel, barter/trade and title-transfer records.
- The parcel file's `S_DATE` is a sale date and `AMT` is the sale amount for
  its most recent qualified sale. It does not define `S_DATE` as closing,
  execution or recording date for All Sales.
- A general disclaimer says users may redistribute "this data," modified or
  unmodified, if all references to HCPA are removed from the final product.
  Because the document is titled as parcel-layer documentation, its scope for
  the separately packaged All Sales archive is not explicit. It also does not
  address commercial model use or redistribution of derived model artifacts.
- The document is internally dated 25 July 2017, while the 2026 listing shows
  it last updated on 6 November 2023. It is useful source evidence but does not
  prove current policy beyond the listed file.

## Decision

Record that the publisher document contains a redistribution permission with
the stated HCPA-reference-removal condition. Keep its application to the
standalone All Sales archive, commercial AVM use and derived artifacts pending
specific publisher clarification. Keep HCPA excluded from certified 90-day
training because the document does not establish a close-date target,
per-record first availability, one-dwelling consideration for every All Sales
row, or historical attribute vintages.

The document narrows two unknowns: it confirms assessor review lag and names
multi-parcel and other unqualified examples. It does not make a `Q` row safe
without transaction-scope validation, and it does not make the current parcel
snapshot historically available.

## Consequences

- The custodian inquiry can quote the permission and ask whether it covers the
  standalone All Sales archive, commercial model use and derived artifacts,
  alongside date meaning, price scope, release history and corrections.
- A fixed historical HCPA baseline remains blocked.
- Prospective exact-byte captures and the frozen 200-row review continue.
