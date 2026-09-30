# ADR 0038: Manhattan preamble formula diagnostic v1

Date: 2026-09-30
Owner: project implementation
Status: frozen before private workbook inspection
Protocol: `nyc-manhattan-formula-diagnostic-v1`
Requirements: US05, US07, US08, US22, US23, US24

## Context and choice

The immutable [v3 worksheet inspection](../runs/u0-nyc-worksheet-inspection-v3-20260930T092659Z/report.md)
found exactly one formula in Manhattan's four-row preamble, zero formulas in
the header or data, and the pinned header and in-period date range. Its rule
forbids every formula and therefore leaves Manhattan unqualified. V3 discards
the formula coordinate and expression by design. A private, bounded diagnostic
is needed to understand the formula before any new qualification policy can
be considered.

Use the exact captured workbook manifest SHA-256
`e29928b44a1b1f733219dac86b8d7e18704bf8c301b458afc2bf1a53895bb9e2`
and Manhattan workbook SHA-256
`8903566fa59c9ce4c2b427ce24e268cc448d8c04f8c779839df942f29a05397a`.
The v3 code commit was `aae83e201710f8e5d04a40f64d44f6c1305bb7ed`.
Do not edit its decision, parser, run, or result. The new diagnostic neither
qualifies a worksheet nor interprets sale consideration or transaction rows.

## Frozen method

Validate the official capture manifest and pinned Manhattan file with the
existing source path, ACL, reparse, hard-link, byte-size and same-handle hash
rules. First run the existing v3 parser on the opened handle to consume and
validate the entire workbook package and worksheet. Require an exact row-five
header, at least one post-header row, exactly one preamble formula and no
header/data formulas or other v3 structural or date violations. A deviation
ends the diagnostic without a valid result.

Then seek the same handle to the beginning and inspect only the four preamble
rows of the same pinned worksheet. Use bounded ZIP reading and defused XML.
Capture the one formula's source row, physical ordinal, cell coordinate,
formula attributes and expression up to 512 characters in protected storage.
Record only whether a cached `<v>` element exists; never read, evaluate or
trust its content. Reject duplicate/malformed formula nodes, excessive
attributes, missing coordinates, extra formulas and ambiguous row placement.
The v3 full scan supplies EOF, CRC, package and date validation. This targeted
second pass may transiently buffer later XML bytes but does not extract or
retain later cell values. Observe the shared 180-second cap.

Write a create-only private run with intent, private result, fixed redacted
public projection and hashes. Replay from the same pinned source without
network or writes and require byte-identical private and public results.
Keep formula text, coordinate, attributes, cache presence and any fingerprint
out of public files, stdout and normal Git history. The public projection
contains only protocol, operation completion, v3 still unqualified and zero
certified sale labels. A failure remains a failed run, not an absent formula.

## Acceptance and next decision

Write synthetic RED tests before implementation for an ordinary formula,
shared or array metadata, empty and oversized expressions, cached-value
canaries, multiple or wrong-zone formulas, changed input bytes, malformed XML,
strict paths, no overwrite, private/public redaction, replay tampering and
v3 regression. Require at least 80% branch-aware coverage for new modules,
Ruff, the full repository suite and code/Python/security review. Commit and
push reviewed code before this diagnostic opens the pinned private workbook.

Report the diagnostic separately with hashes and actual commands. A future
v4 worksheet rule requires a new decision made from the private evidence;
location in the preamble alone cannot waive the v3 prohibition. Source rights,
date semantics, unit/transfer identity and the 200-record manual audit remain
independent U0 blockers. Sale labels certified: zero. G-US: pending.
