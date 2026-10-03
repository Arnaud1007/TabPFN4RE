# ADR 0084: Bind synthetic calendar training to a retained source capture

Date: 2026-10-03
Owner: project implementation
Status: implemented for synthetic engineering only; real-source admission pending
Requirements: US03, US06, US08, US11, US14, US23, US24
Affected protocol: `synthetic_calendar_capture_v1` and `synthetic_capture_bytes_v1`; existing caller-declared fits and frozen real-market evaluations are unchanged

## Problem and alternatives

The earlier synthetic OFF median received the schedule's `source_snapshot_sha256` from its caller. Equality between two declared strings did not show that a model read a source artifact, or that its rows came from that artifact. Hashing an unrelated file while still fitting caller-built examples would not close that gap. A source-specific county adapter is premature: no candidate currently satisfies transaction semantics, first availability and permitted-use requirements.

## Decision

Add a training-only synthetic JSONL capture with a fixed source ID and strict row schema. Its bytes contain only development labels that have matured for the frozen final fit; origin membership and reserved calibration/test rows are supplied separately without reserved prices. The artifact-bound entry point reads the exact bounded file once, computes SHA-256 from those same bytes, compares it with the already-frozen schedule, parses those bytes into immutable training examples, and invokes the existing maturity and leakage guards. A changed byte or extra/missing row cannot silently enter the same frozen fit.

For this entry point, the schedule's `source_snapshot_sha256` denotes the exact synthetic training-source capture, and `source_binding_kind` names the engineering path. That model field is descriptive and can be changed by Python callers. A provenance claim therefore requires retaining the capture and running `verify_synthetic_calendar_capture`, which rehashes, refits and compares the full model. The legacy `fit` path remains a caller-declared synthetic fixture and cannot use this run as proof of raw-source binding.

The parser conservatively rejects malformed schemas, duplicated keys, oversized or linked files, invalid source IDs, publication before observation, and date-only facts at or after the next local midnight boundary. The model still checks 90-day origins, matured training membership, source lineage and OFF-only features.

## Limits and next decision

This capture is generated synthetic data. It proves that the engineering fit can be replayed from retained bytes, not that a publisher supplied an eligible US home sale. Its hardcoded gross-sale and arm's-length values are fixtures, not inferred county facts. An actual source adapter must verify source-specific rights, close-date and price semantics, first publication, unit/transfer identity and historical property versions, then bind every canonical row to independently captured raw source bytes. Keep U0, U3 and G-US PENDING; no real-data training, ON mode or international work is unlocked.
