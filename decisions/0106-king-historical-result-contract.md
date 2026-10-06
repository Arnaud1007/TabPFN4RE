# ADR 0106: King historical prediction result contract

## Status

Accepted for the pinned King historical research predictor. G-US remains
**PENDING**.

## Context

The local form and CLI return an estimate quickly, but the machine response
previously required consumers to infer freshness, market support and missing
uncertainty from scattered fields and prose. The bundle cannot substantiate a
current valuation date, current inputs, calibrated interval, property-specific
comparables or production service coverage.

## Decision

Add response schema `king_historical_prediction_response_v2` to the absolute
error bundle. It reports the verified exclusive training cutoff, historical
data status, schema-only research support, unavailable uncertainty and fixed
evidence and use limitations. It supplies no interval endpoints, current
valuation date, comparable identifiers or current-market claim.

The CLI and form consume the same response. Receipt capture validates the
complete schema and exact disclosure values. Each response receives fresh
nested objects so mutation cannot alter later predictions.

Existing immutable receipts used the same outer receipt protocol before this
response schema existed. Commitment recovery may validate that exact prior
absolute response shape through an explicit compatibility flag. Live capture
and form paths require the current response schema and cannot use the legacy
path.

## Acceptance

- CLI and form preserve the same estimate and disclosure contract.
- Missing, extra, altered or fabricated disclosure fields are rejected.
- Existing hash-valid absolute receipts remain recoverable for commitment.
- Serving and receipt tests retain at least 80% focused branch coverage.
- Five complete CLI predictions remain within two seconds on the declared
  workstation.

## Evidence boundary

This makes the existing research result easier to interpret. It adds no model
accuracy, source rights, calibrated uncertainty, current-market evidence or
G-US acceptance.
