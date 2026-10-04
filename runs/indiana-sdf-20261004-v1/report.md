# Indiana 2024-to-2025 retrospective prediction checkpoint

Date: 2026-10-04. Protocol:
`indiana_sdf_2024_2025_retrospective_research_v1`. Research checkpoint
**verified**; U0 and G-US **PENDING**. This is not a present-day valuation
release or a certified 90-day pre-sale evaluation.

## Result

The fixed run trained on **65,490** eligible 2024 sale disclosures and scored
**71,054** eligible 2025 disclosures. The source was pinned before scoring in
[ADR 0090](../../decisions/0090-indiana-prediction-first-research-benchmark.md).
One economic transfer had to have one disclosure row and one parcel row;
multiple forms or parcels were excluded before fitting. The price and acreage
fields were decoded from the archive's integer fixed-point format. Only county,
property ZIP and acreage entered either model.

| Saved-prediction metric | County/ZIP median | Fixed XGBoost |
| --- | ---: | ---: |
| Median absolute percentage error | **28.68%** | 30.79% |
| Within 10% of sale price | **19.40%** | 15.44% |
| P90 absolute percentage error | 114.67% | 91.49% |
| Median signed percentage error | -3.74% | -15.65% |
| Successful predictions | 71,054 / 71,054 | 71,054 / 71,054 |

The tree improved the P90 tail but worsened typical error, within-10%
accuracy and bias. **It is not promoted.** The median remains the simple
research reference. All numbers come from the public aggregate
[summary](summary.json), which was replayed against the private row-level
predictions. Parsing, training, prediction, scoring and artifact writing took
**24.46 seconds total** on this workstation; separate fit latency was not
measured.

## Source quality and sensitivity

The eligibility rule retained every positive amount satisfying the registered
structural and transfer flags. It did not remove observations by residual or
price. The included training cohort contains 537 prices below $10,000 and
three above $10 million, with a maximum of $244,000,110,000. The 2025 cohort
contains 482 below $10,000 and six above $10 million, with a maximum of
$1,050,000,000. These are source-quality alerts, not adjudicated errors.
The full inclusion funnel and acreage alerts are in [summary.json](summary.json).

A **post-hoc diagnostic only** recomputed scores on the 70,566 rows priced
between $10,000 and $10 million, the thresholds already used for the recorded
quality flags. It excluded 488 rows and did not alter the primary cohort or
model selection. XGBoost still had 30.57% MdAPE versus 28.49% for the median;
see [sensitivity.json](sensitivity.json). The very large full-cohort mean
percentage errors are influenced by low positive consideration amounts.
At least 200 stratified source records and the extreme transactions need
manual review before a factual accuracy claim.

## Evidence and checks

- Frozen training code commit:
  `a7b7d58513ca78ac80c8cdb2f443f2a22463f7b9`.
- [Summary](summary.json) preserves source, split, feature-policy,
  configuration, environment-lock and model hashes, row counts, scorecards
  and runtime. The [private artifact manifest](private_artifact_manifest.json)
  binds the ignored predictions and checkpoint; four artifact hashes and both
  scorecards replayed exactly.
- Seven Indiana fixtures passed. The existing project suite passed 1,320 tests
  in 217.609 seconds with 92% package coverage. Ruff and the pinned
  dependency audit passed. [test_gate.json](test_gate.json) records commands.
- The first attempted full-suite run used the historical Ames model environment
  and failed because its `tzdata` 2026.3 conflicts with the project's frozen
  date policy (2026.4). The project suite was rerun successfully in its own
  environment; the Indiana tests and benchmark used the historical ML
  environment. This environment mismatch was not a model test failure.

## Limits and next action

The official [STATS Indiana files](https://www.stats.indiana.edu/topic/sdf.asp)
are offered for research, but individual publication times, historical
attribute vintages and commercial reuse rights are unresolved. Its
[source notes](https://www.stats.indiana.edu/about/sdf.asp) say prior-year
records can be revised. The archive's sale date cannot be treated as a
90-day pre-sale origin. The current three-field model omits reliable living
area, age and condition, and its weak score confirms this information set is
not sufficient for a useful current-home estimate.

Keep the existing [King historical research predictor](../king-serving-20261004-v1/report.md)
as the runnable local example. Next, audit Indiana sale/parcel identity and
extreme amounts on at least 200 stratified records; qualify one historically
dated source of living area, age and condition before another real-market
model comparison. Any improvement on this consumed 2025 cohort is development
evidence and needs a new untouched future period for acceptance.

Reproduce the fixed benchmark after obtaining and hash-checking both official
archives named in the [source card](../../data/source_cards/indiana_sdf_2024_2025.yaml),
using a **new** private output directory:

```powershell
$env:PYTHONPATH = (Resolve-Path -LiteralPath 'src').Path
& 'data/raw/legacy-replay/.venv/Scripts/python.exe' -m scripts.run_indiana_historical_benchmark --source-2024 data/raw/indiana_sdf/SDF_2024.zip --source-2025 data/raw/indiana_sdf/SDF_2025.zip --output data/raw/indiana_sdf/benchmarks/my-indiana-replay
```
