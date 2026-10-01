# NYC Socrata row-system-timestamp diagnostic

Captured: 2026-09-30 21:26:44–21:26:49 UTC. Status: **diagnostic only**.
Requirements: US05, US08, US22, US24. Protocol: [ADR 0041](../../decisions/0041-nyc-socrata-row-timestamp-probe.md).

The reviewed, committed probe at `0e04e327c4ba48f995c12c6f15cb00a97d1baf86`
made the six fixed GETs: metadata, one aggregate, then metadata for each of
the two official NYC Open Data views. The local source bytes, private manifest
and aggregate are under ignored `data/raw/nyc_dof/system-timestamps-v1-20260930T212636Z/`.
Only the validated aggregate and a manifest of response hashes are published
here. Metadata before and after each aggregate had the same version values;
the saved response hashes and derived aggregate passed offline replay.

| Current API view | Rows | Current-row `:created_at` minimum | Current-row `:created_at` maximum | Complete system timestamps |
| --- | ---: | --- | --- | --- |
| Rolling `usep-8jbt` | 82,345 | 2026-09-15 15:56:41.775 UTC | 2026-09-15 15:56:41.775 UTC | 82,345 / 82,345 |
| Annualized `w2pb-icbu` | 845,607 | 2026-05-27 16:28:09.949 UTC | 2026-06-09 18:31:52.176 UTC | 845,607 / 845,607 |

The current-row `:updated_at` bounds equal the corresponding creation bounds
in this capture. These timestamps describe **current portal row instances**.
They do not establish when each transaction first appeared publicly in an
earlier release or prove how the publisher refreshed the views. The 82,345 and
845,607 counts are API rows, not eligible single-home transfers. The aggregate
does not verify the meaning of `SALE DATE`, the true closing date, property
unit identity, economic-transfer grain or commercial product rights. No
historical as-of feature or sale label is admitted: certified labels **0**.

## Evidence and replay

The [aggregate](aggregate.json) and [manifest](manifest.json) preserve the
fixed output and six source-response hashes. The code gate is
[`u0-nyc-system-timestamps-code-20260930T212103Z`](../u0-nyc-system-timestamps-code-20260930T212103Z/report.md):
30 focused tests passed, 89% branch-aware probe coverage, 871 repository tests
passed, lint and dependency checks passed. The live capture exited 0 and an
offline replay exited 0. From the project root, with the private capture
present, run:

```powershell
& 'runs/u0-nyc-system-timestamps-v1-20260930T212636Z/verify_artifacts.ps1'
```

The next source-evidence task is a dated row-containing archive or publisher
publication log establishing historical first availability. Separately,
inspect a verified deed instrument for the frozen NYC lead, resolve the DOF
date and use-rights inquiry, and continue the 190 remaining review rubrics.
U0 and G-US remain **PENDING**. No real-data model training or country expansion
is unlocked.
