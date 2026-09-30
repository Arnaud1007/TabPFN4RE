# ADR 0034: NYC source-representation and candidate-linkage diagnostic v2

Date: 2026-09-30
Owner: project implementation
Affected requirements: US04, US05, US06, US07, US08, US22, US23, US24
Protocol: `nyc-dof-representation-diagnostic-v2`
Status: frozen protocol; implementation verified; source run pending

## Question and frozen inputs

The [v1 same-publisher comparison](../runs/u0-nyc-row-concordance-v1-20260930T132740Z/report.md) found no exact six-field key pairs or complete-row matches in Bronx, Brooklyn and Queens even though source row counts agree. Staten Island's detailed v1 result is suppressed. This does not establish that the represented transfers differ. V2 asks which strictly declared *representations* allow candidate links and which fields still disagree. It never certifies an economic transfer or a sale label.

Read only the pinned 82,345-row NYC rolling CSV (SHA-256 `84c06057c52a2822f982cd98fb77ef7edf2c14134d00f46b073d2e4b762b2ef2`) and the four v3-qualified XLSX workbooks in capture manifest SHA-256 `e29928b44a1b1f733219dac86b8d7e18704bf8c301b458afc2bf1a53895bb9e2`. Manhattan remains excluded. Pin the v3 result SHA-256 `61dcb9bce362658c475df5e43fa2407e18cb0d85779654941ab67bbb8ee00f83`, v1 public aggregate SHA-256 `4d52add2b6a65df050c9bf0a920e0f9ccc4e7fad8959f1d7e6c1154fb84ea524`, and v1 private result SHA-256 `5fd432e081911ff47df78bf183a40df99da00077d0e666175ca79840f18451ee`. Verify the protected v1 directory ACL, inventory, intent, result, public and hash-manifest digests and their mutual consistency without replaying or modifying v1. Reuse its unchanged source scanners, metadata preflight, same-handle hashes, ACL and timeout controls. The v3 metadata must state `1900_default` for every included workbook; a different date system stops this run. Each source still needs exactly 62,792 in-scope rows. Write a clean-tree intent before reading source rows.

## Fixed transformations and tiers

Retain every original string in memory only, trim outer Unicode whitespace, and never write raw values to artifacts. A raw key contains `(BOROUGH, BLOCK, LOT, APARTMENT NUMBER, SALE DATE, SALE PRICE)`; apartment blank is a real blank, never a wildcard. Borough, block, lot, date and price must be present. Do not link by source order, row ordinal, address similarity, nearest price or realised model error.

Use five independent tiers, all reported separately:

| Tier | Candidate key change from raw K0 |
|---|---|
| K0 | Exact trimmed six-field strings, reproducing v1 |
| K1 | Canonical calendar date only |
| K2 | Exact numeric Decimal price only |
| K3 | Canonical date and Decimal price |
| K4 | K3 plus ASCII digit-only, positive block/lot with leading zeros removed |

K1–K3 preserve raw block, lot and apartment strings. K4 keeps apartment exact. An invalid conversion makes that row ineligible for the affected tier, never a guessed or blank replacement. Price zero or negative may be parsed for representation diagnosis but remains ineligible as a positive sale label. A K4 collision means **within one source and borough** that distinct raw block/lot tuples map to one normalized six-field key; the group remains ambiguous. A unique CSV/XLSX normalized key with different zero padding is an eligible candidate.

CSV dates accept exact `YYYY-MM-DD`, `MM/DD/YYYY`, or ISO local midnight `YYYY-MM-DD[T ]00:00:00` with an optional one-to-six zero fractional digits. No offset, non-midnight time or ambiguous two-digit year is accepted. XLSX dates accept those forms or integral serial matching `[0-9]+(?:\.0+)?` under the pinned 1900 date system, using the already tested workbook date conversion. Invalid dates and dates outside **2025-09-01 through 2026-08-31** are unparseable for typed tiers. CSV prices match `-?(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)(?:\.[0-9]+)?`; XLSX prices match `-?[0-9]+(?:\.[0-9]+)?(?:[Ee][+-]?[0-9]{1,2})?`. The XLSX exponent's absolute value must be at most 12; the mantissa, after leading zeros are ignored, has at most 18 digits. Both become exact finite Decimal values. A leading `+`, currency symbol, invalid comma grouping, rounding, imputed concession or tolerance match is forbidden. Preserve raw lexical form classifications privately.

