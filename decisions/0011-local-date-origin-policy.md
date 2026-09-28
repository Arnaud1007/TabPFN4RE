# ADR 0011: source-local date-only origin policy

Date: 2026-09-28

Owner: project implementation

Affected requirements: US03, US08, US11, US22, US23

Affected protocol: `us_local_date_90d_v1`. Existing synthetic split artifacts and `us_synthetic_rolling_v2` remain unchanged.

## Alternatives and evidence

The synthetic helper uses an exact UTC duration of 90 times 24 hours. A source that records only a local closing date needs 90 **calendar dates** instead. Treating a date as midnight at an arbitrary UTC offset can shift the valuation boundary across daylight-saving changes. Python's `zoneinfo` documentation recommends a `tzdata` dependency for Windows, where an IANA database may be absent. The environment initially could not resolve `America/New_York`; pinned `tzdata==2026.4` supplies the rules. The wheel SHA-256 is recorded in `locks/local-date-requirements.txt`.

## Decision

For a verified source-local close date, subtract 90 calendar days. The valuation cutoff is the first valid midnight of the **following** local date, exclusive in UTC. Exact timestamps are visible only before that cutoff. Date-only availability is interpreted conservatively as available by the end of its declared source-local day. The time-zone rules load directly from the pinned `tzdata` package, independent of host OS data. Repeated midnight uses its earliest valid occurrence; nonexistent midnight or a wholly skipped date fails closed.

The origin record includes the close date, origin date, IANA zone, UTC cutoff, protocol ID, `tzdata` version and a canonical hash. Its computed fields are immutable and cannot be supplied by a caller. Availability with only a date must also identify its own source-local zone; a cross-zone date cannot be compared as a plain calendar number.

This policy does not infer what a source's sale-date field means. Source cards must resolve whether the field is closing, deed execution, recording or another event, and whether date-only availability genuinely means end-of-day publication. The local-date helper does not make current downloads into historical vintages. A qualified real-data adapter, maturity-aware folds and reserved labels are separate work.

## Verification and promotion dependencies

Tests cover spring/fall daylight-saving boundaries, leap/year rollover, repeated and skipped local midnights, a skipped civil date, exact cutoff exclusion, source-local date-only availability, cross-zone publication, invalid zones and forged origin metadata. `locks/local-date-requirements.txt` supports a hash-checked Windows install using `pip install --require-hashes -r locks/local-date-requirements.txt`; ordinary editable installation records the version pin but does not enforce the wheel hash. Full executable evidence is stored in a later `runs/` gate.

Neither Hillsborough's `S_DATE` description nor Florida DOR's monthly sale date is sufficient today to certify a 90-day pre-close history. No real training or G-US claim follows from this engineering policy.
