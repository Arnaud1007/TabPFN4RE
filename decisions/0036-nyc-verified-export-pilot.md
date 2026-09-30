# ADR 0036: verified NYC export comparison pilot

Date: 2026-09-30
Owner: project implementation
Affected requirements: US04, US05, US06, US07, US08, US22, US23, US24
New protocol: `nyc-verified-export-pilot-v1`
Status: frozen before the first private pilot read

## Problem and choice

The [200-row sample](0021-nyc-manual-audit-sample.md) is frozen, but none of its
records has a completed source review. The [v1 review ledger](0025-nyc-private-source-review-ledger.md)
correctly treats asserted evidence references as insufficient to establish
identity. [ADR 0027](0027-nyc-ledger-evidence-boundary.md) therefore forbids a
non-unknown identity finding in that ledger. The separately pinned rolling CSV
and official borough workbooks permit a narrower, byte-checked comparison.
They are two deliveries by the same publisher, not independent confirmation
of a deed, consideration scope, closing date or first publication.

Keep the v1 ledger and all previous diagnostics unchanged. Create a separate
protected pilot addendum that checks actual source bytes and identifies
candidate row pairs for later human review. An automated pair status is not a
completed manual rubric or a certified sale label.

## Frozen inputs and scope

- Rolling CSV: SHA-256
  `84c06057c52a2822f982cd98fb77ef7edf2c14134d00f46b073d2e4b762b2ef2`,
  82,345 data rows, with its pinned snapshot manifest.
- Frozen private sample ledger: SHA-256
  `e137de2cf73aa4a9fea6d024e4564ef6e907020e73fc8dbec3e4026786b189ca`,
  exactly 200 distinct one-based CSV ordinals.
- Captured official workbooks: private manifest SHA-256
  `e29928b44a1b1f733219dac86b8d7e18704bf8c301b458afc2bf1a53895bb9e2`.
  Verify each selected workbook's byte count and SHA-256 from that manifest.
- Worksheet v3 result SHA-256
  `61dcb9bce362658c475df5e43fa2407e18cb0d85779654941ab67bbb8ee00f83`.
  Only Bronx, Brooklyn, Queens and Staten Island passed its frozen structural
  rule. Manhattan remains excluded; this protocol does not waive its formula.

Use the existing bounded CSV and v3-qualified XLSX scanners. Check source
hashes, sizes, schema, complete scans, ACL, reparse and link status before
producing a valid result. A malformed tail invalidates all callbacks. No
network request, archive generation, model training or sale-label admission
occurs in this protocol.

## Pilot selection before comparison

Select from the 200 pinned ordinals only. Determine borough from the pinned
CSV, then exclude Manhattan. For each of the four qualified boroughs, rank
eligible ordinals by SHA-256 of UTF-8
`nyc-verified-export-pilot-v1|<sample_sha256>|<ordinal>`, breaking ties by
ordinal, and select the first two. From the remaining eligible ordinals
across those boroughs, select the first two by the same rank. This yields ten
distinct pilot rows. If any borough lacks two sampled rows or the residual
pool lacks two, fail; do not replace rows based on a match result. Store exact
ordinals only in protected local artifacts.

## Candidate comparison and interpretation

For every scanned row, trim outer whitespace from all 21 values. Define a
candidate key from borough, raw block, raw lot, apartment number, a parsed
calendar sale date and a parsed finite Decimal sale price. Use the existing
frozen date and price grammars, including the default 1900 Excel date system.
Borough, block and lot must be nonempty, date and price must parse; apartment
number may be blank as in the frozen representation rule. An incomplete or
unparseable key has status `invalid_key`. Do not normalize block/lot digits,
infer unit numbers, substitute an address, or match by target-price
proximity. Evaluate all five registered representation tiers over each
complete borough. Union the tier edges for each row. A proposed pair is a
`unique_six_key_candidate` only when its canonical-key group has exactly one
CSV and one workbook row, neither row is marked ambiguous by any tier or by
a K4 block/lot normalization collision, and each row's union of all-tier
edges consists solely of the other row. A collision elsewhere in the
borough does not reject this pair. A valid-key CSV row with a conflicting
edge, duplicate group, or a weaker-tier edge but no unique canonical pair is
`ambiguous`; one with no edge is `unmatched`. An invalid canonical key is
`invalid_key` even if a weaker tier produced a candidate edge.

For a unique candidate, compare the other 15 positionally corresponding
trimmed fields. If they disagree, the terminal status is
`unique_candidate_with_field_disagreement`, with only differing column
positions recorded privately. If all agree, status is
`canonical_full_21_concordance`; raw date and price strings agreeing too
upgrades it to `raw_full_21_concordance`. The six terminal statuses are
`invalid_key`, `ambiguous`, `unmatched`,
`unique_candidate_with_field_disagreement`,
`canonical_full_21_concordance` and `raw_full_21_concordance`.
The raw status requires equality of all 21 trimmed source strings, including
raw borough, block, lot, apartment, date and price; it is not inferred from
date/price alone.
The exact column-G header alias changes no row value. The private addendum
also records the candidate's checked source hashes and workbook row number.

All statuses mean agreement or disagreement between two *published
representations*. Even `raw_full_21_concordance` does not establish one
economic transfer per row, an arm's-length price, a dwelling identity, a
true closing date, historical availability or commercial rights. Keep those
review dimensions `unknown` under the v1 ledger until a separate verified
instrument/publication protocol supports them. Do not upgrade the v1 ledger
automatically from this pilot.

## Artifacts, privacy and gates

Write a new create-only, ACL-protected run under ignored `data/raw/nyc_dof/`:
intent, private result, fixed public projection and hash manifest. Record the
clean pushed code commit, lock and input hashes, run ID and frozen selection
algorithm in an fsynced intent **before** parsing the 200-row sample or
scanning any CSV/XLSX row. The selected ordinals are computed only afterward.
A failed or interrupted run has
no valid public result and cannot be resumed with changed inputs. The
private result may contain pilot ordinals, workbook source-row numbers,
candidate statuses and difference positions; it contains no copied address,
sale price or full source row. Its byte-identical offline replay rechecks all
pinned inputs and regenerates the comparison. The public projection is a
fixed four-borough inventory with null findings and zero sale labels. It must
not reveal per-borough pilot counts, status counts, difference positions,
ordinals or row fingerprints. A tracked report uses hashes and fixed
categories only. Keep initial failures and changed configurations as new
runs, never overwrite a completed result.

Write synthetic RED tests before implementation. Cover deterministic quotas,
missing sample rows, wrong hashes and row counts, invalid key/date/price,
duplicate keys on either side, distinct units, field disagreement, formula or
unqualified workbook rejection, ACL/reparse/hard-link failures, incomplete
run recovery, no-overwrite, replay and public non-disclosure. Require at least
80% branch-aware coverage of new code, the full suite without mandatory
skips, Ruff, dependency integrity, code/Python/security review and a clean
pushed code commit **before** the first new private-row read. Verify the
tracked evidence separately and push it after the private run.

This pilot can direct ten manual reviews. It does not count them as complete.
U0 and G-US remain pending, and no international work is unlocked.
