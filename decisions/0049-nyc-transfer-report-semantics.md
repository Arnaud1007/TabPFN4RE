# ADR 0049: NYC transfer-report semantics do not establish rolling-file semantics

Date: 2026-10-03
Owner: project implementation
Status: accepted as U0 source-qualification evidence only
Requirements: US03, US04, US05, US07, US08, US24
Affected protocols: none; existing private captures, audit rubrics and split files remain unchanged

## Official evidence

The [NYC RP-5217NYC instructions](https://www.nyc.gov/assets/finance/downloads/pdf/02pdf/rp5217nyci.pdf)
distinguish item 10, Sale Contract Date, from item 11, Date of Sale / Transfer.
Item 11 is the date title was conveyed and is generally the closing date,
or the deed date when there was no formal closing. Item 12, Full Sale Price,
has its own consideration definition and excludes seller concessions. The
form also has a number-of-parcels field, permits partial parcels, and lists
all transferred borough-block-lot identifiers. Its conditions-of-sale fields
can flag related parties, fractional interests and conditions that may
include foreclosures.

Those are **transfer-report form** definitions. The [DOF property-sales
glossary](https://www.nyc.gov/site/finance/property/glossary-property-sales.page)
defines rolling-file `SALE DATE` only as the date the property sold and
`SALE PRICE` as the price paid. Neither source states that the rolling-file
columns are direct copies of RP-5217NYC items 11 and 12, or that the form
is the only source for every rolling-file property class. This mapping must
be demonstrated by publisher documentation or record-level source evidence
before using `SALE DATE` as a close date or treating one row's `SALE PRICE`
as the consideration for one eligible dwelling.

The [platform's dataset-archiving guide](https://support.socrata.com/hc/en-us/articles/9486838238743-Introducing-Dataset-Archiving)
explains that a prior version can be exported and reconstructed from changes.
It does not establish when each economic transfer first became publicly
available, when an individual field was corrected, or whether every version
was public at its portal revision timestamp. The locally captured versions
61 and 62 are useful dated representations, but their adjacent-row overlap
under [ADR 0048](0048-nyc-adjacent-archive-concordance-v1.md) is not a
first-publication ledger.

## Decision and next evidence

Keep the rolling source at inventory-only status and retain unknown answers
in the manual review rubric. Ask the DOF data owner whether the rolling
columns map to specific RP-5217NYC items, how co-op and multi-parcel sales
are sourced, and whether row-level publication/correction history is
available. For a bounded record-level pilot, compare an official transfer
report or deed with the pinned source row under the instrument controls in
[ADR 0040](0040-nyc-instrument-and-date-evidence-boundary.md). If the
mapping differs by borough, class or period, define separate cohorts before
using labels.

This evidence certifies zero NYC sale labels or historical features. No
90-day pre-close benchmark, U0 completion or G-US passage follows from it.
