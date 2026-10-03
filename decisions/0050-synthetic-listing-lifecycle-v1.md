# ADR 0050: synthetic US listing lifecycle resolution

Date: 2026-10-03
Owner: project implementation
Status: U1 synthetic contract; real-source admission pending
Requirements: US04, US06, US08, US23, US24
Protocol: `us_listing_lifecycle_v1`

## Problem and alternatives

The U1 schema holds listing events only after a property ID is already known.
It cannot demonstrate conservative property or episode identity resolution,
duplicate feed handling, relists or a historical listing timeline. The OFF
feature assembler intentionally ignores listing events, and ON has no
authorised historical feed. Adding address guesses directly to the OFF
assembler would risk changing its information policy. A separate, synthetic
resolver lets these controls be tested without admitting a real source.

## Fixed synthetic expectations

The tests in `tests/test_listing_lifecycle.py` were written before the
implementation and first failed because the module was absent. Their
expected outcomes are:

1. Duplicated cross-feed publication becomes one logical event only with a
   dated, reviewed episode alias; original source observations remain.
2. Distinct timestamped price changes on one day remain ordered; conflicting
   facts at the same instant quarantine the entire episode.
3. A later-publicized event is absent until its `available_at`, even when its
   event time is earlier. A future-reviewed alias cannot change an earlier
   view.
4. Withdrawal remains the outcome of that listing when another source later
   publishes and marks a different listing sold.
5. A property split into two units uses dated, distinct property identities;
   a record missing the unit is quarantined instead of assigned to either.
6. A relist opens a new episode linked to the same property. Reingestion and
   reversed input order preserve deterministic results. Independently listed
   overlapping episodes stay separate and receive a flag.

## Decision and boundaries

Use frozen records for source-qualified event IDs, source listing IDs,
address/parcel/unit evidence, event time, source first availability and
local ingestion time. A property link requires unique exact evidence in a
dated property version. A cross-feed episode merge requires an explicit
reviewed alias whose evidence is available by the valuation origin. Preserve
raw visible events and reason-coded quarantine; never infer a sale price from
a listing's `sold` status. Unavailable historical source timing is
quarantined, not replaced with the local ingestion timestamp.

The resolver is deliberately in memory and is not a source adapter. It does
not yet cover source corrections/supersession, evidence quality, calibrated
match confidence, cumulative exposure, or production-scale indexing. These
remain US04 tasks. OFF remains independent of listing events and ON remains
blocked. No real sale label, historical listing feed, U1 acceptance or G-US
passage is established by synthetic tests.
