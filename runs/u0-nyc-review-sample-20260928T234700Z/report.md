# U0 NYC private manual-audit sample

Run ID: `u0-nyc-review-sample-20260928T234700Z`
Status: **verified selection; manual review not started; U0 and G-US PENDING**
Code commit at draw: `2b579824171295d084170056e78e3434885d7fbc`
Requirements: US05, US06, US07, US22, US23, US24

## Objective and protocol

Select 200 rows from the pinned, private 82,345-row NYC rolling source for a
future manual identity, date and transaction-scope audit. [ADR 0021](../../decisions/0021-nyc-manual-audit-sample.md)
was committed and pushed as `103b99b` before any row was selected. The
selector implementation and synthetic tests were separately reviewed,
committed and pushed as `2b57982` before the live draw. The source CSV SHA-256
is `84c06057c52a2822f982cd98fb77ef7edf2c14134d00f46b073d2e4b762b2ef2`;
the source-profile SHA-256 is
`6a5a7c57f21ae5a213a00545034fd2cd3c1bb4128d17b56cb1b26f8bedf692ef`.

## Observed selection

The [aggregate result](aggregate.json) records 200 distinct selected rows:
10 price, 10 unit/parcel identity, 10 repeated source-key, 10 gross-area,
5 oldest-month and 5 newest-month primary edge rows, plus 150 structural rows
(15 candidate and 15 other/ambiguous in each of five boroughs). The 50 edge
rows were selected first without replacement. All 200 ordinals, ranks and
flags live only in ignored private JSONL. The ledger is 62,700 bytes with
SHA-256 `e137de2cf73aa4a9fea6d024e4564ef6e907020e73fc8dbec3e4026786b189ca`.
The source profile and selector independently counted 1,447 rows in repeated
exact-string key groups; these remain *candidates*, not confirmed duplicate
transfers. Edge flags overlap: for example, 71 sampled rows carry the price
flag although only 10 have it as their primary selection reason.

The selector verified the pinned bytes, row count, header and source profile,
then ranked from one immutable byte buffer. A separate replay to a new private
file produced a byte-identical 200-row ledger. The independent post-run check
confirmed 200 unique ordinals, each stored SHA rank, bucket totals and the
ledger hash. No row-level source content was copied into tracked files.

## Commands, tests and failures

The exact selection command, seed and hashes are in [configuration.json](configuration.json).
Run `& 'runs/u0-nyc-review-sample-20260928T234700Z/verify_artifacts.ps1'`
from the project root to verify tracked artifacts and both private ledgers.
The live selector exited 0 in approximately four seconds; the replay exited
0 in approximately four seconds. An initial *verification wrapper* command
failed PowerShell parsing before execution because of shell quoting (exit 1).
The [failure record](failed_wrapper.json) preserves the diagnostic and failing
command fragment; the full attempted command was not saved as an artifact.
It did not change either ledger or affect selection. A here-string Python
verifier then completed successfully. This is retained as a tooling failure,
not a data or model failure.

[test_gate.json](test_gate.json) records actual commands, exits, durations and
logs. Ten focused synthetic tests passed; branch-aware selector coverage was
87%. All 394 repository tests passed with one **optional** skipped OpenML
source-integration test because `AMES_ARFF_PATH` was not set; zero mandatory
tests were skipped. Ruff lint/format, `pip check` and the scoped pinned
dependency audit passed. Reviewers found no remaining critical or high code,
Python or security finding after the immutable-source and independent-oracle
fixes. The unrelated HCPA email draft was locally modified at the draw and
does not affect source, protocol or selector bytes; record this dirty-tree
state rather than claiming a wholly clean execution environment.

## Gate and next action

**Zero of 200 records have a completed manual rubric.** Selection is not an
audit or validation of sale eligibility. Review every private ordinal against
the NYC source and available transaction evidence, then record unit identity,
economic-transfer scope, $0/nominal price meaning, sale/closing/recording
date relationship, first publication and field-vintage quality. Preserve
unknown answers and expand the review if systematic defects appear. NYC
rights, historical as-of availability and unit/transaction semantics remain
unresolved. Do not train a real-data temporal model or claim G-US from this
sample.
