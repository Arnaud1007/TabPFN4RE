# U0 Cook County private source-review progress

Run ID: `u0-cook-review-progress-20261003T025709Z`  
Protocol: `cook-source-review-v1`  
Code commit: `80411fa233809170492d8516c9e4b480a1e9902a`  
Requirements: US02, US05, US07, US08, US24  
Status: **one reviewer-attested rubric complete; U0 and G-US PENDING**

## Objective and observed result

Continue the private manual audit of the frozen 200-row Cook County Assessor sample. The reviewer checked a pinned source row, the captured official field metadata and the recorded-instrument access route. A direct request to the official search route returned HTTP 403 in this environment, so it yielded no instrument. The full rubric was attested with unknowns where independent evidence was missing. Completion records review effort; it does not certify a sale label.

The public [aggregate](aggregate.json) and independent [replay](replay_aggregate.json) match byte for byte: **198 untouched, one partial, one complete, zero certified sale labels**. The frozen private ledger snapshot has SHA-256 `f8a25a6f098ea62b5891e1c1a852a4d20826302725664814e54ee3a112f36436`; the public aggregate files share SHA-256 `b72ec03a5bc7d9295c89db436f457edd046c95cfa5774091f4aa3f99c57bfabb`. No row identifiers, prices, findings or reviewer notes are published.

The first entry-preparation attempt assumed that the existing partial entry belonged to the selected row and failed before writing. The corrected entry was validated against the actual prior ledger and appended once. The failed attempt did not alter the ledger.

## Commands and checks

From the project root, the reviewed CLI append ran with `--entry <absolute-private-file>`, `--expected-ledger-sha256 c12b5a161299d5e7a5f0eabec3bf3a2423c02378a72325bab2e65c551f12b043` and `--output runs/u0-cook-review-progress-20261003T025709Z/aggregate.json`. It exited **0** in **1,527 ms**. The independent `summary` command exited **0** in **1,257 ms**. Both outputs report the same frozen counts and ledger hash. No training, split, feature policy, calibration or model checkpoint was used.

The [saved execution gate](test_gate.json) records exit codes, durations and log hashes for 21 focused tests, `pip check`, `pip-audit` and snapshot replay; all exited 0. The existing ledger code gate passed 21 focused tests at 83% branch-aware coverage and 1,020 full-suite tests at its pinned code commit. This run made no package-code change. Verify the current frozen snapshot, capture provenance and private permissions with:

```powershell
& 'runs/u0-cook-review-progress-20261003T025709Z/verify_artifacts.ps1'
```

The private worklist, review entry and ledger snapshot remain in Git-ignored `data/raw/cook_county/`. The public report alone cannot replay them in a fresh clone without authorized private data.

## Remaining work

Complete the other 199 manual rubrics and obtain authoritative transfer, close-date, first-publication, historical-attribute and permitted-use evidence. The official Clerk transfer-list route remains an unacquired paid candidate; no purchase was made. The Cook custodian inquiry remains unsent. Historical as-of eligibility is false, so no Cook row is available for the primary 90-day benchmark or model training.
