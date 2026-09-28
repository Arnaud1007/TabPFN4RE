# ADR 0005: Cook County source feasibility

Date: 2026-09-28

Owner: project implementation

Affected requirements: US02, US05, US06, US07, US08

## Alternatives and evidence

Cook County's [parcel sales](https://datacatalog.cookcountyil.gov/d/wvhk-k5uv) and [improvement characteristics](https://datacatalog.cookcountyil.gov/d/x54s-btds) are official public candidates. The [Assessor's data catalogue](https://datacatalog.cookcountyil.gov/stories/s/Assessor-2025-Open-Data-Refresh/gzdr-q7c4/) describes their uses and known quality limits. The [Assessor's modelling repository](https://github.com/ccao-data/model-res-avm) provides methodological context, but its AGPL code licence is not a data licence.

The official metadata was retrieved without ingesting property rows and saved locally at `data/raw/cook_county/`. SHA-256 checksums and exact dataset IDs are in the source cards. Both API metadata documents have no dataset-specific licence field. The county's [general open-data statement](https://datacatalog.cookcountyil.gov/stories/s/About-Open-Data/pvqg-z4sc/) describes a license-free aspiration where reasonable; it does not establish commercial redistribution rights for these exact extracts. The [county website terms](https://www.cookcountyil.gov/terms-use) include separate content and image conditions. This is a provenance and rights dependency, not a legal conclusion.

The sales source describes `sale_date` as recorded rather than executed and says older dates may have been rounded to the first of a month. Its publication lag can be months. The characteristics source is building-card-level, with multiple cards possible for one PIN/year; `char_bldg_sf` is exterior building area. Tax-year rows do not establish historical first availability. The current extracts can contain corrections and current-year incompleteness.

## Decision

Keep both datasets as U0 acquisition candidates. Do not use the current extract to certify the 90-day pre-close benchmark or to populate historical features as if their tax-year label proved availability. Do not import the county's model code or assume its AGPL licence covers this project's intended use. A scoped research adapter may proceed only after an explicit permitted-use decision and a registered mapping for recorded versus close date, multi-parcel transfers, PIN/year/card cardinality and source availability.

## Next evidence

Determine whether authoritative historical extract snapshots or first-publication timestamps and genuine close/contract dates can be obtained. Verify source-specific reuse terms for research and any future product. Then obtain a small authorised sample, audit at least 200 stratified records, and test one-to-many and many-to-many joins before model training. If these dependencies fail, assess the next official US source rather than silently weakening the origin protocol.
