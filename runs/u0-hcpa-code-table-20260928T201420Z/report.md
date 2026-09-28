# U0 HCPA current parcel code-table audit

Run ID: `u0-hcpa-code-table-20260928T201420Z`. Requirements addressed: US05,
US07 and US24. Status: source metadata verified; U0 and G-US remain pending.
No HCPA sale rows were joined, relabelled, admitted to an eligible cohort or
used for model training.

The [HCPA download page](https://downloads.hcpafl.org/) listed
`parcel_09_25_2026.zip`. The downloaded file remains under Git-ignored
`data/raw/hcpa/`; it is 131,850,054 bytes with SHA-256
`968901f963b6424d89ecba757d8c9d6e1117acb3e2228a0d9885461da9c2e3c8`.
ZIP integrity passed. The only `parcel_dor_names.dbf` member is
`parcel_09_25_2026/parcel_dor_names.dbf`, 16,818 bytes, SHA-256
`0df47f3ba5b380d4e6b81994422023fa596ff3499ef38f0f4ba749494028e54d`.
Its dBASE III header declares 304 rows; all 304 are active. The field contract
is `DORCODE` C(4) and `DORDESCR` C(50).

The pinned, read-only [audit command](../../scripts/audit_hcpa_code_table.py)
emitted [aggregate.json](aggregate.json). It confirms current labels `0100`
→ `SINGLE FAMILY R`, `0400` → `CONDOMINIUM`, and `0800` → `MFR <10 UNITS`.
The command does not open `parcel.dbf` or export parcel identifiers, owner
names, addresses or individual sale rows. A second invocation wrote
[aggregate_replay.json](aggregate_replay.json); the two outputs are byte
identical with SHA-256
`f71a0d5a1c486d6179134047475fb848dc0bf105586ebf18473062a52349d51b`.

The current lookup corroborates the previously audited DOR manual. It does
not establish historical code meanings or first publication, an All Sales to
parcel join, single-dwelling transaction scope, true closing dates or rights
for commercial AVM use. The downloaded ZIP is not a certified historical
feature source. The frozen 200-record HCPA sample still has zero complete
manual-review rubrics.

The [test gate](test_gate.json) records 293 passing full-suite tests, 16
focused code-table tests, 88% branch-aware coverage for this script and 88%
for the Python package, clean Ruff checks, dependency checks and the exact
output files. An initial format check and a combined coverage-report command
failed; formatting was applied and separate package/script coverage commands
passed before this final audit output was regenerated. Review found and fixed
a possible file-replacement race before the final run. The final script hashes
and reads the ZIP through the same handle and checks that hash again after
parsing.

Next, audit identifier cardinality between the frozen 200 All Sales sample
and the current parcel ZIP, keeping row-level discrepancies under ignored
`data/raw/hcpa/`. That is a contemporary cross-check only. Historical
vintages, manual source review, date meanings, publication lag and reuse
rights remain separate dependencies.
