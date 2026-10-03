# ADR 0077: Hold King County extraction at the acknowledgment and rights boundary

Date: 2026-10-03
Owner: project implementation
Status: official access terms verified; source admission pending
Affected requirements: US02, US05, US24
Affected protocols: none

## Evidence and alternatives

The [official Assessor download page](https://info.kingcounty.gov/assessor/DataDownload/default.aspx) requires an acknowledgment concerning commercial use of lists of individuals. The separately operated [eSales site](https://info.kingcounty.gov/assessor/esales/Glossary.aspx?type=k) states that commercial exploitation of its content needs prior written permission. The [run report](../runs/u0-king-rights-v1-20261003T154623Z/report.md) records the exact scope. No terms were accepted and no property records were accessed.

The alternatives were to accept the download acknowledgment, infer that public availability grants use for a commercial AVM, or pause acquisition while requesting a source-specific permission and minimized field route. The first two would make a permitted-use decision without the necessary authority or an exact data contract.

## Decision

Keep King County in inventory only. Do not accept the acknowledgment or ingest the Assessor extract on the owner's behalf. Do not scrape eSales or use the GIS derivative marked Not Public. Seek written clarification on whether a transaction-and-attribute extract excluding all party/contact fields can be used for internal research, later commercial predictions and aggregate reporting, and ask for the applicable release/version and availability history. Any later download requires a separate recorded use decision. This decision does not change the Western-market coverage requirement or admit a label.
