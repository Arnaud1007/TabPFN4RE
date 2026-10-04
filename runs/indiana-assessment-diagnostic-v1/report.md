# Indiana disclosure-snapshot assessment diagnostic

Date: 2026-10-04. Protocol:
`indiana_sdf_snapshot_assessment_retrospective_diagnostic_v1`.
Status: **verified development diagnostic; U0 and G-US pending**.
Requirements: US07, US08, US13, US17, US22 and US24 as partial research evidence.

## Result in 36 seconds

Both XGBoost models trained on the same **65,490** eligible 2024 economic
sales, with identical 180-tree parameters. They predicted the same **71,054**
eligible 2025 sales. The second model added whole-dollar assessed land and
improvement values plus a county-scoped neighborhood code found in the
retrieved sale-disclosure snapshots. Category encoding fitted on 2024 only.
The 2025 cohort was already consumed development data in the earlier run.

| Saved-prediction metric | County/ZIP median | Three-input XGBoost | Assessment-snapshot XGBoost |
| --- | ---: | ---: | ---: |
| Median absolute percentage error | 28.68% | 30.79% | **15.19%** |
| Within 10% of sale price | 19.40% | 15.44% | **36.57%** |
| P90 absolute percentage error | 114.67% | 91.49% | **62.63%** |
| Median signed percentage error | -3.74% | -15.65% | **-2.10%** |
| Successful estimates | 71,054 | 71,054 | 71,054 |

The added fields reduced MdAPE by **47.03% relative to the county/ZIP
median** on these development rows. Both models' fit calls together took
2.07 seconds; parsing, encoding, scoring and artifact writing brought the
complete run to **36.32 seconds**. This is a useful signal-finding result,
not an accepted predictor. Even the augmented model is far from the G-US
point-error requirements and has no calibrated interval.

## Interpretation and limits

The extra values appear in later retrieved sale-disclosure archives. Their
original assessment vintage, first availability before each sale, possible
post-sale revisions and commercial reuse rights have not been established.
They may contain information unavailable at a 90-day pre-sale prediction
origin. **Do not serve this model as a current-home valuation or promote it
from this result.** Assessed values were predictors, never replacement labels.
The 2025 data cannot now be described as an untouched certification cohort.

All positive eligible prices remained in the primary score, including the
previously flagged extreme amounts. The 200-record manual source audit remains
pending. The aggregate score does not establish that gains hold in every
county, price band or property subtype. [ADR 0091](../../decisions/0091-indiana-assessment-snapshot-diagnostic.md)
records the fixed experiment and the separate Gateway source check: the
downloadable Marion PARCEL file matched most sale parcel IDs but did **not**
contain building size, year built or condition. No Gateway field entered this
model.

## Reproducibility evidence

The clean code commit before execution was
`0bcb55da77e5c8ffbedfaa05a1acd8399e825efe`. The [summary](summary.json)
records source, environment-lock, split, feature-policy, configuration and
both model hashes. The old and new runs have **identical training and
validation membership hashes**. The [private artifact manifest](private_artifact_manifest.json)
binds six ignored private files. An independent replay checked all six hashes
and recomputed all three scorecards exactly from the saved prediction CSV.
No row-level source or prediction file is committed.

The [test gate](test_gate.json) records 13 focused tests, the 1,320-test
project suite at 92% package coverage, Ruff, dependency audit, code/Python/
security/MLE review, and the observed run and replay. The full-suite command
passed with zero skips; test-generated failure messages in its private log
were expected negative fixtures.

From a clean clone with authorised copies of the pinned private ZIPs and the
locked Python environment, run with a **new** private output directory:

```powershell
$env:PYTHONPATH = (Resolve-Path -LiteralPath 'src').Path
& 'data/raw/legacy-replay/.venv/Scripts/python.exe' -m scripts.indiana_assessment_diagnostic --source-2024 data/raw/indiana_sdf/SDF_2024.zip --source-2025 data/raw/indiana_sdf/SDF_2025.zip --output data/raw/indiana_sdf/benchmarks/my-new-assessment-run
```

## Next action

Qualify historical assessment snapshots and first-publication dates before
any 90-day OFF experiment uses these signals. Audit at least 200 stratified
Indiana sales, especially extreme consideration and parcel/transfer identity.
Seek dated building-size, age and condition data; Gateway's public PARCEL
download alone does not supply them. A later pre-sale model needs a new
untouched future cohort. Keep the saved King 2015 research predictor as the
current runnable local example.
