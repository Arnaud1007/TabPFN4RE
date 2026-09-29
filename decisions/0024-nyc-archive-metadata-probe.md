# ADR 0024: bounded NYC rolling archive metadata probe

Date: 2026-09-29
Owner: project implementation
Affected requirements: US05, US08 and US24
Protocol version: `nyc-archive-metadata-v1`
Status: approved for a read-only U0 source-qualification probe

## Evidence and decision

[ADR 0019](0019-nyc-rolling-archive-correction.md) records dated Export Archive
controls on the NYC rolling-sales portal, but no archived CSV bytes. The
[Socrata archive guide](https://support.socrata.com/hc/en-us/articles/9486838238743-Introducing-Dataset-Archiving)
says selecting Export Archive can start generation. That state change is outside
this read-only audit. An exploratory anonymous GET of the portal's internal
`/api/archival` route returned visible revision metadata, including versions
53-65. An exploratory anonymous HEAD for three corresponding CSV routes was
reported as HTTP 406. These internal routes are observed behavior, not a
documented public archival API or a durable access contract. The platform
documentation does not establish whether HEAD on the CSV route can start
generation.

Capture the revision metadata reproducibly with one bounded GET. Do not call
the CSV route, generate an archive, download property rows, infer first row
availability, or call any other endpoint. Archive-byte access needs a
separately reviewed protocol and, if generation is required, explicit approval.

## Frozen request and output rules

1. Make one GET to
   `https://data.cityofnewyork.us/api/archival?id=usep-8jbt&version=1`.
   Enforce a 1 MiB cap while reading the stream and require JSON with at most
   13 entries. Save the exact response bytes by atomic create-new publication
   in ignored private storage before parsing; never overwrite on retry. An
   interrupted or unverified write leaves the run incomplete. Record
   their SHA-256, response status, UTC retrieval time and content type.
2. Require unique positive integer `version` values, boolean `visible`,
   timezone-aware `createdAt` timestamps and integer `startVersion`. These are
   portal revision creation times, not first row publication times. Reject a
   malformed list rather than guessing. Report visible versions in descending
   order and their revision dates. Do not treat a visible revision as an
   available CSV.
3. Set a 15-second timeout, reject redirects, do not send credentials, and
   use only the fixed path and exact dataset ID above. Record only HTTP status
   and `Content-Type` when at most 128 printable ASCII characters. Do not
   persist arbitrary headers, cookies, redirect targets or filenames. An HTTP
   error is an observed failure; a timeout or transport failure makes the
   probe incomplete. Never automatically retry a request with unknown outcome.
4. Write a tracked aggregate containing the probe ID, protocol version,
   metadata hash, visible revision dates/versions, command, exit code and
   observed limitations. The raw GET body remains private.
   A replay parses the saved bytes without network access. No property rows,
   addresses, prices or CSV bytes enter tracked artifacts.

Tests must demonstrate fixed-host/path enforcement, caps, redirect rejection,
malformed metadata failure, duplicate-version failure, private raw preservation
and offline replay. Commit and push the reviewed collector before executing the
bounded metadata capture. Retain failed runs and do not reclassify the earlier
406 observations as proof that no archive exists through another route.

## Limits

An archive retrieved later could at most show records known by its archive
timestamp. It would not show the first availability of each row without
further evidence. Current property attributes and sale-date semantics also
remain unqualified. This probe cannot certify a historical as-of feature,
transaction label, reuse right, model score, U0 or G-US.
