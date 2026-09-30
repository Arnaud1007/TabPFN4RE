# NYC same-publisher row concordance v1: exact agreement unproven

**Requirements:** US04–US08, US22–US24. **U0:** pending. **G-US:** pending.

The reviewed code was pushed to `audit/u0` at `642f6afa284b444b342535ef4b241c3d75fd6932` before this comparison read source rows. The [frozen protocol](../../decisions/0033-nyc-same-publisher-row-concordance.md) compares the pinned NYC rolling API CSV with four structurally qualified borough XLSX files. Manhattan remains outside the frame because its v3 worksheet inspection failed. The protected [private run](../../data/raw/nyc_dof/row-concordance-v1-20260930T132740Z-93eb58530149/) has a clean-tree intent, source and code hashes, source ordinals and row fingerprints. Its comparison and independent offline replay both exited 0 and produced byte-identical results. The [redacted aggregate](aggregate.json), [manifest](manifest.json), [test gate](test_gate.json) and [verifier](verify_artifacts.ps1) are the publishable evidence.

The frame contains 62,792 CSV rows and 62,792 XLSX rows across Bronx, Brooklyn, Queens and Staten Island. Bronx, Brooklyn and Queens each had **zero exact six-field candidate-key pairs and zero complete 21-field matches**. Their respective source row counts still agree (6,424, 23,041 and 26,461). Staten Island has 6,866 rows in each source, but its detailed comparison is suppressed because at least one category count is between one and four. No pooled exact-match count is published because it could reveal the suppressed cell. The exact-string rule trims outer whitespace only; it does not normalize dates, price notation, leading zeros or address text. The result establishes a representation mismatch under this rule, not distinct economic transfers or a known formatting cause.

The synthetic RED tests covered pinned-byte and path checks, strict CSV/XLSX parsing, exact keys and duplicate ambiguity, small-cell suppression, atomic publishing, interruption and replay. Forty-nine focused tests passed with branch-aware coverage of 81% for the runner, 95% for the comparison core and 89% for input scanning. The full repository suite passed 658 tests with no skips. Ruff, `pip check`, scoped `pip-audit`, and independent code, Python and security reviews passed. No private row, address, price, ordinal or fingerprint appears in the tracked aggregate.

Run from the project root with the authorised local source files:

```powershell
.\.venv\Scripts\python.exe scripts/compare_nyc_rolling_borough_rows.py replay data/raw/nyc_dof/row-concordance-v1-20260930T132740Z-93eb58530149
& 'runs/u0-nyc-row-concordance-v1-20260930T132740Z/verify_artifacts.ps1'
```

The create-only comparison must not be rerun at the same path. Next, freeze a separate diagnostic for field-format differences and candidate matching that does not retroactively alter v1. Independently diagnose Manhattan's preamble formula. Source rights, actual close-date meaning, first row availability, transfer/unit identity and the 200-record NYC manual audit (zero complete) remain unresolved. **Zero sale labels are certified**, and no NYC model training or G-US claim is unlocked.
