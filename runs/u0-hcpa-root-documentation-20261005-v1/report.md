# HCPA root documentation audit

Date: 2026-10-05. Result: **rights narrowed; temporal label gate still
blocked**. No property rows were ingested and no model was trained or scored.
U0 and G-US remain PENDING.

The official [HCPA Public Downloads](https://downloads.hcpafl.org/Default.aspx)
page lists `_Documentation.doc`. The file was downloaded through its ASP.NET
postback, retained under ignored `data/raw/`, and hashed before inspection.
The 612,352-byte OLE Word file has SHA-256
`207fab6385b9be0a48eab5fe4f0960d0f99ec08d8db83f18474dfa280db37253`.
The private UTF-8 extraction has SHA-256
`b1e6a1adb0bcea2f17fe3b8f83f0158cc18f5701670d95623d91d7c0543db64c`.
The public [manifest](manifest.json) contains no property data.

## What the publisher document establishes

- HCPA receives sale data from the Clerk and reviews it before acceptance.
  It warns that title-company, Clerk and verification delays affect
  timeliness and completeness.
- `allsales.dbf` includes qualified and unqualified records. Its examples of
  unqualified transactions include multi-parcel, barter/trade and title
  transfers. This supports retaining transaction-scope quarantine.
- For the current parcel file, `S_DATE` is described only as sale date and
  `AMT` as the amount for the latest qualified sale. The text does not identify
  the All Sales date as closing, deed execution or recording date.
- A general disclaimer permits redistribution of "this data," modified or
  unmodified, subject to removing all references to HCPA from the final
  product. The document is titled as parcel-layer documentation and does not
  expressly state whether that permission covers the separately packaged All
  Sales archive, commercial AVM use or derived model artifacts.
- The document says shapefiles are updated weekly. That statement is not
  treated as a per-row All Sales publication timestamp.

## Remaining boundary

This evidence narrows the source card's previous blanket `redistribution:
not_established` status: a publisher permission and condition now exist, but
their scope for the standalone All Sales archive is not explicit. It does not
clear commercial model use, `S_DATE` close-date semantics, one-home price
scope, per-record availability, correction history, or historical
parcel-feature vintages. A qualified/free-market indicator still cannot prove
that every row represents one eligible dwelling.

Accordingly, HCPA remains excluded from the certified 90-day training path.
[ADR 0097](../../decisions/0097-hcpa-root-documentation-boundary.md) records
the decision. The next source action is the narrowed custodian inquiry plus
continued prospective exact-byte captures and frozen-sample review.

## Checks performed

- Verified the raw file is a legacy OLE Word document from its magic bytes.
- Rehashed the raw and extracted files independently.
- Confirmed both private files are excluded by the repository's `data/raw/`
  rule.
- Parsed this manifest as JSON and the updated source card and requirement map
  as YAML.
- Searched the complete candidate publication set, including new files, for
  property identifiers, addresses and row-level prices; none were added. The
  verifier uses the commit's file set when replayed from a clean checkout.
