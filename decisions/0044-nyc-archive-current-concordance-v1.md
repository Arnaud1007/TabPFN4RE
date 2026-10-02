# ADR 0044: compare the pinned NYC archive and current snapshot

Date: 2026-10-02
Owner: project implementation
Status: frozen before the first private row comparison
Protocol: `nyc-archive-current-concordance-v1`
Requirements: US05, US06, US08, US22, US23, US24

## Question and inputs

Determine how many complete source-row representations occur in both the dated
NYC rolling archive and the separately captured current export. This is a
source-version diagnostic, not transaction identity resolution or model data.
Pin these immutable inputs:

| Input | SHA-256 | Bytes | Data rows |
| --- | --- | ---: | ---: |
| Ready archive, version 62, portal revision 2026-04-20 | `0746355101b245fb469ce97e19e088fa2b16f0f95728d7a5b07dd670e98c345f` | 11,302,195 | 81,567 |
| Current rolling snapshot, captured 2026-09-28 | `84c06057c52a2822f982cd98fb77ef7edf2c14134d00f46b073d2e4b762b2ef2` | 10,397,977 | 82,345 |

The archive public manifest SHA-256 is
`a85186c249503435494e9c06e4274bbea85d986bba058375cbe7d3537b6e01bc`.
The current `snapshot.json` SHA-256 is
`45049ce1622ba4a819f29c79097869c9f3601d049139869982ec7327ee11962b`.
The archive is private at the fixed `ready-archive-v2-20261002T210520Z`
run directory. Resolve the current filename only through its pinned manifest.
Reject changed manifests, CSV hashes, sizes, row counts, ACLs or file links.

## Exact schema mapping

The current file uses the following display headers in this exact order. Each
line gives its corresponding archive source field ID. The archive header has
the same 21 IDs in the separate exact order shown below. Do not infer the map
by position or by punctuation normalization.

| Current display header | Archive field ID |
| --- | --- |
| BOROUGH | borough |
| NEIGHBORHOOD | neighborhood |
| BUILDING CLASS CATEGORY | building_class_category |
| TAX CLASS AT PRESENT | tax_class_at_present |
| BLOCK | block |
| LOT | lot |
| EASE-MENT | ease_ment |
| BUILDING CLASS AT PRESENT | building_class_at_present |
| ADDRESS | address |
| APARTMENT NUMBER | apartment_number |
| ZIP CODE | zip_code |
| RESIDENTIAL UNITS | residential_units |
| COMMERCIAL UNITS | commercial_units |
| TOTAL UNITS | total_units |
| LAND SQUARE FEET | land_square_feet |
| GROSS SQUARE FEET | gross_square_feet |
| YEAR BUILT | year_built |
| TAX CLASS AT TIME OF SALE | tax_class_at_time_of_sale |
| BUILDING CLASS AT TIME OF SALE | building_class_at_time_of |
| SALE PRICE | sale_price |
| SALE DATE | sale_date |

The exact archive header order is: `neighborhood`, `building_class_category`,
`lot`, `ease_ment`, `building_class_at_present`, `address`,
`apartment_number`, `borough`, `residential_units`, `commercial_units`,
`total_units`, `gross_square_feet`, `block`, `tax_class_at_time_of_sale`,
`building_class_at_time_of`, `land_square_feet`, `sale_date`,
`tax_class_at_present`, `sale_price`, `year_built`, `zip_code`.
The SHA-256 of the UTF-8 JSON array of `[current header, archive field ID]`
pairs in current-header order, with ASCII JSON escaping and compact
separators, is
`f24b1f0b7cff5f0de6fe71bf7306c6bd908de3b54715bf1536f50f161c5d2b8c`.
Require exact header order, unique nonblank fields, strict UTF-8 and 21 fields
per record. Reorder archive values into the current display-header order.

## Comparison and interpretation

For each row, trim outer Unicode whitespace in each of the 21 strings. The
raw tier compares complete reordered tuples as a **multiset**: the overlap is
the sum of minimum multiplicities. Archive-only and current-only residuals
must reconcile to their full source counts. Do not use row order, address
similarity or a price-nearest match.

The second tier changes only `SALE DATE`: accept exact `YYYY-MM-DD`,
`MM/DD/YYYY`, or `YYYY-MM-DD[T ]00:00:00` with zero to six zero fractional
digits, and only calendar dates from 1900-01-01 through 2026-10-02. Convert
valid dates to ISO calendar strings. An invalid date excludes that row from
this tier and is counted separately; it does not invalidate the raw tier.
Other values, including sale price, remain exact trimmed strings. The older
NYC representation parser is not reused because its date window begins in
September 2025 and could silently omit archive history. Record date-eligible
denominators, overlap and residuals separately; verify all arithmetic.

A shared tuple means two representations have the same 21 values under the
declared rule. A residual may be an addition, removal, correction, changed
format or duplicate. No stable source transaction ID is present, so this run
must not classify residuals as economic transfers or infer first publication.
It must not create certified labels, features, a temporal split or training
rows. The archive revision time is at most a candidate conservative known-by
bound pending confirmation of archive reconstruction semantics.

The official borough workbooks were retrieved in September and provide an
independent representation of the current period, not an April vintage.
Existing v1/v2 borough concordance covers that comparison. Do not combine
pairwise matches transitively or make workbooks a third denominator in v1.

## Resources, privacy and execution

Work offline with no network calls. Cap each CSV at 128 MiB and 150,000 data
rows, each field at 16,384 characters, and total cell characters at 64
million per file. Reject malformed tails and any source change during read.
Hold source strings only in memory. Private output may contain aggregate
counts, input hashes and run provenance; it must contain no source row,
address, unit, price, date, row ordinal or per-row fingerprint. Public output
contains exact source denominators and **bucketed** overlap results only:
`zero`, `suppressed_1_to_4`, `5_to_99`, `100_to_999`, or `1000_plus`. This
avoids publishing derivable small residuals and cross-tier differences.
Do not publish per-borough or field-level counts in v1. Both private and public
results state zero certified labels and false historical-as-of eligibility.

Create an ACL-protected, Git-ignored run directory and write an intent with
a clean code commit matching the local `origin/audit/u0` tracking ref,
configuration/code/environment/input hashes before
opening either CSV. Write outputs create-only, mark interrupted runs
incomplete, and provide exact offline replay. A public verifier checks private
hashes and replay without exposing row values. Synthetic RED tests cover
schema mapping, duplicate multiplicities, date boundaries, invalid rows,
CSV failures, hash tampering, privacy and replay/no-overwrite. Require at
least 80% branch-aware coverage for new code, full suite, Ruff, dependency
check and code/Python/security review. Commit and push reviewed code before
the private comparison, verify the actual remote ref with `git ls-remote`,
then push only redacted evidence afterward. The runner itself makes no
network request.

U0 and G-US stay **PENDING**, with `sale_labels_certified: 0`. Dataset-specific
rights, sale-date meaning, first row availability, unit/transfer identity and
the remaining 190 manual source rubrics remain separate blockers.
