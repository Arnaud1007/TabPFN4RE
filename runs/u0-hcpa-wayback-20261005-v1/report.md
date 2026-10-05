# Hillsborough archived parcel listing check

Date: 2026-10-05. Result: **listing bounded, exact ZIP vintage unresolved**.
No model was trained or scored. U0 and G-US remain PENDING.

The [Internet Archive CDX response](capture_manifest.json) returned six
successful page captures for the HCPA shapefile-archive listing in 2025-26.
The saved 8 August 2025 page (24,635 bytes; SHA-256 `d78f4affc4c844cb4773fb746cd5d03bd2a12a3d7a5da173244e88b7cdba8b3f`)
did not list `2025_10_parcels.zip`. The saved 15 April 2026 page (25,240
bytes; SHA-256 `26048d8006dc2cbd750a9817c65c6f54900735afdd99ffe655d63f329cab03ec`)
did list it as 97 MB, displaying a 7 November 2025 update. The pages and CDX
JSON are kept under ignored `data/raw/hcpa/`; the public manifest contains
only page hashes and aggregate observations. The [current official
listing](https://downloads.hcpafl.org/default.aspx?subfolder=_shapefile_archives)
displays the same filename and update time.

The archived page shows **the filename in its 15 April 2026 capture**, not
that our September-downloaded ZIP had identical bytes then. The archived
HTML does not contain a binary checksum. The pinned local ZIP hash is
`2c575a9d7f47a0a3d20527f3c2c5bfa88cb9fbdb9f27dfe3fce59d3edec8260c`;
its exact bytes were first verified on 28 September 2026. For the primary
90-day origin, that observation alone cannot support a sale closing before
27 December 2026. No such future outcome is mature as of this report date.

The [All Sales source card](../../data/source_cards/hillsborough_hcpa_allsales.yaml)
still lacks a verified close-date meaning, per-record publication time,
single-dwelling consideration rule and commercial use decision. The selected
200-row transaction audit remains uncompleted. [ADR 0095](../../decisions/0095-hcpa-archive-listing-asof-boundary.md)
records the no-go for a certified historical HCPA model on the current files.

## Actual checks

- Queried the CDX endpoint in the manifest; HTTP 200, six matching capture
  rows. Its saved 1,405-byte response hashed to
  `63a759d44c44fa85f5d97603e55e1a2c37b91f785b5356baa4ea7edc68a02507`.
- Fetched each timestamped replay with `Invoke-WebRequest -OutFile` and HTTP
  200. Hashes and byte counts matched the manifest. Text search found the
  2025 filename absent in August and present with the stated size/date in
  April. The 2024 filename was present in both, checking that the listing
  content was parsed from the intended folder.
- Rehashed the unchanged local ZIP and matched the existing source card.
  Verified all three new capture files are under Git-ignored `data/raw/`.
- Calculated `2026-09-28 + 90 calendar days = 2026-12-27` with Python's
  `datetime.date` and `timedelta`. This is an information-timing boundary,
  not a forecast or a claim about actual sale dates.

**Next:** Seek contemporaneous ZIP bytes or a publisher release/correction
record for the exact version, and resolve the All Sales questions in the
[ready-to-send inquiry](../../data/requests/hcpa_all_sales_inquiry_draft.md).
Capture future source files on first observation. The existing historical
King County research predictor remains runnable now.
