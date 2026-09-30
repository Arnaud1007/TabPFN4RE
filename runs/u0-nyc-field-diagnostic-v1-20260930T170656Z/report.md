# NYC protected field diagnostic v1

**Requirements:** US04–US08, US22–US24. **Diagnostic:** implemented and verified. **U0:** pending and unaccepted. **G-US:** pending. **Sale labels certified:** 0.

The [frozen protocol](../../decisions/0035-nyc-v2-field-diagnostic.md) and analyzer were pushed on `audit/u0` at `adbb1e1fc3f726d2e51047dbf17cb808cdb6d0d0` before this diagnostic opened the protected v2 result. The analyzer read only the pinned v2 result artifacts, not the original transaction CSV or borough workbooks. Its private run is under Git-ignored, access-controlled `data/raw/nyc_dof/field-diagnostic-v1-20260930T170656Z-f94fe9bb66b3/`.

The analysis and offline replay exited 0; replay reproduced the private and public result bytes. The tracked [aggregate](aggregate.json) is a byte-identical copy of the protected `public.json`. It is a fixed `private_only_v1` projection: all four boroughs have null flags and null selected headers. No private field counts, ranked headers, lexical forms, row ledger, ordinals or fingerprints are published. The protected result may be inspected only locally under its ACL for the separately authorised source audit. The [manifest](manifest.json), [test gate](test_gate.json) and [verifier](verify_artifacts.ps1) pin provenance without releasing private findings.

This run verifies that the frozen v2 counters can be interpreted and checked under the new privacy protocol. It does not settle whether two candidate rows describe one economic transfer, establish close-date or first-publication semantics, qualify a parcel/unit identity, or admit any training label. The NYC manual audit remains at 0 of 200 completed source records. U0 and G-US remain **PENDING**; the diagnostic is neither an accepted US release nor a sale-price accuracy result.

The 30 focused synthetic tests passed, with 86% branch-aware coverage of the new runner. The full suite passed 749 tests in 148.059 seconds with no skips using the locally pinned Ames fixture. A separate 749-test rerun passed in 147.323 seconds; its [terminal output](full_suite.log) is archived with local user-home paths redacted. Ruff lint and format, `pip check`, scoped `pip-audit`, and focused HCPA regression tests passed. Independent code review approved the change with no findings and security review passed. An earlier full-suite attempt failed 13 HCPA tests when the host had 0.93 GB free against a 3 GB fixture precondition; the synthetic fixture was corrected and the complete suite then passed. The failed attempt is retained as a failed attempt, not a valid gate result. Observed analyzer and replay wall times were 5.331 and 3.872 seconds, respectively.

Verify from the project root with the authorised protected artifacts still present. The public verifier invokes the read-only private replay first, which checks ACL, path and link protections before comparing hashes; it prints only the fixed public result:

```powershell
& 'runs/u0-nyc-field-diagnostic-v1-20260930T170656Z/verify_artifacts.ps1'
.\.venv\Scripts\python.exe scripts/diagnose_nyc_representation_fields_v1.py replay data/raw/nyc_dof/field-diagnostic-v1-20260930T170656Z-f94fe9bb66b3
```

The next runnable source work is to obtain and record NYC dataset-specific reuse rights, true close-date meaning, first row availability, transfer/unit identity, and 200 stratified manual source reviews. Diagnose Manhattan's preamble formula separately under a frozen protocol. These dependencies block NYC sale-label admission, and no international implementation is unlocked.
