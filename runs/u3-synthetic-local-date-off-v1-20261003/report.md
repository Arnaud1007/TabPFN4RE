# Synthetic source-local date OFF bridge

Run ID: `u3-synthetic-local-date-off-v1-20261003`  
Code commit: `30f8e3cd7da25df7a32ab827adc2bfb31e13af7b`  
Requirements addressed: US03, US06, US08, US11, US14, US23, US24  
Status: **verified engineering fixture; U0, U3 and G-US PENDING**

## Objective and change

Connect a source-local closing date to a 90-calendar-date OFF feature snapshot
and guarded median fit without inventing a closing timestamp. The new path
retains a typed date-only sale label, derives a local valuation date, applies
an exclusive end-of-origin cutoff to timestamped facts, and checks training
membership against a rebuilt chronological maturity plan. The exact-UTC
engineering path remains available. [ADR 0081](../../decisions/0081-local-calendar-date-off-integration.md)
records the timing and provenance choice.

The baseline records a digest of accepted labels, source manifest descriptors
and feature snapshots, and permits prediction only from sources that appeared
in training labels or feature lineage. It rejects duplicate economic transfer
IDs and duplicate source/deed IDs. Constructor validation rejects invalid
prices and manifests. No trained model bundle or real-market prediction was
created.

## Tests and observed outputs

| Check | Observed result | Evidence |
| --- | --- | --- |
| Full Python 3.11 suite, with the hash-verified private Ames ARFF enabled | Exit 0; **1,244 tests, zero skips**, 220.095 s test time | [gate](test_gate.json), [log](full_suite.log) |
| Branch-aware coverage for the four touched production modules | Local sale 94%, as-of assembler 91%, comparables 90%, local median 82%; **89% combined** | [coverage](coverage.log) |
| Ruff check and format check on six changed Python files | Exit 0 for both | [lint](ruff_check.log), [format](ruff_format.log) |
| Installed-dependency audit | Exit 0; no known vulnerability in audited third-party packages; editable local package skipped | [audit](pip_audit.log) |
| Synthetic fit replay with reversed input order | Identical model record; five matured training rows; plan and accepted-training digests saved | [replay](synthetic_replay.json) |
| Code, Python and security reviews | No remaining critical/high finding after deed-ID, model-constructor and label-digest fixes | [review record](review_evidence.md), reviewed code commit above |

The full-suite command was `.venv/Scripts/python.exe -m coverage run --branch
--source=tabpfn4realestate -m unittest discover -s tests -p test_*.py -q`,
with `AMES_ARFF_PATH` set to the existing local OpenML ARFF. Its file SHA-256
was `10db9fe72ed693212a222e39981133ec1b3ee5090d7f2caf2461190a4ad51279`.
The exact environment and configuration hashes are in [the gate](test_gate.json)
and [manifest](manifest.json). Expected negative-path diagnostics appear in
the passing full-suite log.

Tests were written first. The initial local-path test failed to import its
assembler; the first model test failed to import its label type. Review then
found that changing a training label left the original model identity
unchanged and direct model construction could emit a negative price. The
accepted-label digest and constructor checks closed those paths. A further
RED test showed a duplicated source/deed ID crossing economic transfer IDs;
the final fit guard rejects it. Another RED test showed the local snapshot
hash omitted the assembler policy version; the final hash includes it. The
initial full suite used an unset `AMES_ARFF_PATH` and passed 1,240 tests with
one skip. The saved [pre-review log](full_suite_pre_review.log) instead has
1,242 passing tests and zero skips with that file enabled; it predates the
deed-ID and policy-hash fixes. The final suite above ran with zero skips after
all fixes.

## Evidence boundary and next action

`synthetic_replay.json` contains a placeholder source hash supplied by its
test fixture. The model compares that declaration with the schedule; it does
**not** verify raw source bytes. The five synthetic labels are not US market
sales. The current local feature assembler accepts timestamped property,
attribute and prior-sale facts; date-only feature publication needs a typed
adapter. No real source has established first publication, closing-date
semantics, source rights or a historical attribute vintage. There are zero
certified modern US sale labels. The run has no real data snapshot, saved
checkpoint, model card, calibration result or G-US score.

Continue the [U0 source and legacy audit](../../next_action.md). Before any
real-data fit, bind a trusted immutable source artifact hash to the records,
verify date-only feature availability where applicable, and rerun the local
chronological tests with source-specific fixtures. Do not open final labels or
start Part II.
