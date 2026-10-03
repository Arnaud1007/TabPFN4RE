# U0 Illinois PTAX-203 exact-document linkage audit

Run ID: `u0-illinois-ptax203-link-v1-20261003T032248Z`  
Baseline repository commit at capture: `69ba276401b520bea77850ce7ead165f079baf78`  
Requirements: US02, US05, US06, US07, US08, US24  
Status: **technical capture and offline replay verified; U0 and G-US PENDING**

## Question and observed result

The [frozen plan](plan.md) selected all 100 rows from the protected Cook Assessor sample whose year was 2024 or 2025 and whose document number was nonempty. They contained 83 distinct exact document strings. A single read-only run against the official Illinois Department of Revenue PTAX-203 dataset made 20 GET requests, below the 22-request cap, and returned **80 declaration records**. The [public aggregate](aggregate.json) records the source and response-set hashes. Request URLs, document strings, PINs, prices, dates and declaration IDs stay in ACL-restricted, Git-ignored storage.

The [offline replay](verify_artifacts.ps1) checked the frozen Cook input, exact query selection, count/row agreement, unique declaration IDs, schema and licence metadata stability, response hashes, private ACL and public aggregate. It passed. The private run artifacts total 562,317 bytes, dominated by two metadata snapshots. No raw declaration rows were committed.

## Interpretation and limits

These are candidate declaration links. A declaration can cover multiple parcels, and its Line 11 amount is declaration-level full actual consideration under the [IDOR instructions](https://tax.illinois.gov/localgovernments/property/general-information/ptax-203_instructions.html). The captured recording and instrument dates are not verified closing dates. The current official dataset does not establish each row's first public availability at a historical valuation origin. The Cook Assessor source retains separate rights, transfer-scope and attribute-vintage questions. No matched candidate was promoted automatically, and **zero sale labels are certified**.

The next source task is a private record-by-record review of candidate cardinality, county/PIN consistency, parcel count, transfer flags, consideration and date differences. Resolve the close-date and first-publication questions with official evidence before any model-training or 90-day as-of claim. The existing Cook custodian inquiry remains an unsent draft.

## Checks and recovery

The focused probe suite passed **9 tests** in the locked Python environment; branch-aware coverage of the new probe was **84%**; the [coverage report](coverage_report.txt) records the measured statement and branch counts. Ruff lint and format checks passed. The full suite passed **1,052 tests, with one skip**, in 175.883 seconds. The skipped test's identity was not captured in this run, so it is not used to claim an accepted U0 gate. `pip check` and `pip-audit` exited 0; pip-audit reported no known vulnerabilities among auditable packages and excluded the local package from PyPI lookup. The [gate record](test_gate.json) retains the exact commands and observed status. Initial pytest-based probe tests could not run in the locked environment; they were converted to unittest and rerun before capture. No network request was retried.

The private run is create-only. Replay it from the repository root without issuing another GET:

```powershell
& 'runs/u0-illinois-ptax203-link-v1-20261003T032248Z/verify_artifacts.ps1'
```

The local C: drive reached zero free bytes after the full regression suite. Cache-removal commands were rejected by automatic command review. Space was recovered by transparent compression of a temporary text file without changing its contents; the configured Git remote is used for this checkpoint. A source or code revision must use a new versioned protocol and cannot rerun this one-shot capture.

Split hash, feature-policy hash and model checkpoint are inapplicable to this source audit. The frozen Cook manifest SHA-256, plan hash, environment-lock hash, metadata hash and response-set hash appear in [test_gate.json](test_gate.json). No training, calibration or final-test evaluation occurred.
