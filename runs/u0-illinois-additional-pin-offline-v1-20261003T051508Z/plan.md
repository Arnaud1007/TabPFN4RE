# Frozen Cook / Additional PIN offline diagnostic plan

Frozen 2026-10-03 UTC before computing Cook-to-Additional-PIN relations. A prior public-artifact security scan examined private strings only to check for leakage; it did not compute cross-source matches. This run is local-only and requests no new data.

## Exact inputs and grains

- Cook capture SHA-256: `130b5169ff81ccbc0a729cba98400f2fb377ff9a25999316aaac1960e38a3cf7`.
- PTAX response-set SHA-256: `69d86b7fb9c221dee662d49ebc01b94ef26f5e2862a0c9d26afb887f997cd05a`.
- Additional PIN response-set SHA-256: `5b9d230f76f66d33b024009ee1c81aec18d5318b0cd5c748752ddf4300fba013`.
- Prior private Cook/PTAX worklist SHA-256: `7981f32fe1970afcb2c20768271c8831e3e69cf3e464e75c02e0`.
- Reverify all four inputs with their current offline verifiers before creating output. Reconstruct the 100-row prior worklist and require exact-byte agreement with the pinned private file. Retain its 83 exact document strings and 80 unique declarations; do not infer missing declarations from a near-document match.
- Build exactly one new review item per frozen Cook row. Each item retains its previous ordinal and row ID privately, all exact declaration candidates, and every Additional observation for each declaration. A declaration may appear under repeated Cook document rows; the same consideration never becomes multiple sale labels.

## Predeclared PIN states

Use only full-string matches: `[0-9]{14}` or `[0-9]{2}-[0-9]{2}-[0-9]{3}-[0-9]{3}-[0-9]{4}`. Bare and display strings yield the same 14-digit comparison key only for `display_equivalent` triage; preserve raw form and leading zeros. Detect `PT` immediately before either permitted shape or after exactly one ASCII space as `part_parcel`; an equal base yields `part_parcel_lead`, never an ordinary match. Detect `ROW only` by ASCII case-insensitive full-string comparison. Missing (`None` or empty string), malformed type/value, and nonmatching valid PINs remain separate. Do not trim, remove any other punctuation, accept Unicode digits or interpret lot sizes and `split_parcel` text as identity rules.

For each Cook/declaration candidate compute one primary relation and one relation per Additional observation: `raw_exact`, `display_equivalent`, `part_parcel_lead`, `valid_unequal`, `missing`, `right_of_way`, or `unknown`. Keep primary and Additional results independent; flag primary-and-Additional equality, repeated identical five-field observations, multiple distinct Additional PINs, Line 3 true with zero rows, Line 3 false with rows, and any repeated Cook document/row relationship as private review prompts, not eligibility decisions. Keep raw Additional observations in their pinned capture; the new worklist references each by captured-order ordinal and row hash rather than copying its raw fields into repeated Cook items. No observation is deduplicated. The full review item and source lineage stay under private ACL.

## Persistence and public boundary

Use new private create-only directory `data/raw/illinois_ptax203/ptax-additional-offline-v1-130b5169ff81ccbc/`, with a `worklist.jsonl` of exactly 100 Cook items followed by a completion manifest written last. The worklist has a 1 MiB cap; candidate pairs and Additional references each cap at 500. A failure leaves no valid public aggregate. Offline replay re-verifies all source bytes, ACL, exact private file set, worklist bytes, hashes and completion manifest. No network request or existing private file mutation is allowed.

The public aggregate is a fixed allowlist: protocol, four pinned input hashes, new private worklist hash, prior 100/83/80 denominators, zero certified labels, false historical as-of eligibility, and U0/G-US PENDING. It omits all new row/match/conflict counts and all identifiers, PINs, prices, dates, query URLs and free text. A private human-review queue is an audit aid, not a completed 200-record manual source audit.

## Tests and acceptance

Write synthetic tests first for bare/display leading zeros, exact versus formatted equality, `PT` and `ROW only`, malformed and Unicode digits, duplicate identical observations, same PIN in nonidentical rows, zero/one/multiple Additional observations, repeated Cook deed rows, multiple PTAX declarations, Line 3 disagreement, unknown split text, unrelated declaration ID, private ACL failure, tampering, cap failure, create-only output and public-output privacy. Prove an injected future/corrected row cannot be admitted without changing the pinned source hash. Require at least 80% branch-aware coverage on the new module, Ruff, the full suite, replay and code/security review. Keep all sale labels at zero.
