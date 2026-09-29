# U0 NYC rolling archive metadata probe

Run ID: `u0-nyc-archive-metadata-20260929T021258Z`  
Status: **verified metadata inventory only; U0 and G-US PENDING**  
Code commit at capture: `c70f00844b064de50e5f5ed04ac5e126d0839866`  
Requirements: US05, US08, US22, US24

## Objective and frozen protocol

Determine which revision identifiers the NYC Open Data rolling-sales portal
currently lists, without requesting an archived CSV or starting generation.
[ADR 0024](../../decisions/0024-nyc-archive-metadata-probe.md) was reviewed and
pushed before the probe. The collector and tests were separately reviewed,
committed and pushed before the live request. The fixed route is an observed
**internal** portal metadata endpoint, not a documented archival API contract.
The [platform guide](https://support.socrata.com/hc/en-us/articles/9486838238743-Introducing-Dataset-Archiving)
says its Export Archive action can start generation; that action and the
undocumented CSV route were excluded.

## Actual observations

One anonymous GET returned HTTP 200 and 1,130 JSON bytes at
`2026-09-29T02:13:17.885283+00:00`. The saved private response SHA-256 is
`f384664c57b701a7908c8c9ec6620095c7f7ad3cceeaba9204d142d4aea0f2f9`.
The [allowlisted aggregate](aggregate.json) reports 13 visible revision records,
versions 53 through 65. Their portal `createdAt` values range from
2025-03-12 to 2026-09-15. Both the [offline replay](replay.json) and the
aggregate have SHA-256
`40e8fa2e53feb6f911df538cd62b0e393c633caa2f47bb7e95251ced71a2bcb3`.

No CSV bytes, property rows, transaction labels, or row-level publication times
were obtained. A visible revision and its creation timestamp do not prove an
archived CSV is downloadable or show when any sale row first became available.
The earlier three exploratory HEAD results of HTTP 406 remain route observations
only; this frozen run made no HEAD request. Source-specific product and
redistribution rights, sale/close-date semantics, property/unit identity, and
historical attribute vintages remain unresolved.

## Reproduction and checks

The exact fixed route and commands are in [configuration.json](configuration.json).
The private raw body and its capture manifest live only under ignored
`data/raw/nyc_dof/archive-metadata-20260929T021258Z/`. Run from the project
root:

```powershell
& 'runs/u0-nyc-archive-metadata-20260929T021258Z/verify_artifacts.ps1'
.\.venv\Scripts\python.exe scripts/probe_nyc_archives.py replay data/raw/nyc_dof/archive-metadata-20260929T021258Z
```

The [run manifest](manifest.json) binds the code commit and blobs, environment
lock, configuration, source bytes and immutable public artifacts. The verifier
passed against the private body and both public reports. [test_gate.json](test_gate.json)
records the actual commands and exits: 13 focused tests passed with 94%
measured statement/branch coverage of the collector; the full repository suite
passed 459 tests with zero skips; Ruff, `pip check` and a scoped pinned
dependency audit passed. The live GET and offline replay each exited 0. A
pre-protocol exploratory PowerShell digest call failed because its SHA-256
static method was unavailable; a corrected read-only call recovered the same
metadata hash and did not change the frozen collector or this run.

## Gate and next action

This verifies only revision **metadata**. NYC remains inventory-only, with no
certified historical as-of rows or sale labels. Qualify a supported archival
retrieval route and rights before seeking archived CSV bytes; archive generation
would require separate authorization. Continue the independent frozen
200-record manual source audit, currently at zero completed reviews. Do not
begin NYC model training or claim U0/G-US acceptance from this probe.
