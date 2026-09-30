# One-home NYC index lookup: private source evidence

Run ID: `u0-nyc-source-lookup-live-v1-20260930T193830Z`  
Status: **verified source-lookup effort only; U0 and G-US pending**  
Requirements: US04, US05, US07, US08, US22, US23, US24

## Objective and observed result

The previously [frozen plan](plan.md) was pushed at `4cb52bd` before using
the reviewed collector at `9aa6f5d`. It selected one untouched ACRIS-eligible
row from the protected 200-entry NYC review sample. The capture command
completed, its private evidence was saved, and offline replay recomputed the
same evidence state without making a network request. The protected evidence
manifest hashes the private run files, frozen ledger snapshot, state and command
logs; its SHA-256 is
`c9fdcfd9d63c6bc17374667a40174f8b65da60a9e1d640d388c0a20766bb328d`.
The live review ledger still matches the frozen hash. No global capture lock
was left behind.

The [public aggregate](aggregate.json) is a fixed `private_only_v1`
projection. The selected property, query count, route state, document leads
and response bytes remain in the Git-ignored, ACL-protected local evidence.
**No review form was appended and no sale label was certified.** The ledger
remains at 10 completed rubrics of 200 selected records; 190 remain
unreviewed. Route completion, if any, would not establish a matched economic
transfer or source publication time.

## Checks and limitations

Capture and offline replay exited zero under the pinned Python 3.11
environment. A separate local check verified directory ACLs, the unchanged
review ledger, bounded request count, frozen file hashes and fixed CLI
projection. [Test gate](test_gate.json) records the commands and exits; exact
one-home durations are retained in protected evidence because request pacing
makes timing informative about the private request count. The unchanged
collector and its imported project helpers are hash-pinned for replay. The
collector already passed 29 focused tests at 82%
branch-aware coverage, and the full suite passed 815 tests with one optional
Ames source integration skip. This data-only run did not retrain or select a
model.

The index attempt does not verify a deed image, transaction scope, actual
closing date, first record availability or dataset-specific commercial reuse
rights. Under ADR 0027, those rubric dimensions remain `unknown` without
independent evidence. Staten Island requires a separate Richmond adapter;
Manhattan's workbook preamble is a separate structural issue. U0, G-US,
country expansion and national claims remain blocked.

## Next action

Inspect the protected index leads against dated source instruments, then
create an attested rubric only for facts actually verified. Seek the pending
source clarification and rights response. Keep the reviewed sample order and
all failures; do not turn an index candidate into an eligible sale label.
