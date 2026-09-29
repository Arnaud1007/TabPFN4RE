# ADR 0026: bounded NYC official borough export capture

Date: 2026-09-29
Owner: project implementation
Affected requirements: US05, US07, US08, US22 and US24
Protocol version: `nyc-official-borough-xlsx-v1`
Status: approved protocol for a read-only U0 source-qualification capture; no export captured by this decision

## Evidence and decision

The [NYC Department of Finance rolling-sales page](https://www.nyc.gov/site/finance/property/property-rolling-sales-data.page)
currently offers one Excel file per borough for September 2025 through August
2026. [ADR 0021](0021-nyc-manual-audit-sample.md) froze 200 ordinals from a
separate, pinned NYC Open Data CSV. [ADR 0025](0025-nyc-private-source-review-ledger.md)
requires a separately retrieved official DOF export or recorded instrument
before a reviewer can record a source-row identity match. Capture the five
static DOF workbooks as private, unchanged source evidence for that future
comparison. This is a source acquisition step, not an automatic comparison or
manual-review finding.

The page and file paths are mutable. The capture describes the bytes returned
at the recorded retrieval time, not an immutable September 2025-August 2026
release or a historical snapshot. If any file no longer corresponds to that
period, preserve the captured bytes, mark row comparison blocked and revise
the comparison protocol before use. Successful byte capture alone does not
qualify the workbook period or schema.

## Frozen request set and budget

Issue exactly one anonymous `GET` to each URL below, in this order. No other
request is part of this capture, including a new page fetch, `HEAD`, portal
archive generation or a retry. A failed request or uncertain transport outcome
ends the run as incomplete. A deliberate later attempt receives a new run ID
and never overwrites earlier bytes.

| Borough | Exact URL |
| --- | --- |
| Manhattan | `https://www.nyc.gov/assets/finance/downloads/pdf/rolling_sales/rollingsales_manhattan.xlsx` |
| Bronx | `https://www.nyc.gov/assets/finance/downloads/pdf/rolling_sales/rollingsales_bronx.xlsx` |
| Brooklyn | `https://www.nyc.gov/assets/finance/downloads/pdf/rolling_sales/rollingsales_brooklyn.xlsx` |
| Queens | `https://www.nyc.gov/assets/finance/downloads/pdf/rolling_sales/rollingsales_queens.xlsx` |
| Staten Island | `https://www.nyc.gov/assets/finance/downloads/pdf/rolling_sales/rollingsales_statenisland.xlsx` |

Use HTTPS with certificate verification. Reject redirects, including a final
URL different from the requested URL. Disable environment proxies and send no
credentials, cookies, authorization headers or conditional request headers.
Do not follow links embedded in a response. Require HTTP 200, the exact Excel
OOXML MIME type
`application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` with no
parameters, and identity content encoding. An unexpected status or type is a
failure, not a reason to accept an HTML page saved with an `.xlsx` suffix. Do
not log response bodies, arbitrary headers or redirects.

Limit connection/read timeout to 30 seconds per request, elapsed transfer time
to 240 seconds per file, and the entire capture including ZIP validation to
1,800 seconds. Enforce 16 MiB per file and 80 MiB for the five responses,
checking declared `Content-Length` before reading and actual bytes while
streaming. A missing length is allowed under the streaming cap; a
nondecimal, negative or mismatched declared length fails. Do not retry or
increase a cap within this protocol.

## Private capture and validation

Before the first request, create a new, restricted, Git-ignored directory
`data/raw/nyc_dof/official-exports-<UTC>-<nonce>/`. Refuse symlink or hard-link
redirection, including reparse-point or junction ancestors, and existing
output paths. On Windows, disable inherited access and verify that only the
current user, SYSTEM and Administrators have access; on POSIX require mode
0700. Fail closed on ACL creation or verification, both before the first
private write and during replay. The threat boundary assumes trusted local
processes with the same privilege; static checks cannot defeat a malicious
concurrent directory swap.

Create and fsync an immutable `intent.json` in that directory **before the
first GET**, recording the run ID, protocol, intended URLs and start time.
After each validated workbook, create and fsync a separate no-overwrite
receipt with its hash, size and response metadata. A run with an intent but no
final manifest is incomplete after a crash; receipts and original bytes remain
for diagnosis. Stream each exact response into a
create-new temporary file, hash the raw bytes with SHA-256, flush and fsync,
then publish by an atomic no-overwrite operation in the same directory. Do
not edit, reserialize or extract the original workbook. Preserve an incomplete
run and its failure status without publishing it as a valid five-file bundle.

Validate each saved workbook as a ZIP-based `.xlsx` before accepting the
bundle. Require an intact central directory, unique normalized relative
member names, no traversal or symlink entries, no encryption, at most 256
members, and only stored or deflated compression. Require
`[Content_Types].xml`, `_rels/.rels` and `xl/workbook.xml`. Bound each declared
uncompressed member to 256 MiB and the sum to 512 MiB per workbook. Stream
every member without extraction, enforce the same decoded-byte caps against
actual output, and verify CRC; a malformed or oversized package fails. ZIP
validity does not establish worksheet schema, row count or factual accuracy.
It also does not make workbook formulas, external links or content safe to
execute or open interactively. A later comparison requires a bounded,
read-only parser that does not execute formulas or fetch external resources.

Write a private create-new manifest only after the five responses and package
checks succeed. It records protocol version, run ID, code commit and dirty-tree
status, environment lock hash, source page and advertised period, each
borough's fixed URL, UTC request and completion times, HTTP status, safe MIME
type, declared and received byte counts, raw SHA-256, ZIP member count and
declared decoded-byte total, plus bundle status. The intent and receipts
provide durable incomplete-run evidence even if a failure report cannot be
written. A completed manifest never replaces a previous file. The tracked
report contains only aggregate capture status, run ID,
manifest hash, five borough names, raw file hashes and sizes, command, exit
code, test evidence and limitations. It contains no workbook cells, addresses,
prices, exact sampled ordinals or reviewer notes. Raw workbooks and any
row-level comparison remain under protected ignored storage.

An offline replay makes no network call. It verifies the private intent,
receipts, manifest and all five raw hashes, lengths and ZIP checks, then
regenerates the same aggregate report. A missing, changed or invalid file
fails replay rather than being replaced by a live download. A private offline
worksheet inspection must separately record actual period, sheet names,
headers and row counts before any sampled-row comparison. Until then, the
bundle status is `bytes_captured_content_unqualified` even if all five ZIPs
pass. Test the fixed URL allowlist, one-request
cap, redirect/credential/proxy rejection, MIME and byte caps, malformed ZIP,
ZIP expansion and path attacks, ACL failure, no-overwrite publication,
interrupted-run recovery, and offline replay with synthetic transports before
live capture. Commit and
push the reviewed collector before its first real request.

## Interpretation and next step

The five files are another extract from the **same DOF publisher** as the
portal CSV. Later matching by borough, block, lot, apartment identifier where
present, sale date and price may support a reviewer finding that the extracts
agree for a sampled row. Such agreement does not independently prove
dwelling identity, one economic transfer, arm's-length consideration,
contract or closing date, factual ground truth, first row publication, or
historical attribute availability. Absence or disagreement is an investigation
signal, not an automatic mismatch decision; workbook period, category,
refresh and correction differences must be assessed first. The comparison
workflow and each private ADR 0025 review entry require their own evidence.

The [rolling-sales source card](../data/source_cards/nyc_dof_rolling_sales.yaml)
still limits this source to private inventory. Official publication does not
settle commercial reuse or redistribution rights. This capture cannot make
the rows eligible for training, certify historical as-of features, finish the
200-record audit, pass U0 or G-US, or unlock international work.
