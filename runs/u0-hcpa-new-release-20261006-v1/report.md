# HCPA new-release capture checkpoint, 6 October 2026

Status: **new exact parcel release observed; source remains unqualified; G-US PENDING**.
Requirements: US05, US08, US22, US24.

## Result

The clean-commit `--new-only` command checked the official HCPA listing at
`2026-10-06T00:30:18.804786Z`. It skipped the already represented
`allsales_09_18_2026.zip` file and captured only the newly listed
`parcels_10_05_2026.zip` archive.

The exact parcel archive contains 155,508,715 bytes and has SHA-256
`b6451f5889fd63aa621d4d0266c25c1f7e2b95dfdca6f9ea0f498108c31188c6`.
Capture completed at `2026-10-06T00:30:31.715649Z` from clean implementation
commit `f7958a94ab420977bae33cc1257db4cec69bda5b`. The private ledger classifies
it as `new_release`; its three-event chain now has SHA-256
`c8ba62169bf04912aaa71a1942688cb065a68d6a8b469826db73436dfcfe64e8`.

No raw archive, parcel rows, addresses or property identifiers are tracked in
this evidence directory. See the [privacy-safe summary](summary.json).

## Verification

- 27 focused capture, orchestration and ledger tests passed.
- Branch coverage was 87% for the capture module and 86% for the ledger module.
- Ruff, format and compile checks passed.
- Code, Python and security reviews approved the implementation.
- The live command exited zero, skipped the unchanged family and registered the new exact bytes.

## Evidence boundary

This proves that this workspace observed these exact parcel bytes at the stated
capture time. It does not prove an earlier public-availability date, historical
attribute vintages, sale closing semantics, one-home consideration, arm's-length
eligibility or commercial model-use rights. It creates zero certified sale
labels and does not unlock HCPA training or G-US.

Future checks use:

```powershell
$env:PYTHONPATH = ".;src"
.\.venv\Scripts\python.exe -m scripts.capture_hcpa_release --new-only
```

Use `--force-current` only for an explicit same-filename correction check; it
re-downloads current archives and records whether bytes changed.
