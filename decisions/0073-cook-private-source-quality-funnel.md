# ADR 0073: audit the pinned Cook source observations before label eligibility

Date: 2026-10-03

Owner: project implementation

Status: frozen before quality execution

Requirements: US06, US07, US24

Protocol: `cook_source_quality_v1`

## Decision

Use the existing 200-row Cook private capture and verified parcel-observation
staging as the complete input. Classify every source row without filtering on
price or residuals. Keep a private, create-only row-level quality file and a
private count summary. Publish only the pinned input and output hashes, the
already disclosed 200-row denominator, zero certified sale labels, false
historical as-of eligibility and PENDING gate statuses. New reason counts
remain private because this deliberately stratified small sample contains
unusual transfers and the prior staging decision prohibits new public
small-cell disclosures. A pre-execution security review identified that a
public digest of low-entropy counts might support guessing small cells. The
count-file digest therefore remains only in the private completion manifest.

## Frozen rules

- Price states are the staged `positive`, `nonpositive`, `malformed`, `missing`
  and `null` states. Positive does not mean arm's-length or single-home.
- PIN states are `valid`, `malformed`, `missing` and `null`. A valid PIN retains
  all 14 original ASCII digits, including leading zeros.
- Recorded-date states are `valid`, `malformed`, `missing` and `null`. A valid
  date remains the source's **recording** date, not a close date.
- `is_multisale` is interpreted only when it is exactly JSON boolean. Missing,
  null and other values are distinct unknown/invalid diagnostic states.
- `num_parcels_sale` is a positive integer up to 99,999,999 or an ASCII
  decimal string of at most eight characters representing one. Longer strings
  and values outside that bound are malformed. One, multiple, missing, null
  and malformed are separate states. This field alone does not establish
  economic transfer scope.
- `doc_no` groups exact nonempty strings. Missing, null, non-string and
  whitespace-padded values are unusable. Every row in a repeated document
  group receives a review reason; no rows are deduplicated or priced apart.
  `unique` means unique within these 200 sampled rows only, not in the source
  population or among all parcels in an economic transfer.
- Every source row is `audit_only`, including rows with apparently complete
  fields. No field or count converts to canonical `Transaction`, comparable,
  training label or historical `available_at`.

The private findings use fixed reason codes and preserve original ordinal,
row ID and source-row hash solely for manual review. They do not contain
prices, PINs, document numbers or addresses. The private count summary
partitions all 200 rows for each quality dimension. Both private outputs are
deterministic functions of the verified staging file. A completion manifest is
written last. The runner replays the original capture and staging hashes,
rejects wrong count/order, duplicates, changed fields and hash drift, and
publishes no result on failure.

## Alternatives and limits

Metadata-only documentation would not prioritize the 200-record manual audit.
Automatic label eligibility would confuse parcel observations with single-home
transfers and is prohibited. A public detailed funnel from this sample risks
small-cell disclosure and falsely implies population prevalence. The current
quality funnel is therefore a private audit checkpoint. A later accepted
source can publish an inclusion funnel under a separately justified release
policy and a complete eligible population.

No new HTTP request, purchase, source-row collection, rights claim, close-date
inference or model fit is part of this protocol. See the
[frozen run plan](../runs/u2-cook-quality-v1-20261003T135237Z/plan.md).
