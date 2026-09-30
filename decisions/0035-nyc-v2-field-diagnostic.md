# ADR 0035: Protected field diagnostic of the frozen NYC v2 result

Date: 2026-09-30
Owner: project implementation
Affected requirements: US04, US05, US06, US07, US08, US22, US23, US24
Protocol: `nyc-dof-v2-field-diagnostic-v1`
Status: frozen after private-only pre-run privacy amendment; no private v2 result read under this protocol yet

## Question and evidence boundary

The [frozen v2 result](../runs/u0-nyc-representation-v2-20260930T152830Z/report.md) found many isolated candidate links after canonicalizing sale-date representation in Bronx, Brooklyn and Queens. Fewer candidates meet its strict `format_only_candidates` definition. This analysis asks whether disagreements in the other 19 trimmed fields and typed date/price parse failures are present among those candidate pairs, and which field families warrant a later source-semantics audit. It does not determine economic-transfer identity, label eligibility or as-of availability.

Read only the protected, immutable v2 **result artifacts**, never the original CSV/XLSX rows. Pin private run ID `representation-diagnostic-v2-20260930T152830Z-460cba306f9d`, code commit `cbbc14e3f3351b75a32956e4841f219fba314745`, intent SHA-256 `1b87392277fd57298192bbd037c0b3f5805b0119554bdcac4a90a41e45e6624a`, result SHA-256 `2b7b7643c6b07a763e0e3cd842b5f60b2819805acb50341d485c7aa910141199`, public SHA-256 `e3ae01bd7d551a66cf84f8862668e90f0a4071c3352ce8ac622d22938c4d766f` and hash-manifest SHA-256 `a0cba0b35b4d9cc683d2df64119d05f16212e74cf372a7735b640443fe222fe1`. Require exact protected inventory, ACL, no reparse point or hard link, bounded same-handle hashing and canonical JSON. Match the tracked v2 public aggregate and fixed four-borough frame. A mismatch stops the analysis; it does not trigger a source rerun.

## Frozen questions and interpretation

For each borough, use top-level scope/row metadata and `counts.statuses` only for validation and denominators; select the fixed aggregate `counts.fields`, `counts.overlap`, `counts.parse_failures` and `counts.lexical_forms` for analysis. The existing v2 validator may traverse its protected ledger to check integrity, but this diagnostic must never select, filter, print, persist or export ledger entries, ordinals, fingerprints, row values or source keys. Its private output is a freshly constructed aggregate object, not a copied v2 borough record.

Predeclare these checks before opening the result:

1. `n = csv_isolated_candidate = xlsx_isolated_candidate`. Each raw date/price, full-row and other-19 match-plus-mismatch pair equals `n`. Each canonical date and Decimal-price match-plus-mismatch-plus-unparseable triple equals `n`. Reconcile the 21 per-column disagreement bounds and known address, class, date and price indices. Each of the other 19 column disagreement counts must be no greater than `other_19_mismatches`.
2. Test whether `other_19_mismatches` is positive. A positive result proves only that some *candidate pair representations* disagree outside date and price; it does not identify which source is correct.
3. Test whether `canonical_date_unparseable` or `decimal_price_unparseable` is positive among isolated pairs. Also report source-level parse failures privately with their separate source-row denominators. A source parse failure is not automatically a failure on an isolated pair.
4. Rank the fixed 21 header columns privately by candidate-pair disagreement count, breaking ties by header index. Compare each raw-column unordered multiset overlap with its source denominators; compare canonical date, Decimal price, block and lot overlaps. An unordered overlap is never a row link or identity proof.
5. For Bronx, Brooklyn and Queens, compare `n` and `format_only_candidates` with the pinned public v2 projection. For Staten Island, verify that recomputing the v2 public projection remains suppressed and matches its pinned public artifact; never publish its private counts. These stored marginals can show presence and size of overlapping mechanisms. Do not announce an exclusive or causal explanation for the gap without a separately proven partition and source-semantics audit.

No new date, price, address or category normalization is permitted. This task is an interpretation of v2 counters, not a revised v2 comparison. Staten Island stays in the protected integrity check but no Staten detail may be released.

## Publication and privacy rule

The verified field analysis is private. Its result contains fixed aggregate counts, definitions, ranking and no copied row ledger; the protected intent retains source-hash provenance. It remains under the Git-ignored, ACL-protected NYC root. The public projection is deliberately constant for the four pinned boroughs: it names each borough in the already published order, sets flags and disagreement_headers to null, and uses the fixed reason private_only_v1. It includes the pinned v2 result hash, unqualified label status and zero certified sale labels. No public field count, field name selected by the private data, lexical form, overlap, rank, ordinal, fingerprint, pooled total or conditional claim is released.

This is a pre-run privacy amendment. The earlier proposal to publish 200-count flags and selected headers was rejected before opening the protected v2 result. Published v2 exact candidate counts, format-only counts and the field validator's inequalities can jointly narrow a threshold flag to an exact new count even when simple small-cell and denominator checks pass. A sound joint disclosure proof is deferred. The diagnostic remains useful as a protected source-audit artifact; the public evidence proves provenance, reproducibility and the fact that zero sale labels were certified. Any later field-level publication requires a new versioned protocol and review before opening or releasing its result.

The public projection still verifies exact agreement with the tracked v1 and v2 public artifacts, fixed borough inventory and source hashes. An upstream public suppression remains suppressed. Staten Island is always suppressed. A mismatch stops the run; it never triggers a source rerun or a data-dependent public fallback.

## Implementation, acceptance and stop rules

Add a new analyzer and synthetic tests without changing the pinned v1/v2 code. `plan` reads only tracked metadata. `analyze` requires a clean, pushed code commit and writes a create-only protected intent **before** opening any protected v2 artifact. It builds private and redacted public results atomically, marks an interruption incomplete and supports byte-identical offline replay. Save the source hashes inherited from v2 provenance without reopening CSV/XLSX, plus environment lock, code hashes and exact commands. Limit protected result reads to 64 MiB and never call original source-row scanners.

Synthetic RED tests cover hash, ACL, reparse and hard-link failures; unexpected artifact inventory; JSON/schema and arithmetic tampering; accidental source-scanner calls; no leakage through ledger or output; constant private-only projection across adversarial aggregate counts; Staten Island; interruption; and replay. Require above 80% branch-aware coverage for every new module, the full suite, Ruff, pip check, scoped pip-audit and independent code/security review. Push reviewed code before the first result read. Then run once, replay, verify, publish only the fixed redacted aggregate, report, test gate and immutable manifest, and push that evidence.

Failure leaves the source v2 evidence untouched. The private run remains incomplete or rejected with a reason. Zero sale labels are certified, and U0 and G-US remain pending. Source reuse rights, actual close-date meaning, first-row availability, parcel/unit identity, Manhattan worksheet status and the 200-record manual audit are separate dependencies.
