# ADR 0046: label-free synthetic calendar evaluation schedule

Date: 2026-10-03
Owner: project implementation
Status: adopted for synthetic engineering; real-data protocol remains pending
Requirements: US11, US22, US23, US24
Protocol: `us_synthetic_calendar_schedule_v1`

## Purpose and boundary

Add a small, immutable calendar schedule that freezes four quarterly
development windows, a disjoint calibration interval and a 12-calendar-month
final-test interval from declared dates and label-free sale-cohort metadata. This
closes a synthetic engineering gap only. It neither chooses a real test
period from observed outcomes nor opens reserved labels. Retrospective origin
dates may be derived from completed sales; this builder is no evidence of a
prospectively enrolled cohort. Source-backed
eligibility, complete history, 1,000 matured calibration labels, geographic
blocks, test opening and G-US remain separate gates.

## Contract

- Input rows contain only unique economic-transfer row IDs, property IDs and
  source-local **origin dates**. No target, close date, sale price or
  `available_at` field enters this builder. Reject non-date values, including
  datetimes disguised as dates.
- The caller supplies 64-character source snapshot and origin-policy SHA-256
  values, declared first usable history date, calibration start and test
  start. All boundary dates
  are first-of-month dates. The calibration start must be a conventional
  calendar-quarter start (January, April, July or October).
- The four development windows are the four consecutive calendar quarters
  ending at the calibration start. The declared history begins at least 24
  calendar months before the first development start. The calibration window
  is `[calibration_start, test_start)` and must span at least one complete
  calendar month. The final test is `[test_start, test_start + 12 calendar
  months)`. All intervals are half-open; no 90-day approximation is used for
  quarters or years.
- Every supplied origin must fall within `[history_start, test_end)`; reject
  out-of-range rows. Record the pre-development history IDs separately and
  require at least one origin in every development, calibration and test
  window. Within each window sort IDs deterministically. Hash the protocol,
  both source/policy fingerprints, exact boundaries and every input row's ID,
  property ID and origin date in sorted order, plus assigned membership.
  Reordering input records must not change the hash; changing a boundary,
  property, date or membership must.
- The schedule states each development training cutoff as the start of its
  validation quarter and exposes only `training_candidate_ids` from earlier
  origins, not `train_row_ids`. The existing synthetic fold builder receives
  **only** that fold's pre-cutoff training-side maturity records and enforces
  `available_at <= training_cutoff`. This schedule itself does not inspect
  maturity or make any row eligible for training.
- Source-local calendar dates must be mapped to timezone-aware cutoff instants
  by a source-specific policy before a real fold is built. The test's UTC-noon
  mapping is only a synthetic fixture.

## Tests and adoption

Write behavioral tests first. Cover four exact quarters, year/leap-month
boundaries, half-open membership, duplicate IDs, short history, misaligned or
overlapping periods, invalid source hash, deterministic hash, changed-row
hashes and test-label independence. Include an integration test that feeds a
quarter to the existing synthetic fold builder and shows a delayed earlier
label entering training only after it becomes available. Aim for at least 80%
branch-aware coverage of the new module, and run the full repository suite,
Ruff and dependency checks. Review code and security before a conventional
commit and push. Report this as **synthetic engineering verified** only; do
not change U3, U0 or G-US acceptance from pending.
