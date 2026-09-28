# U0 HCPA document-group source audit

Run ID: `u0-hcpa-document-groups-20260928T181606Z`

Status: **verified source-quality increment; U0 and G-US pending**. Requirements
addressed: US02, US05, US07, US22, US23 and US24. No modelling cohort, target
or performance score was created.

## Objective and method

Count repeated Clerk instrument identifiers in the unchanged HCPA All Sales
archive, then identify which of the frozen 200 manual-review rows need extra
transaction-grain scrutiny. [ADR 0015](../../decisions/0015-hcpa-document-group-audit.md)
freezes exact trimmed, nonblank `DOC_NUM` grouping. Blank values are ungrouped;
finite decimal amounts are normalised for equality. All parcel identifiers and
row-level flags remain in Git-ignored `data/raw/hcpa/`. The tracked
[aggregate](aggregate.json) contains counts only.

## Observed results

| Measure | Full source |
| --- | ---: |
| Active DBF rows | 2,453,187 |
| Blank instrument-number rows | 269,947 |
| Nonblank instrument-number rows | 2,183,240 |
| Distinct nonblank instrument groups | 1,784,697 |
| Singleton groups | 1,730,847 |
| Repeated groups | 53,850 |
| Rows in repeated groups | 452,393 |
| Largest group | 2,294 rows |
| Repeated groups with a repeated valid amount | 53,689 |
| Repeated groups with differing known parcel identifiers | 53,749 |
| Repeated groups with differing valid amounts | 290 |
| Repeated groups with differing sale dates | 699 |

Counts reconcile with the previous source profile: 269,947 + 2,183,240 =
2,453,187; 1,730,847 singleton rows + 452,393 repeated-group rows =
2,183,240. Among the **edge-enriched, nonrepresentative** 200-row sample, 19
rows have blank instrument numbers, 145 are in singleton groups and 36 are in
repeated groups. All 36 repeated-group sample rows have a repeated valid amount
and differing known parcel identifiers within their instrument group. These
are review leads, not 36 confirmed multi-property transfers.

The full [group-size histogram](aggregate.json) includes 723 groups with more
than 100 rows. A repeated identifier can reflect one transfer covering several
parcels, repeated consideration, corrections or other source semantics. Neither
this scan nor the instrument number alone proves a duplicate economic sale,
single-property price, eligible residence or recorded closing date. The 200
manual rubrics remain at zero complete; one earlier Clerk comparison is partial.

## Executed checks and provenance

[scan_execution.json](scan_execution.json) gives the exact scan command,
38.183-second duration and exit code 0. The second full scan took 37.606
seconds with exit code 0. The aggregate SHA-256 is
`1ed92d5eaedb13b4008bd1a2a42a766754eb64336e59984bed76d9b18da0f9f7`;
both aggregate files and both private sample-flag files reproduced byte for
byte. The private flags contain 200 rows, are Git-ignored, and no disposable
SQLite spool remains. [manifest.json](manifest.json) records source, sample,
script, test, configuration and environment hashes. The run used the pinned
source archive; the working tree was dirty because the new audit code was under
review at execution.

[test_gate.json](test_gate.json) lists command, exit code, duration and log for
each check. Fourteen synthetic tests and the full 259-test engineering suite
passed with zero skips. The new audit script has 87% combined statement and
branch coverage. Ruff lint/format, the scoped pinned dependency audit,
executable [artifact verification](verify_artifacts.ps1), aggregate-schema
check and count reconciliation passed. The dependency audit
was `--no-deps` and is not a full transitive vulnerability audit. Code, Python
and security reviewers found no remaining critical or high issue. A hard
process crash between the two output installs can leave the private flags
alone; a rerun refuses overwrite, requiring verified manual recovery.
Three PowerShell-captured logs had whitespace-only separator lines normalised
for Git; substantive command output is unchanged.

The tests first failed because the profiler module did not exist. During
implementation, a resource-limit review identified an assumed SQLite page
size; the code now reads and verifies the actual page size. Fault-injection
tests cover timeout and spool-limit cleanup after rows are inserted. The two
full pinned-source scans themselves completed without failure. No failed run
was turned into a valid source or model score.

## Gate effect and next action

This source-quality result does not verify `S_DATE` as closing, historical
first availability, single-dwelling consideration or commercial AVM reuse
rights. It cannot train a certified 90-day as-of model. Prioritise the 36
sampled rows in repeated instrument groups for deed/parcel review while
completing all 200 rubrics. The drafted custodian inquiry remains local and
unsent. U0 and G-US stay pending; Part II remains locked.

Resume the evidence check from the project root with:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File runs/u0-hcpa-document-groups-20260928T181606Z/verify_artifacts.ps1
Get-Content next_action.md
```
