# ADR 0083: Do not project confidential transfer-declaration fields onto Douglas downloads

Date: 2026-10-03
Owner: project implementation
Status: source evidence recorded; admission pending
Affected requirements: US03, US05, US07, US08, US24
Affected protocols: none

## Evidence

The official [Douglas County TD-1000 form](https://www.douglasco.gov/documents/transfer-declaration-form_-rev-10-18.pdf/) calls the completed declaration confidential and unavailable for public inspection. It requests a closing date and a separate contract date. Its total sale-price field includes real and personal property, with personal property separately itemised. It also asks about partial interests, related parties and concessions. The form proves these distinctions matter to the assessor, but does not describe how the public `Property_Sales.txt` fields are populated.

The County's [mass-appraisal page](https://www.douglasco.gov/assessor/mass-appraisal/) says selected sales for valuation are screened, adjusted for personal property and adjusted for time. Its assessment modelling data need not equal the public [Property Sales download](https://www.douglasco.gov/assessor/data-downloads/). The public page lists `Sale_Date` and `Sale_Price` without mapping them to declaration or adjusted-assessment fields. The [Open Data Guidelines](https://www.douglas.co.us/documents/open-data-guidelines.pdf/) address portal datasets; their applicability to the separate direct assessor files remains unconfirmed.

## Decision

Keep `Sale_Date` and `Sale_Price` unresolved in the Douglas source card. Do not infer closing date from the TD-1000 form, infer gross or adjusted consideration from the assessment method, request confidential declarations, or admit public download rows as sale labels. Ask the custodian for a written mapping of public fields, historical availability and dataset-specific rights. Continue with public metadata only until those dependencies are resolved.

This decision narrows [ADR 0080](0080-douglas-county-western-source-candidate.md); it neither changes the existing source capture nor opens any model test. If the publisher provides a field mapping, version the source card and check it on a rights-cleared audited sample before changing eligibility.
