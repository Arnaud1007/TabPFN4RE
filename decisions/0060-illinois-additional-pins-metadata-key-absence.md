# ADR 0060: version the Additional PINs metadata correction

- Date: 2026-10-03
- Owner: project implementation
- Requirements: US02, US05, US06, US07, US24
- Supersedes: only the failed v1 Additional PINs capture plan for a new v2 attempt; earlier Cook/PTAX captures remain frozen.
- Status: approved for a bounded private v2 source audit

## Evidence and decision

The [v1 failure report](../runs/u0-illinois-additional-pins-v1-20261003T044111Z/failure_report.md) records a metadata-only rejection. The official metadata response omits `rowIdentifierColumnId`; its absence was mistaken for an explicit null in the initial inventory. The five observed fields, published/official/Public Domain indicators, `rowsUpdatedAt` and `viewLastModified` match the frozen v1 inventory. There is still no declared unique row key.

Version the collector and private run as v2. Require that `rowIdentifierColumnId` remain **absent** in both metadata snapshots. Continue to compare all five field names, column IDs and data types across the snapshots and require the pinned update markers. Reject a newly present identifier property, even if null. Preserve every returned row and duplicate. Keep the same frozen 80 declaration IDs, eight ten-ID batches, 18-request cap, field allowlist, limits, privacy policy and zero-label interpretation. The [v2 plan](../runs/u0-illinois-additional-pins-v2-20261003T050600Z/plan.md) is frozen before any v2 row request.

This correction is based only on public metadata; no Additional PIN row or match count was viewed. A later Cook-PIN comparison remains a separate offline protocol. V2 capture success would not establish one-home consideration, close date, row-first availability or permission for commercial use.
