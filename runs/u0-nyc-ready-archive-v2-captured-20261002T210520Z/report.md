# NYC rolling archive version 62: bounded capture

Status: **verified source inventory; U0 and G-US pending**. Requirements:
US05, US08, US22 and US24. Frozen protocol: [ADR 0043](../../decisions/0043-nyc-ready-archive-status-v2.md), retaining [ADR 0042](../../decisions/0042-nyc-ready-rolling-archive-capture.md). The reviewed collector code was pushed at `a4e99bc2963a1e9f4cd5a0c00b600ab3ba238867` before this live capture.

## Observed result

| Field | Value |
| --- | --- |
| Dataset and archive version | NYC rolling sales `usep-8jbt`, version 62 |
| Portal revision `createdAt` | 2026-04-20T18:29:25.966Z |
| Capture interval | 2026-10-02T21:05:34.134Z to 21:05:46.764Z |
| CSV size | 11,302,195 bytes |
| Parsed source rows | 81,567 |
| CSV SHA-256 | `0746355101b245fb469ce97e19e088fa2b16f0f95728d7a5b07dd670e98c345f` |
| Header SHA-256 | `8c6ae5508597dec1810b16654c1e0958f7b16b4d3425e55c8ea7c6614982048f` |
| Collector manifest | [manifest.json](manifest.json) |
| Public aggregate | [aggregate.json](aggregate.json) |

The capture command was `.venv\Scripts\python.exe scripts/capture_nyc_generated_archive.py capture data/raw/nyc_dof/ready-archive-v2-20261002T210520Z` and exited 0. It made the five fixed anonymous GETs. Before and after checks agreed on the visible version-62 revision and the exact six-field `done` status. The raw CSV and JSON responses remain in a Git-ignored, ACL-protected local directory. No source row, address or returned storage path is published here.

Offline replay with `.venv\Scripts\python.exe scripts/capture_nyc_generated_archive.py replay data/raw/nyc_dof/ready-archive-v2-20261002T210520Z` exited 0 and reproduced the same aggregate. The [verifier](verify_artifacts.ps1) checks the private bytes against the committed manifest and repeats the replay; its [test gate](test_gate.json) records exit 0 and duration. The earlier v1 attempt remains [FAILED_STATUS_SCHEMA](../u0-nyc-ready-archive-v1-failed-20261001T104628Z/report.md); this v2 run has its own run ID and does not rewrite that failure.

## Evidence boundary

This establishes that version 62 has a retrievable, row-containing CSV with the recorded aggregate and hash. The portal revision time is **not** each row's first publication time. The file has not been audited for one economic transfer per row, arm's-length consideration, reliable unit identity, true close-date meaning or dataset-specific release rights. Current property attributes are not historical as-of features merely because sale rows exist in an archive. No model may train on these rows for certification yet.

NYC sale labels certified: **0**. Historical as-of eligibility: **false**. U0 and G-US: **PENDING**. The next source experiment is a separately frozen, read-only comparison of version 62 with the current snapshot and official dated exports to investigate row changes and publication timing; independently pursue DOF date/rights clarification, instrument evidence and the remaining 190 manual review rubrics. No country expansion is unlocked.
