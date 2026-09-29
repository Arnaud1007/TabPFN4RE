# U0 NYC official borough export capture v2

Run ID: `u0-nyc-official-export-v2-captured-20260929T033558Z`
Status: **five workbook byte streams captured; content unqualified; U0 and G-US PENDING**
Requirements: US05, US07, US22 and US24

## Objective and execution

Execute the five-URL, one-GET-per-borough source-byte capture defined by
[ADR 0026](../../decisions/0026-nyc-official-borough-export-capture.md) and
the fixed transparent user-agent revision in
[ADR 0028](../../decisions/0028-nyc-borough-export-user-agent-revision.md).
The reviewed v2 collector was pushed at `6f58c45` and the capture ran from
clean commit `841e20e`. The earlier failed v1 request remains preserved in
[its separate run](../u0-nyc-official-export-v1-failed-20260929T031155Z/report.md).

The five fixed HTTPS GETs each returned status 200 and the exact XLSX MIME.
The collector stored 8,094,187 compressed bytes in five ignored, protected
workbooks, with one receipt per file, an intent and a final manifest. It
enforced response, transfer, aggregate and ZIP safety limits. The private
manifest records request/completion times, byte counts, hashes and ZIP
member totals. [replay.json](replay.json) is the successful offline hash and
structure replay; [manifest.json](manifest.json) pins its hash and the private
intent and manifest hashes. Run `& 'runs/u0-nyc-official-export-v2-captured-20260929T033558Z/verify_artifacts.ps1'`
from the project root for version-independent byte-hash verification.

## Evidence boundary

The workbook filename/URL period is only an advertised period. Worksheet
cells, headers, sale dates, price fields and row counts have not yet been
qualified. These same-publisher files can potentially check consistency of
the existing rolling API snapshot; they cannot independently establish true
consideration, close versus deed dates, first row publication, commercial
use rights, single-home identity or historical feature vintages. No NYC
manual audit rubric has been completed and no row was admitted to a model.

Focused v2 collector tests passed 33/33 with 86% branch-aware collector
coverage. The full repository suite passed 510/510 tests, zero skips. Ruff,
dependency integrity and the scoped dependency audit passed. The synthetic
privacy test variable was renamed after a pre-commit hook false positive;
the focused suite and independent code review were repeated before commit.

## Next action

Qualify the workbook worksheet structure and advertised date period offline
under a separate frozen protocol, then compare only matched same-publisher
rows. Keep source rights, first availability, label semantics and the 200-row
manual review as independent blockers. U0 and G-US remain pending.
