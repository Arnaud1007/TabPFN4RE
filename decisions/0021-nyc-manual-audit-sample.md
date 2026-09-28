# ADR 0021: NYC rolling manual-audit sample

Date: 2026-09-29
Owner: project implementation
Affected requirements: US05, US06, US07 and US24
Protocol version: `nyc-review-v1`

## Evidence and choice

The [frozen source profile](../runs/u0-nyc-rolling-profile-20260928T232337Z/report.md)
has 82,345 portal rows and a five-borough by structural-candidate table. It
also counts zero/nominal prices, missing unit identifiers, exact-string repeat
candidates, area defects and the oldest/newest sale months. Those counts are
*screening signals*, not verified sale or duplicate classifications. A purely
uniform draw might miss important ambiguities; an edge-only draw would miss
ordinary records. Use a fixed, edge-enriched 200-row sample for manual source
qualification. Its observed proportions must not be reported as source-wide
prevalence.

## Frozen frame and ranking

The frame is every one of the 82,345 CSV data rows in the pinned private
snapshot, with one-based ordinal in file order. Verify the source hash
`84c06057c52a2822f982cd98fb77ef7edf2c14134d00f46b073d2e4b762b2ef2`,
10,397,977 bytes, exact 21-column header and row count before selection.
The expected aggregate SHA-256 is
`6a5a7c57f21ae5a213a00545034fd2cd3c1bb4128d17b56cb1b26f8bedf692ef`.
Do not remove zero-price, nonresidential or apparently duplicate rows from
this audit frame. Never use a model prediction, residual, future outcome or
manual judgement to change inclusion.

For each row compute SHA-256 of UTF-8 text
`nyc-review-v1|84c06057c52a2822f982cd98fb77ef7edf2c14134d00f46b073d2e4b762b2ef2|42|<ordinal>`.
Sort by `(digest, ordinal)` ascending in each bucket. Seed 42 is part of this
string, not a pseudorandom-generator state. The selection is repeatable across
Python versions and row content changes are detected by the source hash.

## Selection order and quotas

Select the following **50 edge rows first**, without replacement. Each bucket
uses the smallest ranks remaining after earlier buckets. Record every edge
flag for selected rows, including flags beyond its primary selection bucket.

| Order | Primary bucket | Quota | Definition |
| --- | --- | ---: | --- |
| 1 | price | 10 | Sale price missing, invalid, negative, zero, or positive at most USD 1,000 using the profile's strict decimal parser |
| 2 | identity | 10 | Missing block or lot, or class-at-sale prefix `R` with blank apartment number |
| 3 | repeated source key | 10 | Key group of size >1 using whitespace-trimmed raw borough, block, lot, sale-date and sale-price strings; complete keys only |
| 4 | gross area | 10 | Gross square feet missing, invalid or nonpositive using the same strict parser |
| 5 | oldest month | 5 | Sale month `2025-09` under the profile parser |
| 6 | newest month | 5 | Sale month `2026-08` under the profile parser |

Then select **15 more rows from each** borough 1–5 × structural screen
`candidate`/`other_or_ambiguous` cell, excluding all edge rows. Candidate
means both `BUILDING CLASS CATEGORY` begins `01 ONE FAMILY` and class at time
of sale begins `A`, after whitespace trim and uppercase. The other cell
includes every remaining row in that borough. All boroughs are known in the
profile. Select the smallest ranks in each cell, yielding 150 structural rows
and 200 distinct ordinals overall. Sort the private final ledger by ordinal.

If any bucket cannot meet its quota after prior selections, or the pinned
profile does not reconcile with the source, **fail without producing a valid
sample**. Revise this ADR and protocol version before any replacement draw.
No silent fallback, rebalancing, row filtering or duplicate-key normalization
is permitted. The aggregate profile shows sufficient pre-overlap supply but
does not prove the disjoint quotas succeed; the implementation must verify it.

## Artifacts and manual review

The selector writes only a private, no-overwrite JSONL ledger under ignored
`data/raw/nyc_dof/`: ordinal, rank, primary bucket, structural cell and all
edge flags. It does not copy addresses, amounts, dates or personal names into
the ledger. Manual reviewers may look up each ordinal in the pinned private
source and store their evidence and notes only in an ignored private review
file. The tracked run records source/aggregate/sample hashes, aggregate
selection counts, exact command, test results and failure status. It contains
no individual ordinals, addresses, sale prices, keys or notes.

Review all 200 selected rows against official source definitions and, where
feasible, a transaction instrument. The rubric records property/unit and
economic-transfer identity, consideration scope, $0/nominal status, sale-date
meaning versus closing/recording, first availability, current-versus-historical
attribute vintage, corrected records, and evidence quality. Unknown remains
unknown. Investigate every discovered schema anomaly and expand the audit if
a systematic defect appears. Selection is not review: acceptance remains
pending until actual source comparisons are recorded.

This decision only authorizes a private U0 source audit. It cannot establish
historical as-of eligibility, source-specific commercial reuse, a completed
transaction label, model accuracy, U0 acceptance or G-US.
