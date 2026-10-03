# ADR 0075: Admit the current Sales Web CSV schema to U0 inventory only

Date: 2026-10-03
Owner: project implementation
Status: verified bounded private export; source admission pending
Affected requirements: US03, US05, US07, US08, US24
Affected protocols: none; no label, split, feature or model result changes

## Evidence and alternatives

The official Sales Web browser search returned 25 Albany County results for one sale date. Its download control created a CSV with 78 columns, including sale, deed, contract, database-load and correction fields. The [run report](../runs/u0-nys-salesweb-export-v1-20261003T150117Z/report.md) and [schema observation](../runs/u0-nys-salesweb-export-v1-20261003T150117Z/observation.json) preserve the exact scope and checksum. The raw rows are Git-ignored because the export also contains party and contact details.

The earlier alternatives were to infer the current export from the old dictionary or static UI labels, or to declare the current export entirely unverified. The first would overstate evidence; the second is now stale. The bounded CSV directly verifies the **field names and file format** for this capture, while record meanings, first public availability, correction history and reuse rights remain unverified.

## Decision

Record the current CSV header as a verified U0 schema observation. Permit only bounded, private source qualification using this capture. Do not admit its rows as canonical sale labels, train a model, infer a historical as-of feature from `load_dt`, or use the downloaded party/contact fields as predictors. A nonpositive price in this sample confirms the need for eligibility checks but does not define the entire source's inclusion rule.

Before source admission, verify dataset-specific use rights, sale-date and price semantics against the applicable RP-5217/instrument evidence, row-to-dwelling identity including multi-parcel transfers, corrections, and a defensible first-availability rule. Audit at least 200 stratified records under a registered protocol. U0 and G-US remain PENDING; certified labels remain zero.
