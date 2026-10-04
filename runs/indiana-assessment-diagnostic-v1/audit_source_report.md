# Indiana low-price source audit: first checkpoint

Date: 2026-10-05. Status: **targeted review incomplete; 90-day assessment
model blocked**. This report adds source-quality evidence. It does not train,
rescore or certify a model.

## Frozen inputs and outputs

| Item | Evidence |
| --- | --- |
| 2025 SDF archive SHA-256 | `f574f75604c953a1c0e498550ea05a20ebf705e8dfaca9aa1090d7a358ee4e12` |
| Sampler code commit | `d59c3f4f68c991e650b993519a0201ee740b6d39` |
| Private 200-row queue SHA-256 | `d52f3fdd7c2e2152ba971bc275b551b584effb195764ea464a8e767cb296b7c3` |
| Private first-20 review SHA-256 | `f340b809b2ea1fbba4a8d7a64557326ecc4559c21db8daa52b6c525cd37a1b44` |
| Public counts | [Selection manifest](audit_sample_manifest.json) and [review progress](audit_review_first20.json) |

The sampler verified the pinned archive and the unchanged 71,054-row 2025
development membership. It selected 50 distinct economic sales from each of
four cells: price up to/above the 2024-derived $117,000 boundary, crossed
with the assessor's post-sale trending flag Y/N. Each cell contains its ten
lowest prices, ten highest remaining prices and 30 hash-ranked remaining
records. The 200-row queue is private, Git-ignored and ACL-protected. The
public files contain no form IDs, parcel numbers, addresses or row-level
prices. Selection is not manual review or a representative prevalence sample.

## First 20 source records inspected

The first ten lowest-price low/Y and first ten lowest-price low/N records
were checked against the original disclosure and parcel rows. All have
positive but very small stated consideration. Ten assessor notes explicitly
indicate nonmarket consideration or invalidity, including no consideration,
a minimum-amount failure, family/adjacent-party or related-entity transfers.
The other ten have unresolved extreme prices; a trending-valid Y flag does
not establish an arm's-length sale. All 20 are marked **eligibility unresolved**
until independent conveyance/source checks. The private review ledger retains
form lookup, reason code, source-field references and a digest of each note.
No records were removed from the frozen 2025 diagnostic score.

Only 20 of the selected 200 are inspected; 180 remain. The wider US07 audit
must also cover excluded transfers, duplicates, ambiguous property identity
and geographic coverage. The targeted queue cannot satisfy that gate alone.

## Decision and next action

[ADR 0094](../../decisions/0094-indiana-assessment-asof-no-go.md) blocks the
assessed-value challenger from 90-day OFF or current valuation. The source
does not establish that its values were available before each origin, and
the first source review found nominal/nonmarket label concerns. The 15.19%
MdAPE remains an unchanged retrospective development result. G-US is PENDING.

The next bounded source check is the existing Hillsborough 2025 parcel
archive paired with later sale records. Verify original publication time,
transaction grain, rights and pre-origin availability before fitting one
fixed baseline. The saved King County historical research predictor remains
the immediate runnable prediction example.

## Verification performed

- `python -m unittest tests.test_sample_indiana_audit -v` in `.venv`: 9 tests
  passed, including duplicate joins, source hash, deterministic selection,
  create-only writes, interrupted-run recovery, tampering and spreadsheet
  formula rejection.
- Ruff check and format on the sampler and its tests: passed.
- Pinned requirement audit: no known vulnerabilities found.
- Real sampler CLI: exit 0; 200 distinct rows, exactly 50 per cell; private
  queue hash matched the manifest; private ACL and Git ignore checks passed.
- Private review ledger and public progress hashes matched; the public
  progress records 20 inspected, 180 pending and zero eligibility decisions.
- The initial broad `.venv` run executed 1,345 tests with two environment
  errors (`sklearn` absent); the affected 9-test Indiana module passed in the
  pinned ML interpreter. A second full run used the pinned ML interpreter
  with the project `.venv` site-packages first on `PYTHONPATH` for its pinned
  timezone/XML/test tools: **1,345 tests passed in 231.247 seconds**, with
  **92% package coverage**. This combined test environment is disclosed
  rather than presented as a single locked release environment. Commands and
  exit codes are in [audit_test_gate.json](audit_test_gate.json).
