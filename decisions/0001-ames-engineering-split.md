# ADR 0001: Separate Ames engineering split

- Date: 2026-09-28
- Owner: Arnaud
- Affected protocol: `ames_engineering_v1`
- Status: adopted for U0 smoke only

## Context

The legacy 1,168/292 membership and exposure history are unavailable. OpenML Ames has no recorded `available_at` field that could support the real-world 90-day origin protocol.

## Alternatives

1. Recreate an 80/20 split and call it the original holdout. Rejected: membership would be invented.
2. Wait for legacy artifacts before any engineering check. Rejected: schema and code plumbing can be tested independently.
3. Create a named 200-row engineering split and make no release claim. Chosen.

## Decision and evidence

Use 200 source rows for a deterministic seed-42, 80/20 engineering smoke split. Hash and save exact membership. Fit a constant median on development rows and score the reserved engineering rows. The result tests execution only; it does not measure future-sale, multi-market or national performance. `tests/test_ames_smoke.py` checks the split identity, disjointness and reserved-ID fit guard.

If the legacy artifacts arrive, preserve their membership separately and never rename this split. A future US certification cohort must be chronologically defined and untouched.
