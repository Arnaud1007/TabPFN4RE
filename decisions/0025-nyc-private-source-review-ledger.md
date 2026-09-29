# ADR 0025: private NYC source-review ledger

Date: 2026-09-29
Owner: project implementation
Affected requirements: US05, US07, US22 and US24
Protocol version: `nyc-source-review-v1`
Status: approved for a private U0 manual-audit workflow

## Evidence and choice

[ADR 0021](0021-nyc-manual-audit-sample.md) froze 200 distinct ordinals from a
pinned 82,345-row rolling-sales CSV. Its selection is verified, but no source
rubric is complete. [ADR 0023](0023-nyc-acris-document-triage-v2.md) records
incomplete, bounded instrument-linkage pilots; those outputs are not certified
sales or reviewer judgements. Editing the frozen sample would destroy replay
identity. Use a separate, revisioned private JSONL review ledger, following
the established [HCPA pattern](0014-hcpa-review-ledger.md) while keeping its
frozen implementation and evidence unchanged.

The [NYC DOF glossary](https://www.nyc.gov/site/finance/property/glossary-property-sales.page)
defines `SALE PRICE` as price paid, `SALE DATE` as date sold and a zero price
as a transfer without cash consideration. It does not establish contractual
closing time, first publication, dwelling-level consideration or historical
attribute availability. A source row and a glossary entry therefore support
some descriptions, but do not settle those other fields.

## Frozen inputs and identity

- Source CSV SHA-256:
  `84c06057c52a2822f982cd98fb77ef7edf2c14134d00f46b073d2e4b762b2ef2`.
- Private selection ledger SHA-256:
  `e137de2cf73aa4a9fea6d024e4564ef6e907020e73fc8dbec3e4026786b189ca`.
- Exactly 200 unique one-based `ordinal` values from the selection ledger are
  admissible. `ordinal` is not HCPA's `record_ordinal` field.
- The reviewer reads the corresponding pinned source row by ordinal. Source
  hash, sample hash and ordinal appear in each private review entry. Neither
  input may be rewritten to reflect a later finding.

## Review entry and rubric

Each JSONL entry has `entry_id`, `ledger_id`, `protocol`, `source_sha256`,
`sample_sha256`, `ordinal`, `revision`, `supersedes_entry_id`, `review_status` (`partial` or
`complete`), `reviewer_code`, UTC `reviewed_at`, boolean `attested`, an
`evidence` list and a `rubric` map. Evidence items have a unique ID, kind,
reference and UTC observation time. Allowed kinds are `source_record`,
`official_documentation`, `independent_dof_export`, `recorded_instrument`,
`recording_index`, `closing_record`, `archived_row_snapshot`,
`publication_log`, `correction_record` and
`unavailable_attempt`. References and free-text limitations stay private.
Every evidence observation time is UTC and no later than `reviewed_at`; it is
when the reviewer observed the evidence, never a claimed historical
publication time. Reject a `reviewed_at` later than the current UTC time.
Archived-row evidence also records the verified snapshot
SHA-256, official revision date, and the row identity fields used to match
this sample ordinal. A reference alone does not create a time bound.

The rubric contains these dimensions, each with an enum finding, evidence IDs
and a limitation when unknown:

| Dimension | Permitted findings |
| --- | --- |
| `source_row_identity` | `match`, `mismatch`, `unknown` |
| `property_unit_identity` | `match`, `mismatch`, `not_applicable`, `unknown` |
| `economic_transfer_scope` | `single_property`, `multiple_properties`, `partial_interest`, `non_sale`, `unknown` |
| `repeated_consideration` | `distinct_transfer`, `repeated_amount`, `unknown` |
| `price_semantics` | `reported_positive`, `reported_zero`, `invalid`, `unknown` |
| `sale_date_vs_contract` | `before`, `same`, `after`, `unknown` |
| `sale_date_vs_closing` | `before`, `same`, `after`, `unknown` |
| `sale_date_vs_recording` | `before`, `same`, `after`, `unknown` |
| `first_row_availability` | `upper_bound_only`, `first_publication_verified`, `unknown` |
| `attribute_vintage` | `historical_asof_supported`, `later_or_current`, `unknown` |
| `source_correction` | `documented_correction`, `no_correction_in_checked_history`, `unknown` |
| `property_class` | `single_family`, `condominium`, `small_multifamily`, `other_residential`, `nonresidential`, `vacant_land`, `unknown` |
| `evidence_quality` | `high`, `medium`, `low`, `unknown` |

Every finding cites at least one evidence item. `unknown` requires a concrete
limitation, not a blank or a guess. `source_row_identity=match` or `mismatch`
means comparison of the pinned row's borough/block/lot, apartment number when
present, sale date and price against an independently retrieved official DOF
export or recorded instrument. Cite that evidence; if no comparable record is
available, use `unknown`. Agreement between two DOF extracts still does not
prove the facts are correct. A non-unknown transfer, repeated-price or
unit-identity conclusion requires a recorded instrument or another explicitly
qualified source. The price-semantic findings describe the **published row**;
they do not certify arm's-length consideration. Under ADR 0021's strict
decimal parser, a positive price is `reported_positive`, zero is
`reported_zero`, and a missing, negative or unparseable price is `invalid`.
The price-edge flag (positive at most USD 1,000) marks a **nominal candidate
for investigation**, not a separate mutually exclusive price state or proof
of nominal consideration. A non-unknown comparison to contract or closing
requires the corresponding record; a recording comparison
requires a recorded instrument or recording index. `upper_bound_only`
requires actual archived row bytes, verified SHA-256, official archive date
and a checked identity match to this row. `first_publication_verified`
requires a source publication log naming this row and ruling out an earlier
release. The metadata-only archive probe qualifies for neither. The dates
stay in the private evidence record. `historical_asof_supported` requires
dated attribute evidence. `no_correction_in_checked_history` is limited to
the history actually checked, never proof that no other correction exists.
Its private evidence records the checked history bounds and version IDs.
`property_unit_identity`
may be `not_applicable` only when a recorded instrument establishes a
whole-property, non-unit transfer. Missing unit or contract/closing evidence
means `unknown`, never `not_applicable`.

Non-unknown findings need evidence suited to their dimension: pinned source
row plus official documentation for `price_semantics` and `property_class`;
independent DOF export or instrument for `source_row_identity`; instrument for
unit and economic-transfer scope; an instrument or independently qualified
transaction record for repeated consideration; contract, closing or recording
record respectively for date comparisons; dated attribute snapshot for
`historical_asof_supported`; correction history for either non-unknown
`source_correction` value. Evidence quality cites the checked sources. An
unavailable request supports an unknown limitation, never an affirmative
match. Reviewers cannot turn a blank source field into an N/A finding.

`complete` requires all dimensions, source-row evidence, an official definition
check, a recorded instrument **or documented unavailable access attempt**, and
reviewer attestation. Unknown outcomes can remain after these checks. A
completed form measures review effort, not a verified label, eligibility,
historical as-of correctness or source rights. Rights are assessed at source
level in the source card, not inferred from one transaction.

## Ledger behavior and privacy

`scripts/review_nyc_sample.py` validates the two frozen hashes and 200 ordinals
before accepting an entry. A one-time `init` creates an empty private ledger
and a private manifest with a generated `ledger_id`; it never overwrites an
existing ledger. Each append supplies that ID and the expected SHA-256 of the
**entire prior ledger** from the previous verified summary. A missing ledger,
different ID or changed hash fails. Validate the full prior history, require
unique entry IDs and contiguous revisions (`revision = previous + 1`,
`supersedes_entry_id = previous entry_id`), and reject all duplicate appends.
The `summary` action validates the current ledger after a crash and can
produce a new summary if an append committed before its report. Re-init after
loss creates a different ID and is a new audit history, never a silent restart
of the old one. Truncated or malformed history is an error, not repaired.

Use an exclusive PID/host/time lock, bounded private files, static symlink and
hard-link checks, a verified restricted ACL on the private ledger directory
before the first write and on replay, fsync plus same-directory atomic
replacement of the JSONL image, and create-new aggregate output. The threat
boundary assumes trusted
same-privilege local processes; it does not claim to defeat concurrent
directory swaps by a malicious peer. No network request occurs in the ledger
tool. Keep addresses, BBLs, prices, document IDs, exact ordinals, URLs, notes
and row-level findings under a protected Git-ignored
`data/raw/nyc_dof/manual-review-v1/` directory. Logs and tracked reports
contain only hashes, commands with generic private filenames, total
selection/review status and suppressed aggregate outcomes. Commands must not
encode ordinals, addresses, BBLs, document IDs or evidence URLs. Do not
publish interim finding/unknown cells or differences that reveal a small
number of reviewed properties. In a later full-audit report, publish a finding
cell only when at least five independently confirmed properties support it;
distinct CSV rows are not a substitute for distinct properties.

## Execution and acceptance

Write synthetic tests first for wrong hashes/ordinal, missing or conflicting
evidence, unjustified non-unknown findings, incomplete versus attested forms,
revision/replay, crash/short write, locking, private path escapes and
aggregate-only output. Verify more than 80% branch-aware coverage and the full
suite before a private pilot. Commit and push protocol and reviewed code before
the first real review entry.

Pilot one or a few frozen ordinals using the source row, official definitions
and available transaction evidence. Record an access limitation as unknown;
never convert a failed lookup into a negative match. Then review all 200,
including edge rows, and expand the audit under a new protocol if a systematic
defect appears. Reports state the 200 denominator, complete/partial/untouched
counts, hashes and gate status. Any published evidence limitation is a
suppressed fixed-category aggregate, never a free-text note or small-cell
disclosure. The first pilot and even
200 completed forms leave U0 pending until rights, date semantics, first
availability and transfer/dwelling identity are adequately established.
