# ADR 0062: correct the frozen offline worklist hash in v2

- Date: 2026-10-03
- Owner: project implementation
- Requirements: US02, US03, US05, US06, US07, US08, US24
- Status: approved for local-only v2 diagnostic

The v1 [plan](../runs/u0-illinois-additional-pin-offline-v1-20261003T051508Z/plan.md) pinned a mistyped prior worklist SHA-256. The authoritative private file and previously committed public aggregate both give `7981f32fe1970afcb2c20768271c5c0c58dc05ff9a3905fe94981aeef9f8ac8e`. The v1 diagnostic was not executed, and no match result was viewed. Keep its [rejection report](../runs/u0-illinois-additional-pin-offline-v1-20261003T051508Z/rejected_report.md) and do not rewrite the frozen plan.

Use the exact same comparison policy and privacy boundary from [ADR 0061](0061-illinois-additional-pin-offline-triage.md), with the corrected worklist hash in a separately frozen [v2 plan](../runs/u0-illinois-additional-pin-offline-v2-20261003T051910Z/plan.md). Version the protocol and private output directory as v2; no v1 run name may be reused. Reverify all three captures and the prior worklist before computing any cross-source relation. No network request, sale-label promotion or G-US claim follows.
