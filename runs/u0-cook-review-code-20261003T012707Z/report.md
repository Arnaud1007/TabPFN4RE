# U0 Cook County private review ledger: code gate

Run ID: `u0-cook-review-code-20261003T012707Z`

Protocol: [ADR 0052](../../decisions/0052-cook-private-review-ledger.md),
`cook-source-review-v1`

Reviewed code commit: `a6632c0e755ebac6ea3a1c297c3769a2108526f9`
(pushed to `origin/audit/u0` before the first real ledger initialization)

Frozen input capture manifest SHA-256:
`130b5169ff81ccbc0a729cba98400f2fb377ff9a25999316aaac1960e38a3cf7`

Environment lock SHA-256:
`92d4969aa37973d021c9215c67448b26ac689ca8d6f5b4414c701f126f4ac3e7`

Status: **ledger code implemented and verified; U0 and G-US PENDING**

## Objective and changes

The offline ledger verifies the exact 200-row Cook County capture, source
metadata, ordered row membership and restricted private ACLs before creating a
review worklist. It binds each review to the capture, ordinal and row hash.
Append validates a full JSONL history and uses a lock, expected prior hash and
atomic replacement. Only aggregate counts and hashes leave private storage.
The v1 rubric cannot turn source flags, an arbitrary URL or a reviewer's
assertion into a certified transaction, historical input or sale label.

The existing private Cook root and captured-run directory originally inherited
broader Windows ACLs. Before the real-data gate, both were restricted with the
project's `private_review_io.secure_directory` helper and verified. A captured
manifest file inherited only the user, system and administrator entries. The
original [capture verifier](../u0-cook-sales-sample-20261003T004123Z/verify_artifacts.ps1)
still exited zero after the ACL change.

## Actual checks

[test_gate.json](test_gate.json) stores the eight exact commands, exit codes,
durations, redacted log hashes and stable source/test/ADR hashes. All eight
checks passed. The focused suite ran **21 tests** at **83% branch-aware
coverage** for `review_cook_sales_sample.py`. The full Python suite ran **1,020
tests** with no skips and exited zero. The real pinned capture and private ACL
replay returned 200 rows. Ruff lint and format, `pip check` and `pip-audit`
passed; `pip-audit` reported no known vulnerabilities in auditable packages
and skipped the local editable project because it is not a PyPI package.

The gate ran on a dirty working tree based on commit
`057e61036f291facf7f0022fd62895bb4614f2a6`; the source, test and ADR
hashes remained unchanged throughout. The subsequently pushed reviewed code
commit is stated above. No model was fitted, so there is no split, feature
policy or checkpoint identity for this run.

Replay from the project root with:

```powershell
& 'runs/u0-cook-review-code-20261003T012707Z/verify_artifacts.ps1'
```

The verifier checks saved log and input hashes, the environment lock and the
original private capture. A fresh clone needs the authorized private capture
restored. The public logs do not contain PINs, prices or source row IDs.

## Review findings and next action

Code, Python and security reviewers found two medium integrity gaps before the
gate: an arbitrary HTTPS page could stand in for official metadata, and review
times could predate the capture or ledger. Both were corrected and covered by
regressions before the saved gate. Reviewers then found no remaining blocker.

The next action is the separately recorded
[private-ledger initialization](../u0-cook-review-init-20261003T013215Z/report.md).
This code gate verifies an audit workflow; it does not complete any manual
rubric, certify a label or satisfy G-US. The 90-day closing origin, first
publication, single-dwelling consideration, source rights and broader US
coverage remain unresolved.
