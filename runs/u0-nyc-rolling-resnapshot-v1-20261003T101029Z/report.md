# U0 NYC rolling-sales repeat source observation

Run ID: `u0-nyc-rolling-resnapshot-v1-20261003T101029Z`  
Protocol: `nyc-rolling-resnapshot-v1`  
Requirements: US02, US05, US06, US08, US22, US24  
Status: **verified source inventory only; U0 and G-US PENDING**

## Frozen question and inputs

The [plan](plan.md) was committed and pushed as
`e1e3f1337315bb51c3f94ca2819f0906b6647bc9` before the source read; the
working tree was clean at invocation. It restricted this run to one bounded
capture of the official NYC `usep-8jbt` rolling-sales CSV and a byte-level
comparison with the [September capture](../u0-nyc-rolling-snapshot-20260928T225512Z/report.md).
The committed capture script and environment-lock SHA-256 values are in the
plan. There is no model configuration, split, feature policy or checkpoint in
this source-observation run.

## Observed result

| Check | September observation | October observation |
| --- | ---: | ---: |
| Capture completed, UTC | 2026-09-28 22:55:43.929203 | 2026-10-03 10:13:06.833850 |
| CSV bytes | 10,397,977 | 10,397,977 |
| Strict parsed rows | 82,345 | 82,345 |
| Columns | 21 | 21 |
| CSV SHA-256 | `84c06057c52a2822f982cd98fb77ef7edf2c14134d00f46b073d2e4b762b2ef2` | same |
| Source API count before/after October capture | n/a | 82,345 / 82,345 |

The two privately retained CSV files are byte-for-byte equal by independently
computed SHA-256 and size, as recorded in [verification.json](verification.json).
The October capture's metadata SHA-256 differs from September's, even though
its CSV bytes and portal `rowsUpdatedAt` value agree. This is a metadata
observation, not evidence of a changed sale row. Both files remain under
Git-ignored `data/raw/nyc_dof/`; the public records contain no address,
unit, price, row identifier or row-level fingerprint.

The October [snapshot manifest](snapshot.json) gives the source URLs, the
before/after metadata and count hashes, the HTTP response metadata and the
conservative known-by time for this *file*. Equality across the two captures
does not prove when any row was first published. A source sale date is not yet
verified as a close date. No sale label, historical feature, as-of modelling
row, calibration row or certification cohort was created.

## Commands and validation

- The committed `capture_snapshot()` function was invoked **once** from the
  project root. It returned `inventory_only_not_asof_eligible` after 17.125
  seconds, with exit code 0. The new `snapshot.json` was created without
  overwrite. No capture failure or retry occurred.
- An independent Python read verified each private file's SHA-256, byte count,
  strict CSV row count, column count and Git exclusion, and reconciled the
  October API counts. It exited 0 in 0.589 seconds and wrote
  [verification.json](verification.json).
- `python -m unittest tests.test_capture_nyc_rolling_snapshot -q` passed 19
  tests in 1.096 seconds of command wall time, exit code 0; see
  [focused_tests.log](focused_tests.log). PowerShell prefixed its captured
  stderr with a `NativeCommandError` formatting label despite the zero exit
  code and `OK` result. A clean subprocess replay also passed 19 tests,
  exit code 0, in 0.891 seconds; see
  [focused_tests_replay.log](focused_tests_replay.log). No implementation code
  changed, so the full suite and coverage were not rerun for this observation.
- The [September run verifier](../u0-nyc-rolling-snapshot-20260928T225512Z/verify_artifacts.ps1)
  passed again in 0.382 seconds; see [prior_replay.log](prior_replay.log).

## Decision and next action

The repeat capture is accepted as a verified source observation. NYC remains
inventory-only with **zero certified sale labels**, and U0/G-US remain
PENDING. Seek dated publisher evidence for first row availability, source
`SALE DATE` meaning, transfer/unit identity, historical physical attributes
and dataset-specific reuse rights. Do not train on these rows or treat the
capture interval as an exact publication interval. The Cook source-review and
custodian questions remain separate U0 work.
