# King LightGBM in-memory diagnostic

Date: 2026-10-06  
Code commit: `65e5ea0`  
Evidence class: development diagnostic; artifact-producing run blocked by zero disk space

The committed one-configuration LightGBM runner completed all four frozen King
development fits in memory with its artifact writer replaced by a no-write
callback. It parsed zero March-May labels and scored the same 5,108 validation
sales as the XGBoost log absolute-error incumbent.

| Metric | XGBoost incumbent | LightGBM challenger |
|---|---:|---:|
| MdAPE | 8.274982% | 8.426767% |
| Within 10% | 57.341425% | 56.597494% |
| P90 APE | 26.949733% | 26.949828% |
| Median signed percentage error | -0.808070% | -0.801563% |
| RMSE | 114,454.77 | 113,951.93 |

LightGBM improved MdAPE in one of four windows and failed the frozen development
screen. XGBoost remains the development reference. Four fit calls took about
5.08 seconds; total pre-output runtime was about 7.16 seconds.

This is not an accepted experiment artifact because the no-write diagnostic did
not save row predictions, native boosters, encoder manifests or replay evidence.
The registered run must be repeated when the private output volume has space.
G-US remains `PENDING`.
