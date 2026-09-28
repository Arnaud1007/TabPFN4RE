# U0 NYC DOF aggregate API inventory

Captured: 2026-09-28 22:04:44 UTC. Requirement: US05. Status: **inventory only**.

The official [NYC DOF rolling sales page](https://www.nyc.gov/site/finance/property/property-rolling-sales-data.page)
lists the last twelve months of tax-class 1, 2 and 4 sales. The
[annualized page](https://www.nyc.gov/site/finance/property/property-annualized-sales-update.page)
links annual files since 2003. The Open Data API datasets queried here are
separate, mutable portal views; the annualized API view currently spans 2016
through 2025. Its count must not be presented as a count of all DOF annual files.

| API dataset | Query result rows | Minimum sale date | Maximum sale date |
| --- | ---: | --- | --- |
| Rolling `usep-8jbt` | 82,345 | 2025-09-01 | 2026-08-31 |
| Annualized `w2pb-icbu` | 845,607 | 2016-01-01 | 2025-12-31 |

These are `count(*)` of published API **rows**, not eligible residential sales,
unique properties, economic transfers or matured labels. The [JSON inventory](inventory.json)
records the exact query URLs, raw response paths and SHA-256 hashes. Raw API
responses and previously captured metadata stay ignored under `data/raw/nyc_dof/`.
The two responses were parsed as one aggregate record each. No individual
transaction rows or addresses were downloaded for this check.

Local replay of the captured responses in PowerShell:

```powershell
Get-FileHash data/raw/nyc_dof/*-aggregate-20260929.json -Algorithm SHA256
Get-Content data/raw/nyc_dof/*-aggregate-20260929.json | ConvertFrom-Json
```

The [NYC Open Data API guide](https://www.nyc.gov/opendata/get-started/user-guides/open-data-apis)
describes the query language and default row limit. The
[city open-data law](https://cityofnewyork.github.io/opendatatsm/LocalLaw11of2012.html)
describes public dataset access without registration or a licence requirement,
subject to source/version/modification identification. Dataset metadata itself
has a blank licence field, and dataset-specific redistribution and product-use
decisions have not been recorded. No rights approval is inferred here.

Blocking facts remain: neither view supplies a per-row first-publication time
or verified contract/close-date interpretation; the present annualized view has
later tax-roll attributes; tax lots and units may not identify a unique home;
and row-level eligibility and duplicate transfers have not been audited. The
observed row counts cannot satisfy G-US or enable training. Next: qualify
rights and timing, then freeze an authorised row snapshot and manually audit
its identity/transaction grain before an adapter.

The annualized API metadata describes `sale_date` with text about `$0` sale
prices, while the [DOF glossary](https://www.nyc.gov/assets/finance/downloads/pdf/07pdf/glossary_rsf071607.pdf)
defines sale date separately. This documentation inconsistency is retained as
a source question; it does not change the dataset field values or prove a close
date.
