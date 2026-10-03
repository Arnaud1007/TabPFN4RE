# Frozen Cook / Additional PIN offline diagnostic plan, v3

Frozen 2026-10-03 05:35:06 UTC **before** any v3 real comparison. The [v2 plan](../u0-illinois-additional-pin-offline-v2-20261003T051910Z/plan.md) and [ADR 0061](../../decisions/0061-illinois-additional-pin-offline-triage.md) define every unchanged comparison and privacy rule. V2 failed on its separate observation-reference resource cap and remains [FAILED](../u0-illinois-additional-pin-offline-v2-20261003T051910Z/failed_report.md). [ADR 0063](../../decisions/0063-illinois-additional-pin-reference-cap-v3.md) authorises only the following versioned changes:

- Protocol: `illinois-additional-pin-offline-v3`.
- New create-only private directory: `data/raw/illinois_ptax203/ptax-additional-offline-v3-130b5169ff81ccbc/`.
- Additional-observation reference cap: **5,000**. Candidate-pair cap remains **500**; private worklist cap remains **1 MiB**. Reference count is a resource guard, not a count of independent sales.
- New public aggregate path: `runs/u0-illinois-additional-pin-offline-v3-20261003T053506Z/aggregate.json`.

Pinned input SHA-256 values are unchanged: Cook `130b5169ff81ccbc0a729cba98400f2fb377ff9a25999316aaac1960e38a3cf7`, PTAX response set `69d86b7fb9c221dee662d49ebc01b94ef26f5e2862a0c9d26afb887f997cd05a`, Additional PIN response set `5b9d230f76f66d33b024009ee1c81aec18d5318b0cd5c748752ddf4300fba013`, and prior private Cook/PTAX worklist `7981f32fe1970afcb2c20768271c5c0c58dc05ff9a3905fe94981aeef9f8ac8e`. Require source replay and the prior public aggregate check before output.

Use strict token formats, exact declaration-ID joins, independent primary and Additional comparison states, duplicate captured-order ordinal plus row hash, one review item per frozen Cook row and no sale labels. Never collapse repeated references into repeated economic sales. Retain private ACL, create-only completion-last persistence and byte-identical offline replay. The public aggregate has the v1 fixed allowlist with only protocol/name updated; no new match/conflict counts, identifiers, PINs, prices, dates, raw rows, URLs or free text. No HTTP request.

Before the one real run, require synthetic tests for 501 admissible references and 5,001 rejected references, all prior synthetic boundary/security cases, at least 80% branch-aware coverage, Ruff, the full suite and code/security review. On success, verify private/public replay and write a technical report from actual artifacts. On failure, preserve the failure and version any further change. U0 and G-US remain PENDING and certified sale labels remain zero.
