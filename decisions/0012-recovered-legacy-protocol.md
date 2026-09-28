# ADR 0012: Recovered legacy Ames protocol and replay boundary

- Date: 2026-09-28
- Owner: Arnaud
- Status: adopted for U0 audit; replay comparison completed with historical XGBoost mismatch
- Affected protocols: `ames_legacy_fivefold_v1` (retrospective), `ames_engineering_v1`; no change to `us_local_date_90d_v1` or G-US

## Evidence

The owner's private legacy repository became accessible at commit `60580b6`. Its original `holdout_ids.csv` has 292 unique zero-based row indices that exactly match the saved seed-42 80/20 split order. Both saved score files and the Day 8 summary are development aggregates. No original `ames.csv`, row-level predictions, checkpoint, `feature_catalog.csv` or run manifest exists in that commit. The actual `run_experiment.py` uses one shuffled five-fold CV; the 3 × 5-fold description in the supplied v2 document is not the executable legacy protocol.

## Alternatives

1. Execute `run_experiment.py` unchanged. It calls `make_split(X, y)` and constructs `y_hold`, unnecessarily bringing reserved labels into the process.
2. Reconstruct a new holdout and call it original. This would discard the recovered membership and misstate provenance.
3. Replay on the original development row order with a guard that excludes the 292 frozen holdout ARFF rows before target parsing, preserving the original model and fold rules.

## Choice

Use option 3 in a separate Python 3.11 environment approximating the repository's `uv.lock` pins. Compare saved aggregate and per-fold development metrics with repeated local runs. Record any data conversion or environment mismatch rather than forcing equality. The original holdout's exposure history is unknown, so every historical score remains retrospective. Future G-US certification requires a different untouched cohort.

## Observed outcome

The final v9 guarded replay and comparison are in `runs/u0-legacy-replay-20260928T145000Z/`. All five Dummy folds match the archived metrics exactly, while XGBoost differs: archived mean MAE $15,624.4750; replay mean MAE $15,499.7416; largest absolute fold MAE difference $653.3657. Corrected-parser repeats had identical development predictions. The historical XGBoost result is **not reproduced**. Missing original `ames.csv` and historical installed versions remain plausible but unproven causes. No holdout score was computed.

The legacy replay may reproduce its historical use of raw `Id` and clipped RMSLE for comparison only. Neither behaviour is admitted to the current modelling or metric policy.
