# U3/US13 synthetic paired block-bootstrap checkpoint

Run ID: `u3-synthetic-paired-20261003T023000Z`

## Objective and changes

The [decision](../../decisions/0055-synthetic-paired-block-bootstrap.md)
defines a synthetic paired comparison for US13. It joins the baseline and
challenger by exact economic-transfer row IDs, rejects unmatched or failed
predictions, groups geographic/time cells connected by repeat properties,
and resamples those components within each market. It reports
challenger-minus-baseline differences, including pooled and equal-market
metrics, and returns `INCONCLUSIVE` without intervals when independent units
are too few. It does not select a champion or certify a real US cohort.

## Observed verification

[The gate record](test_gate.json) contains exact commands and exit codes.
The tests failed first because the module did not exist. After implementation
and review fixes, **12 focused tests passed** at **95% branch-aware coverage**.
The full suite passed **1,043 tests** in **173.710 seconds** with no failures
or skips. Ruff lint and format, `pip check`, and the installed-distribution
dependency audit passed. The latter did not audit this local package on PyPI.

The review uncovered a transitive-property component-ordering defect that
changed seeded draws when input rows were reordered; canonical union and a
permutation test fixed it. A subsequent work-budget check incorrectly rejected
a large but inconclusive cohort; it now runs only when resampling will occur.
The cost-probe writer was changed to publish a complete result atomically.
These failed or rejected intermediate states were not used as valid scores.

The [atomic cost probe](benchmark_result_atomic.json) measured **36.535
seconds** for 10,000 generated rows, two markets, 10,000 independent blocks
and 100 draws on this host. A linear 5,000-draw extrapolation is about 30
minutes; that configuration was **not** run at this scale. Earlier local
probe files in this directory are retained as preliminary engineering
measurements. No training time, model accuracy, peak RAM or VRAM is inferred
from this probe. The published comparison hash is
`9af3b80a7a7b73abe96ceb67b4847111e986d381936d26113ea34bee698a1b5b`.

## Gate and next action

This checkpoint is **verified synthetic engineering**; US13 overall remains
**planned**, and U0, U3 and G-US remain **PENDING**. The probe's split and
block-plan hashes are explicit synthetic sentinels, not proof that a frozen
real cohort or development-selected blocks exist. US13 still requires
source-backed paired predictions, real temporal/geographic block design,
sensitivity to block choices, four-window consistency and a frozen champion
decision. Continue the Cook/NYC source audit; do not start international
implementation.

From the project root, reproduce the focused tests with:

```powershell
.venv\Scripts\python.exe -m coverage run --branch --source=tabpfn4realestate.evaluation.paired_bootstrap -m unittest tests.test_paired_bootstrap -q
.venv\Scripts\python.exe -m coverage report -m
```

The cost probe is create-only. Use a new output filename for a replay and
compare its `comparison_hash` to the frozen atomic result:

```powershell
.venv\Scripts\python.exe runs/u3-synthetic-paired-20261003T023000Z/benchmark_replay.py --rows 10000 --draws 100 --output runs/u3-synthetic-paired-20261003T023000Z/benchmark_result_replay.json
```
