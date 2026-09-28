# ADR 0020: NYC rolling source semantics and bounded profile

Date: 2026-09-29

Owner: project implementation

Affected requirements: US03, US05, US06, US07, US08 and US24

## Source evidence

The [NYC Open Data FAQ](https://www.nyc.gov/opendata/get-started/FAQs) says
there are no general restrictions on using Open Data. The portal's
[Terms of Use](https://data.cityofnewyork.us/stories/s/Terms-of-Use/k9k7-3cje/)
also bind users to any additional data-provider terms. The rolling dataset's
current metadata has a null licence field; no separate DOF terms or affirmative
commercial/redistribution permission have been recorded for this project.
The conservative project decision remains **internal source inventory only**.
A releasable product or redistribution requires a specific documented review;
public downloadability alone is not that decision.

The [DOF rolling page](https://www.nyc.gov/site/finance/property/property-rolling-sales-data.page)
describes tax classes 1, 2 and 4 and a last-twelve-month file. The
[DOF glossary](https://www.nyc.gov/site/finance/property/glossary-property-sales.page)
says sale price is the price paid, sale date is the date sold, and a $0 price
indicates an ownership transfer without cash consideration. It identifies
borough/block/lot as tax-property identifiers and building class at time of
sale separately from present class. The official
[RP-5217 NYC transfer form](https://www.nyc.gov/assets/finance/downloads/pdf/02pdf/rp5217nyci.pdf)
says its date of sale/transfer is generally the closing date, and its full
sale price can include noncash consideration. The link between those form
fields and this rolling CSV's `SALE DATE` / `SALE PRICE` has **not** been
verified; form instructions cannot by themselves certify the API columns.

A [DOF rolling-file header](https://www.nyc.gov/assets/finance/downloads/pdf/rolling_sales/rollingsales_manhattan.pdf)
states that descriptive data for sales prior to the final tax roll reflect a
more recent final roll. This directly cautions against treating current
property descriptors as historical as-of features. The private
[current snapshot](../runs/u0-nyc-rolling-snapshot-20260928T225512Z/report.md)
is known by its capture completion, not by each sale date.

## Decision before row profiling

Profile only the exact frozen CSV hash
`84c06057c52a2822f982cd98fb77ef7edf2c14134d00f46b073d2e4b762b2ef2`.
The profiler must verify file bytes, row count and header against the snapshot
manifest before aggregation. Its tracked output may contain only denominator
counts by borough, class-at-sale family, price parse state, missing area/unit
state and duplicate-candidate counts. Include the joint borough by one-family
versus other/ambiguous table, aggregate counts for each proposed review edge
bucket and oldest/newest sale-month counts. No addresses, block/lot values, sale
dates, prices, row ordinals or private group keys appear in tracked output.
The first duplicate screen uses exact source strings after whitespace trimming;
it can miss format-equivalent dates, prices or lot numbers. Label its output
`exact_source_string_duplicate_candidates` and do not present it as a complete
economic-transfer deduplication rule.
The raw file and any eventual 200-record review sample remain ignored under
`data/raw/nyc_dof/`.

Use strict source-value parsing and report missing, zero, positive, negative
and invalid prices separately. This is a **source profile**, not an eligibility
funnel. A zero-price transfer is excluded from the eventual primary positive
sale-price label under US07, but no row is dropped from this diagnostic. A
repeated borough/block/lot/date/price tuple is only a duplicate candidate;
co-ops, condos and multi-property instruments require a separate economic
transfer audit. Do not infer unique properties from BBL alone.

The profile determines feasible strata for a pre-registered 200-record manual
source audit. That edge-enriched sample cannot estimate population prevalence
without appropriate weights; use full-profile denominators for source rates.
The profile does not admit a model cohort, resolve rights, prove closing
time, reconstruct historical first availability or unlock US real-data
training. Preserve the prior snapshot and gate statuses.
