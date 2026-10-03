# U3 synthetic chronological maturity checkpoint

Run ID: `u3-synthetic-chronological-plan-20261003T113906Z`  
Code commit: `ab5cffbf955feb86b45b103c87ee4423d4d6f46c`  
Status: **verified synthetic engineering; U0, U3 and G-US PENDING**  
Requirements: US11, US22, US23, US24

## Objective and changes

Bind the previously frozen synthetic calendar windows to evidence that a
training-side sale label had become available by a single UTC model-fit
cutoff. The [implementation](../../src/tabpfn4realestate/evaluation/chronological_plan.py)
checks the pinned local 90-calendar-day policy for each row, verifies the
schedule hash and membership, rejects reserved-label maturity and records
immature candidates separately. It freezes four development folds and one
final predictor fit set before calibration. No prices or real test labels enter
the plan. [ADR 0068](../../decisions/0068-synthetic-chronological-maturity-binding.md)
records the conservative treatment of date-only closing and publication.

## Commands and observed results

The [test gate](test_gate.json) records the commands, exit codes and logs. A
RED test committed as `b5a2b8b` failed because the module was absent. The
GREEN implementation committed as `ab5cffb` passed its direct tests. Reviews
found a quadratic membership check and an insufficiently conservative
same-day publication guard; both were corrected before the GREEN commit and
then independently re-reviewed with no remaining critical or high finding.

| Check | Observed result |
| --- | --- |
| Direct chronology tests | 10 passed; exit 0. |
| Chronology, local-date and calendar tests under coverage | 36 passed; exit 0; 88% combined branch-aware coverage for the two touched modules. |
| Full Python 3.11 suite with local ignored Ames source path | 1,136 passed; no skips; exit 0; 202.587 seconds reported by unittest (203.315 wall seconds). |
| Ruff lint and formatting | Exit 0 for both. |
| `pip check` and `pip-audit --local` | Exit 0; no broken requirements or known vulnerabilities in auditable distributions. The local editable project was not audit-listed on PyPI. |

The full suite intentionally exercises error fixtures, so its redacted
[log](full_suite.log) includes expected diagnostic messages despite overall
success. The first in-progress suite was interrupted after implementation
changed; it is not counted as a passing run. The completed suite used the
committed production code and tests. Only documentation and requirement links
changed while it ran.

## Limits and next action

The [manifest](manifest.json) distinguishes synthetic fixture hashes from
real source, split, feature-policy and model-checkpoint hashes, which are all
absent. The fixture plan hash is
`b21567102536f23bddc930e1dfe70da0c73d06fe5e24e22b68a21403883ae169`.
It is not a real certification split. There are **zero certified modern US
sale labels**, no model fit, no final calibration and no prospective evidence.

U0 still needs an authorised source with verified single-home gross sale
consideration, actual close-date meaning, first availability and reuse
rights. The 200-record source audits, historical attributes and geographic
coverage remain incomplete. Thus U3 and G-US remain PENDING. Once one source
passes U0/U2, freeze its real origin membership and source-local policy,
then apply this maturity contract to development labels without supplying
calibration or test outcomes. Do not treat the declared 24-month span as
evidence of 24 months of usable history.

Resume the synthetic check from the project root:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_chronological_plan -q
```

The dependency-ready source work and exact replay commands remain in
[next_action.md](../../next_action.md). International implementation stays
locked until G-US passes.
