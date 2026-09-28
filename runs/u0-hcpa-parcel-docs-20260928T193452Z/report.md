# U0 Hillsborough parcel archive documentation check

Run ID: `u0-hcpa-parcel-docs-20260928T193452Z`. Status: source-documentation
increment; U0 and G-US remain pending. Requirements addressed: US02, US05,
US06, US07, US08 and US24. No property rows were joined or modelled.

## Source and observed results

The [official HCPA parcel archive listing](https://downloads.hcpafl.org/?subfolder=_shapefile_archives)
displayed annual parcel ZIPs for 2004–2025 and a small readme document on
2026-09-28. The readme was downloaded through the publisher's ASP.NET file
selection, copied unchanged into Git-ignored `data/raw/hcpa/`, and verified at
SHA-256 `b04476ab5586097b1f082a3acc3a135b04fbdb5e0862e9c27003f1f866420020`.
The source card records its name, retrieval date and local path. This is a
documentation snapshot; no annual parcel ZIP or code-name DBF was ingested.
The three source-card versions used here are copied under `source_cards/` in
this run so later card updates do not change this audit's recorded claims.

The readme defines `DOR_C` as primary parcel use and directs readers to
`parcel_dor_names.dbf` for individual code descriptions. It places `0100`
within a list of residential and smaller multifamily codes for which aggregate
room and unit fields are generally accurate, but does not individually name
`0100`. It defines `HEAT_AR`, bedroom, bathroom and unit fields as **totals
over all buildings on a parcel**. These cannot be treated as attributes of one
sold dwelling without a checked parcel-to-building link. The readme warns
that older archive files may lack fields and that fall archives reflect tax
value corrections and appeals. The current download listing shows 2021 update
times for 2004–2021 ZIPs; neither the year in a filename nor the present
listing establishes first publication at a historical prediction origin.

The [official Clerk public-data guide](https://www.hillsclerk.com/records-and-reports/public-data-files)
confirms that daily `D` files include recorded **or modified** instruments and
that at least two months are kept online. A read-only local connectivity check
to the bulk readme timed out after 8.36 seconds (`curl` exit 28); the guide
itself returned HTTP 200 (`curl` exit 0 in 0.42 seconds). Commands and logs
are in [clerk_bulk_head.json](clerk_bulk_head.json) and
[clerk_guide_head.json](clerk_guide_head.json). PowerShell-captured text logs
were converted to UTF-8 with trailing blank lines removed. No bulk file or
layout was downloaded and hashed. The frozen HCPA sample has only one sale date
within the directory range observed earlier; that row remains a partial
spot check, not a complete rubric. The Clerk recording date is not a verified
closing date.

## Verification and limits

The copied readme hash matched the downloaded file; its DOCX XML was opened
with Python's standard `zipfile` module and the relevant definitions were
checked against the extracted text. The three source cards passed `git diff
--check` and a source-document hash/text check. No Python package or model
code changed, so the prior 277-test engineering result remains the latest
code gate. An attempted YAML parse could not run because PyYAML is not in the
locked local environment; the cards were reviewed as text. The exact local
readme, rather than a reconstructed paraphrase, is retained under the ignored
raw-data directory for later verification.

The county code table, reuse rights, historical first availability, exact
single-home transaction scope and close-date semantics remain unverified.
The readme cannot make HCPA All Sales or parcel archives eligible for a
certified as-of model. Continue the 200-record source review and obtain
authoritative field, timing and rights clarification through an authorised
route. The prepared custodian inquiry remains unsent.
