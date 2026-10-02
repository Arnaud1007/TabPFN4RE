# ADR 0047: bounded capture of NYC rolling archive version 61

Date: 2026-10-03
Owner: project implementation
Status: approved for code and synthetic tests; live CSV capture requires reviewed code pushed first
Protocol: `nyc-ready-rolling-archive-v61-v1`
Requirements: US05, US08, US22, US24

## Evidence and decision

The [saved publisher revision inventory](../runs/u0-nyc-archive-metadata-20260929T021258Z/aggregate.json)
lists version 61 as visible, created `2026-01-27T14:48:20.467Z`, with
`startVersion=60`. A bounded exploratory anonymous status GET on 2026-10-03
to `https://data.cityofnewyork.us/api/archival?id=usep-8jbt&version=61&method=status`
returned HTTP 200, JSON content type, 245 bytes and SHA-256
`19f0d47313ab5e129a39837867cba77bc5f0459f33a1cf91856b90c58b6bfa35`.
Its exact six-field status reported `done`, dataset `foxtrot.67157`, version
61, `rowLocation=compressed/materializations/v3/foxtrot.67157/61/rows`,
`columnLocation=compressed/materializations/v3/foxtrot.67157/61/columns`,
positive `refSize=4473824` and `gzipped=true`. This probe retrieved no CSV.

Capture version 61 as the adjacent earlier publisher vintage to the verified
version 62. A later, separately frozen comparison may bound changes between
those reconstructed releases. Do not infer per-row first publication or
economic-transfer identity from the revision timestamp or a matching row.

The existing version-62 collector's saved replay binds its exact code bytes.
Changing it would invalidate that immutable evidence. Create a separate
version-61-only collector that reuses its generic, checked parsing, CSV and
private-storage helpers. Do not duplicate the entire collector, mutate its
module globals, add an arbitrary version flag or reinterpret v62 artifacts.

## Frozen capture contract

Use exactly five anonymous GETs, in order: archive list (`version=1`), v61
status, v61 CSV export, v61 status, archive list. The collector must reject a
missing or changed pinned list entry or non-`done`/changed status before
starting the CSV. Require the exact v61 backend dataset and row/column paths;
`refSize` must be a positive integer within the 128 MiB cap, and `gzipped`
must be true. The two status responses and selected list records must agree.
No PUT, POST, archive generation, redirect, credential, automatic retry or
arbitrary URL is allowed. A 401, 403 or login response stops the run.

Retain ADRs 0042 and 0043's response limits and integrity checks: at most
1 MiB list JSON, 4 KiB status JSON, 128 MiB CSV, 150,000 strict CSV data rows,
30-second socket timeout and 240-second CSV transfer budget. Require HTTP 200,
expected content types and identity HTTP encoding. Preserve exact response
bytes and timestamps in a new create-only ACL-protected, Git-ignored direct
child of `data/raw/nyc_dof/`. Save the manifest last; failures remain
incomplete. Bind v61 code, imported v62 helper code, environment and resolved
configuration hashes. Offline replay validates raw bytes and all identities
without network access. Publish only a bounded aggregate with version,
revision date, retrieval time, byte and row counts, hashes, and gate flags.

## Tests and interpretation

Write synthetic RED tests before implementation for fixed request order,
valid capture and replay, wrong/missing/hidden version, malformed or changed
status, response tampering, redirected CSV and no manifest on partial failure.
Verify existing v62 tests and the saved v62 replay still pass. Review code and
security, then commit and push code before one live v61 capture.

The captured archive is source inventory only. It cannot establish a true
closing date, first row availability, historical property attributes,
dwelling-level consideration, commercial rights, or the US11 24-month
historical feature floor. Certified NYC sale labels remain zero; U0, U3 and
G-US remain PENDING.
