# King batched ACL latency, 6 October 2026

Status: **PASS for local cold-start target; historical research only; G-US PENDING**.

## Result

Profiling found that separate ACL verification of the private King root and
model bundle consumed about 1.2 seconds and launched four Windows processes.
The committed loader now validates both paths in one ordered operation using
one SID lookup and one PowerShell process.

Ten complete CLI processes took **0.95-1.39 seconds**, with a **1.28-second
median** and **1.39-second maximum**. Every process returned exactly
**$553,846.9739548098** and the complete historical disclosure schema. The
two-second cold target passed in all ten observations.

## Security and correctness

- Paths are JSON environment data and never enter PowerShell command text.
- `Get-Acl -LiteralPath` validates the private root before the bundle.
- PowerShell fails immediately on an unprotected ACL, missing owner or foreign
  SID; Python independently checks count, types and the same policy.
- Empty batches fail closed and POSIX mode checks remain unchanged.
- No manifest or model bytes are read before ACL and path validation pass.

## Verification

- Implementation commit: `adecc2a`.
- 63 tests passed, one optional integration was skipped and 86 subtests passed.
- Ruff and code, Python and security reviews passed.
- Real Windows ACL verification and the exact pinned bundle were exercised.

## Evidence boundary

This reduces local startup overhead without weakening the private-directory
gate. It changes no model, accuracy, uncertainty, source right, current-market
claim or G-US status.
