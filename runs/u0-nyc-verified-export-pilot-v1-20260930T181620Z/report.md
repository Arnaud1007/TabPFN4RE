# NYC verified export comparison pilot v1

**Requirements:** US04–US08, US22–US24. **Pilot:** implemented and verified. **U0:** pending. **G-US:** pending. **Sale labels certified:** 0.

The [frozen protocol](../../decisions/0036-nyc-verified-export-pilot.md) and reviewed code were pushed to `audit/u0` at `bbb881bd7a342dc302e3599df58867ee22c80314` before the first new protected sample or source-row read. The run used the pinned 200-row NYC sample, rolling CSV, four structurally qualified official borough workbooks, and v3 structural result. The registered selector chose ten sample rows without replacement or result-based substitution. Manhattan was outside this protocol because its v3 worksheet structure was not qualified.

The [public plan](plan.json) was captured without reading private rows. The create-only analysis completed and its offline replay reproduced the private and public bytes. The protected run is under Git-ignored, access-controlled `data/raw/nyc_dof/verified-export-pilot-v1-20260930T181620Z-70ed3ced7f7d/`. The tracked [aggregate](aggregate.json) is an exact copy of its `public.json`: four borough names, null findings, and zero certified sale labels. The public artifacts contain no selected ordinals, match-status counts, row values, differences, or fingerprints. The [manifest](manifest.json) and [verifier](verify_artifacts.ps1) pin protected artifact hashes for local replay without publishing findings.

This pilot compares two same-publisher representations. It does **not** establish economic-transfer identity, arm's-length consideration, dwelling or unit identity, a true closing date, first historical availability, or dataset-specific commercial reuse rights. The NYC manual audit remains **0 of 200** completed source reviews; the ten selected rows are leads for that audit, not completed reviews. No NYC model training or label admission is unlocked.

The final focused synthetic suite passed 16 core and 21 runner tests. Branch-aware coverage was 93% for the core, 90% for the runner, and 91% combined. The complete suite passed **786 tests with no skips** in 186.814 seconds; its [terminal output](full_suite.log) is archived with local home paths redacted. Ruff check and format, `pip check`, and scoped `pip-audit` passed. Independent code, Python, and security reviews approved the final code. A post-fix full-suite start initially failed while the host disk had no free space; no raw evidence was removed, and the subsequent complete run passed. The earlier pre-fix complete suite passed 785 tests but is not used as the final gate.

Verify locally from the project root with the protected source artifacts still present:

```powershell
& 'runs/u0-nyc-verified-export-pilot-v1-20260930T181620Z/verify_artifacts.ps1'
.\.venv\Scripts\python.exe scripts/verify_nyc_review_artifacts_v2.py replay data/raw/nyc_dof/verified-export-pilot-v1-20260930T181620Z-70ed3ced7f7d
```

The [test gate](test_gate.json) records commands and observed outcomes. Next, resolve dataset-specific reuse rights, sale-date meaning, first row availability and transfer/unit identity, then complete the 200 stratified manual reviews under the existing ledger. Diagnose Manhattan's preamble formula in a separately frozen protocol. U0 and G-US remain **PENDING**; international implementation stays locked.
