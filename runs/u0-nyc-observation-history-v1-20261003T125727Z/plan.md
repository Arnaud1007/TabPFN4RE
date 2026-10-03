# NYC rolling source observation history v1 — frozen offline plan

Run ID: `u0-nyc-observation-history-v1-20261003T125727Z`  
Protocol: `nyc-observation-v1`  
Status at plan: planned; no private ledger entries have been written by this run.

## Question and inputs

Can the existing 28 September and 3 October 2026 NYC `usep-8jbt` captures be
recorded as two distinct, conservatively timed observations without mistaking
source-row duplication, ordering, or a repeated file for sale-level events?

Use only these already pinned manifests, in chronological order:

1. `runs/u0-nyc-rolling-snapshot-20260928T225512Z/snapshot.json`
2. `runs/u0-nyc-rolling-resnapshot-v1-20261003T101029Z/snapshot.json`

Both name Git-ignored source CSVs under `data/raw/nyc_dof/`. Their published
aggregate verification says 82,345 rows, 21 columns and identical full-file
SHA-256 `84c06057c52a2822f982cd98fb77ef7edf2c14134d00f46b073d2e4b762b2ef2`.
This is an expected check, not a result of this run. Do not access live source
endpoints or reserved labels. Local processing cap: two files, each at most
128 MiB and 150,000 rows; stop on a hash, schema, time or integrity mismatch.

## Method and decision

The module validates each manifest and raw byte stream, computes full-row
representation hashes only in memory, and stores a create-only capture-level
entry in `data/derived/nyc_dof/observation_history/`. This directory is Git-ignored.
On a later append it revalidates prior manifests and private CSV bytes before
recomputing the previous multiset. No row fingerprint is persisted.
Each event uses capture completion as its conservative project-known-by time.
Compare multisets in capture order; a row absent from the later snapshot is a
representation difference, not a proven deletion or corrected transfer.

The public summary may contain only source-level hashes, capture times, exact
total rows and suppressed change-count buckets. It must contain no address,
unit, price, row fingerprint, or source row ordinal. For byte-identical files,
the expected added and removed buckets are both `zero`. Replay must be
idempotent, and partial temporary files must not be treated as completed
observations. Failed integrity checks are retained as failures, not scores.

This experiment is adopted as source-observation evidence only if focused and
full tests pass, the two private files verify, two distinct events are saved,
the later comparison reports no row-representation change, and public output
contains no row-level data. It cannot establish first public availability,
sale/close semantics, property identity, permitted commercial use, historical
features or a certified training label. U0 and G-US remain pending.
