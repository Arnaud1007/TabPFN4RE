# U1 foundation increment report

Run ID: `u1-foundation-20260928T091610Z`
Code commit: `c85abb2` (full hash in `test_gate.json`)
Requirements touched: US03, US04, US06, US07, US08, US09, US22, US23, US24
Status: foundation **verified**; milestone U1 **PENDING**; G-US **PENDING**

## Objective and completed changes

Establish a synthetic US OFF data contract before any real-source training. Added immutable canonical records, explicit missing and eligibility states, source-scoped raw IDs, economic-transfer deduplication, and an as-of feature snapshot with lineage and content hash. The assembler enforces valuation and source cutoffs, blocks target-derived/unregistered fields, excludes listing events in OFF, and excludes the subject economic transfer across feeds. ON explicitly reports unavailable.

## Commands and observed results

The actual commands, exit codes, durations, code commit, environment and SHA-256 artifact hashes are in `test_gate.json`. Its outputs show 67 Python 3.11 tests passed with zero skips and 90% statement coverage. Ruff lint and format checks passed. The source-bound Ames test used the verified local OpenML 42165 ARFF; the U1 tests themselves use synthetic fixtures. Independent code and Python reviewers found no remaining high or medium issue after the final duplicate-eligibility fix.

The first gate attempt, `u1-foundation-20260928T091518Z`, failed its lint step because Ruff was absent from the project `.venv`; the tests and coverage steps passed. That failed run remains saved. The successful gate used the installed `python -m ruff` for lint and format without changing the Python 3.11 test environment.

## Remaining work

This increment does not satisfy all of U1. T05 reserved-ID fit guards, T06 training-only categorical encoding, T07 unseen-property split validation and T08 shared full metric cases remain to be implemented and verified. No real US source adapter, date-only availability rule, comprehensive identity resolver, model bundle or application is claimed. U0 legacy recovery still needs the missing repository/artifacts. The exact next task and external dependencies are in `next_action.md`.
