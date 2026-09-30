# NYC borough header diagnostic v1: candidate found, provenance correction required

**Requirements:** US05, US07, US08, US22, US23, US24. **U0:** pending. **G-US:** pending.

The reviewed diagnostic code was committed and present on `origin/audit/u0` at `757540b694cef30109046021e8e97ff4cf52efd7` before this private workbook read. The immutable private run is `data/raw/nyc_dof/header-diagnostic-20260930T073001Z-79529824f388/`. It read the five byte-pinned workbooks under [ADR 0031](../../decisions/0031-nyc-borough-header-diagnostic.md), returned a redacted [aggregate](aggregate.json), and its offline replay exited 0 with the same candidate-only projection. The public [manifest](manifest.json) binds the private files and capture hashes.

Every borough had a unique, formula-free 21-cell candidate at worksheet row 5, physical ordinal 5. Each scored 20 of 21 exact positional matches against the pinned rolling API header, with the same candidate fingerprint `4f8efb3fe379c1adb05938d397271d6c38002b6c2fdbe2224b3c4aa68d529e95`. Private inspection of that protected vector found the sole difference at column G: workbook `EASEMENT` versus API `EASE-MENT`. The private comparison confirmed the full trimmed vector was identical across all five files. These observations identify a schema candidate only; no sale row, price, date, or label was qualified.

During evidence review, the intent's `environment_lock_sha256` was found to identify the earlier worksheet-inspection lock (`581fb3eb3c479a93552238c3aabe2a5fa138536c5597477e431b91e609fddf06`) rather than the dedicated header-diagnostic lock (`d54e08c3bd00a2da18d2aaf8bad388694c01fd8d16c0a297fe53c837a3651013`). Preserve this run as **preliminary with provenance mismatch**. A regression test reproduced the defect. The lock attribution is being corrected before a new, separately identified private run; no artifact here is rewritten or promoted to a qualified source.

Exact commands run from the project root:

```powershell
.\.venv\Scripts\python.exe scripts/diagnose_nyc_borough_headers.py plan
.\.venv\Scripts\python.exe scripts/diagnose_nyc_borough_headers.py diagnose data/raw/nyc_dof/official-exports-20260929T033558Z-62ad417fb39f data/raw/nyc_dof/header-diagnostic-20260930T073001Z-79529824f388
.\.venv\Scripts\python.exe scripts/diagnose_nyc_borough_headers.py replay data/raw/nyc_dof/official-exports-20260929T033558Z-62ad417fb39f data/raw/nyc_dof/header-diagnostic-20260930T073001Z-79529824f388
& 'runs/u0-nyc-header-diagnostic-v1-20260930T073001Z/verify_artifacts.ps1'
```

The first three commands exited 0. The verifier checks the retained public/private hashes and candidate-only status. The earlier v1 and v2 worksheet inspections remain unchanged and unqualified. Rights, close-date semantics, first availability, transfer/unit identity, and the 200-record manual review (zero completed) remain independent blockers.
