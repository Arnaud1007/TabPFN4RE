# NYC borough worksheet inspection v3: four structural passes

**Requirements:** US05, US07, US08, US22, US23, US24. **U0:** pending. **G-US:** pending.

The reviewed v3 code was pushed at `aae83e201710f8e5d04a40f64d44f6c1305bb7ed` before it opened worksheet cells. The protected [private run](../../data/raw/nyc_dof/worksheet-inspection-v3-20260930T092659Z-6acaf2c84265/) used the five byte-pinned NYC Department of Finance borough XLSX files. Its clean-tree intent contains both correct environment-lock hashes. The inspection and independent offline replay exited 0 and matched the canonical private and public results. The [redacted aggregate](aggregate.json), [manifest](manifest.json), [test gate](test_gate.json) and [verifier](verify_artifacts.ps1) retain the publishable evidence.

All five workbooks have the exact 21-column row-5 header under the frozen single-column alias and the same raw fingerprint `4f8efb3fe379c1adb05938d397271d6c38002b6c2fdbe2224b3c4aa68d529e95`. Dates in their post-header rows parse within 2025-09-01 through 2026-08-31; the aggregate counts 82,370 physical rows and 82,345 post-header data rows. Bronx, Brooklyn, Queens and Staten Island pass the strict **worksheet structure** rule. Manhattan remains unqualified because one formula appears in a preamble cell. The v3 rule forbids formulas anywhere, so that failure is retained; its location does not permit an unregistered exception. No sale price was interpreted. **Zero transaction labels are certified.** Physical and data row counts are not eligible sale counts.

The synthetic RED tests covered the exact alias, row placement, header fingerprint, duplicate candidate, formulas, dates, ZIP/XML/MIME controls, private lineage and public redaction, lock drift, failure artifacts and replay. Thirty-two focused tests passed with branch-aware coverage of 90% for the runner and 94% for the XML parser. The full suite passed 608 tests with no skips. Ruff, `pip check`, scoped `pip-audit`, and independent code, Python and security reviews passed. An earlier full-suite attempt failed on an unrelated flaky HCPA test that matched a coincidental digest substring; its failure and correction are preserved in [failed_test_attempt.md](failed_test_attempt.md).

Run from the project root with authorised local captured workbooks:

```powershell
.\.venv\Scripts\python.exe scripts/inspect_nyc_dof_borough_exports_v3.py inspect data/raw/nyc_dof/official-exports-20260929T033558Z-62ad417fb39f data/raw/nyc_dof/worksheet-inspection-v3-20260930T092659Z-6acaf2c84265
.\.venv\Scripts\python.exe scripts/inspect_nyc_dof_borough_exports_v3.py replay data/raw/nyc_dof/official-exports-20260929T033558Z-62ad417fb39f data/raw/nyc_dof/worksheet-inspection-v3-20260930T092659Z-6acaf2c84265
& 'runs/u0-nyc-worksheet-inspection-v3-20260930T092659Z/verify_artifacts.ps1'
```

The first command is create-only and **must not be rerun** on the same output path. Replay and verification are safe. The next technical step is to freeze a same-publisher row-comparison protocol for the four structurally qualified boroughs and separately diagnose Manhattan's preamble formula under a new decision; do not change this v3 rule or result. Rights, actual close-date meaning, first row availability, transfer/unit identity, and the 200-record NYC manual audit (zero complete) remain independent blockers for U0 and G-US. No NYC model training or certification is unlocked.
