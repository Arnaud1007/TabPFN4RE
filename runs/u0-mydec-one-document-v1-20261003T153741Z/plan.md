# Planned one-document MyDec representation check

Run ID: `u0-mydec-one-document-v1-20261003T153741Z`
Date: 2026-10-03
Status: **prepared, no external query**
Requirements: US02, US05, US07, US24

## Question and source boundary

Can the official [MyDec public declaration search](https://mytax.illinois.gov/MyDec/) display the filed PTAX-203 representation for one already captured Cook/PTAX document number? The [interactive form check](../u0-mydec-document-form-interactive-v3-20261003T153202Z/report.md) verified the blank Document Number and County fields. The answer can confirm only a source representation or access failure. It cannot certify a deed, closing date, single-home sale price, first publication or commercial use rights.

The input is the previously pinned [private offline worklist](../u0-illinois-ptax203-offline-v1-20261003T035947Z/report.md), SHA-256 `7981f32fe1970afcb2c20768271c5c0c58dc05ff9a3905fe94981aeef9f8ac8e`. Its exact private bytes replayed successfully before selection. Select the first worklist item in frozen source order satisfying: one Cook row for its document, exactly one exact-document PTAX declaration, Cook county confirmed by the captured declaration, and `single_reported` parcel-scope diagnostic. This rule was frozen before any MyDec result. The exact document number, row ordinal and declaration identity are stored only in Git-ignored `data/raw/illinois_ptax203/u0-mydec-one-document-v1-20261003T153741Z/selection.json`, under a verified private ACL. No property or transaction identifier enters Git.

## Action limit and expected evidence

The only planned external action is one exact Document Number plus County search in the official MyDec interface, after the required action-time approval for transmitting that record identifier. Do not search by PIN or address. Do not retry an unsuccessful query under a changed spelling, county or identifier without a new plan. Capture any result, declaration view or access error privately, with source URL, capture time and byte hash. The public report may state only status, method, limitations and non-identifying aggregate checks. It must not publish document number, PIN, address, party, declaration ID, price, date, row hash or a small-cell result.

If a result is accessible, compare only the same filed fields already present in the pinned PTAX capture and record discrepancies privately. A match is a representation check, not an independent transaction label. Keep the full 200-record source audit, Clerk instrument, as-of availability and reuse-rights tasks open regardless of outcome. The query cannot open certification labels.

## Prepared state

Private selection file was created once and read back. The frozen worklist hash was checked against the committed aggregate, and the private file is Git-ignored. Identifiers entered: **0**. Searches submitted: **0**. Declarations opened: **0**. Certified sale labels: **0**. U0 and G-US remain **PENDING**.
