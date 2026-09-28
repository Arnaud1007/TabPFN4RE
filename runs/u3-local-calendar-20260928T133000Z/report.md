# U0 source feasibility and U3 calendar engineering report

Run ID: `u3-local-calendar-20260928T133000Z`

Code commit: `df74bc0`

Gate status: **COMPLETE for the engineering check only**. U0, U3 and G-US remain pending.

## Objective and changes

Implement a source-local 90-calendar-day origin and conservative publication visibility rule without relabelling the synthetic UTC split as a real benchmark. Pin IANA time-zone data for Windows and record a newly found daily-date US source candidate. Requirements addressed in part: US02, US05, US08, US11, US22 and US23.

The `us_local_date_90d_v1` helper subtracts 90 calendar dates, computes the next local midnight as an exclusive UTC cutoff, and requires a source zone for date-only availability. Computed origin fields cannot be supplied or replaced by callers. It fails closed on missing or skipped local midnights. The existing `us_synthetic_rolling_v2` split builder and baseline are unchanged. ADR 0011 records the protocol and its limits.

The Hillsborough County Property Appraiser All Sales archive was audited only as a source candidate. Its documented `S_DATE` is a sale date, but closing semantics and historical first availability remain unverified. `data/source_cards/hillsborough_hcpa_allsales.yaml` records the official page, archive and documentation hashes, fields and rights blocker. No property rows were ingested or trained.

## Actual checks

`test_gate.json` stores the exact commands, exit codes, durations, output paths, log hashes, code commit, dependency-lock hash, fixture hash, configuration hash, Python and tzdata versions. All seven recorded commands returned exit code 0:

| Check | Observed result |
| --- | --- |
| Full Python 3.11 coverage test suite | 188 tests, 0 skipped, pass |
| Statement coverage | 90.65% overall; `coverage.json` and report preserved |
| Ruff lint and format | Pass |
| Python package consistency | `pip check` pass |
| Pinned `tzdata` dependency vulnerability audit | No known vulnerabilities reported by `pip-audit` |

The 17 new focused tests cover DST, leap/year rollover, exact cutoff exclusion, cross-zone date-only availability, skipped dates, invalid zone keys and attempts to forge origin metadata. Three read-only reviews identified two leakage risks in the first implementation; both were corrected before this gate and re-reviewed with no remaining medium/high findings.

An earlier launcher attempt in `runs/u3-local-calendar-20260928T132430Z/` passed its underlying checks but failed while PowerShell parsed the coverage JSON. Its initially invalid manifest was preserved and marked failed; it is not evidence for this gate. The current gate was rerun and its seven log hashes were checked independently against saved files.

## Residual limitations and next action

No real US source has yet proved close-date meaning, row-level first availability, historical feature vintages, rights and safe property identity together. This helper is not wired into a real-data adapter or a certified temporal fold. There is no US accuracy, interval, market-coverage or prospective score from this run. The owner's private legacy repository is still inaccessible; the requested split, XGBoost artifacts and feature catalogue were confirmed unavailable. See `next_action.md` for the resume command and source qualification task.
