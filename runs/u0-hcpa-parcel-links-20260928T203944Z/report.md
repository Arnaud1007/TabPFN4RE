# U0 HCPA current parcel linkage audit

Run ID: `u0-hcpa-parcel-links-20260928T203944Z`. Requirements addressed:
US05, US06, US07 and US24. Status: source-quality linkage evidence only;
U0 and G-US remain pending. The [protocol](../../decisions/0016-hcpa-current-parcel-linkage-audit.md)
was recorded before matching the frozen sample. The category correction made
after an initial aggregate scan is disclosed there and below.

Inputs were the ignored 2026-09-25 current parcel ZIP (SHA-256
`968901f963b6424d89ecba757d8c9d6e1117acb3e2228a0d9885461da9c2e3c8`),
the frozen edge-enriched 200-row All Sales sample (SHA-256
`2f26728c37f8218d1bb79ee75e4082fb918665eb2cb4cc287feba7f6250aaec9`),
and the private repeated-document flags (SHA-256
`f7ef4afeabd33825741ec2655747b42bc4ae61b3a1cb25ab0e1093aa91975f33`).
The scan read only selected fields in `parcel_09_25_2026/parcel.dbf` from the
pinned archive. Its header and scan both report 531,612 active parcel rows,
zero deleted rows, 3,152 incomplete PIN/FOLIO keys and zero duplicate
complete two-key rows.

The [aggregate](aggregate.json) finds **0/200 exact PIN+FOLIO matches** and
**200/200 single FOLIO-only leads** on the frozen sample. The subset of 36
sample rows in repeated instrument-number groups has 0/36 exact matches and
36/36 single FOLIO-only leads. There are zero proven identifier conflicts
under the corrected category definition. No parcel was admitted as a joined
record, so DOR agreement, buildings, units, area and sale-reference checks
have no evaluable sample rows; their zero counters must not be read as
favourable or unfavourable results. This edge-enriched sample is not a
county-wide match-rate estimate.

An initial aggregate used the same strict two-key rule but mistakenly
labelled one-key leads as `identifier_conflict` and classified heated area as
a unit count. Code review also found that absent sale references would be
reported as a nonmatch. [The rejected preliminary aggregate](preliminary_aggregate_rejected.json)
is retained for traceability, and its categories are not accepted evidence.
Tests and source code were corrected before the final scan. Both final
aggregate invocations are byte identical, SHA-256
`aa36d164d62c9ce34dd01835667aea08f4573dc4b177473598c2e2c482c32ec9`.
The private row-level flags and their replay are also byte identical,
SHA-256 `c0e393bc25eeb04fd0d97d1ec9ea21a07691306c5952f7f8e7546a1e43629dbc`;
they remain under Git-ignored `data/raw/hcpa/`.

The current 2026 parcel ZIP has a different PIN field width and observed
format from the separately inspected [2025 archive](../u0-hcpa-2025-vintage-20260928T203518Z/report.md).
An empirical conversion was noticed on the same 200 records and therefore
cannot validate itself. [ADR 0017](../../decisions/0017-hcpa-pin-crosswalk-validation.md)
registers a disjoint sample and a separate cross-vintage validation plan.
This run does not establish historical parcel availability, single-home
transaction scope, closing-date semantics or reuse rights. The 200 manual
source-review rubrics still have zero complete entries.

The [test gate](test_gate.json) records 308 passing full-suite tests with no
skips, 15 focused tests, 84% branch-aware coverage for the new script, 88%
for the package, clean Ruff checks, dependency checks and final replay hashes.
The local audit assumes a trusted workspace without a malicious process
renaming its private raw-data directory during execution; the security review
records a low residual path-race and hostile-ZIP availability risk. This
script accepts only SHA-pinned local archives, and no private identifiers or
prices are in the tracked aggregate.
