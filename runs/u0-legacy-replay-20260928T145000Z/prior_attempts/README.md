# Prior replay attempts

These are redacted aggregate-score copies of local development-only runs. The original run directories are under Git-ignored `data/raw/legacy-replay/`. Row-level development predictions, which contain sale labels, are deliberately not copied into Git. A source manifest in this directory describes its **complete local run**, not completeness of this redacted copy.

`dev-only-20260928` used an ARFF string parsing rule that stripped literal apostrophes; its XGBoost comparison was rejected. `dev-only-20260928-v4` used the corrected string rule, but exact historical XGBoost scores remained unreproduced. The final comparison uses a later fully guarded run.
