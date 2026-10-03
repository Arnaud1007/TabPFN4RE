# Frozen Cook source-quality run plan

Frozen 2026-10-03 13:52:37 UTC, before inspecting staged row quality outcomes.
Protocol: `cook_source_quality_v1`. Requirements: US06, US07, US24.

## Inputs and operation

- Pinned Cook capture manifest SHA-256:
  `130b5169ff81ccbc0a729cba98400f2fb377ff9a25999316aaac1960e38a3cf7`.
- Pinned source metadata SHA-256:
  `c967e289fdd1a45319b1efdedf38276c670b1cdb0e11e5466e95e31731119dce`.
- Pinned staged observations SHA-256:
  `7b315b4b001d3b14ffc64ab0277f486738e53b83b120da592a952f94a175c167`.
- Exactly 200 source observations in the frozen capture order. First call the
  existing staging verifier, which replays the original capture and checks
  all staged bytes. The staged record must round-trip through
  `CookParcelSaleObservation.from_record` before classification.
- No network access, model fit, test-label opening, modification of the
  capture/staging files or change to the existing reviewer ledger.

## Outputs and caps

Create `data/raw/cook_county/parcel-quality-v1-130b5169ff81ccbc/` once with
ACL restriction. Write `findings.jsonl` (at most 256 KiB), `counts.json`
(at most 16 KiB) and `complete.json` last (at most 4 KiB). The findings retain
only ordinal, row ID, row hash, fixed states and reason codes. Private counts
partition all 200 rows. Reject an existing run directory, malformed JSON,
unexpected fields, wrong order/count, digest mismatch or changed completion
manifest. Keep an incomplete private run for inspection if execution fails.

Publish a create-only `aggregate.json` under this run directory only after
private replay passes. Its exact allowlist is protocol, pinned capture and
staging hashes, private findings hash, `sample_rows: 200`,
`certified_sale_labels: 0`, `historical_asof_eligible: false`, U0/G-US
`PENDING`. No row IDs, PINs, documents, dates, prices, free-text values or new
small-cell counts enter a public artifact. The sample is deliberately
stratified and supplies no population-rate estimate.

Pre-execution amendment, 2026-10-03 14:01:12 UTC: security review identified a
possible small-cell inference from a public digest of the private count file.
Remove that digest from the public allowlist before the first real run. Keep it
in the private completion manifest and replay check. No rows or counts from
the real sample had been classified when this amendment was made. The
eight-character parcel-count string limit in ADR 0073 was clarified after
Python review and before the real run.

## Tests and adoption

Write synthetic RED tests first for partition completeness, missing/null/
malformed distinctions, positive-but-uncertified rows, shared documents,
multisale/parcel conflicts, duplicate ID rejection, tampered hashes and
count/order changes, exact public allowlist, create-only persistence and
generic errors. Achieve at least 80% branch-aware coverage for new modules;
run Ruff, the full suite, security review and private replay. Record actual
commands, exits, durations and output hashes in `report.md`. Do not call this
an accepted US source or release. U0 and G-US remain PENDING.
