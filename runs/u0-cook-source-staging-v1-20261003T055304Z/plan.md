# Frozen Cook parcel-source staging plan, v1

Frozen 2026-10-03 05:53:04 UTC before creating source observations from private rows. Protocol: `cook-parcel-source-staging-v1`. This is a local-only U0 source-schema exercise; no model row, sale label, historical feature or new HTTP request may result.

## Inputs and output boundary

- Cook capture directory: `data/raw/cook_county/cook-sales-v1-20261003T004123.032937Z-c08de13e9f1d/`.
- Pinned capture manifest SHA-256: `130b5169ff81ccbc0a729cba98400f2fb377ff9a25999316aaac1960e38a3cf7`.
- Pinned source metadata SHA-256: `c967e289fdd1a45319b1efdedf38276c670b1cdb0e11e5466e95e31731119dce`.
- Expected sample: exactly 200 rows in captured manifest order, from the 20 original ten-row pages. Reuse `review_cook_sales_sample._capture_rows()` and existing ACL/source replay; reject row-order, response-hash or manifest drift before writing output.
- Private create-only directory: `data/raw/cook_county/parcel-staging-v1-130b5169ff81ccbc/`. Write `observations.jsonl` (at most 1 MiB) and `complete.json` last. Verify expected bytes and exact file set before any public aggregate.
- Public aggregate: `runs/u0-cook-source-staging-v1-20261003T055304Z/aggregate.json`, with only protocol, pinned capture/metadata hashes, private observations hash, `sample_rows: 200`, `certified_sale_labels: 0`, `historical_asof_eligible: false`, and U0/G-US `PENDING`.

## Adapter rule

Use exactly the 18 requested Cook fields from the frozen capture. Reject unknown, nested, or personal fields. Preserve raw scalar values and missing versus explicit null. A valid `row_id` is required. Keep the PIN as 14 ASCII digits with leading zeros, or mark missing/malformed; never coerce a number to a PIN. Parse a source-local recorded date from `sale_date`, retaining its raw representation; do not map it to close or contract date. Parse decimal published price exactly when finite, retain zero/nonpositive and malformed states as unqualified source observations, and never infer concession or consideration scope. Preserve document and parcel flags without resolving an economic transfer. Attach the original page response hash, retrieval observation time and row hash; these do not establish historical first availability.

The observation type is frozen and has no `eligible_prior_sale` or conversion to canonical `Transaction`. Missing close/availability/property identity and uncertain arm's-length/rights block all label promotion. A repeated document remains two parcel observations and zero labels.

## Verification and decision

Write synthetic RED tests before implementation for strict field types, PIN leading zeros, missing/null/false/zero distinctions, exact Decimal price, recorded versus close dates, repeated documents, row-order/hash tampering, immutable round trip, create-only private persistence and public allowlist privacy. Run focused tests with at least 80% branch-aware coverage, Ruff, the full suite and code/Python/security review. Run one real offline staging operation only after checks pass. A failure is preserved rather than silently changing this plan; a changed protocol gets a new run ID. On success, replay private/public artifacts exactly, report actual results and keep U0/G-US PENDING with zero labels.
