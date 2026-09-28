# ADR 0017: Validate HCPA PIN formats on disjoint sales

Date: 2026-09-28

Owner: project implementation

Affected requirements: US05, US06, US07 and US24

## Discovery is not validation

The pinned 2026 current parcel archive uses `PIN` C(25); the separately
pinned 2025 archive uses `PIN` C(29) and `STRAP` C(22). An exploratory check
of the **same frozen 200 All Sales records used for source audit** found no
exact two-key PIN/FOLIO matches in 2026, but 200 unique FOLIO leads.
A private exploratory comparison suggested a segment reordering between the
29-character formatted sale PIN and current parcel PIN. That comparison did
not produce a reproducible tracked aggregate, so no success count is claimed
for the proposed transformation. It was discovered on the same 200 records,
which makes it an overfit-risk hypothesis, not an accepted mapping. Do not
revise the strict run or count its one-key leads as accepted joins.

## Fixed independent validation sample

Select 1,000 distinct All Sales records from the original pinned archive,
excluding all 200 frozen audit ordinals before ranking. Use the same five
sale-date bands crossed with Q/U and take 100 records per cell. Rank by
SHA-256 of an ASCII string containing protocol version
`hcpa-pin-validation-v1`, source archive SHA-256, seed `43` and one-based DBF
ordinal; choose the 100 lowest ranks per cell. Fail if any cell is short or
the exclusion set cannot be reconciled. Store selected row-level identifiers
only under ignored `data/raw/hcpa/`; publish aggregate cell counts and hashes.
This sample must be frozen before testing either mapping.

## Comparisons and adoption rule

First compare raw, trimmed text PIN+FOLIO against the 2025 ZIP's `PIN` C(29)
and `FOLIO` C(10). Report missing, redacted, zero, one and many exact matches,
one-key leads, conflicting candidates and duplicate keys. Do not let a
single-key lead count as a confirmed join. Also compare each exact 2025
match's `STRAP` C(22) with the candidate transform below.

For a formatted All Sales PIN, remove only the source's presentation
punctuation under a documented fixed-format ASCII guard, yielding the
candidate 22-character `sale_alnum`. The discovered candidate is:

```text
sale_alnum[5:7] + sale_alnum[3:5] + sale_alnum[1:3]
    + sale_alnum[7:] + sale_alnum[0]
```

Compare it to the 2025 `STRAP` and the 2026 parcel `PIN` only on this
disjoint set, using FOLIO as a separate consistency check. Report transform
success, malformed inputs, blank current PINs, collisions, multiple parcel
rows, and cases where PIN and FOLIO point to different records. A validated
format rule requires at least 99% exact agreement with nonblank `STRAP` among
uniquely exact-matched 2025 parcel controls, plus zero unexplained conflicts
and zero duplicate transformed keys in the observed validation set. Report
2026 archive agreement separately on the subset with a unique FOLIO lead
and a nonblank parcel PIN; do not hide missing parcel PINs in that denominator.
Any failure remains visible and blocks automatic
join promotion until investigated. No property or sale is made eligible by
passing this identity check.

The 2025 and 2026 comparisons are separate vintage-specific experiments.
Neither archive's year, ZIP timestamp or current listing metadata proves
first availability at past valuation origins. The mapping is empirical; the
official field descriptions distinguish formatted PIN and unformatted
STRAP but do not document this exact segment permutation. Seek custodian
confirmation before treating it as a source contract for production.

## Privacy and auditability

Hash all input archives and private sample files. Keep row-level identifiers
and discrepancy flags only under ignored raw storage. Publish counts and
denominators, selected-source schema hashes, run commands and a replay path.
Do not use target price to decide a match. A mismatch in label scope, rights,
close-date meaning or historical availability remains a separate blocker.
