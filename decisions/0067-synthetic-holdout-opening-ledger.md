# ADR 0067: One-use synthetic holdout opening ledger

Date: 2026-10-03
Owner: project implementation
Status: synthetic engineering contract; no real certification test opened
Affected requirements: US11, US22, US23 T12
Affected protocol: `us_synthetic_holdout_v1`; the legacy Ames holdout and any
future real-market split remain untouched.

## Context and alternatives

The temporal splitter freezes outcome-free membership and rejects maturity
metadata for reserved rows. It did not yet stop a test process from reopening
reserved labels after a crash. A run-ID-only marker was rejected because a new
run ID or model would permit another opening of the same sales. A file marker
was considered, but an SQLite transaction gives one atomic record containing
the prediction snapshot and opening intent while enforcing unique row IDs
across overlapping cohorts.

## Decision

The [synthetic evaluator](../src/tabpfn4realestate/evaluation/holdout_ledger.py)
accepts a frozen split/source/model identity, exact reserved row IDs and
outcome-free estimates. It snapshots the estimates into a tuple and commits
their serialized values, digest and `opening_intent` to an on-disk SQLite
ledger with `synchronous=FULL` before calling the label loader. The registry
rejects a repeated cohort or any overlap with previously reserved row IDs.
An error after opening leaves the cohort consumed with no valid scorecard.
Completed scores can be replayed through a read-only connection after checking
the saved identity and prediction/result digests. Relative and in-memory
ledger paths are rejected.

The current interface scores one frozen model bundle. A later certification
runner must freeze all predeclared champion and baseline outputs before its
single label opening and bind the evaluator to one controlled ledger location.
Hashes stored beside the payload detect accidental corruption; they do not
protect against an operator who can rewrite both, and this code does not
establish external retention or signature controls. It does not prove that
upstream source labels, timestamps, rights or splits are valid.

## Verification and next step

The [synthetic T12 fixture](../tests/test_holdout_ledger.py) covers crash
after intent, loader failure, immutable prediction scoring, overlapping rows,
concurrent opening, read-only replay, tamper detection and the in-memory path
bypass. Actual commands and outcomes are recorded in the
[run report](../runs/u1-synthetic-holdout-ledger-20261003T111210Z/report.md).
Keep U0, U3, U6 and G-US pending. Integrate this contract only after a real
source, frozen final cohort, prediction bundle and controlled evaluator path
have passed their own gates.
