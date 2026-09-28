# ADR 0006: NYC and King County source feasibility

Date: 2026-09-28

Owner: project implementation

Affected requirements: US02, US03, US05, US06, US07, US08, US11

## Alternatives and evidence

NYC's Department of Finance publishes [rolling](https://www.nyc.gov/site/finance/property/property-rolling-sales-data.page) and [annualized](https://www.nyc.gov/site/finance/property/property-annualized-sales-update.page) sales. Their official Open Data metadata was saved locally without property rows; source cards record IDs, hashes and field names. The rolling file covers the latest 12 months and is updated monthly. The annualized page exposes longer sales history. The [DOF glossary](https://www.nyc.gov/assets/finance/downloads/pdf/07pdf/glossary_rsf071607.pdf) calls sale price the amount paid and sale date the date sold. Neither current schema supplies contract date, per-row first availability or a dated vintage for every property attribute. The annualized `building_class_as_of_final_roll` field is specifically a later-roll value. The [Open Data terms](https://data.cityofnewyork.us/stories/s/Terms-of-Use/k9k7-3cje/) permit source updates and overwrites without retained older versions. Both API metadata documents have a null dataset-specific licence field; permitted product use and redistribution need a recorded decision.

King County's [sale extract description](https://www5.kingcounty.gov/sdc?Layer=rpsale_extr) says an economic sale can span multiple parcel records. Its [residential building description](https://www5.kingcounty.gov/sdc?Layer=resbldg_extr) permits multiple buildings per parcel. Both GIS derivatives are labelled **Not Public**, weekly updated and non-authoritative relative to the Assessor's [download route](https://info.kingcounty.gov/assessor/DataDownload/default.aspx). The [Assessor glossary](https://info.kingcounty.gov/assessor/esales/Glossary.aspx?type=k) defines sale price from a recorded excise affidavit and document/sale date as the date associated with that affidavit. Neither definition proves exact close date or first public availability. The [GIS terms](https://kingcounty.gov/en/dept/kcit/data-information-services/gis-center/about/terms-conditions-copyrights) and Assessor access terms require separate use decisions. No download acknowledgement was accepted and no property rows were ingested.

All three regions examined so far are single local areas. Even if independently validated, Cook County, NYC and King County would not satisfy G-US's four-region, eight-metro and two-nonmetro coverage floors.

## Decision

Retain NYC and King County as acquisition candidates. Their current public descriptions support schema research and future data qualification, not a certified 90-day pre-close OFF backtest. Do not substitute sale/affidavit dates for verified close dates or current property descriptions for as-of features. Do not treat a sale-file row as a unique economic transfer without an audit. No country implementation or G-US claim follows from this inventory.

## Next evidence

For NYC, determine a source-specific reuse decision, capture or obtain genuine historical monthly source snapshots, establish a conservative row-availability and close-date rule, and audit whether tax-lot rows describe single eligible homes. For King County, establish an authorised Assessor download route and rights, obtain transaction and building history with availability evidence, and verify affidavit/close-date semantics and parcel/building join cardinalities. Then audit at least 200 stratified records per admitted source before training. If exact closing times cannot be recovered, register a separately named conservative monthly-origin experiment; it cannot silently replace the primary protocol.
