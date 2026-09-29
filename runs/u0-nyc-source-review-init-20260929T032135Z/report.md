# U0 NYC private source-review ledger initialization

Run ID: `u0-nyc-source-review-init-20260929T032135Z`
Status: **verified empty ledger; U0 and G-US PENDING**
Requirements: US05, US07, US22 and US24

## Objective and implementation

Initialize the [ADR 0025](../../decisions/0025-nyc-private-source-review-ledger.md)
private, revisioned review ledger for the frozen 200-row NYC sample. The
[ADR 0027](../../decisions/0027-nyc-ledger-evidence-boundary.md) v1 restriction
permits an affirmative finding only for the pinned source's published price
state; all other rubric findings remain explicitly unknown until a later
verified-artifact protocol. Reviewed code was pushed at `b99c90d` before this
first real ledger write. The ledger implementation was committed at `2c57d9a`.
The working tree at init also had concurrent uncommitted borough collector and
collector-test edits unrelated to the ledger; the run manifest records this.

## Actual result

The pinned 10,397,977-byte source CSV SHA-256 and private 200-ordinal sample
SHA-256 matched their frozen values. The protected directory and create-new
manifest/empty ledger were created. [aggregate.json](aggregate.json) reports
200 sampled rows, **zero** reviewed, zero complete, zero partial and 200
untouched. [replay.json](replay.json) is byte-identical with SHA-256
`ee68bae54aaf46a350bb04ba8963403670583a86900efbad16ce8ea9efa747e6`.
The private manifest SHA-256 and empty ledger SHA-256 are in
[manifest.json](manifest.json). A protected no-overwrite copy of that initial
state remains under ignored `data/raw/nyc_dof/manual-review-v1/init-snapshot-20260929T032135Z/`
so the initialization bytes remain hash-verifiable after later reviews append
to the active ledger. The summary command was replayed on the active ledger
at initialization; the snapshot paths are outside its permitted input contract.
The ledger ID stays private. Run
`& 'runs/u0-nyc-source-review-init-20260929T032135Z/verify_artifacts.ps1'`
from the project root to verify hashes and the zero-review state.

The first direct-script CLI invocation failed before any private write because
its package import needs module invocation. A second `-m` invocation using
relative paths created only the protected empty directory and then failed
path validation. The successful init used `python -m scripts.review_nyc_sample`
with resolved absolute paths. Both failed commands and exit codes are retained
in [test_gate.json](test_gate.json); neither created a review entry. The
18-test focused suite and 504-test repository suite passed before init; Ruff,
dependency integrity and scoped audit passed in the shared code gate.

## Gate and next action

This establishes a crash-safe private place to record reviews, not a completed
manual audit, validated sale, as-of feature or use right. The 200 rows still
need actual source and instrument comparisons. Preserve unknowns and keep
addresses, prices, IDs and notes in ignored private storage. U0/G-US remain
pending. For subsequent commands, use module invocation with resolved paths;
fix the direct-script and relative-path CLI ergonomics under tests before
recommending them. The separate borough-export v1 access failure is recorded
at [its failed run](../u0-nyc-official-export-v1-failed-20260929T031155Z/report.md).
