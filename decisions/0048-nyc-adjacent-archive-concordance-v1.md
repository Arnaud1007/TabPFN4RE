# ADR 0048: compare adjacent NYC rolling archive representations

Date: 2026-10-03
Owner: project implementation
Status: frozen before any private version-61/version-62 row comparison
Protocol: `nyc-adjacent-archives-v1`
Requirements: US05, US06, US08, US22, US23, US24

## Question and fixed inputs

Measure full-source-row representation overlap between the two already captured
NYC rolling-sales archives. This is a source audit, not a transaction join or
historical as-of certification. The inputs are immutable and remain Git ignored.

| Archive | Public/private manifest SHA-256 | CSV SHA-256 | CSV bytes | Strict rows |
| --- | --- | --- | ---: | ---: |
| Version 61, portal revision `2026-01-27T14:48:20.467Z` | `52090b7c0279868c54adfbc4b5b043d87d896f79f3ec963a06a8e501b8b4cdab` | `19ecb0eb368df66f60758098213fd4855109e6afa20c82e99787930b893ba0f7` | 11,120,362 | 79,335 |
| Version 62, portal revision `2026-04-20T18:29:25.966Z` | `a85186c249503435494e9c06e4274bbea85d986bba058375cbe7d3537b6e01bc` | `0746355101b245fb469ce97e19e088fa2b16f0f95728d7a5b07dd670e98c345f` | 11,302,195 | 81,567 |

The source paths are the fixed `ready-archive-v61-20261002T230327Z` and
`ready-archive-v2-20261002T210520Z` directories beneath the protected,
Git-ignored `data/raw/nyc_dof/` root. The expected source header is the exact
21-field `ARCHIVE_HEADER` in `compare_nyc_archive_snapshot_v1.py`. Both saved
public aggregates state header SHA-256
`8c6ae5508597dec1810b16654c1e0958f7b16b4d3425e55c8ea7c6614982048f`.
Require exact header order and strict UTF-8; do not infer a column map.

## Comparison rule

Reuse the previously reviewed pure archive CSV parser, 21-field reordering,
date parser and multiset comparison unchanged. Trim outer Unicode whitespace
in every cell. Count full 21-field tuple overlap as the sum of minimum
multiplicities; reconcile each version's residual to its source denominator.
The second tier changes only sale-date representation: normalize exact ISO,
US slash and zero-time midnight forms between 1900-01-01 and 2026-10-02.
Exclude invalid dates only from this second tier and report their counts
privately. Keep all other cells, including price, exact after trimming.

Two matching tuples are matching *source representations*. A residual might
be a new, removed or corrected row, a changed format, or duplicate. No stable
transaction key or per-row first-publication timestamp is established here.
Do not classify economic transfers, infer additions or deletions from the row
count difference, or certify any sale label, feature, temporal split or model
training row. Neither portal revision timestamp proves that every row was
first available by that date; the archives were captured later.

## Resource, privacy and run controls

The runner makes no network request. Require exact public/private manifest
bytes, pinned hashes, source protocol/version/CSV stage and filename, source
byte and strict-row counts. Reject links, changed files, schema drift,
malformed CSV, invalid UTF-8 or ACL failure. Cap each CSV at 128 MiB and
150,000 data rows, each field at 16,384 characters and all cell characters
at 64 million per file.

An output run resides in a new protected, Git-ignored directory. Require a
clean code commit matching `origin/audit/u0`, the pinned CPython environment
lock, code/helper/config/input hashes and create-only intent before opening
either private CSV. Save private aggregate result and a separate public
projection, then a hash manifest; interrupted runs stay incomplete. Replay
offline from the same pinned inputs and require byte-identical aggregates.
Never overwrite or repair an existing run in place.

Private output may contain only aggregate counts, hashes and provenance. It
must contain no source row, address, unit, price, date, row ordinal or per-row
fingerprint. Public output contains exact source denominators and only broad
overlap buckets: `zero`, `suppressed_1_to_4`, `5_to_99`, `100_to_999` and
`1000_plus`. Do not publish field, geography or small residual counts. Both
outputs state zero certified labels and false historical-as-of eligibility;
U0, U3 and G-US remain PENDING.

## Verification and decision

Write synthetic tests first for multiplicity, date-only normalization,
invalid dates, schema and manifest tampering, privacy, create-only failure,
replay and no overwrite. Require at least 80% branch-aware coverage for the
new runner, full suite, Ruff, dependency audit and code/Python/security
review. Commit and push the reviewed runner and frozen plan before the first
private comparison. Verify the remote branch points to that commit. Then run
once, replay, publish only redacted evidence and push it in a separate commit.

The result may guide a later publisher-publication and source-identity audit.
Dataset rights, DOF sale-date meaning, first row availability, unit/transfer
identity and remaining manual rubrics are independent admission conditions.
