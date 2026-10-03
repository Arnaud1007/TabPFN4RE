# ADR 0054: synthetic projected-grid geographic holdout

Date: 2026-10-03
Owner: project implementation
Status: adopted for synthetic engineering only
Requirements: US11, US22, US23, US24
Protocol: `us_synthetic_rolling_v2`

## Decision

Build geographic membership on top of the existing validated temporal fold.
The builder calls `build_temporal_fold` itself, so a caller cannot supply an
unverified fold or validation maturity records. Every origin needs exactly one
matching projected point. A declared EPSG code and projection-version hash
identify the synthetic metric grid; the builder does not itself verify a real
coordinate transformation or source geocode.

Assign points to half-open square cells with exact rational arithmetic and
floor division, including negative coordinates. Accepted CRS identifiers are
an explicit metre-unit allowlist; source transformations still need audit.
Select the frozen heldout cells from development data. Validation
contains only temporal-validation origins in those cells. Training contains
only temporally matured labels outside the heldout cells and beyond the
registered buffer. The buffer is measured from each point to the **closed cell
rectangle**, including its boundary; an exact-distance match is purged. A
zero-metre buffer is allowed and still purges boundary points. Purge any
training row sharing a property ID with spatial validation, even if the two
points disagree. The purge reasons are disjoint and counted. Fail when either
final partition is empty.

The split hash binds the parent temporal hash, projected coordinates and
identities, CRS and projection version, grid, heldout cells, buffer and every
membership. Input order and equivalent Decimal spelling do not affect it.
The input contract accepts finite, bounded Decimal metres; it rejects floats
and malformed cell selections, and caps the selection at 256 cells. This gives
arithmetic and hash stability across process Decimal contexts. It does not
establish that a real geocode has metre accuracy.

## Alternatives and boundary

Point-to-point separation was rejected because an empty portion of a heldout
geographic block would admit nearby training sales. Geographic distance in
latitude/longitude degrees was rejected because it is not a metre measure.
A spatial-only split was rejected because it could train on labels unavailable
at the simulated cutoff. The normal future-sale operational test retains known
earlier property sales; this separate unseen-geography diagnostic purges
repeat properties to prevent property identity from crossing its boundary.

This module is **synthetic-only**. Real US11 evidence still requires source
geocodes and coordinate reference system audits, a development-only recorded
choice of block size and buffer from dependence diagnostics, actual source
availability dates, a frozen market scope and untouched test labels. It does
not release U3 or G-US. Those conditions require a new, versioned real-data
protocol; this builder rejects non-synthetic protocol IDs.

## Verification

Behavioral tests were written first and failed because the module was absent.
They cover temporal label maturity, reserved-label injection, half-open and
negative cells, exact axis and diagonal buffer boundaries, identity conflicts,
one-to-one location joins, invalid input, low-precision Decimal context and
canonical hashes. The checkpoint gate and actual
commands are recorded under `runs/u3-synthetic-spatial-20261003T021311Z/`.
