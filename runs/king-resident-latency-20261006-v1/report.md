# King resident prediction latency, 6 October 2026

Status: **resident predictions fast; cold startup remains variable; historical research only; G-US PENDING**.
Requirements: US21, US22, US24.

## Result

The hash-pinned absolute-error bundle was loaded once, then the synthetic example request was predicted 100 times through the same `LoadedPredictor` used by the local form. Every response was exactly **$553,846.9739548098**.

On this run, bundle verification and cold model loading took **19.96 seconds**. Once resident, prediction latency was **0.99 ms p50**, **1.27 ms p95** and **8.64 ms maximum** across 100 requests. All 100 amounts were identical.

## Decision

Keep one verified model resident for the lifetime of the local form. Do not reload the checkpoint per click or retrain for a request. A proposed shortcut to the runtime identity probe was measured and discarded because cold NumPy/XGBoost loading, with variable Windows file scanning, dominates startup.

The user can obtain predictions immediately after the one-time loading state clears by double-clicking `Launch-KingResearchForm.cmd`. This evidence does not turn the 2015 research model into a current valuation or satisfy the two-second cold-start target.

## Evidence boundary

The request is synthetic and the saved model remains a historical King County research fixture. The result proves local response behavior only. It does not prove current-market accuracy, calibrated intervals, source rights, 90-day origin correctness or G-US acceptance.