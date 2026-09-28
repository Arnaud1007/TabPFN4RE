# U0 NYC rolling source profile

Run ID: `u0-nyc-rolling-profile-20260928T232337Z`  
Status: verified source inventory only; U0 and G-US **PENDING**  
Code commit at profiling: `ef3638f7d4a00c7e17aa200878f0c085ae206265`  
Requirements: US05, US06, US07, US22, US23, US24

## Objective and input

Profile the private, frozen current NYC rolling CSV before freezing a 200-record
manual source-audit sample. [ADR 0020](../../decisions/0020-nyc-source-semantics-and-profile.md)
registered the fields and boundaries before the first row scan. The input is
the 82,345-row, 10,397,977-byte file with SHA-256
`84c06057c52a2822f982cd98fb77ef7edf2c14134d00f46b073d2e4b762b2ef2`.
The profiler verified its hash, byte count, header and row count against the
[capture manifest](../u0-nyc-rolling-snapshot-20260928T225512Z/snapshot.json).
Raw rows and the two private profile copies remain under ignored `data/raw/nyc_dof/`.

## Observed aggregate

The complete machine-readable results are in [aggregate.json](aggregate.json).
These are published CSV *rows*, not verified homes or economic transfers.

| Measure | Rows or groups |
| --- | ---: |
| Portal rows | 82,345 |
| Positive prices | 54,013 |
| Zero prices | 28,332 |
| Positive prices at most USD 1,000, for investigation | 1,552 |
| Missing gross-area values | 37,929 |
| Nonpositive gross-area values | 1,777 |
| Class `R` rows with missing apartment number | 1,549 of 22,266 |
| Trimmed source-string repeated-key groups | 339 |
| Rows within those groups | 1,447 |

The repeated key is raw borough, block, lot, sale date and sale price after
whitespace trimming. It can miss equivalent formats and can combine distinct
dwelling records. It is **not** a deduplication or label-eligibility decision.
The one-family *candidate* requires both a category beginning `01 ONE FAMILY`
and a class-at-sale beginning `A`; 330 rows disagree between those screens.
Candidate counts by borough 1–5 are 152, 1,315, 3,303, 8,437 and 3,767.
The source month range in this frozen file is September 2025–August 2026.
Current descriptive fields and sale dates are not proven available at any
earlier valuation origin.

## Execution and verification

The first live profiler invocation wrote a valid private aggregate, but the
surrounding PowerShell/Python summary wrapper then requested the absent JSON
key `one_family_candidate_by_borough` and exited 1. This is a **failed wrapper
command**, not a failed or discarded source scan. Its first tracked copy used
Windows CRLF (`aggregate_initial_crlf.json`, SHA-256
`ca204cf1b9e39195c280bdc04e3004c2528de8922c5d663e3a00f154c07654cb`).
The canonical tracked `aggregate.json` was copied byte-for-byte from the
successful private output. A second invocation of
`python scripts/profile_nyc_rolling_snapshot.py` completed with exit 0 to a
new private output; `aggregate_replay.json` is byte-identical to the canonical
aggregate, SHA-256
`6a5a7c57f21ae5a213a00545034fd2cd3c1bb4128d17b56cb1b26f8bedf692ef`.
The profiler command template and both output names are in `configuration.json`.

[verification.json](verification.json) records reconciliation of borough,
class, price and joint structural denominators to 82,345. Every proposed
borough × candidate/other cell has at least 15 rows and every proposed edge
bucket has at least 10 before overlap removal. A disjoint 200-row sample is
therefore *plausible*, not yet selected or proved feasible after deduplication.

[test_gate.json](test_gate.json) records exact commands, exits, durations and
logs: 12 focused synthetic tests passed with 89% branch-aware script coverage;
all 384 repository tests passed; Ruff, `pip check` and the scoped pinned
dependency audit passed. The full test log had a local temporary path replaced
with `<LOCAL_TEMP>` before tracking; the substantive test outcome was retained.
Run `& 'runs/u0-nyc-rolling-profile-20260928T232337Z/verify_artifacts.ps1'`
from the project root to check hashed evidence and the private source/profile
copies. This verification requires those ignored private files locally.

## Limits and next action

This is a source inventory, not a manual record audit, sale eligibility funnel,
as-of benchmark, model run, performance result or use-rights decision. The
[DOF glossary](https://www.nyc.gov/site/finance/property/glossary-property-sales.page)
describes $0 rows as transfers without cash consideration, while the
[rolling-file header](https://www.nyc.gov/assets/finance/downloads/pdf/rolling_sales/rollingsales_manhattan.pdf)
warns that descriptors of earlier sales can reflect later tax-roll data.
First publication, close-date mapping, transaction scope and unit identity
remain unverified. Next freeze a deterministic, disjoint 200-record sample
protocol against this exact aggregate and hash; only then select private rows
for manual review. Do not start NYC model training.
