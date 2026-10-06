# ADR 0105: Dependency-free King XGBoost inference

## Status

Accepted for the pinned King research bundle. G-US remains **PENDING**.

## Context

Loading NumPy and XGBoost for each command dominated prediction latency even
though the frozen checkpoint is a bounded numeric `gbtree` JSON model. The
model, training procedure and target remain unchanged.

## Decision

Serve protocol `king_log_absolute_error_serving_refit_v1` with inference
runtime `stdlib_xgboost_json_v1`. The evaluator accepts only scalar numeric
`gbtree` regression models, validates the complete tree graph and array
structure, rejects duplicate keys and non-finite JSON constants, and performs
tree accumulation with the same float32 rounding used by XGBoost 3.2.0.

Keep ADR 0103's exact Python, platform, machine, NumPy and XGBoost identity
gate. Read package versions through distribution metadata so the gate does not
import either scientific library on the serving path. Return the inference
runtime identity with every prediction. The release evidence binds the
evaluator to its implementation commit and the unchanged checkpoint SHA-256.

Before promotion, run `scripts/verify_king_xgboost_json.py` in the pinned
scientific environment against checkpoint
`de9a7e8b1b6261a689070af200e4c4d1eb51a4fb5d77d8977341875bbf7d7357`.
The verifier compares 1,000 seeded rows plus the predecessor, exact value and
successor of every checkpoint split threshold. Any bitwise float32 mismatch
blocks use of the evaluator.

## Rollback

If model validation, runtime validation, or differential verification fails,
use the parent release at commit `2ac6229e07366fab356487b190da3994f2acae6c`,
which loads the same hash-pinned checkpoint through XGBoost 3.2.0. Do not
change the checkpoint or tolerance to make a failed comparison pass.

## Evidence boundary

This changes local inference cost only. It does not add final-test evidence,
historical publication timestamps, a certified 90-day origin, source rights,
or current market accuracy. The predictor remains a historical 2015 research
example.
