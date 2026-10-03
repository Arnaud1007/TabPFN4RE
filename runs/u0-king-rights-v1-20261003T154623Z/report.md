# King County Assessor access and reuse boundary

Run ID: `u0-king-rights-v1-20261003T154623Z`
Date: 2026-10-03
Status: **official access terms inspected; no data acquired**
Requirements: US02, US05, US24

## Objective and evidence

Clarify the [King County source card](../../data/source_cards/king_county_sales.yaml)'s unresolved access and commercial-use status before attempting a Western-region acquisition. The official [Assessor Data Download](https://info.kingcounty.gov/assessor/DataDownload/default.aspx) page places an acknowledgment before its files and warns against releasing or using lists of individuals for commercial purposes. The separate [eSales terms](https://info.kingcounty.gov/assessor/esales/Glossary.aspx?type=k) state that publishing, distributing or commercially exploiting that site's content requires prior written county permission. King County's [property lookup directory](https://kingcounty.gov/en/dept/assessor/buildings-and-property/property-value-and-information/look-up-property-information) lists eSales and Assessor downloads as different routes.

The download warning concerns lists of individuals; it is not proof that a minimized sale-and-property extract has the same permitted-use decision. Conversely, the eSales terms cannot be silently treated as a grant for an Assessor bulk extract. The current [Washington statute page](https://app.leg.wa.gov/rcw/default.aspx?cite=42.56.070) provides the primary legal text; this source audit makes no legal determination about a contemplated AVM use.

The existing [eSales glossary](https://info.kingcounty.gov/assessor/esales/Glossary.aspx?type=k) defines sale price from a recorded excise affidavit and document/sale date as associated with that affidavit. Neither is an evidenced closing date or first public availability timestamp for the project's 90-day origin. One affidavit may cover multiple parcels, so a price cannot be allocated to an individual dwelling from a repeated row without a justified rule.

## Decision and next action

No acknowledgment was accepted, data file downloaded, property searched or sale row ingested. Keep King County as a source-inventory candidate with **zero certified labels** and ask the Assessor for written clarification on a minimized, non-party transaction extract, historical vintages, permissions and sale-date meaning. The [inquiry is an unsent draft](../../data/requests/king_county_assessor_source_inquiry_draft.md). If this route remains unsuitable, assess another Western-market source under the same US05 card and rights criteria. U0 and G-US remain **PENDING**.

Local checks: Python 3.14 parsed the source-card and requirement-map YAML and verified the pending eligibility flags and three requirement evidence links (exit 0); `git diff --check` passed (exit 0); the project environment's `pip-audit --local --progress-spinner off` found no known vulnerabilities in audited distributions (exit 0, unpublished local package skipped). This is a documentation-only review of official pages. No model, calibration, final test or full code suite was run.
