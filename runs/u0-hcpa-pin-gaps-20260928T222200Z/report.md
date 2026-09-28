# U0 HCPA frozen PIN-gap diagnosis

Requirement: US05/US06/US07/US24. Protocol: [ADR 0018](../../decisions/0018-hcpa-crosswalk-gap-diagnostic.md).
Code commit at execution: `393788f99c335a2fe75bc03f9ff2e05d653fdced`.
Status: **source-quality diagnostic only; automatic joining BLOCKED; U0 pending**.

The diagnostic re-read the unchanged 1,000-row private validation sample,
the excluded 200-row discovery sample, the pinned 2025 and 2026 parcel ZIPs,
and the prior crosswalk aggregate. It recomputed the match categories from
source fields, checked the prior aggregate, and then applied the ADR's frozen
count controls. [Configuration](config.json), [aggregate](aggregate.json) and
[test gate](test_gate.json) record inputs, actual commands and results.
Identifiers and row-level discrepancy flags remain in ignored `data/raw/hcpa/`.

| Frozen sample category | Sale rows |
| --- | ---: |
| Exact 2025 PIN+FOLIO, current PIN nonblank | 983 |
| Exact 2025 PIN+FOLIO, current PIN blank | 1 |
| No exact 2025 control, current PIN nonblank | 11 |
| No exact 2025 control, current PIN blank | 5 |
| **Total** | **1,000** |

The 16 rows without an exact 2025 two-key control split into six unique
FOLIO-only leads and ten with no one-key lead. All six FOLIO-only 2025 rows
have raw all-space PIN fields; their nonblank STRAP values agree with the
predeclared conversion. They remain **leads only** because the exact PIN+FOLIO
rule did not match. Of the 16, 14 sales predate and two postdate the 2025 DBF
header date of 12 September 2025. The header date is file metadata, not
evidence of public availability, and these date counts do not establish why
any control is absent.

All six current PINs that were blank after trimming are raw all-space fields
in unique-FOLIO active parcel records. Five overlap the 2025 FOLIO-only leads;
one has an exact 2025 two-key control. There were no new observed conflicting
or multiply matched candidates in this frozen sample. These findings narrow
manual source questions; they do not resolve a publisher field contract,
dwelling identity, transaction price scope, historical as-of availability or
reuse rights.

The first and replayed public aggregates have identical SHA-256
`4c8df646c8ef1bb9016fcce069545aea85a3ac9efcf90c647814a66cdf41936e`.
The first and replayed private flags have identical SHA-256
`c110c8a065f1348aa51765a042bc3153d18689d38cc1a952e5da73009a91504b`.
The latter files are ignored and contain row ordinals; they must not be
committed. Public artifacts were checked for raw PIN/FOLIO values, prices,
addresses and ordinals before staging.

The [full test log](full_tests.log) records 353 passing tests with no skips.
The [focused log](focused_tests.log) records 15 passing synthetic diagnostic
tests and 86% branch-aware coverage. [Quality checks](quality_checks.log)
record Ruff, package integrity and a scoped dependency audit. The numerical
replay checks passed. No current or historical parcel row was admitted into a
canonical property record, sale label or model feature.

Next action: use the existing private 200-record manual review protocol to
check deed and dwelling identity, prioritising these gap types; obtain the
custodian's confirmation of PIN/STRAP semantics, sale-date meaning, source
publication timing and permitted use. The owner has a ready-to-send inquiry;
delivery has not been verified. Continue other US source qualification in
parallel. G-US and international implementation remain locked.
