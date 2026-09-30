# NYC Manhattan preamble formula diagnostic v1

**Requirements:** US05, US07, US08, US22, US23, US24. **Diagnostic:** passed. **U0:** pending. **G-US:** pending.

The [frozen plan](plan.md) and reviewed code were pushed before opening the pinned private Manhattan workbook. The create-only diagnostic completed from a clean tree at `a38edfd5d15ebb45e6e02a462b5f67e23b0ce2cc`; the independent offline replay returned byte-identical private and public results. The protected local run contains the formula details and hashes. Its [public aggregate](aggregate.json) is a fixed redaction and contains no expression, coordinate, attributes, cached value, or private result fingerprint.

The diagnostic confirms the frozen v3 worksheet decision is still **unqualified**. It does not interpret a sale price, admit a transaction row, change the v3 result or certify a label. **Zero sale labels are certified.** A new worksheet policy would require a separate versioned decision and tests; this diagnostic alone cannot qualify Manhattan.

The [test gate](test_gate.json) records 14 focused tests, 82% runner and 83% XML branch-aware coverage, and 829 full-suite tests passing with one optional integration skip. Ruff, `pip check`, scoped `pip-audit`, code review, Python review and security review passed. The [full-suite log](../u0-nyc-manhattan-formula-code-20260930T201000Z/full_suite.log) retains actual output. The local [verifier](verify_artifacts.ps1) replays the protected result and checks public artifacts without printing the formula.

From the project root, with authorised local source files:

```powershell
& 'runs/u0-nyc-manhattan-formula-v1-20260930T201602Z/verify_artifacts.ps1'
.\.venv\Scripts\python.exe scripts/diagnose_nyc_manhattan_formula_v1.py replay data/raw/nyc_dof/official-exports-20260929T033558Z-62ad417fb39f data/raw/nyc_dof/manhattan-formula-v1-20260930T201602Z-6d714e014144
```

The next technical decision is whether a new v4 protocol may exclude a tightly defined preamble-only formula from feature and label parsing. Evaluate that proposal against the private evidence; preserve v3 unchanged and rerun on a new protocol if adopted. Independently, NYC dataset-specific reuse rights, true close-date meaning, first row availability, transfer/unit identity and 190 remaining manual source-review rubrics remain unresolved. U0 and G-US cannot pass, and NYC transaction rows must not be used for model training yet.
