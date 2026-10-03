# Synthetic as-of validity contract: verification

Run ID: `u1-synthetic-validity-v1-20261003T160514Z`
Code commit: `21850ca6dcc02f16a34b0bde04de09ae8eff783f`
Requirements: US06, US08, US22, US23, US24
Status: **verified engineering fixture; U0, U1 and G-US PENDING**

## Change and observed behavior

The canonical `Property` and `Attribute` records now carry an optional
effective start, end and separate end-publication time. The OFF assembler
applies a known end at the exclusive boundary, ignores an end that was not
published by the source snapshot cutoff, reconciles identical source
observation copies, and rejects unresolved overlap or contradictory revisions.
The assembler and synthetic bundle input fingerprints changed. [ADR 0078](../../decisions/0078-synthetic-asof-validity-and-corrections.md)
records the decision and its limits.

The first eight synthetic tests failed because the validity fields were absent.
Review then found an expired-value fallback through an older open copy; its
new test failed before the reconciliation fix. Further RED tests exposed a
changed-value/observation fallback and a later open-copy retraction. All are
now passing or explicitly rejected. The final [manifest](manifest.json)
hashes the tested code and artifacts; the code was uncommitted when tests ran,
then committed unchanged at the hash above.

## Actual checks

| Check | Result | Evidence |
| --- | --- | --- |
| Full Python 3.11 suite, with `AMES_ARFF_PATH` set to the local verified OpenML ARFF | Exit 0; **1,201 tests, zero skips**, 210.134 s test time; 210.951 s wall time | [gate](full_gate.json), [stderr](full_stderr.log), [stdout](full_stdout.log) |
| Focused validity, foundation and bundle tests under branch-aware coverage | Exit 0; **65 tests** | [gate](focused_gate.json), [stderr](focused_stderr.log) |
| Coverage of touched production modules | Schema 87%, assembler 89%, bundle 88%; **88% combined** | [coverage report](coverage_touched.log) |
| Ruff check and format check on five touched Python files | Both exit 0 | [style gate](style_gate.json), [lint](ruff_check.log), [format](ruff_format.log) |
| Dependency audit scoped to the project `.venv` | Exit 0; no known vulnerabilities in audited packages; editable local package skipped | [audit gate](project_audit_gate.json), [output](project_pip_audit.log) |

An initial `py -3.14 -m pip_audit --local` invocation audited the unrelated
global Python 3.14 environment and **failed**. The failed [gate](audit_gate.json)
and [host audit summary](host_audit_summary.md) are retained; this result was
not converted into a project pass. Project security review confirmed that the
scoped `.venv` audit is the relevant dependency gate. Code, Python and
security reviews found no remaining high issue in this synthetic scope.

A read-only artifact verifier first failed under the project `.venv` because
PyYAML is absent there. The same hash, gate and requirement-link checks then
passed under Python 3.14, which has PyYAML installed. This verifier did not
alter data, model or test results.

## Limits and next action

The assembler still receives one selected `Property` version. A source adapter
must prove complete property-version selection, source rights, identity,
publication history and closing-date semantics. Cross-source attribute
corrections also need source-specific reconciliation before certified use.
No real-market labels, calibration cohort, checkpoint or final test were used.
The run's split hash and checkpoint identity are null for that reason.

Continue the U0 source and legacy-artifact work in [next_action.md](../../next_action.md).
The pending MyDec one-document query requires the already requested action-time
approval before entering its private identifier. Do not treat this synthetic
gate as acceptance of U1 or G-US.
