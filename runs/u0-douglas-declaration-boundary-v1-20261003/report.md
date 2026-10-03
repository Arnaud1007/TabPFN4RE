# U0 Douglas County transfer-declaration boundary

Run ID: `u0-douglas-declaration-boundary-v1-20261003`  
Date: 2026-10-03  
Requirements: US03, US05, US07, US08, US24  
Status: **source meaning narrowed; U0 and G-US PENDING**

## Objective and observed evidence

Read the official [TD-1000 declaration](https://www.douglasco.gov/documents/transfer-declaration-form_-rev-10-18.pdf/), [mass-appraisal description](https://www.douglasco.gov/assessor/mass-appraisal/), [Assessor download page](https://www.douglasco.gov/assessor/data-downloads/) and [Open Data Guidelines](https://www.douglas.co.us/documents/open-data-guidelines.pdf/). The declaration is confidential and separates closing and contract dates, total consideration including personal property, personal-property amount, and contracted price when different. The appraisal page describes screening and adjustments for assessment. Neither source maps those values to public `Sale_Date` or `Sale_Price`. This is a distinction among official source documents, not a finding about any downloaded transaction row.

The [source card](../../data/source_cards/douglas_county_co_assessor_downloads.yaml), [ADR 0083](../../decisions/0083-douglas-confidential-declaration-field-boundary.md) and [unsent inquiry draft](../../data/requests/douglas_county_assessor_source_inquiry_draft.md) now preserve this boundary. The acquisition backlog and next action point to the precise unresolved mapping. No confidential form, sales row, party name or paid report was acquired. No email was sent.

## Validation and interpretation

The saved [check record](test_gate.json) contains commands, exit codes and measured durations for YAML parsing, source-card admission invariants, `git diff --check` and `pip-audit`. An initial staged check caught Markdown trailing spaces in the new decision header; they were removed before the passing check. An initial `pip-audit` invocation used an invalid option combination; the corrected invocation found no known vulnerabilities in auditable packages and skipped the local editable project. This is a documentation and source-meaning checkpoint; no model tests, accuracy scores, source-row hash, split, feature-policy hash or checkpoint apply. The previous metadata-only HEAD evidence remains [separate](../u0-douglas-co-source-feasibility-v1-20261003T172000Z/report.md).

The candidate has zero certified sale labels. Ask the custodian for public-field mappings, historical first availability and dataset-specific use rights before defining a minimized row audit. A confidential declaration cannot serve as the public verification route. U0 and G-US remain PENDING.
