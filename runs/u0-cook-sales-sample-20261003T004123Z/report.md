# U0 Cook County parcel-sales private audit sample

Run ID: `u0-cook-sales-sample-20261003T004123Z`  
Protocol: [ADR 0051](../../decisions/0051-cook-sales-private-audit-sample.md)  
Capture code commit: `4851fb9dc86f38262a7a170a36f2332c514729b5` (pushed to `origin/audit/u0` before the live capture)  
Requirements: US02 and US05 source-audit evidence; US06, US07 and US08 dependencies identified but not satisfied  
Status: **private source-audit sample verified; U0 and G-US PENDING**

## Objective and completed work

The source card and ADR recorded a narrow internal audit decision before retrieval. The reviewed capture requested only 18 named fields from the official Cook County Assessor Parcel Sales API, excluding buyer and seller names. It selected two ten-row slices from each of ten predeclared recorded-date and price cells. A retained exclusive claim prevents a second v1 capture. Raw responses, row keys, PINs and document numbers are under Git-ignored `data/raw/cook_county/`; only fixed counts and hashes are checked in.

The live capture ran from `2026-10-03T00:41:23.032937Z` through `2026-10-03T00:42:14.862412Z`. All ten cell counts exceeded 20. It retained 200 distinct API row keys across 42 bounded HTTP responses. Metadata versions and each cell count agreed before and after the page requests. The private response replay and public aggregate rebuild both passed. [aggregate.json](aggregate.json) contains the actual counts and hashes; the private manifest SHA-256 is `130b5169ff81ccbc0a729cba98400f2fb377ff9a25999316aaac1960e38a3cf7`.

The selected sample has 60 rows marked `is_multisale = true`, 30 rows in ten repeated document-number groups, and 100 rows with no `sale_type` field in the response. These are **review priorities within a deliberately stratified sample**, not prevalence estimates or proof of duplicate economic transfers. All 200 sampled PINs have the 14-digit text format. No manual source rubric is complete and **zero sale labels are certified**.

## Executed checks and evidence

[test_gate.json](test_gate.json) records each command, exit code, duration and redacted output hash. All ten technical checks exited zero: 19 focused capture tests at 85% branch-aware coverage, two public-projection privacy tests, private replay, aggregate replay, the full 998-test suite with no skips, Ruff lint/format, `pip check`, and `pip-audit`. The audit found no known dependency vulnerability; the editable local project is not a PyPI package and was skipped by `pip-audit`. User-profile and username strings were redacted from public logs; the gate stores hashes of those redacted outputs. PowerShell rendered some successful native stderr as `NativeCommandError` text in the logs; the saved exit codes and `OK` test summaries establish the check outcomes.

[post_review_check.json](post_review_check.json) preserves a distinct check after a timestamp-order review fix. It binds the current aggregate builder and privacy-test file hashes to three passing privacy tests, aggregate replay and Ruff lint, with separate output hashes. The original ten-check gate was not rerun or rewritten; its 998-test count predates the third privacy test.

From the project root, replay the retained private evidence with:

```powershell
& 'runs/u0-cook-sales-sample-20261003T004123Z/verify_artifacts.ps1'
```

The verifier checks the private manifest and source hashes, the environment lock, all ten gate logs, the post-review code and output hashes, exact response queries and hashes, metadata/count brackets, 200-row membership and the checked-in aggregate. A fresh clone needs the private capture restored through an authorised route; the public aggregate alone cannot replay private records.

## Failed attempts and remaining dependencies

The first test-gate wrapper attempt stopped before writing a gate artifact because PowerShell treated ordinary `unittest` stderr as an error under `ErrorActionPreference = Stop`. The checked-in wrapper uses the native exit code, saves each output and completed the gate. An early public aggregate draft exposed exact sample price extremes and raw category values; review caught this before commit. The final projection maps categories to fixed buckets and omits exact price extremes, raw class values and identifiers. Its malicious-value privacy test passes.

The Assessor describes `sale_date` as recorded rather than executed/closed. First row publication dates, historical characteristic vintages, multi-parcel price scope, arm's-length status and dataset-specific commercial use remain unresolved. This sample cannot support the 90-day pre-close benchmark, a model fit, or a released prediction service. The [custodian inquiry draft](../../data/requests/cook_county_sales_inquiry_draft.md) is unsent.

## Next action

Create a private 200-record review ledger tied to the pinned sample and manually check the Assessor rows, repeated document groups and official Clerk instruments where accessible. Record unknown evidence explicitly. Prioritise the 60 multi-parcel flagged rows and ten repeated-document groups without assuming those groups are disjoint. The first exact resume command is the verifier above. Source rights and timing questions must be resolved before any Cook record enters the certified label layer. U0, U3 and G-US remain PENDING; international implementation is locked.