## Candidate graph and accounting

For each tier, group eligible rows by key in each source. A key occurring exactly once in each source creates one candidate edge. Any shared key duplicated on either side is ambiguous; do not Cartesian-expand or arbitrarily pair it. A row becomes an isolated candidate pair only when the union of all five tiers has exactly one reciprocal counterpart and it has no shared duplicate-key ambiguity in any tier. Conflicting edges, unequal multiplicities and normalization collisions remain ambiguous. For isolated pairs, count raw date/price equality, canonical date/price equality, complete 21-field equality, exact equality of the other 19 fields, address equality, building-class-at-sale equality and disagreements in each of the 21 fields. Canonical date/price comparisons are **equal, different or unparseable**; a failed parse is never counted as different. A `format_only_candidate` requires equal canonical date and price **and** exact equality of the other 19 trimmed fields; it remains a candidate, not a proven transaction.

Before pairing, compute unordered raw-trimmed **multiset overlap for each of the 21 fields** as the sum of minimum token frequencies across sources. Also compute canonical-token overlap among parse-valid rows for date, price, block and lot. These are aggregate representation diagnostics, not row links. Reconcile every source row to exactly one exclusive status: isolated candidate, ambiguous shared key or cross-tier conflict, unmatched, or raw-key incomplete. For each tier and source, `valid + invalid_or_incomplete = total`; `valid = unique_edge_rows + shared_ambiguous_rows + source_only_rows`. Source-only duplicate groups count in source-only rows, not shared ambiguity. Separately report parse failures, normalization collisions and lexical-form counts. Recompute K0 counts and require agreement with the frozen v1 private result. Do not infer a new label from a high candidate count.

## Security, privacy and acceptance

Process one borough at a time. Retain no more than 32 million raw cell characters for its combined sources, and cap serialized private output at 64 MiB. Private Git-ignored artifacts may contain ordinals, fingerprints, tier/status codes and equality flags, but no raw address, unit, date, price, key or source row. Public output contains only allowlisted fixed-category **tier unique-edge counts and isolated-pair summary**, source denominators, input hashes and zero-label status; per-field overlap, lexical forms and ledger stay private. Never publish ordinals, fingerprints, examples or pooled comparison totals. Suppress an entire borough breakdown if any positive public category count is 1–4, if a difference among published tiers or against v1 K0 would reveal such a cell, or if a known arithmetic complement would reveal it. Keep Staten Island's v2 breakdown suppressed unconditionally because differencing against v1 could reveal its protected small cell.

Synthetic RED tests must cover date epochs and invalid timestamps, strict money parsing and exponent bounds, leading-zero block/lot versus significant apartment, K0–K4 ablations, duplicate and cross-tier conflicts, field comparisons, source reordering, same-handle tampering, cap failures, cross-version privacy, interruption and replay. Add new v2 modules and tests without modifying v1 code, whose hashes are pinned by v1 replay. The v2 intent hashes its new modules and every unchanged v1 dependency used at runtime. Write canonical artifacts atomically and create-only, mark interrupted runs incomplete, verify byte-identical offline replay, and retain failures. Require code, Python and security reviews; more than 80% branch-aware coverage for each new module, full suite, Ruff, package and scoped dependency checks. Commit and push reviewed code before the first v2 private row read. Then save a redacted aggregate, hashes, actual command results, verifier, report, requirement links and next action; push those evidence files to `audit/u0`.

Passing v2 means only that the declared representation experiment was executed and its candidate results are reported. Rights, actual close-date meaning, first row availability, transfer/parcel/unit identity, Manhattan structural status and the 200-record manual audit remain separate U0 dependencies. All outputs state `label_status: unqualified` and `sale_labels_certified: 0`; U0 and G-US remain pending.
