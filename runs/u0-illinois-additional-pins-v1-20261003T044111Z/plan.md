# Frozen Illinois Additional PINs capture plan, v1

Frozen on 2026-10-03 UTC before any Additional PIN row query. This is a source-identity audit, not a price-label or as-of benchmark.

## Input identity and source

- Reuse the frozen Cook sample manifest SHA-256 `130b5169ff81ccbc0a729cba98400f2fb377ff9a25999316aaac1960e38a3cf7` and the completed PTAX-203 response-set SHA-256 `69d86b7fb9c221dee662d49ebc01b94ef26f5e2862a0c9d26afb887f997cd05a`.
- Before any request, run both private offline verifiers and the ADR 0058 replay. Derive the exact 80 unique PTAX `declaration_id` strings from those verified response bytes. Preserve this selection and its hash privately. Do not print, commit or transmit the IDs except in the bounded official API query.
- Official source: `https://illinois-edp.data.socrata.com/api/views/ay2h-5hx3.json` and `https://illinois-edp.data.socrata.com/resource/ay2h-5hx3.json`. The [official page](https://data.illinois.gov/Government-and-Public-Employees/PTAX-203-Additional-PINs/ay2h-5hx3) describes one row per Additional PIN. The read-only metadata inventory returned five columns, `published`, `official`, `PUBLIC_DOMAIN`, `rowIdentifierColumnId: null`, `rowsUpdatedAt: 1790506807` and `viewLastModified: 1789611867`; the inventory body SHA-256 was `25a80a2c9274813cfda7d84ad717562765743fae7a9e33aced92edd7daa829cd`. Abort if identity, schema, licence or both version markers differ at capture time or change between the first and final metadata responses.

## Bounded read-only requests

Sort the 80 exact declaration strings and form eight batches of ten. For every batch make a `count(*)` request and then a row request using the same exact `declaration_id IN (...)` predicate. Escape quotes in the query; never interpolate an unvalidated value. Select only `declaration_id,pin,lot_size_or_acreage,lot_size_units,split_parcel`; order by these fields and limit to 100 rows. All five fields are retained to preserve source-observation differences and scope context, not for model training. Query all 80 IDs, regardless of the primary declaration's additional-PIN indicator.

At most **18 GETs** are allowed: initial metadata, eight count/row pairs, final metadata. Use HTTPS on the exact official host and path, no redirects, credentials, payments or retries, a 15-second timeout and HTTP 200 with JSON content type. Cap metadata at 64 KiB, each count at 8 KiB and each row response at 64 KiB. Abort if a batch count exceeds 100 or all returned rows exceed 500; do not paginate or silently sample. The count and row response must agree for each batch. Require every row's exact declaration ID to be in its requested batch; reject unexpected fields and oversized or nested values. Empty results are valid observations, not proof of a single-parcel transfer.

## Private capture and replay

Create one new ACL-restricted directory under Git-ignored `data/raw/illinois_ptax203/`. Save exact successful response bodies, request timings/status and hashes, a private selection manifest, and a completion manifest **last**. Retain every returned observation, including identical duplicate rows; no unique row key is declared. Invalid HTTP or validation responses contribute only bounded hashes and failure status, not body text. Cap all private artifacts at 1 MiB. On failure leave the directory incomplete and do not publish a valid aggregate. No second capture is allowed under the same run ID.

Offline replay must reverify both frozen inputs, selection membership, expected URLs, metadata before/after, count/row agreement, source-row multiplicity, exact response hashes, ACL and exact private artifact names. The committed public aggregate may contain only protocol, source/response hashes, the previously published 100 Cook-row and 80 declaration denominators, zero certified labels, false historical as-of eligibility and U0/G-US PENDING. It contains no new returned-row count, match/conflict bucket, identifier, PIN, lot size, date, query URL or free text. A later Cook-PIN diagnostic needs a separately frozen comparison policy and versioned output.

## Falsification and acceptance

Write synthetic tests before implementation for zero/one/multiple Additional PINs, repeated identical rows, count/row disagreement, a declaration outside the frozen set, malformed PIN or `PT`/ROW-only source text, null lot size, unexpected fields, metadata drift, batch saturation, redirect or wrong host, response cap, truncated/failed request, crash before completion, ACL failure, tampering, and public privacy. Source PIN values remain raw in this capture; no normalization or sale eligibility rule is applied. Require at least 80% branch-aware coverage of new code, Ruff checks, complete repository tests, security and code review, and byte-identical offline replay before committing and pushing. A capture that passes these engineering checks still certifies **zero** sale labels.
