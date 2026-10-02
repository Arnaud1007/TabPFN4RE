# NYC rolling archive version 61: bounded capture

Status: **verified source inventory; U0, U3 and G-US PENDING**. Requirements: US05, US08, US22 and US24. The capture followed [ADR 0047](../../decisions/0047-nyc-ready-archive-v61.md). The collector was pushed at `0e0fb29f50a75d42bbd337845de87dc92a0a5c7c`; the frozen plan was pushed at `99dd1a0ce65937753afcc29c361d2228d8673533` before the live read. The [manifest](manifest.json) records that latter clean-tree commit as the run's code commit.

## Observed source inventory

| Field | Observed value |
| --- | --- |
| Publisher dataset and version | NYC rolling sales `usep-8jbt`, archive version 61 |
| Portal revision `createdAt` | `2026-01-27T14:48:20.467Z` |
| Capture interval | `2026-10-02T23:04:52.491Z` to `2026-10-02T23:04:59.513Z` |
| Anonymous GETs | Five fixed, ordered requests; no archive-generation request |
| Strict CSV data rows | 79,335 |
| CSV bytes | 11,120,362 |
| CSV SHA-256 | `19ecb0eb368df66f60758098213fd4855109e6afa20c82e99787930b893ba0f7` |
| Header SHA-256 | `8c6ae5508597dec1810b16654c1e0958f7b16b4d3425e55c8ea7c6614982048f` |
| Public projection | [aggregate.json](aggregate.json) |
| Private original responses | Git-ignored `data/raw/nyc_dof/ready-archive-v61-20261002T230327Z/` |

The live capture command was `.venv\Scripts\python.exe scripts/capture_nyc_generated_archive_v61.py capture data/raw/nyc_dof/ready-archive-v61-20261002T230327Z` (exit 0). The before and after list/status responses agreed; the CSV passed bounded parsing and hashing. The source responses and row-level data remain private. Offline replay with `.venv\Scripts\python.exe scripts/capture_nyc_generated_archive_v61.py replay data/raw/nyc_dof/ready-archive-v61-20261002T230327Z` exited 0 and reproduced the aggregate. The public `& 'runs/u0-nyc-ready-archive-v61-20261002T230327Z/verify_artifacts.ps1'` checked committed/private artifact hashes and offline replay, exited 0 in 1.074 seconds, and printed: `NYC version-61 archive: private hashes and offline replay verified; zero labels certified; U0, U3 and G-US pending`.

The [test gate](test_gate.json) records 10/10 focused v61 tests, 41/41 combined v61/v62 tests, 82% branch-aware v61 module coverage, 938/938 full-suite tests with zero skips, Ruff and dependency-audit results. The initially attempted coverage command selected the wrong source and collected no data; it was corrected before reporting the 82% result. The saved version-62 private replay still exits 0 with its unchanged 81,567-row aggregate. These checks establish collector integrity, not transaction-label suitability.

## Unresolved evidence and next action

Version 61 has 79,335 source rows and version 62 has 81,567. This report **does not compare their row membership** or infer additions, deletions or corrections from the count difference. The version-61 revision timestamp is not a per-row first-publication timestamp. `SALE DATE` has no verified close/contract mapping. Repeated deed consideration, dwelling and unit identity, dataset-specific commercial rights, and historical property-attribute availability remain unresolved. The archive alone does not establish 24 months of usable pre-origin features or mature temporal test labels.

Certified NYC sale labels: **0**. Historical as-of eligibility: **false**. No real NYC model training, U3 acceptance, G-US claim or international implementation is unlocked. Next, freeze and implement a separate v61/v62 row-level source-representation comparison using the two immutable private captures, then seek publisher publication and date semantics evidence. Continue the source rights and manual transaction review independently. Preserve both captured archives and earlier failed attempts unchanged.
