# King dependency-free inference, 6 October 2026

Status: **PASS for local inference; historical research only; G-US PENDING**.

## Result

The pinned 84-feature, 250-tree King XGBoost checkpoint now runs through the
strict `stdlib_xgboost_json_v1` evaluator. Five complete CLI processes returned
the same example estimate, **$553,846.9739548098**, with cold elapsed times of
1.64, 1.77, 1.26, 1.74 and 1.18 seconds. Median cold time was **1.64 seconds**
and the maximum was **1.77 seconds**, below the proposed two-second cached
tabular target on all five measured processes.

The previous measured cold load was 19.96 seconds. This change removes heavy
NumPy and XGBoost imports from prediction while retaining lightweight checks
of their pinned installed versions.

## Exactness gate

The implementation commit is `9fee3ea`. The verifier internally freezes the
checkpoint SHA-256, 84-feature contract, XGBoost 3.2.0, NumPy 2.4.6, Python,
platform and machine. It compared the stdlib evaluator with native XGBoost on
1,000 seeded rows and three adjacent float32 values at every one of the 10,095
internal tree nodes. Each targeted row was proven to reach its intended node.
All **31,285 predictions matched bit for bit**.

## Verification

- 61 tests passed, one optional integration was skipped, and 82 subtests passed.
- Focused branch coverage was 81%.
- Ruff passed.
- Code, Python, security and ML reviews approved the change.
- Rollback is the native XGBoost loader at commit `2ac6229`.

## Evidence boundary

This improves startup time for an existing model. It does not improve or
re-estimate predictive accuracy. The model remains a retrospective 2015 King
County research example without certified source availability, commercial-use
clearance, calibrated intervals or G-US evidence.
