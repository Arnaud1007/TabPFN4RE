# ADR 0081: Source-local date origins for synthetic OFF integration

Date: 2026-10-03
Owner: project implementation
Status: implemented engineering contract; source certification pending
Affected requirements: US03, US06, US08, US11, US14, US23, US24
Affected protocols: `us_local_date_90d_v1` and synthetic OFF as-of assembly;
no frozen real-market split changed

## Problem and alternatives

The existing OFF baseline and feature assembler use aware UTC timestamps and an
exact 90-times-24-hour horizon. A county source that provides only a closing
date cannot enter that protocol without inventing a closing time. Across
daylight-saving transitions, an exact UTC duration also differs from 90
source-local calendar dates. Reinterpreting the established exact-UTC path
would change its historical engineering fixtures. Coercing a date to UTC
midnight would imply precision the publisher did not provide.

## Decision

Add a separate `LocalDateOrigin` route for the synthetic OFF feature assembler
and median baseline. Its valuation origin is 90 source-local calendar dates
before the recorded closing date. Timestamped facts at the first local
midnight *after* the origin date are excluded. A source snapshot captured
earlier still caps information at its inclusive `as_of` instant. Property
versions, attributes and prior sales follow the same boundary; the exact-UTC
entry points retain their prior behavior.

Use `LocalDateSale` to retain source-local closing-date precision and a typed
publication date or aware timestamp. The baseline rebuilds the frozen
chronological plan, requires exact matured training membership and rejects
reserved or ineligible labels. Its model record contains a digest of accepted
label facts, source manifest descriptors and feature snapshot hashes. The
recorded source snapshot SHA-256 remains a **caller declaration**; the model
does not verify raw source bytes. Prediction sources are limited to label and
feature sources actually used in training.

## Evidence and limits

The synthetic run report under `runs/u3-synthetic-local-date-off-v1-20261003/`
records tests, coverage and review results. Fixtures cover daylight-saving
boundaries, publication lag, source caps, frozen membership, accepted-label
digest changes and deterministic replay. These verify code behavior only.

The feature route currently accepts timestamped property, attribute and
prior-sale facts. A source with date-only *feature* publication needs a typed
adapter and additional tests before use. The caller-declared source digest
must be bound to an independently hashed, immutable input artifact before a
real training run can claim source provenance. No modern US label source has
passed that test. U0, U3 and G-US remain pending; this decision does not
unlock ON mode or international implementation.
