# HCPA source-admission gate evidence plan

Run ID: `u0-hcpa-source-admission-v1-20261006`

## Scope

Verify the bounded, non-row HCPA source-admission validator and its frozen
one-fit policy. This run may read only committed metadata, synthetic test
fixtures, and the decision record. It must not read HCPA archives, sale rows,
private review ledgers, or model artifacts, and it must not fit a model.

## Expected decision

The v1 validator is expected to return `pending`, with
`source_admitted=false` and `model_fit_permitted=false`. An admitted result is
outside the v1 protocol and must fail closed until a later reviewed version
authenticates authoritative acceptance, passes a separate fit-readiness gate,
and atomically reserves the declared single fit in a run ledger.

## Checks

1. Run the focused tests with branch coverage for
   `scripts/hcpa_source_admission.py`.
2. Run Ruff checks and formatting verification on the validator and tests.
3. Invoke the production CLI twice and compare its exact output.
4. Hash the implementation, tests, admission record, model policy, and ADR.
5. Publish only privacy-safe metadata and observed outcomes.
