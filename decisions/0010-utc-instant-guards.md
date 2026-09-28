# ADR 0010: UTC instant guards and synthetic horizon v2

Date: 2026-09-28

Owner: project implementation

Affected requirements: US06, US08, US10, US11, US22, US23

Affected protocol: `us_synthetic_rolling_v2`. The v1 gate in `runs/u3-synthetic-temporal-20260928T123500Z/` remains historical evidence and is not rewritten.

## Alternatives and evidence

Python compares two aware datetimes that share a `tzinfo` object by their wall times and can ignore the fall-back `fold`. A label published at 01:30 in the second hour was wrongly considered available at 01:45 in the first hour. The v1 split was fixed, but an audit found equivalent risks in OFF feature assembly, comparable retrieval and guarded baseline training. Ten initial regression canaries were written RED; additional tests covered context reuse, month-window boundaries and horizon representation.

Inferring a source-local calendar from an input datetime was considered and rejected. A fixed UTC offset is not a seasonal timezone, and equivalent instants can carry different timezone representations. Without a verified source-local zone/date rule, the implementation cannot certify the specification's 90-calendar-day pre-close origin.

## Decision

Normalize all point-in-time ordering, membership, recency and identity comparisons to UTC instants. Snapshot and split hashes serialize instants in UTC, so equivalent representations hash alike. Keep original source timestamps and timezone offsets in the canonical records. Comparable result reuse compares all non-time context fields and explicitly compares time fields as UTC instants. The synthetic comparable month window is measured in UTC calendar months, pending a source-local market-window rule.

For `us_synthetic_rolling_v2` and the synthetic OFF median, the exact horizon is **90 days of 24 hours each in UTC**. The fold builder rejects other protocol IDs so its output cannot be labelled as a real-source split. This is deliberately an engineering protocol. A local wall-clock pair 90 calendar dates apart across a daylight-saving transition may fail it. The real-source protocol must explicitly identify the source-local date/time zone, handle ambiguous and nonexistent times, and version its own origin construction before any U3 certification. A source's fixed offsets alone do not establish that policy.

## Verification and promotion dependencies

The new fall-back canaries cover property/attribute/sale visibility, comparable eligibility and pricing context, label maturity, repeat-hour ordering, identical-instant hashes, month-window invariance and baseline prediction. Code, Python and security reviews are recorded in the implementation session; the complete executable gate is filed separately in `runs/`.

Before real ingestion, source cards must specify event-date meaning, source-local timezone or date-only convention, first availability and correction handling. Add real-source fixtures across daylight-saving changes, then freeze a new protocol ID and test period. No previous split or reported score is retroactively changed.
