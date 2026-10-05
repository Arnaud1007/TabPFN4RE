# King/FHFA retrospective sensitivity

Run ID: `king-hpi-adjustment-20261005-v1`  
Protocol: `king_fhfa_adjustment_replay_v1`  
Gate status: **G-US PENDING**

The frozen King County XGBoost predictions were replayed without refitting. For April-May 2015 only, the saved prediction was multiplied by the current revised FHFA Seattle-Bellevue-Kent purchase-only NSA ratio `311.57 / 293.68`. March 2015 predictions remain byte-equivalent in numeric value because both the base and target are 2015Q1. All 4,752 saved rows were retained.

| Cohort | Estimate | Rows | MdAPE | Within 10% | P90 APE | Median signed error |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| overall | xgboost | 4,752 | 10.52% | 47.94% | 26.98% | -6.99% |
| overall | hpi_adjusted_xgboost | 4,752 | 9.30% | 53.24% | 26.11% | -3.76% |
| 2015Q1 | xgboost | 1,875 | 9.67% | 51.41% | 26.05% | -5.48% |
| 2015Q1 | hpi_adjusted_xgboost | 1,875 | 9.67% | 51.41% | 26.05% | -5.48% |
| 2015Q2 | xgboost | 2,877 | 10.95% | 45.67% | 27.45% | -8.17% |
| 2015Q2 | hpi_adjusted_xgboost | 2,877 | 9.07% | 54.43% | 26.15% | -2.57% |

Overall MdAPE changes from **10.52%** to **9.30%**. On the affected 2015Q2 rows it changes from **10.95%** to **9.07%**.

## Evidence boundary

This is an exploratory sensitivity calculation with revised hindsight. The full 2015Q2 index was unavailable at those sale origins, the cohort had already been consumed, and the source does not verify that every record is an eligible single-family arm's-length transfer. The result is machine-labelled `promotion_eligible=false`, `historical_asof_eligible=false`, `uses_revised_hindsight=true`, and `applicability_verified=false`. It does not validate the current form illustration, a 90-day forecast, or any release claim.

## Reproduction

```powershell
$env:PYTHONPATH = "$(Resolve-Path .);$(Resolve-Path src)"
& '.venv/Scripts/python.exe' -m scripts.run_king_hpi_adjustment
```

Inputs and output hashes are pinned in [manifest.json](manifest.json); aggregate results are in [scorecards.json](scorecards.json). Private row-level predictions and the raw FHFA snapshot remain outside Git.
