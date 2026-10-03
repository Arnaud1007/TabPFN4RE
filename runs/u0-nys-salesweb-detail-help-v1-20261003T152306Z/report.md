# New York State Sales Web live detail help

Run ID: `u0-nys-salesweb-detail-help-v1-20261003T152306Z`  
Date: 2026-10-03  
Status: **field help observed; source admission pending**  
Requirements: US03, US05, US07, US08, US24

## Objective and method

Inspect the official [Sales Web detail view](https://pad.tax.ny.gov/salesDetailReport) for definitions that the [bounded CSV header audit](../u0-nys-salesweb-export-v1-20261003T150117Z/report.md) could not establish. A public Albany County search for the single sale date 2025-08-01 returned 25 results. The first result was opened only to inspect field labels and help controls. No property ID, address, party name, price, contact detail or row value is retained in this run.

The rendered page has sections for sale information, parcel specifications and updates. The three rendered help controls and their text are transcribed in [observation.json](observation.json). This is a live UI observation, separate from the earlier static JavaScript inspection.

## Findings and boundary

- The “Personal property” help says “Value of personal property included in the sale price”. This is in tension with the indexed legacy dictionary description of a sale-price field net of personal property. The current UI does not directly define the exported `sale_price` field or prove that `personalProp` maps one-to-one to CSV `personal_prop`. The price basis therefore remains unresolved.
- The “Sale loaded to database” help describes initial entry or loading by New York State. It does not state when the record first became publicly visible. The current UI does not prove a direct mapping to exported `load_dt`.
- The “Electronic update” help describes assessor review status. It does not establish a public correction-history timestamp.

The inspected result may have been corrected since original entry. No historical snapshot, recorded instrument or first-publication timestamp was obtained. **Certified sale labels: 0. U0 and G-US: PENDING.** No model training, calibration or holdout evaluation occurred.

## Verification and next action

Reopen the public detail view through the same county/date search and inspect only the three field-help buttons named in `observation.json`. The observation is reproducible only while the portal serves the same UI; the prior static asset hash and bounded CSV hash identify the surrounding evidence, not an immutable copy of the live page.

Local checks after recording this observation: Python 3.14 parsed the run JSON, source-card YAML and requirement-map YAML and verified the zero-label and hash boundaries (exit 0); `git diff --check` passed (exit 0); `git check-ignore` confirmed the raw CSV remains ignored (exit 0); the project environment's `pip-audit --local --progress-spinner off` found no known vulnerabilities in audited distributions (exit 0, local editable package skipped as unpublished). No model or full test suite was run for this documentation-only source audit.

Ask the custodian to reconcile the price and personal-property descriptions, confirm current CSV mappings and clarify first public availability. The [inquiry remains an unsent draft](../../data/requests/nys_salesweb_inquiry_draft.md). Source admission, 200-record manual audit and any as-of modelling depend on those answers and a permitted-use decision.
