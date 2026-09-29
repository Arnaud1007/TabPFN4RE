# ADR 0028: versioned User-Agent revision for NYC borough export capture

Date: 2026-09-29
Owner: project implementation
Affected requirements: US05, US07, US08, US22 and US24
Protocol version: `nyc-official-borough-xlsx-v2`
Status: approved retry protocol; no v2 request or workbook capture is claimed here
Supersedes: ADR 0026's request-header definition for a new run only

## Context and evidence

[ADR 0026](0026-nyc-official-borough-export-capture.md) froze a bounded,
anonymous capture of the five workbooks linked from the [official NYC
Department of Finance rolling-sales page](https://www.nyc.gov/site/finance/property/property-rolling-sales-data.page).
The first v1 live run, `official-exports-20260929T031155Z-e3f467c372ad`,
ended on request ordinal 1 with `HTTPError` reported under the safe `OSError`
class. Its private `failure.json` records phase `request`; no workbook response
bytes or completed five-file manifest resulted. Preserve that incomplete run
and its intent/failure artifacts. Neither replay nor reinterpret it as a v2
attempt. The v1 GET's HTTP status was not recorded, so this decision does not
assign one.

A subsequent independent, read-only `HEAD` check of the Manhattan URL returned
HTTP 403 with Python's default User-Agent and HTTP 200 with the fixed,
transparent `TabPFN4RealEstate-U0/1.0` User-Agent, with the expected Excel MIME
type and a declared 1,807,597-byte length. A PowerShell `HEAD` also returned
HTTP 200. These observations motivate a one-factor retry; they do not prove
why the v1 GET failed or that any v2 GET will succeed. A `HEAD` response does
not qualify workbook content, publication timing, sale labels or reuse rights.

## Decision

For v2, send exactly one application-supplied header on every frozen workbook
`GET`:

```text
User-Agent: TabPFN4RealEstate-U0/1.0
```

The five URLs, their borough order and the one-request-per-URL rule remain
exactly as in ADR 0026. This is an identified research client, not a browser
impersonation string. Do not add credentials, cookies, authorization,
conditional headers, proxy configuration or any other application-supplied
request header. Keep HTTPS certificate verification, the no-redirect policy,
the 30-second connection/read timeout, the 240-second per-file transfer limit,
the 1,800-second run limit, the 16 MiB per-file and 80 MiB bundle caps, and
all response status, MIME, encoding and length checks. No `HEAD`, retry,
redirect follow, archive-generation action or new page request is part of the
v2 run. A request failure or uncertain transport outcome ends that run.

Start v2 only in a fresh restricted, Git-ignored
`data/raw/nyc_dof/official-exports-<UTC>-<nonce>/` directory with a new run ID.
Never reuse the v1 path or any existing intent, receipt, workbook, failure or
manifest. Before the first GET, the create-new, fsynced intent records the v2
protocol and exact User-Agent along with the ADR 0026 run identity, fixed URLs
and start time. A completed v2 manifest records the same exact User-Agent;
offline replay verifies it and rejects a v1 manifest or a changed value. The
private no-overwrite receipts, original byte hashes, ZIP validation, ACL and
link checks, crash recovery, aggregate public reporting and offline replay
remain governed by ADR 0026. Successful transport still yields only
`bytes_captured_content_unqualified` until separate private worksheet and
row-identity checks are performed.

When a request raises `HTTPError`, write only its safe integer HTTP status
(100-599) as `http_status` in the private create-new `failure.json`, alongside
the existing protocol, run ID, incomplete status, phase, request ordinal and
safe error class. Omit `http_status` for other failures. Never save the
exception message, reason phrase, response body, arbitrary response headers,
redirect target or URL query in that failure artifact or public report. If
the failure artifact cannot be written, the immutable intent still marks the
run incomplete. An HTTP status is diagnostic transport evidence, not an
assertion about data quality or access rights.

## Alternatives and trade-offs

- Retrying unchanged would preserve the exact v1 transport but offers no
  evidence-based way to diagnose a first-request `HTTPError`.
- Browser impersonation, proxy changes, cookies or redirects could change the
  request identity and increase access, provenance and security ambiguity.
- A fixed, transparent User-Agent changes one declared request factor while
  retaining the original capture bounds. Its benefit is uncertain until a
  complete, validated v2 run exists.

## Acceptance before a live v2 GET

Write failing synthetic tests before the transport change. Verify the exact
fixed header on each permitted URL, rejection of extra headers and redirects,
one-request limits, preservation of v1 artifacts, new-run/no-overwrite
behavior, safe `HTTPError` status recording without body/header/URL leakage,
and v2 intent/manifest/replay compatibility checks. Re-run the ADR 0026
transport, byte, ZIP, ACL and offline-replay tests. Review the code and
security boundary, then commit and push the reviewed v2 implementation before
issuing its first live GET. Do not expand limits or automatically retry if it
fails.

The official workbooks come from the same DOF publisher as the portal CSV.
Their capture or agreement with sampled rows cannot establish independent
ground truth, first publication, historical as-of availability or permission
for a releasable model. The NYC 200-record audit, U0 and G-US remain pending.
