# Bounded NYC source lookup runner: code verification

Run ID: `u0-nyc-source-lookup-code-20260930T193000Z`  
Protocol: `nyc-source-lookup-v1`  
Status: **implementation verified only; U0 and G-US pending**  
Requirements: US04, US05, US07, US08, US22, US23, US24

## Objective and changes

Added a one-home, bounded ACRIS index lookup for the remaining private NYC
200-record source-review sample under [ADR 0037](../../decisions/0037-nyc-bounded-review-lookups.md).
The runner selects the lowest-ranked untouched ACRIS sample row, freezes the
review-ledger state privately, records each request intent and response body,
and supports read-only offline replay. A global lock, create-only run directory,
strict private paths, response caps and fixed public CLI projection limit
concurrent requests and disclosure. Missing identity or sale date fails closed
before any GET. Linked multi-lot or blank-unit records remain unresolved.

This run is a **code and synthetic-fixture verification**. It made no live
sampled-property lookup, appended no review rubric and certified no sale label.
The prior protected review ledger remains **10 of 200 reviewed**, with 190
unreviewed and zero certified labels. Route completion does not prove a
matched economic transfer, actual close date, first publication or lawful
commercial reuse.

## Verification and failed attempts

The focused Python 3.11 run passed **29 tests in 6.056 seconds**, with **82%**
branch-aware coverage for the new runner. Ruff check and format checks passed.
`pip-audit` on the pinned runtime requirement reported no known
vulnerabilities. Review by code, Python and security agents found no remaining
critical or high issue after the malformed-date guard and privacy fixes.

An early full-suite run on an earlier worktree snapshot passed 812 tests but
was not the final code. A subsequent full-suite invocation mistakenly used the
system Python 3.14 and failed (815 tests, 10 failures, 69 errors, one skip),
primarily because the Ames environment lock requires Python 3.11. Both logs
are retained. The final full suite in the project Python 3.11 environment
passed **815 tests in 199.460 seconds**, with one optional Ames source
integration skip because `AMES_ARFF_PATH` was not set. The full result is
recorded in [test_gate.json](test_gate.json).
Shell redirection logs were transcoded from UTF-16LE to UTF-8 for review;
their text content was preserved.
From the project root, run
`& 'runs/u0-nyc-source-lookup-code-20260930T193000Z/verify_artifacts.ps1'`
to verify the file hashes, mandatory check exits and zero-label gate status.

## Remaining blockers and next action

The official source clarification and dataset-specific rights remain pending.
Ten completed rubrics contain no certified sale label; the 190 remaining
reviews need dated instrument and transfer evidence. Staten Island needs a
separate Richmond adapter, and the Manhattan workbook preamble is still a
separate structural issue. No NYC training, G-US acceptance or international
implementation is unlocked.

After this reviewed code is pushed, freeze a new public run plan and resource
budget, then capture **one** privately selected ACRIS row with an opaque run
ID. Replay its private evidence, preserve failures, and continue manual review
without converting index leads into labels.
