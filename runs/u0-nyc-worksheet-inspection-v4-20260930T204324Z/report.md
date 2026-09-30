# NYC borough worksheet inspection v4: five structural passes

**Requirements:** US05, US07, US08, US22, US23, US24. **Worksheet structure:** five of five qualified under v4. **U0:** pending. **G-US:** pending.

The [frozen v4 plan](plan.md) was pushed after reviewed code `80af77fdd4faafedafd7c0e85ecd3bf0d100a078` and before the private workbooks were opened by v4. The protected create-only run recorded a clean tree at `c1c2b5a82dc5f077b63e551ffecd99eb2c45b256`. It replayed the earlier protected Manhattan diagnostic, inspected the five pinned official XLSX files, and passed an independent offline byte-identical replay. The [public aggregate](aggregate.json), [test gate](test_gate.json), [manifest](manifest.json) and [verifier](verify_artifacts.ps1) retain publishable evidence; formula details and private fingerprints remain under ignored, ACL-protected storage.

All five workbooks pass the **v4 worksheet structure** rule. Manhattan alone uses the exact private preamble-formula exception; its header and data remain formula-free. Bronx, Brooklyn, Queens and Staten Island continue to pass the unchanged v3 checks. The preserved v3 run was replayed and still reports **four** structural passes with Manhattan unqualified under v3. The two protocol results are kept distinct.

This inspection does not interpret sale consideration or establish an economic transfer. The 82,345 post-header rows across the five files are source rows, **not certified sale labels**. `sale_labels_certified` remains **zero**. The v4 exception does not use the preamble formula or its cached value as a feature, date or freshness signal.

Twelve focused synthetic tests passed with branch-aware coverage of 82% for the runner and 89% for the core. The full Python 3.11 suite passed 841 tests with no skips; its [log](../u0-nyc-worksheet-v4-code-20260930T203800Z/full_suite.log) is retained. Ruff, `pip check`, scoped `pip-audit`, independent code/Python/security reviews, the v3 artifact verifier and the v3 private replay passed.

To verify with authorised local source files, run from the project root:

```powershell
& 'runs/u0-nyc-worksheet-inspection-v4-20260930T204324Z/verify_artifacts.ps1'
.\.venv\Scripts\python.exe scripts/inspect_nyc_dof_borough_exports_v4.py replay data/raw/nyc_dof/official-exports-20260929T033558Z-62ad417fb39f data/raw/nyc_dof/worksheet-inspection-v4-20260930T204324Z-417da725ab3d
```

The next dependency-ready NYC work is to review the remaining 190 sampled source records and resolve dataset-specific reuse rights, true close-date meaning, first row availability and economic-transfer/unit identity. A later row-comparison protocol may include Manhattan, but v4 structural qualification alone does not admit training labels. Do not start NYC model training or international implementation while U0 and G-US remain pending.
