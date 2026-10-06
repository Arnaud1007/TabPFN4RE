# King historical result contract, 6 October 2026

Status: **result contract PASS; cold two-second target FAIL; G-US PENDING**.

## Result

The pinned King predictor now returns response schema
`king_historical_prediction_response_v2`. The CLI and form disclose:

- the exclusive 1 March 2015 training cutoff and historical-only freshness;
- schema support qualified by an unvalidated service area;
- unavailable 80% and 90% intervals with no fabricated bounds;
- missing certified 90-day, G-US, interval and comparable evidence; and
- explicit research, current-market, national and production limitations.

Receipt capture requires the exact schema and rejects missing, extra or altered
disclosures. Commitment recovery retains a narrowly scoped validator for
hash-valid absolute responses captured before the schema change. Live capture
and form paths cannot use that compatibility route.

## Verification

- Implementation commit: `0d2b91002ca4a4a193c924ffe57578d854a08ab7`.
- 58 tests passed, two optional integrations were skipped and 81 subtests passed.
- Focused branch coverage was 80%.
- Ruff and code, Python and security reviews passed.
- Ten complete CLI processes returned the identical estimate and disclosure
  statuses.

## Latency observation

The ten complete CLI processes took 2.00-2.64 seconds, with a 2.40-second
median. This run did not reproduce the earlier all-under-two-second result, so
the proposed cold two-second target is marked **FAIL** rather than hidden.
Resident predictions remain the recommended form workflow and were previously
measured at 1.27 ms p95 after one model load.

## Evidence boundary

This change clarifies the existing historical result. It does not improve
accuracy, add a current valuation date, create calibrated uncertainty, clear
source rights or validate King County service. G-US remains pending.
