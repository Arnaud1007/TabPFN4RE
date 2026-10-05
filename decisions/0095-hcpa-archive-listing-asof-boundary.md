# ADR 0095: An archived HCPA listing does not date the local parcel ZIP's bytes

Date: 2026-10-05. Owner: Arnaud. Status: adopted for the current local copy.
Affected requirements: US05, US08, US24. Protocol: `hcpa-2025-parcel-archive-listing-v1`.

## Evidence

An Internet Archive capture of the [HCPA archive listing](https://web.archive.org/web/20250808150017id_/http://downloads.hcpafl.org/Default.aspx?subfolder=_shapefile_archives)
on 8 August 2025 does not list `2025_10_parcels.zip`. A separate [capture on
15 April 2026](https://web.archive.org/web/20260415105851id_/http://downloads.hcpafl.org/Default.aspx?subfolder=_shapefile_archives)
does list that name, 97 MB, with a displayed 7 November 2025 update time.
The captured pages and CDX response are saved unchanged under Git-ignored
raw storage with hashes in the [evidence report](../runs/u0-hcpa-wayback-20261005-v1/report.md).

The April page establishes that an archive with this name was listed by that
capture date. It supplies no checksum or contents for the ZIP. The exact
local `2025_10_parcels.zip` bytes, SHA-256
`2c575a9d7f47a0a3d20527f3c2c5bfa88cb9fbdb9f27dfe3fce59d3edec8260c`,
were first verified from the live official site on 28 September 2026. A
file's embedded September 2025 timestamp and the current page's displayed
November 2025 update time do not establish when those exact bytes were
publicly available or whether later corrections occurred.

The accompanying All Sales file still describes `S_DATE` only as date of
sale. Its first publication per record, one-dwelling price scope and reuse
rights remain unresolved. Repeated instrument-number groups require review;
the selected 200-record source audit has zero completed rubrics. These are
separate blockers even if the parcel ZIP vintage is later verified.

## Decision

Do not certify a 90-day OFF historical feature from the current local 2025
parcel ZIP merely because its filename appeared in April. With exact content
first verified on 28 September 2026, a sale whose origin is 90 days later
cannot close before 27 December 2026; no such outcomes have matured as of
5 October 2026. No HCPA model is trained or scored under this decision.

Retain the April listing as a useful provenance lead. To admit an earlier
origin, obtain the contemporaneous ZIP bytes/checksum or publisher release
and correction record for the exact version. Resolve sale event meaning,
single-home consideration, rights and the manual audit before certification.
Capture future source files at observation time to create prospective
availability evidence.

## Rejected shortcuts

- Backdate the September-downloaded bytes to the archive year or the displayed
  update date without proof of byte identity.
- Treat a parcel's `S_DATE` or `S_AMT` as a pre-origin attribute.
- Treat repeated All Sales rows or one parcel-use code as verified single-home
  sales without transaction and dwelling checks.
