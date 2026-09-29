# U0 NYC ACRIS document-code inventory

Run ID: `u0-nyc-acris-codes-20260929T004355Z`  
Status: **verified current code table only; U0 and G-US PENDING**  
Requirements: US04, US05, US07, US22, US24

## Objective and source

After the [first bounded ACRIS pilot](../u0-nyc-acris-pilot-20260929T003102Z/report.md)
stopped at a linked-Legals cap, inspect the official [ACRIS Document Control
Codes](https://data.cityofnewyork.us/City-Government/ACRIS-Document-Control-Codes/7isb-wh4c)
before changing the candidate-document rule. The metadata and bounded 1,000-row
API response were saved unchanged under Git-ignored `data/raw/nyc_dof/`.
[The source card](../../data/source_cards/nyc_acris_document_control_codes.yaml)
records their exact URLs, dates, byte counts and SHA-256 hashes. The API
`count(*)` request returned HTTP 500; no error body was retained. The bounded
row response contained 126 rows, below the 1,000-row limit. This is a current
code table, not a historical vintage or a transaction source.

## Observed structure

All 126 document-type codes were distinct, with no blank code, description,
class or record-type field. The source grouped 34 codes under DEEDS AND OTHER
CONVEYANCES, 29 under UCC AND FEDERAL LIENS, 40 under OTHER DOCUMENTS and 23
under MORTGAGES & INSTRUMENTS. `CDEC` is described as CONDO DECLARATION within
the broad conveyances class. NYC's [official ACRIS daily-file guide](https://a836-acris.nyc.gov/EDS/Overview/How%20To%20Process%20ACRIS%20Daily%20File%20v1%207.htm)
also lists `CDEC` as a condo declaration. That explains why a class-only deed
filter would include the first saturated pilot document. It does not prove
which document, if any, supports the rolling sale row.

## Verification and limits

[Aggregate counts](aggregate.json) and the [manifest](manifest.json) record
the source bytes, environment and source-card hashes. Run
`& 'runs/u0-nyc-acris-codes-20260929T004355Z/verify_artifacts.ps1'` from the
project root to verify the two ignored source responses and tracked files.
There were no sampled property-row queries in this code-table inventory.
No manual sale review, price validation, closing-date validation or
historical-availability proof resulted. The portal metadata's licence field
is null; reuse and redistribution remain pending. A revised ACRIS pilot must
freeze exact candidate-code rules and response limits before querying the
selected properties again.
