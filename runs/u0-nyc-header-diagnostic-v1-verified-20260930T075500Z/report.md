# NYC borough header diagnostic v1: verified candidate-only evidence

**Requirements:** US05, US07, US08, US22, US23, US24. **U0:** pending. **G-US:** pending.

The diagnostic was run against the five byte-pinned official borough XLSX files only after corrected, reviewed code was pushed at `7d7ba0759e84bd4f7d5b127749ffece858ef3e4c`. The private run `data/raw/nyc_dof/header-diagnostic-20260930T075500Z-ab8936b58a5a/` has a clean-tree intent, the correct diagnostic and worksheet-inspection environment lock hashes, the full private candidate vector, a redacted public projection, and a hash manifest. Independent offline replay exited 0 and matched both canonical private and public results. The [public aggregate](aggregate.json), [manifest](manifest.json), and [test gate](test_gate.json) retain safe evidence. The [verifier](verify_artifacts.ps1) checks the retained hashes and candidate-only status.

All five files contain a unique 21-cell candidate at worksheet source row 5, physical ordinal 5, with zero formulas and zero cells beyond column U in that row. Each matches 20 of the 21 ordered rolling API header names. The candidate fingerprint is identical across boroughs: `4f8efb3fe379c1adb05938d397271d6c38002b6c2fdbe2224b3c4aa68d529e95`. A private comparison of the protected strings found exactly one difference: workbook column G `EASEMENT` versus API column G `EASE-MENT`. That spelling is the only proposed mapping candidate; it is not yet an accepted workbook schema. The aggregate physical-row count is 82,370, not 82,370 eligible sales.

The preceding [preliminary run](../u0-nyc-header-diagnostic-v1-20260930T073001Z/report.md) reached the same candidate result but recorded the wrong environment lock in its intent. It remains frozen with `PRELIMINARY_PROVENANCE_MISMATCH` status. The corrected run has a new ID and did not overwrite it. V1 and v2 worksheet-inspection failures also remain unchanged.

The correction's regression tests first failed on the wrong lock hash and an unretryable empty directory when the diagnostic lock was absent, then passed after the fix. The final 27 focused tests passed with branch-aware coverage of 83% for the runner and 89% for the XML scanner. The full suite passed 576 tests with no skips using the pinned local Ames fixture. Ruff lint and format, `pip check`, scoped `pip-audit`, and independent code, Python and security reviews passed. Commands, measured durations and statuses are in `test_gate.json`.

Exact source commands from the project root:

```powershell
.\.venv\Scripts\python.exe scripts/diagnose_nyc_borough_headers.py diagnose data/raw/nyc_dof/official-exports-20260929T033558Z-62ad417fb39f data/raw/nyc_dof/header-diagnostic-20260930T075500Z-ab8936b58a5a
.\.venv\Scripts\python.exe scripts/diagnose_nyc_borough_headers.py replay data/raw/nyc_dof/official-exports-20260929T033558Z-62ad417fb39f data/raw/nyc_dof/header-diagnostic-20260930T075500Z-ab8936b58a5a
& 'runs/u0-nyc-header-diagnostic-v1-verified-20260930T075500Z/verify_artifacts.ps1'
```

Both source commands exited 0. The diagnostic intentionally did not interpret transaction rows, sale dates or prices. It certified **zero labels and zero boroughs**. The next dependent step is a new, frozen worksheet qualification protocol with an exact column-G alias and all v2 structure/date/integrity safeguards, followed by tests and a new run. Rights, close-date semantics, first availability, transfer/unit identity, and the 200-record manual audit (zero complete) remain separate blockers for U0 and G-US.
