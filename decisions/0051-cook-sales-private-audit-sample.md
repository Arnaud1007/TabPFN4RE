# ADR 0051: bounded Cook County parcel-sales audit sample

Date: 2026-10-03

Owner: project implementation

Affected requirements: US02, US05, US06, US07, US08

## Evidence and alternatives

The [Cook County Open Data overview](https://datacatalog.cookcountyil.gov/stories/s/About-Open-Data/pvqg-z4sc/) describes download and API access for independent analysis and an aim to publish data without licence restrictions where reasonable. The [Assessor's catalogue](https://datacatalog.cookcountyil.gov/stories/s/Assessor-2025-Open-Data-Refresh/gzdr-q7c4/) explicitly addresses researchers and real-estate participants. The inspected `wvhk-k5uv` metadata has a null licence field, no additional dataset-specific terms, and buyer/seller names among its columns. The [County terms](https://www.cookcountyil.gov/terms-use) disclaim accuracy and discuss third-party material, especially images. These public statements support a bounded, private source audit; they do not establish rights to redistribute source rows or use them in a commercial release.

The [Assessor's Open Data SOP](https://github.com/ccao-data/wiki/blob/master/SOPs/Open-Data.md) describes sales as parcel-sale rows and says sale document numbers are unique only when `is_multisale = FALSE`. The dataset metadata calls `row_id` a row identifier, but that is not a proven one-home transfer key. The same metadata contains conflicting statements about whether sales remain filtered after the 2023 change. `sale_date` is a recording date; first row availability and close date are absent.

Options considered: remain at metadata-only inventory, capture a small private audit sample, or export the full dataset. Metadata alone cannot test row-level price, date, flag and transfer semantics. A full export is premature, includes personal names by default, and would not fix historical availability. The bounded sample limits data handling while testing those questions.

## Decision and frozen v1 protocol

Permit **internal, private source qualification only** for at most 200 selected parcel-sale rows. No source row, PIN, document number, address or name may enter Git or a public report. This is an operational permitted-use decision for the specified research audit, not a legal conclusion about a product. Commercial model use, redistribution, and any expanded acquisition remain pending source-specific review. No training or certified 90-day historical labels are admitted from this sample.

Use the official `wvhk-k5uv` API and bracket the capture with source metadata and ten cell counts. The ten disjoint cells cross two recorded-date intervals, `[2015-01-01, 2020-01-01)` and `[2024-01-01, 2026-01-01)`, with five sale-price intervals: `< 10000`, `[10000, 100000)`, `[100000, 300000)`, `[300000, 1000000)`, and `>= 1000000`, all in source USD. These include nominal and high-price cases deliberately. They are not a random or representative sample. If any cell has fewer than 20 rows, stop and version a revised protocol before viewing its sampled rows.

For each cell, sort by `row_id ASC` and capture two ten-row slices with offsets `floor((n-20)/4)` and `10 + floor(3(n-20)/4)`. Select only `row_id`, `pin`, `year`, `township_code`, `nbhd`, `class`, `sale_date`, `is_mydec_date`, `sale_price`, `doc_no`, `deed_type`, `mydec_deed_type`, `is_multisale`, `num_parcels_sale`, `sale_type`, and the three `sale_filter_*` fields. Never request `buyer_name` or `seller_name`. Preserve validated response bytes, exact query URLs, HTTP evidence, UTC capture times and SHA-256 hashes in Git-ignored `data/raw/cook_county/`. Publish aggregate counts and hashes only. Validate 200 unique row keys, exact cell membership, response shape, source version and counts before marking capture complete. A matching metadata/count bracket is a consistency check, not an atomic snapshot or proof of first publication.

Protocol v1 is single-use. An exclusive, retained private claim file blocks another capture, including concurrent invocations or a retry after a crash. On failure, inspect the private incomplete directory and record the cause; a retry that could select other rows needs a new, versioned protocol and a revised data-handling decision. Rejected row responses containing unrequested fields are not written. The offline verifier accepts only a completed direct child of the private raw root and replays every source response, count, query and sample membership under byte caps.

Follow with a manually reviewed 200-row ledger and a separate bounded anomaly sample for multi-parcel documents, repeated prices/document numbers, missing dates and unusual flags. The audit must inspect official Clerk instruments where available. Unknown evidence remains unknown. No row gains label eligibility merely by passing schema validation.

## Decision boundary

The current API probe showed a bounded count query works, but it did not save rows or establish a historical origin. Source-specific reuse rights, source filtering, true close/contract dates, first publication, economic transfer identity, physical characteristics and PIN/year/card join cardinality remain unresolved. Continue independent US engineering while those dependencies are investigated. G-US remains PENDING.
