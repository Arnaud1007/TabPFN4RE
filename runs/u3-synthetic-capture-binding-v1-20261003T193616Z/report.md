# Synthetic calendar capture byte binding

Run ID: `u3-synthetic-capture-binding-v1-20261003T193616Z`  
Code commit: `999d3b73c27e548e71847766c641c4ecfc759ad5`  
Requirements addressed: US03, US06, US08, US11, US14, US23, US24  
Status: **verified synthetic engineering; U0, U3 and G-US PENDING**

## Objective and result

The earlier synthetic OFF median accepted a caller-declared source digest.
This experiment adds a training-only JSONL capture. The new fit path hashes
the same bounded bytes it parses into training examples, checks the frozen
calendar schedule, and applies the existing maturity and leakage guards. The
retained capture can be replayed against the complete saved model record using
`verify_artifacts.py`. [ADR 0084](../../decisions/0084-synthetic-calendar-capture-byte-binding.md)
records the design and limits.

The five artificial rows are all training rows; reserved calibration and test
IDs have no prices in the capture. A file edit, extra row, schema change,
wrong publication date or next-midnight observation fails the fit or replay.
The old caller-declared fit remains explicitly distinguishable. The
`source_binding_kind` marker is descriptive; the replay check, not the marker
alone, supplies this run's byte-binding evidence.

## Executed checks

| Check | Observed result | Evidence |
| --- | --- | --- |
| Exact retained capture and full model replay | Exit 0, PASS | [replay log](replay.log), [replay record](synthetic_replay.json) |
| Tampered reserved IDs, median summary and replay status | All three rejected | [tamper log](tamper.log) |
| Full Python 3.11 suite, with verified local Ames ARFF | Exit 0; **1,262 tests, zero skips**; 210.274 s test time, 211.362 s wall time | [test gate](test_gate.json), [full log](full_suite.log), [suite command](full_suite_gate.json) |
| Branch-aware coverage, two touched production modules | 83% capture module, 80% median module, 81% combined | [coverage](coverage.log) |
| Ruff check and format check | Both exit 0 | [check](ruff_check.log), [format](ruff_format.log) |
| Package dependency and vulnerability checks | `pip check` and `pip-audit --skip-editable` both exit 0 | [dependency](pip_check.log), [audit](pip_audit.log) |
| Code, Python and security review | Final evidence issues corrected before publication | [review record](review_evidence.md) |

The suite command was `.venv/Scripts/python.exe -m coverage run --branch
--source=tabpfn4realestate -m unittest discover -s tests -p test_*.py -q`,
with `AMES_ARFF_PATH` set to the existing ARFF whose SHA-256 is
`10db9fe72ed693212a222e39981133ec1b3ee5090d7f2caf2461190a4ad51279`.
The gate stores each exit code, duration, log hash, source digest, split hash,
feature policy manifest hash, environment lock hash and checkpoint identity.
The test log replaces the local home path with `<USER_HOME>`; it contains no
private source rows.

The seven RED/GREEN commits from `6f2bdef` through `999d3b7` preserve the
test-first history. A first format check on the run verifier failed and was
corrected. Review then found unchecked duplicate summary fields and an
unbounded read in the run verifier, plus a local account path in the saved
suite log. All three were corrected, followed by the five recorded checks.

## Limits and next action

This run uses generated synthetic values. **No real-market label was trained,
no sale-price accuracy was measured, and no final evaluation was opened.** A
generated capture cannot establish source ownership, permissible use,
transaction semantics or first public availability for any US county. The
verified Ames ARFF is only an engineering fixture in the full suite.

Continue [U0 source qualification](../../next_action.md): acquire an
authoritative sale source through an authorised route, resolve rights and
economic-transfer semantics, establish first publication and historical
attribute vintages, then bind manually audited canonical rows to an
independently hashed raw source. Do not begin real training until those
dependencies pass.
