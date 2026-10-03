# U0 Cook County private source-review initialization

Run ID: `u0-cook-review-init-20261003T013215Z`  
Protocol: `cook-source-review-v1`  
Code commit: `a6632c0e755ebac6ea3a1c297c3769a2108526f9`  
Requirements: US02, US05, US07, US22, US23, US24  
Status: **private review worklist initialized and verified; U0 and G-US PENDING**

## Objective and actual result

The reviewed offline tool verified the immutable 200-row Cook County source
capture, its official field metadata and private-file permissions, then created
one ACL-restricted worklist and append-only review ledger. The initial public
[aggregate](init_aggregate.json) and independent [replay](replay_aggregate.json)
match byte for byte: 200 untouched, zero partial, zero complete and zero
certified sale labels. The private manifest and worklist hashes are pinned in
[verify_artifacts.ps1](verify_artifacts.ps1).

One source-only review entry was appended as `partial`. The later public
[aggregate](partial_aggregate.json) and [replay](replay_after_partial.json)
also match byte for byte: **199 untouched, one partial, zero complete and zero
certified sale labels**. The frozen private ledger snapshot has SHA-256
`c12b5a161299d5e7a5f0eabec3bf3a2423c02378a72325bab2e65c551f12b043`.
All individual records, findings, reviewer notes and source values remain in
the ignored private directory.

The first append attempt supplied a relative private entry path. The CLI
rejected it with exit code 1, and a summary confirmed the ledger was still
empty. A second append using the entry's resolved absolute path succeeded with
exit code 0. This is an input-path constraint of the current private-file
helper, not a discarded review or a changed source record.

## Commands and evidence

The [reviewed code gate](../u0-cook-review-code-20261003T012707Z/report.md)
contains the exact eight technical commands, exit codes, durations, output
hashes and environment lock. It passed 21 focused tests at 83% branch-aware
coverage, 1,020 full-suite tests, Ruff, dependency checks and private capture
replay. The source capture manifest SHA-256 is
`130b5169ff81ccbc0a729cba98400f2fb377ff9a25999316aaac1960e38a3cf7`.

The [execution record](execution_record.json) preserves the observed command
patterns, exit codes, output hashes and environment identity. The successful
live commands were `python -m scripts.review_cook_sales_sample
init --output <new-public-file>`, `append --entry <absolute-private-file>
--expected-ledger-sha256 <empty-ledger-hash> --output <new-public-file>`, and
`summary --output <new-public-file>`. Each exited 0. Their original invocation
durations were not captured and are recorded as unknown, rather than
reconstructed. The verifier below checks
the paired output hashes, pinned private manifest and worklist, immutable
ledger snapshot, capture and ACLs; its saved invocation exited 0. The live
commands did not train, calibrate or open reserved evaluation labels, so no
model checkpoint, split or feature-policy hash applies.

Replay from the project root with the authorized private capture present:

```powershell
& 'runs/u0-cook-review-init-20261003T013215Z/verify_artifacts.ps1'
```

The public aggregate JSON outputs contain counts and cryptographic hashes only.
The worklist, ledger and frozen snapshot are under `data/raw/cook_county/`,
which is Git-ignored. A fresh clone requires the authorized private capture
and ledger snapshot; this public report alone cannot reconstruct them.

## Remaining work

Continue the 200-record manual source audit and seek authoritative evidence
for economic-transfer and dwelling identity, closing-date meaning, first
publication, historical attribute vintages and permitted use. The Cook source
card still marks the 90-day historical benchmark ineligible. The custodian
inquiry is a local unsent draft. No result here is an eligible US sale label,
and no downstream model or international gate is unlocked.
