# NYC ready archive v61 capture plan

Run ID: `u0-nyc-ready-archive-v61-20261002T230327Z`  
Frozen: 2026-10-02 23:03:27 UTC, before the live CSV GET  
Status: planned; no v61 CSV requested by this run yet  
Protocol: `nyc-ready-rolling-archive-v61-v1`, [ADR 0047](../../decisions/0047-nyc-ready-archive-v61.md)  
Collector code commit: `0e0fb29f50a75d42bbd337845de87dc92a0a5c7c`

## Fixed operation

Run the reviewed, pinned `scripts/capture_nyc_generated_archive_v61.py`
once with action `capture` and private directory
`data/raw/nyc_dof/ready-archive-v61-20261002T230327Z`. It must request only
the five GETs in ADR 0047: version list, v61 ready status, v61 CSV export,
ready status, version list. The status must remain `done` with the exact
registered backend dataset and storage paths. The version-list entry must
remain visible with the pinned 2026-01-27 creation timestamp. Never request
`createArchive` or retry an incomplete capture under this run ID.

Raw metadata and CSV remain Git-ignored with private ACL. Stop on redirect,
login, changed status, malformed CSV, failed integrity check, or exceeded
limits. Cap CSV at 128 MiB and 150,000 data rows, with a 30-second socket
timeout and a 240-second transfer budget. The free C: disk observation just
before freezing was 362,610,688 bytes, above the CSV cap; check again before
capture. No paid service or credential is used.

## Acceptance and interpretation

After capture, run the collector's offline `replay` action, verify saved
hashes and request chronology, and publish only a bounded aggregate and a
report. Keep failed or incomplete files; do not relabel them as a success.
The archived version is source inventory only. It cannot certify historical
first availability, closing dates, transfer identity, attributes or rights.
NYC certified sale labels remain zero; U0, U3 and G-US remain PENDING.

Exact commands from the project root after this plan is pushed:

```powershell
git status --short --branch
.\.venv\Scripts\python.exe scripts/capture_nyc_generated_archive_v61.py capture data/raw/nyc_dof/ready-archive-v61-20261002T230327Z
.\.venv\Scripts\python.exe scripts/capture_nyc_generated_archive_v61.py replay data/raw/nyc_dof/ready-archive-v61-20261002T230327Z
```
