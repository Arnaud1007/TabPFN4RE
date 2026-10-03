# Synthetic property-history selection: verification

Run ID: `u1-synthetic-property-history-v1-20261003T164855Z`
Code commit: `b04b12cbe82f7650628b7bb7970dbee5b8f01659`
Requirements: US06, US08, US10, US23, US24
Status: **verified engineering fixture; U0, U1 and G-US PENDING**

## Change and observed behavior

OFF assembly now resolves a history of property versions at the valuation
origin. Comparable retrieval resolves each neighbor's physical version at its
sale date while restricting information to what was known by the valuation
origin and source snapshot. Later publication of a pre-sale observation is
allowed; an observation after the sale is excluded. Unpublished end dates are
redacted from selected properties. Equivalent source copies have stable
snapshot hashes and returned end instants. [ADR 0079](../../decisions/0079-synthetic-property-history-selection.md)
records the timing decision.

New RED tests reproduced five defects before fixes: the selector lacked a
later information cutoff, order-equivalent copies changed snapshot hashes,
late-published corrections chose an outdated comparable area, late-published
expiry admitted an invalid comparable, and an unlisted visible candidate
source was ignored when no sale matched. Review found a post-sale observation
backdating path and timezone-dependent returned end; their tests also failed
before the fixes. The final checks below evaluate the finished code.

## Actual checks

| Check | Result | Evidence |
| --- | --- | --- |
| Full Python 3.11 suite with verified local OpenML ARFF | Exit 0; **1,224 tests, zero skips**, 222.276 s test time | [gate](test_gate.json), [log](full_suite_verified.log) |
| Branch-aware coverage of touched modules | Assembler 91%, comparables 90%, **90% combined** | [coverage](coverage_verified.log) |
| Ruff check and format check on five touched Python files | Exit 0 for both | [lint](ruff_check.log), [format](ruff_format.log) |
| Project `.venv` dependency audit | Exit 0; no known vulnerabilities in audited packages; editable local package skipped | [audit](pip_audit.log) |
| Code, Python and security read-only reviews | No remaining critical/high issue after fixes | Reviewer summaries in this run's final handoff |

The first full suite completed before the last two test and code corrections
and is retained as [preliminary evidence](full_suite_final.log), not the
finished-code gate. The initial [earlier suite](full_suite.log) is also
retained. Some negative-path tests intentionally print diagnostic failures to
the log while the unittest suite exits zero.

The finished suite command was `coverage run --branch
--source=tabpfn4realestate.features.asof,tabpfn4realestate.features.comparables
-m unittest discover -s tests -q` under project Python 3.11, with
`AMES_ARFF_PATH` set to the local hash-verified OpenML ARFF. Ruff check,
Ruff format check and `pip_audit --local --progress-spinner off` each exited
zero. The [manifest](manifest.json) records exact file, environment,
configuration and input hashes; no real-market split or checkpoint exists.

## Limits and next action

These fixtures prove behavior under declared synthetic histories. No real
source has yet demonstrated complete property-version vintages, trustworthy
effective dates or first-publication times. The Cook, NYC and other source
audits, rights questions and legacy U0 recovery remain open. There are zero
certified modern US sale labels and no trained real-market champion,
calibration cohort or G-US final test. The run's split hash and checkpoint
identity are null. Continue the source and legacy work in
[next_action.md](../../next_action.md); do not start international models.
