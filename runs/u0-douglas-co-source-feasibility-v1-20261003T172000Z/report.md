# U0 Douglas County source feasibility: metadata-only checkpoint

Run ID: `u0-douglas-co-source-feasibility-v1-20261003T172000Z`
Date: 2026-10-03
Code base commit: `c0a6926614c8558541d38ed7a3a34076e3426ecf`
Requirements: US02, US05, US06, US08, US24
Status: **candidate only; U0 and G-US PENDING; zero certified sale labels**

## Objective and actual work

Inspect a possible Western US transaction and property-attribute source while
King County's terms remain unresolved. Read the official [Douglas County
Assessor Data Downloads](https://www.douglasco.gov/assessor/data-downloads/),
[Assessor FAQ](https://www.douglasco.gov/assessor/about/assessor-faqs/) and
[County Open Data Guidelines](https://www.douglasco.gov/documents/open-data-guidelines.pdf/).
Issue exactly two HTTP `HEAD` requests with `Invoke-WebRequest -Method Head
-TimeoutSec 20 -UseBasicParsing`; save only response metadata. No sales,
party names, addresses or improvement rows were downloaded. The actual
response URLs, UTC observation times, HTTP statuses and headers are in
[head_metadata.json](head_metadata.json).

| File | HEAD status | Content-Length | Last-Modified |
| --- | ---: | ---: | --- |
| Property Sales | 200 | 97,830,143 bytes | 2026-10-01 15:59:58 GMT |
| Property Improvements | 200 | 45,358,468 bytes | 2026-10-01 15:48:24 GMT |

The official page displays **Last Updated 2026-10-01** and **Next Update
2026-11-02** and limits downloads to **active accounts only**. It calls sales
information parcel-linked and lists `Account_No`, `Sale_Date`, `Sale_Price`,
`Deed_Type` and recording references, plus grantor and grantee names. The
improvement file lists `Account_No`, `Building_ID`, physical and area fields.
The page disclaims accuracy and timeliness. The FAQ's adjusted sale-price
description concerns assessor valuation and does not define the raw download
field. A one-to-many account/building join, inactive-account omission and
current attributes are material risks for a historical model.

The County Open Data Guidelines allow unrestricted use for data on its Open
Data Portal, but the direct assessor text downloads are not explicitly
identified there as portal datasets. Commercial AVM and redistribution rights
for these files remain unconfirmed. The file's Last-Modified header is not a
row's first publication time. `Sale_Date` is not yet verified as closing date;
raw-versus-adjusted consideration, deed multiplicity, correction policy and
historical vintages also remain open. [ADR 0080](../../decisions/0080-douglas-county-western-source-candidate.md)
and the [source card](../../data/source_cards/douglas_county_co_assessor_downloads.yaml)
record the admission boundary.

## Validation and next action

The two HEAD requests completed with status 200 and no response bodies. The
[validation gate](test_gate.json) checks the recorded URLs, method, statuses,
sizes, dates, zero-body flags, YAML parsing and requirement links. There were
no model tests or scores in this run. `data_snapshot_sha256`, split hash,
feature-policy hash and checkpoint identity are null because no property data,
features, split or model were used. The [manifest](manifest.json) hashes the
recorded metadata, configuration and environment record.

The first local validator invocation failed because the source card encoded
`raw_file_sha256` as non-null text. The card was corrected to YAML `null`;
the next invocation passed. An isolated failure-path check also confirmed
that a later validation failure replaces a stale PASS gate with FAIL. These
were artifact-validation checks, not model results or downloaded-data findings.

Seek the publisher's source-specific decision on permitted use and historical
vintages, then define a minimized field allowlist and a frozen 200-record
manual audit before any row-level acquisition or adapter. Continue the Cook,
NYC and legacy U0 work in [next_action.md](../../next_action.md). Douglas
County is a candidate, not an accepted Western metro or G-US market.
