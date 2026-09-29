# U0 NYC official borough export capture: failed v1 attempt

Run ID: `u0-nyc-official-export-v1-failed-20260929T031155Z`
Status: **FAILED_SOURCE_REQUEST; U0 and G-US PENDING**
Requirements: US05, US07, US08, US22 and US24

## Objective and protocol

The [official NYC DOF rolling-sales page](https://www.nyc.gov/site/finance/property/property-rolling-sales-data.page)
currently advertises five borough Excel files for September 2025 through
August 2026. [ADR 0026](../../decisions/0026-nyc-official-borough-export-capture.md)
froze one bounded anonymous GET per file, private immutable bytes, and offline
replay. Reviewed collector code, synthetic tests and the environment lock were
pushed before this attempt. The working tree was clean at commit `af2d671`.

## Actual outcome

The first GET failed with Python `HTTPError` before a workbook body was saved.
The collector exited 1 and stopped; it did not request the other four files.
The private `failure.json` records `incomplete`, phase `request`, ordinal 1,
and safe class `OSError`. It does **not** contain the HTTP status, so the status
of this failed GET is unknown. The private directory contains only the
923-byte `intent.json` and 215-byte `failure.json`, with hashes in
[manifest.json](manifest.json). An offline replay correctly rejected this
incomplete run. [test_gate.json](test_gate.json) records actual test and
command outcomes, including 504 passing repository tests before capture.

After the failure, independent read-only HEAD diagnostics to the same first
URL returned HTTP 403 for Python's default user agent with proxies disabled,
and HTTP 200, Excel MIME and a 1,807,597-byte declared length for the named
`TabPFN4RealEstate-U0/1.0` user agent with proxies disabled. PowerShell HEAD
also returned 200. These are separate access observations. They do not prove
the failed GET's status or that a subsequent GET will succeed.

## Gate and next action

The v1 failure and private bytes remain immutable. No workbook, sampled sale
comparison, first-publication time, close-date evidence, source-rights
decision, eligible transaction label or model training resulted. A versioned
request change with a fixed transparent user agent is the next testable
access hypothesis. Review, test and push that change before any **new** run;
use a new run ID and keep this failure in the experiment record. NYC U0
source qualification and G-US remain pending.
