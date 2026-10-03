# Cook private source-quality funnel, v1

Run ID: `u2-cook-quality-v1-20261003T135237Z`  
Protocol: `cook_source_quality_v1`  
Date: 2026-10-03  
Requirements: US06, US07, US24  
Status: **verified private source-quality audit; U0 PENDING; G-US PENDING**

## Objective and changes

[ADR 0073](../../decisions/0073-cook-private-source-quality-funnel.md) and the
[frozen plan](plan.md) govern a deterministic audit of the already captured
200 Cook County Assessor parcel-sale observations. The new quality module
classifies published price, PIN, recording-date, multisale, parcel-count and
document-group states. It preserves every row and emits fixed review reasons.
The offline runner replays the original capture and staged observation bytes,
writes an ACL-restricted private findings file and count partition, then
publishes only the fixed [aggregate](aggregate.json). No additional source
row was requested and no model was trained.

## Observed result and evidence

The one-time local command exited 0 in 5.261 seconds. It wrote exactly 200
private findings (72,652 bytes) under Git-ignored
`data/raw/cook_county/parcel-quality-v1-130b5169ff81ccbc/`. The findings
SHA-256 is `58708585e185e2b57aa865dff0d1dc250589f8d6214babd8600dc1326424eb5c`.
The public aggregate SHA-256 is
`2865a67ab7de3d2b8af94bd0c9b76a22b80a9d6ef5fda244f4c899ebf5ffd326`.
Independent offline replay exited 0 in 2.193 seconds and matched the private
findings, private count partitions and completion manifest byte-for-byte
against the pinned source. The detailed reason counts stay private and are
**not** population-rate estimates because the sample was intentionally
stratified by recorded date and price. A document classified `unique` was
seen once in this sample; no source-wide uniqueness is inferred.

The [evidence manifest](evidence_manifest.json) records the source and staged
hashes, code-file hashes, pre-commit dirty-tree state and package-pin snapshot.
There is no split, feature policy, model configuration or checkpoint in this
source-quality run. The [test gate](test_gate.json) records exact commands,
exits and durations where measured. The staged-source verifier passed before
the real run. Focused tests passed **13/13** with **89% branch-aware
coverage**; the full repository suite passed **1,185 tests with zero skips**
in 204.777 seconds, using the hash-verified Ames ARFF. Ruff check/format,
`pip check` and `pip-audit` passed. The local editable package could not be
audited on PyPI. The [full test gate](full_gate.json) retains original and
sanitized log hashes; the committed logs replace the local home path with
`<USER_HOME>`.

Synthetic test development initially failed because the new modules did not
exist, then because test fixtures used a different synthetic capture hash and
one attempted tamper string did not match the JSON spacing. These were test
setup errors corrected before the real source run; no failed real-source run
was retried or hidden. Code, Python and security reviews found no remaining
critical or high issue. Before execution, security review led to removing
the private count-file hash from the public summary; the frozen plan records
that amendment. Python review led to documenting the eight-character
parcel-count string limit.

## Interpretation and next action

**All 200 are parcel-source observations, not 200 eligible home sales.** A
positive price, valid PIN, recording date and single-parcel-looking flags do
not establish an arm's-length single-home transfer, true close date, first
public availability, historical feature vintage or commercial-use right.
There are **zero certified sale labels**. The existing private 200-record
review ledger remains the next identity/date investigation; the new private
findings and count partitions can prioritize its unresolved cases without
changing the frozen sample. The custodian inquiry remains unsent.

Replay from the project root in PowerShell:

```powershell
& '.venv/Scripts/python.exe' -m scripts.profile_cook_staged_observations verify --run-dir data/raw/cook_county/parcel-quality-v1-130b5169ff81ccbc
```

The replay requires the authorised, Git-ignored private Cook capture and
staging files. A fresh clone without them must report that dependency rather
than invent a passing replay. U0 and G-US remain **PENDING**; real-market
training, ON mode and international implementation are still blocked by the
applicable gates.
