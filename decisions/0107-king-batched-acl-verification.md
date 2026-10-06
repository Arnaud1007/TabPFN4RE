# ADR 0107: Batched King bundle ACL verification

## Status

Accepted for the local King research predictor.

## Context

Profiling showed that two sequential private-directory ACL checks launched four
Windows subprocesses and consumed about 1.2 seconds of cold model loading.
The checks applied the same owner, protected ACL and allowed-SID policy to the
private root and its bundle directory.

## Decision

Verify both directories with one SID lookup and one constant PowerShell
command. Paths travel as JSON in an environment variable and are passed to
`Get-Acl -LiteralPath`; they are never interpolated into command text. The
PowerShell process validates each result in order and stops on the first
failure. Python independently validates result count, types, protected status,
owner presence and the exact SYSTEM, Administrators and current-owner SID
allowlist.

An empty batch fails. Non-Windows systems retain the existing group/other mode
bit check for every directory. The single-directory `verify_acl` API delegates
to the same implementation.

King verifies direct parent membership, then the root and bundle ACLs in that
order, then bundle path structure, before reading any manifest or model bytes.

## Rollback

Revert to commit `61ca52b72364e48a9d6fefd78a82bfa9d83a137b` if the batch parser,
PowerShell compatibility or security verification fails. Do not bypass ACL
checks to meet a latency target.

## Evidence boundary

This reduces local startup overhead only. It changes no model, prediction,
data scope, accuracy claim or G-US status.
