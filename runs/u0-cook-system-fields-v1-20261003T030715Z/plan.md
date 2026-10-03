# Cook County Socrata row-timestamp probe, v1

Frozen before the bounded request on 2026-10-03 UTC.

## Question

Does the official Parcel Sales SODA endpoint expose `:created_at` and
`:updated_at` for a row already in the protected 200-row audit sample? These
are platform row timestamps, not assumed first-publication or transaction
dates. The exact row and system identifiers remain private.

## Input and request limit

- Reuse the immutable sample capture manifest SHA-256
  `130b5169ff81ccbc0a729cba98400f2fb377ff9a25999316aaac1960e38a3cf7`.
- Select one row already in its ACL-restricted worklist. Filter by its pinned
  `row_id`; request only `:id`, `:created_at`, `:updated_at` and `row_id` with
  `$limit=1` from the official `wvhk-k5uv` SODA resource.
- Make one anonymous read-only GET, with a 12-second timeout and a 16 KiB
  response cap. No publisher write endpoint, token, property image, address,
  personal name or sale price is requested.
- Save the exact response privately with a hash, HTTP status and UTC capture
  time. Check that any returned `row_id` equals the pinned source row before
  interpreting fields. An error or timeout is recorded, not silently retried.

## Interpretation

The probe can show whether these fields are exposed for this source row and
their literal values. Socrata documents `:created_at` as platform record
creation and `:updated_at` as last platform update. Full dataset replacement
can alter update timestamps. Neither field, without publisher confirmation or
dated archive evidence, certifies first public availability, historical
property attributes, a closing date or a right to model from the source.

Publish only aggregate status and hashes. Keep row identifiers and timestamp
values in Git-ignored `data/raw/cook_county/`; preserve the zero-certified-label
status regardless of the response.

Official documentation: https://dev.socrata.com/docs/system-fields.html
