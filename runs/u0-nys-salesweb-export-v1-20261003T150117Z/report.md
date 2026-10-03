# New York State Sales Web bounded export inventory

Run ID: `u0-nys-salesweb-export-v1-20261003T150117Z`  
Date: 2026-10-03  
Status: **current CSV schema observed; source admission pending**  
Requirements: US03, US05, US07, US08, US24

## Objective and method

Resolve the current-export schema question left open by the [static UI check](../u0-nys-salesweb-ui-v1-20261003T115547Z/report.md). In the official [Sales Web portal](https://pad.tax.ny.gov/salesSearch), the public browser UI was filtered to Albany County (SWIS 01) and sale date 1 August 2025 through 1 August 2025. No property identifier, address, party name, login, payment or credential was submitted. The UI showed **25 results**. Its `Download Search Results` control created `SaleswebExtract.csv`, even though the broader portal description calls the export Excel.

The browser tool timed out after the download click, so it did not return a download handle. A filesystem check found the 14,039-byte CSV created at 2026-10-03T15:01:17Z. Its SHA-256 is `5548b290ac36772070799800dfc7f875bdaf04c1599aaa169562b43ec6f9b355`. It was copied byte-for-byte to Git-ignored `data/raw/nys_salesweb_portal/sample-20261003-albany-20250801.csv`; source and copy hashes matched. The browser timeout is retained as a failed observation step, not represented as a clean download-event result.

The [query record](query.json) was written after the capture. It accurately records the criteria selected before search, but is not a preregistered experiment plan. [Observation metadata](observation.json) records the source, configuration and environment hashes, all 78 header names, capture boundary and gate status. The private file contains names and addresses; no row values, identity values, prices or addresses are committed or used as predictors.

## Observed evidence

The CSV has **25 rows and 78 columns**. All 25 `sale_dte` values match the one-day filter, and all rows belong to one county. Fields present in the current CSV include `sale_dte`, `deed_dte`, `contract_dt`, `sale_price`, `personal_prop`, `arms_length_flag`, `nbr_of_parcels`, `prop_class_at_sale`, `book`, `page`, `load_dt`, and `last_fm_dt`. Thus the current export contains much more than the ten visible result-table columns. It also contains buyer, seller, attorney, address and phone fields, which remain confined to the ignored raw file and are excluded from this public inventory.

All 25 rows have nonblank sale dates and prices; at least one price is nonpositive. This is a data-quality finding, not an arm's-length inclusion decision. The field `load_dt` is nonblank on all 25 rows, but its presence does **not** prove first public availability. The header names do not prove that `sale_dte` is a closing date, that `sale_price` has the required gross consideration semantics, or that each row represents one eligible home. The [official ORPTS report and RP-5217 definitions](../../decisions/0071-nys-orpts-report-date-price-boundary.md) remain candidate mappings to verify against instruments and publisher guidance.

**Property rows acquired privately: 25. Certified sale labels: 0. U0 and G-US: PENDING.** No training, calibration, holdout opening, source admission or rights decision occurred. One county and one sale date do not establish a historical source pipeline or the G-US service population.

## Verification and next action

The following checks were run after the capture: SHA-256 equality between the browser download and the ignored copy; `Import-Csv` shape 25 by 78; required header presence; one-county and exact sale-date filter; Git ignore for the raw path. The source checksum and schema are in `observation.json`. The original browser-event timeout and exact acquisition duration beyond that timeout are not recoverable.

Focused verification exited 0 and printed `PASS: bounded NYS schema, hashes, source filter, Git ignore and pending gates verified.` It loaded `observation.json`, rehashed the private CSV, `query.json` and `environment_lock.txt`, compared all 78 header names to `Import-Csv`, checked the 25-row filter, and verified the browser download had the same hash. The run JSON files parsed with Python 3.11. PyYAML was absent from the project venv, so the first YAML-parser check exited 1; the installed system Python 3.14 with PyYAML 6.0.3 parsed the source card and confirmed `certified_sale_labels: 0` (exit 0). `git diff --check` passed. A scoped installed-environment `pip-audit --local --progress-spinner off` exited 0 with no known vulnerabilities in audited distributions; the local editable package was skipped because it is not on PyPI. No full test suite was run for these source documentation changes.

The private replay needs the CSV at the ignored path named in `observation.json`. From the project root, the essential checks are:

```powershell
$o = Get-Content runs/u0-nys-salesweb-export-v1-20261003T150117Z/observation.json -Raw | ConvertFrom-Json
$raw = $o.source_snapshot_path
if ((Get-FileHash -LiteralPath $raw -Algorithm SHA256).Hash.ToLowerInvariant() -ne $o.source_snapshot_sha256) { throw 'Source hash mismatch' }
$rows = @(Import-Csv -LiteralPath $raw)
if ($rows.Count -ne 25 -or @($rows[0].PSObject.Properties.Name).Count -ne 78) { throw 'Shape mismatch' }
if (@($rows | Where-Object { $_.sale_dte -ne '2025-08-01' }).Count -ne 0) { throw 'Date filter mismatch' }
git check-ignore -q -- $raw
if ($LASTEXITCODE -ne 0) { throw 'Raw CSV must remain Git-ignored' }
```

Next, qualify source-specific use rights and the meaning of `sale_dte`, `sale_price`, `load_dt`, corrections and multi-parcel rows. Then register a bounded, stratified 200-record manual audit before any adapter or model can use Sales Web labels. If historical public-availability evidence cannot be obtained, only project-observed prospective captures can support a separately named benchmark. No current download is retroactively available to an earlier origin.
