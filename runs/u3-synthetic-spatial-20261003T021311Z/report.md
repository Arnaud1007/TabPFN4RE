# U3 synthetic geographic holdout checkpoint

Run ID: `u3-synthetic-spatial-20261003T021311Z`

## Objective and changes

Add a deterministic, leakage-resistant **synthetic** geographic holdout to the
existing US temporal evaluation harness. [ADR 0054](../../decisions/0054-synthetic-spatial-grid-holdout.md)
defines the frozen behavior. The new builder requires one projected location per
origin, calls the validated temporal fold internally, selects heldout grid
cells, purges matured training rows inside heldout cells or their buffer, and
purges repeated properties. It records excluded rows and hashes all split
inputs. This satisfies an engineering subtask of US11, US22, US23 and US24.

## Observed verification

See [test_gate.json](test_gate.json) for commands, exit codes and output.
Tests were written before implementation; the initial import failed as
expected. After implementation and review fixes, all **11 focused tests**
passed and the new module had **97% branch-aware coverage**. The final full
suite passed **1,031 tests** in **169.734 seconds**, with no failures or skips.
Ruff lint and format, `pip check` and the installed-distribution dependency
audit passed. Code, Python and security reviewers confirmed their findings
were fixed before commit.

The first full-suite attempt failed after 1,028 tests because the C: drive
reached zero free bytes while an NYC audit fixture wrote a temporary file.
Purging 61.8 MB of disposable pip cache restored working space; the complete
rerun passed. No source archive or raw data was deleted. The failed attempt is
retained in the gate record.

The deterministic fixture has parent temporal hash
`383bf9b2e27395ee6b3e48c69963d0cd59399e693ade37e441c90e8d5d8a14b4`
and spatial split hash
`d87ffa6a72b8395e2aa57f0f502d400aea7f6a6b55bf4ef6f308b5fff4907154`.
It begins with three matured training rows and two temporal validation rows;
one training and one validation row remain after spatial selection and purging.
These are fixture counts, not US accuracy or coverage results.

## Gate and next action

This checkpoint is **verified synthetic engineering**. U0, U3 and G-US remain
**PENDING**. No Cook or NYC sale label has been certified for a real 90-day
origin benchmark. Real geography needs audited source coordinates and CRS,
development-only block/buffer selection, historical source availability and a
frozen eligible market scope. Continue the Cook/NYC U0 source review. An
independent next harness task is US13 paired block-bootstrap uncertainty on
saved synthetic predictions. Resume this checkpoint with:

```powershell
$env:AMES_ARFF_PATH = (Resolve-Path 'data/raw/openml/house_prices-42165.arff').Path
.venv\Scripts\python.exe -m unittest discover -s tests -q
.venv\Scripts\python.exe -m coverage run --branch --source=tabpfn4realestate.evaluation.spatial_splits -m unittest tests.test_spatial_splits -q
.venv\Scripts\python.exe -m coverage report -m
```
