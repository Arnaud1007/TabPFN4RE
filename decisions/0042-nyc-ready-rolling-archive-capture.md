# ADR 0042: capture one already-generated NYC rolling archive

Date: 2026-10-01
Owner: project implementation
Status: approved for a bounded read-only U0 source capture
Protocol: `nyc-ready-rolling-archive-v1`
Requirements: US05, US08, US22, US24

## Evidence and choice

The [Socrata archive guide](https://support.socrata.com/hc/en-us/articles/9486838238743-Introducing-Dataset-Archiving)
distinguishes generation by **Export Archive** from downloading a version
whose green completion control is already available. ADR 0024 intentionally
excluded CSV retrieval until a separate protocol existed. The NYC portal's
[current JavaScript bundle](https://cdn.socrata.com/frontend/S26-HF-0/javascripts/build/shared/common.js)
(`S26-HF-0` `common.js`, inspected 2026-10-01)
uses `PUT /api/archival?...method=createArchive` to start generation, `GET
/api/archival?...method=status` to check it, and `GET
/api/archival.csv?...method=export` to download. These are observed internal
routes, not a documented durable public API.

An exploratory read-only status check on 2026-10-01 returned `done` for
versions 53-62 and `not_started` for 63-65. The version-62 status named
the backend dataset `foxtrot.67157`; pin that identity as an additional
control. A HEAD on the version-62 export
returned HTTP 200 and `text/csv`; it did not retrieve CSV bytes. The already
captured official archival metadata lists version 62 as visible with portal
`createdAt=2026-04-20T18:29:25.966Z`. These observations justify one
bounded GET of **version 62**. They do not prove that the GET will succeed,
that the CSV has the expected schema, or that each row was first published on
the revision date.

This is a source-qualification read under the project's existing bounded
internal-research decision. No public data rows or individual addresses may
enter Git, and no use-specific commercial right is inferred. A 401, 403 or
login request stops the capture; do not bypass access controls.

## Frozen request and validation

Use only `https://data.cityofnewyork.us` and dataset `usep-8jbt`, version 62.
In order: GET `/api/archival?id=usep-8jbt&version=1`, GET
`/api/archival?id=usep-8jbt&version=62&method=status`, GET
`/api/archival.csv?id=usep-8jbt&version=62&method=export`, then repeat the
status and metadata-list GETs. Start the CSV only when the first status is
`done` for version 62 and backend dataset `foxtrot.67157`. Require its visible
metadata record, revision date and status to agree before and after. No PUT,
POST, redirect, arbitrary version,
credential, automatic retry or archive generation is allowed.

Require HTTP 200, expected JSON/CSV content type, identity encoding, bounded
responses and exact fixed URLs. Cap each metadata response at 1 MiB, status
at 4 KiB, CSV at 128 MiB and 150,000 parsed data rows. Use 30-second socket
timeouts and a 240-second elapsed transfer budget; OS resolver/connection
setup can overrun an elapsed budget and must be recorded as incomplete.
Validate strict UTF-8 CSV, unique nonblank headers, the normalized fields
`borough`, `address`, `sale_price` and `sale_date`, and consistent field
counts. The header check establishes structure only, not column semantics.
Do not compare archive rows with the current mutable view count.

Save exact responses with hashes in a new direct child of ignored
`data/raw/nyc_dof/`, with a checked private ACL. The run directory and every
file are create-only. Save a manifest last, after all five responses and the
derived aggregate validate. A failed or interrupted run stays incomplete;
never overwrite its directory. Offline replay checks response hashes,
registered request order, code/configuration identity, CSV grammar and the
derived aggregate without network access. Publish only a fixed projection:
version, revision date, retrieval time, byte count/hash, row count, header
fingerprint, status and gate flags. No property rows or raw metadata enter a
tracked run directory. Commit and push reviewed code/tests before live GET.

## Interpretation

A verified archive may establish that its records were present in the
reconstructed version associated with 2026-04-20. Confirm the reconstructed
version's public-history semantics before admitting a historical as-of join;
the revision timestamp is not each row's first-publication timestamp. Even a
successful capture does not establish `SALE DATE` as a close date, identify
single-home consideration, resolve units, prove historical attribute vintages
or grant commercial product rights. NYC certified sale labels remain zero and
U0 and G-US remain pending.
