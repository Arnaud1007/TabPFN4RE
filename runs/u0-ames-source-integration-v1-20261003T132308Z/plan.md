# U0 OpenML Ames source integration — frozen local plan

Run ID: `u0-ames-source-integration-v1-20261003T132308Z`  
Protocol: `ames_source_integration_v1`  
Status at plan: planned; no test has been run under this run ID.

## Question and inputs

The previous full-suite run reported one skip because `AMES_ARFF_PATH` was not
set. The official OpenML ARFF is already present at
`data/raw/openml/house_prices-42165.arff`, Git-ignored, with 479,052 bytes and
SHA-256 `10db9fe72ed693212a222e39981133ec1b3ee5090d7f2caf2461190a4ad51279`.
The existing source card and migration audit record its OpenML identity. The
missing historical artifact is the separate legacy `ames.csv`.

Use the current committed code and the local Python 3.11 `.venv`. Set
`AMES_ARFF_PATH` to the resolved private ARFF path only for the test process.
Run the existing `RealAmesSourceTests` source-integration test, then the full
`unittest discover -s tests -q` suite with the same environment variable.
Read only the existing source; make no network request, model fit, holdout
opening, source redistribution or claim of real-market certification.

## Decision rule

Accept this as a verified engineering source-integration check only if the
private file hash and Git exclusion match the source card, the focused test
passes without a skip, and the full suite passes without skips. Save command,
exit code, duration, environment and output. If the full suite has another
skip or failure, record it rather than changing the source or test to force a
pass. Keep the previous report's skip as historical fact and publish a new
correction explaining why it happened.

This test can verify the current OpenML ARFF's schema and labels. It cannot
reconstruct the unavailable original `ames.csv`, prove old XGBoost scores,
establish historical feature availability or satisfy G-US.
