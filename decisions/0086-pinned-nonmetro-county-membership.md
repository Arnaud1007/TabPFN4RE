# ADR 0086: Pin the two proposed nonmetro county sets

Date: 2026-10-03
Owner: project implementation
Status: candidate geography verified; service-area admission pending
Requirements: US01, US05, US24
Affected protocol: `us-market-candidates-v2`; no final test, sale label or release changed

## Evidence and decision

The [July 2023 Census delineation workbook](https://www2.census.gov/programs-surveys/metro-micro/geographies/reference-files/2023/delineation-files/list1_2023.xlsx)
lists counties assigned to metropolitan and micropolitan statistical areas. It
does not enumerate counties outside every such area, so its rows alone cannot
define a complete nonmetropolitan stratum. Use the official
[2023 Census county Gazetteer](https://www.census.gov/geographies/reference-files/2023/geo/gazetter-file.html)
as the county universe for New York and Florida, then subtract **all** counties
assigned to a Metropolitan Statistical Area in the pinned delineation workbook.
This retains micropolitan counties. It is a geographic definition, not a
claim that every included home is rural.

Pin the exact [New York](https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2023_Gazetteer/2023_gaz_counties_36.txt)
and [Florida](https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2023_Gazetteer/2023_gaz_counties_12.txt)
Gazetteer files by SHA-256 alongside the existing workbook pin. The
[candidate manifest](../data/us_market_candidates.json) stores the resulting
sorted county FIPS lists. The [validator](../scripts/validate_us_market_scope.py)
checks the file hashes before parsing the same bounded bytes, requires the
full 62 New York and 67 Florida county universes, and compares each stored
list with the universe minus all metropolitan counties. It reports 25 proposed
New York nonmetro counties and 22 proposed Florida nonmetro counties.

The pure validation function can establish consistency with a supplied
county set, but it does not label that set as officially verified. Only the
CLI path that checks all three pinned source files reports verified geography.

## Alternatives and limits

Subtracting metropolitan counties only from the delineation workbook's own
rows would omit noncore counties. Treating micropolitan counties as
metropolitan would change the declared definition. Both approaches were
rejected. The official county lists and delineation have 2023 vintages; any
future boundary change needs a new manifest and protocol version before the
affected freeze.

This decision verifies candidate county membership only. Neither statewide
transaction feed has passed rights, target, close-date, first-publication,
identity, historical-feature or sample-floor checks. Supported markets and
certified sale labels remain zero, and U0 and G-US remain pending.
