# U3 synthetic calendar schedule checkpoint

Run ID: `u3-synthetic-calendar-schedule-20261002T223619Z`  
Code commit: `33100dbcc95f824cf16652ec06e1040ad3232c8b`, pushed to `origin/audit/u0`  
Status: **verified synthetic engineering; U0, U3, and G-US PENDING**  
Requirements: US11, US22, US23, US24

## Objective and changes

Implement [ADR 0046](../../decisions/0046-synthetic-calendar-evaluation-schedule.md): a label-free schedule with four consecutive calendar-quarter development windows, a disjoint calibration interval, and a 12-calendar-month test interval. The builder validates source-local origin dates, unique transfer row IDs, declared 24-month predevelopment history, complete window membership, and SHA-256 source/policy fingerprints. It exposes earlier training **candidates**, not admitted labels. A deterministic hash freezes the declared boundaries and synthetic row membership.

This checkpoint adds [calendar_schedule.py](../../src/tabpfn4realestate/evaluation/calendar_schedule.py) and [nine behavioral tests](../../tests/test_temporal_schedule.py). An integration fixture confirms that the existing fold maturity guard does not admit a prior label before its `available_at` cutoff. No real transaction source was converted into a certified training or test cohort. The local ignored Ames file was configured only to remove an unrelated optional integration-test skip from the full suite.

## Commands and observed results

The [test gate](test_gate.json) preserves the exact commands, exit codes, reported counts, and captured durations. The [manifest](manifest.json) records code, environment, protocol, and fixture schedule hashes. Both full-suite durations are unittest-reported; other duration fields are explicitly null.

| Check | Observed result |
| --- | --- |
| TDD RED before implementation | Import failed with `ModuleNotFoundError`, as expected. |
| Targeted synthetic tests | 9 passed, 0 skipped; exit 0. |
| Branch-aware module coverage | 92% rounded; 116 statements with 7 missed, 36 branches with 5 partial. |
| Full Python 3.11 suite with local `AMES_ARFF_PATH` | 928 passed, 0 skipped; exit 0; 168.878 seconds. |
| Ruff lint and changed-file format checks | Both exit 0; two changed files already formatted. |
| Installed-environment `pip-audit` | Exit 0; no known vulnerabilities in audited distributions; the local project could not be checked against PyPI. |

The first full-suite invocation without `AMES_ARFF_PATH` had one optional source-integration skip. It was rerun with the local ignored source path and had zero skips. An initial `pip-audit --disable-pip --no-deps -r requirements.txt` invocation failed because that file does not exist; the installed-environment path command above was the corrected audit. Neither attempt is treated as the passing gate.

Independent code-quality, Python, and security reviews reported no blocking finding before the code commit. The reviewed implementation and tests are already on the named GitHub branch.

## Limits, failed gates, and next action

The synthetic fixture schedule hash `f1670e860faa0fb1e1e252be84258314ae91dc8157f6d46f7db348f32fd98859` is a reproducibility check on test membership, **not** a frozen real-data split. There is no real source snapshot hash, feature-policy hash, or model checkpoint for this run. The schedule accepts source-local dates but does not connect an audited source-specific date-to-instant policy. It does not prove label eligibility, 1,000 matured calibration rows, twelve months of real final-test origins, geographic coverage, reserved-label protection, or prospective performance. U0, U3, and G-US remain PENDING.

Resume the synthetic check from the project root with:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_temporal_schedule -q
```

The dependent U3 task is to qualify a real US transaction source with dated first availability, correct close-date/transfer semantics, source-local cutoff conversion, and matured labels; then freeze a real schedule and connect the existing fold maturity guard without exposing the certification cohort. In parallel, continue the unresolved NYC source and legacy evidence work in [next_action.md](../../next_action.md). No NYC sale label is certified and international implementation remains locked.
