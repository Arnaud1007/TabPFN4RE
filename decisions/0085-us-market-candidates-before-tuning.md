# ADR 0085: Record US market candidates before real-market tuning

Date: 2026-10-03
Owner: project implementation
Status: candidate inventory recorded; service-area admission pending
Requirements: US01, US05, US24
Affected protocol: `us-market-candidates-v1`; no frozen test or accepted release changed

## Decision and evidence

Record [eight metro candidates and two proposed nonmetro strata](../data/us_market_candidates.json)
before real-market model tuning. The metro names, codes and county counts were
checked against the U.S. Census Bureau's [July 2023 delineation file](https://www2.census.gov/programs-surveys/metro-micro/geographies/reference-files/2023/delineation-files/list1_2023.xlsx),
SHA-256 `952c4b1e78acbb54e6ec9412434b7602fedacbf021736351a63c181bdb753629`.
The [Census region table](https://www.census.gov/programs-surveys/economic-census/geographies/levels/2022-levels.html)
places the sampled states in the four required regions. The map has two metro
candidates per region: NYC and Albany; Chicago and Springfield, Illinois;
Tampa and Miami; Denver and Seattle. The nonmetro candidates are separate
New York and Florida state strata, defined as counties outside metropolitan
CBSAs under the same Census vintage. Micropolitan counties may remain.

The candidate list is a planning control. Several sources cover only one
county of a larger CBSA; the file states that gap. Neither the full CBSA nor
even its listed source counties are a supported service area. The New York
and Florida nonmetro county membership, sample floors, and selection
variation have not been audited. Price, density, stock and recent market
direction are stated as hypotheses to test from qualified historical data,
not measured differences.

## Alternatives and change control

Leaving markets unnamed until model tuning would permit a favourable subset
to be selected after results. Calling the available county extracts eight
supported metros would overstate their coverage and admissibility. A candidate
manifest makes the intended comparison visible now while keeping all
qualification questions open. Replace a candidate only through a new decision
and manifest version **before** the applicable final tuning and service-area
freeze. Once a certification cohort is opened, its scope cannot be revised
retroactively.

## Admission boundary

Every candidate still needs a source-specific use decision, single-home gross
consideration and transaction identity, close-date and first-publication
semantics, historical physical attributes, sample floors, and a measured
variation audit. Only then may a later service-area manifest define supported
geographies, exclusions, split rules and test denominators. This decision
certifies zero sale labels and accepts no U0, U3 or G-US gate.
