# U0 NYC ACRIS source inventory

Run ID: `u0-nyc-acris-inventory-20260929T000000Z`
Status: **metadata and aggregate count inventory only**
Requirements: US04, US05, US06, US07, US08, US22, US24

## Objective and official source meaning

Identify a bounded official corroboration route for the already frozen NYC
rolling-sales sample before viewing any ACRIS candidate instrument. The
[NYC Department of Finance ACRIS page](https://www.nyc.gov/site/finance/property/acris.page)
says its record search and document images cover Manhattan, Bronx, Brooklyn
and Queens. Staten Island deed review needs a different route. It also warns
against excessive automated traffic to the ACRIS application, so the pilot
will use the official Open Data API with strict request and byte caps.

The official [Master dataset](https://data.cityofnewyork.us/City-Government/ACRIS-Real-Property-Master/bnx9-e6tj)
describes `document_date` as the date of document,
`recorded_datetime` as the legal recording date, `percent_trans` as the
reported interest transferred, and `document_amt` as **principal debt or
obligation**. The [Legals dataset](https://data.cityofnewyork.us/City-Government/ACRIS-Real-Property-Legals/8h5j-fqxa)
exposes document ID, borough, block, lot, unit and partial-lot fields. None
of these definitions establishes closing date, transaction price, first
publication or a dwelling-level match. A document can link several legal
rows. [ADR 0022](../../decisions/0022-nyc-acris-linkage-pilot.md) freezes the
next four-row pilot before any sampled row lookup.

## Actual inventory

Read-only HTTPS GETs retrieved the two official `/api/views/{id}` metadata
objects and two `count(*)` aggregate responses on 2026-09-29 local time.
Responses were bounded to 2 MiB for metadata and 1 KiB for counts, required
JSON and the expected dataset IDs, and were saved unchanged under ignored
`data/raw/nyc_dof/`. [aggregate.json](aggregate.json) records exact sizes,
SHA-256 hashes, columns and row counts:

| Dataset | Current portal rows at inventory | Metadata SHA-256 |
| --- | ---: | --- |
| Master `bnx9-e6tj` | 17,090,001 | `d3642afb5a9e44722970258c946d5d26843e49154595ea63e0aa72ec157eee01` |
| Legals `8h5j-fqxa` | 22,761,783 | `24c274581feddbcae77cbbd0d3f6c45f7980eb71145e140162f75bcd48f6108d` |

These are mutable **portal row counts**, not unique transfers, eligible sales
or matched sample records. Metadata reports last data updates on 2026-09-08;
it does not give a historical first-availability timestamp for each row.
Both metadata objects have a null licence field. The
[Master](../../data/source_cards/nyc_acris_master.yaml) and
[Legals](../../data/source_cards/nyc_acris_legals.yaml) source cards therefore
retain internal qualification only and pending reuse/redistribution decisions.
No ACRIS transaction row or document image was downloaded in this run.

## Verification and next action

The run manifest hashes the source cards, protocol, aggregate, report and
verification script. Run
`& 'runs/u0-nyc-acris-inventory-20260929T000000Z/verify_artifacts.ps1'`
from the project root with the ignored metadata/count responses present to
recheck their bytes, IDs and row counts. The first verifier invocation exited
1 because a PowerShell JSON-array wrapper added an unintended level; the
[failed check](verification_failure.log) is preserved. After a targeted fix,
the same command passed against the unchanged private responses. A later
[stale-manifest failure](verification_stale_manifest.log) occurred after the
report changed without refreshing its recorded hash; it did not indicate a
source response change. The manifest was refreshed and the final verifier
passed. No model or source-linkage test was performed: this is inventory, and
the four-row pilot is the next step.

Implement ADR 0022's bounded read-only pilot with synthetic tests, then
inspect ambiguity before expanding the query budget. Continue the 200-record
manual review separately. U0 and G-US remain pending; the source is not
admitted to an as-of benchmark or a releasable system.
