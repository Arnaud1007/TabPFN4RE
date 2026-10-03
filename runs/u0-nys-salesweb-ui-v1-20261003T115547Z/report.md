# New York State Sales Web current static UI inventory

Run ID: `u0-nys-salesweb-ui-v1-20261003T115547Z`
Date: 2026-10-03
Status: **documentation verified, source admission pending**
Requirements: US05, US08, US24

## Objective and method

Check whether the current Municipal Data Portal exposes the field names and
timing clues described only in the older SalesWeb dictionary. The official
[portal page](https://www.tax.ny.gov/pit/property/munidataportal.htm) links to
`https://pad.tax.ny.gov/`. The portal's root HTML loaded
`https://pad.tax.ny.gov/base/js/spa.js`. A bounded GET saved that public static
asset under Git-ignored `data/raw/nys_salesweb_portal/spa.js`. No property
search, export, API row request, login or terms acceptance occurred.

The acquisition used HTTPS, no redirect, a 20-second timeout and a 2 MB byte
cap. The HEAD request returned HTTP 200, content length 1,378,915 bytes,
ETag `"69712598-150a63"` and last-modified
`Wed, 21 Jan 2026 19:14:32 GMT`; the GET exited 0 and its SHA-256 was
`36af85aa06fce5839eec5a0adb354548cafd8adc2e2db410dd40bc810773627c`.
The local extraction checked the exact byte count and hash, then selected 13
static `PADT_*` labels/help strings into [observation.json](observation.json).
The local copy of the public asset is not committed because a fresh reader can fetch the
published URL and compare the hash.

## Observed evidence and limits

The static bundle declares sale date, sale price, deed date, contract date,
arm's length, part of parcel, condo, class at sale, sale-loaded date and
last-update labels. Its help text says the sale-loaded date is when a sale was
initially entered or loaded by New York State. This narrows the question for
the publisher; it is **not** evidence that the date is the row's first public
availability. Static strings do not prove the rendered UI or Excel export
contains the same fields, their exact types, correction history or their
transaction-level meanings. The live interactive portal could not be
inspected through the browser surface available in this session.

The official portal page says Sales Web is updated weekly, may receive sales
after several weeks, and permits Excel download of search results. Its
[RP-5217 guidance](https://www.tax.ny.gov/pdf/current_forms/orpts/rp5217pdfins.pdf)
still supplies the stronger definitions for title conveyance and price, but
no current exported row has been matched to that form here.

**Property rows acquired: 0. Certified sale labels: 0. U0 and G-US: PENDING.**
No model fit or frozen split changed, and no source-specific commercial or
redistribution right was established. The current export schema, row-level
first public availability and historical attribute vintages remain the next
source-admission evidence needs. See the updated
[source card](../../data/source_cards/nys_salesweb.yaml) and
[ADR 0066](../../decisions/0066-nys-salesweb-source-feasibility.md).

## Replay

From the project root in PowerShell, if the same static version remains live:

```powershell
New-Item -ItemType Directory -Path 'data/raw/nys_salesweb_portal' -Force | Out-Null
$assetPath = 'data/raw/nys_salesweb_portal/spa-replay.js'
if (Test-Path -LiteralPath $assetPath) { throw 'Choose a new replay path' }
curl.exe --proto '=https' --max-redirs 0 --max-time 20 --max-filesize 2000000 --silent --show-error --output $assetPath https://pad.tax.ny.gov/base/js/spa.js
Get-FileHash -LiteralPath $assetPath -Algorithm SHA256
```

The replay must not overwrite an existing immutable raw copy; use a new
ignored path for a later version. A new hash is a new source observation,
not a failed reproduction of the documented 3 October bytes.

This is a source-observation run, not a model or release-gate run. The exact
original GET duration was not captured; `observation.json` records that gap
alongside the command, exit code and baseline commit.
