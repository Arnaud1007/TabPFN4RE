# U0 Illinois Additional PINs bounded source audit

- Date: 2026-10-03 UTC
- Requirements: US02, US05, US06, US07, US24
- Protocol: `illinois-ptax203-additional-pins-v2`
- Status: **verified private source capture; U0 PENDING; G-US PENDING**

## Objective and changes

The [official Illinois Additional PINs view](https://data.illinois.gov/Government-and-Public-Employees/PTAX-203-Additional-PINs/ay2h-5hx3) can supply parcel-scope evidence for the 80 previously captured PTAX declarations linked to the frozen 100 Cook sample rows. [ADR 0059](../../decisions/0059-illinois-additional-pins-bounded-capture.md) and [ADR 0060](../../decisions/0060-illinois-additional-pins-metadata-key-absence.md) restrict it to a private source audit. The v1 attempt failed on metadata before a row query; its [failure report](../u0-illinois-additional-pins-v1-20261003T044111Z/failure_report.md) remains intact. The v2 plan was frozen before any Additional PIN row query.

The new collector verifies both prior private captures and the offline Cook/PTAX worklist, derives the same 80 exact declaration IDs internally, performs at most 18 read-only GETs on the official endpoint, retains every returned row in ACL-restricted Git-ignored storage, and replays exact response bytes offline. It enforces pinned metadata, exact five-column schema and types, count agreement, URL and response bounds, no redirects/proxies and a fixed public-output allowlist. The private completion manifest was written last. No raw PIN, declaration ID, query URL or new small-cell count is published.

## Observed evidence

The one-shot v2 capture exited 0. It produced 38 private files totalling 44,330 bytes, including the completion manifest, under `data/raw/illinois_ptax203/ptax-additional-v2-130b5169ff81ccbc/`. The offline verifier exited 0 and generated [aggregate.json](aggregate.json). The official metadata response SHA-256 is `25a80a2c9274813cfda7d84ad717562765743fae7a9e33aced92edd7daa829cd`; the complete v2 response-set SHA-256 is `5b9d230f76f66d33b024009ee1c81aec18d5318b0cd5c748752ddf4300fba013`. The public aggregate SHA-256 is `79165c27ae69b2c915c00cbd644dd76dc6d8cf2da83000ffe53f9cc45169e265`. These are source-observation hashes, not model scores.

Focused synthetic/offline tests: 19 passed, 87% branch-aware coverage for the new collector, Ruff check and format passed. The full repository suite passed 1,086 tests in 180.007 seconds with one optional Ames source-integration skip because `AMES_ARFF_PATH` was unset; all 19 Ames smoke tests passed separately when the verified local ARFF was provided. `pip check` passed and `pip-audit` reported no known vulnerabilities among auditable installed packages; the editable local package was not found on PyPI. Reviewers found no remaining critical/high code or security issue after the v2 metadata correction. Exact commands and artifacts are in the [test gate](test_gate.json).

## Interpretation and blockers

The capture certifies **zero sale labels**. Additional PIN rows have no declared unique row key and cannot allocate declaration-level consideration to a dwelling. A missing row cannot prove a single-parcel transfer. Closing date, first row publication, historical property attributes, commercial-use rights for the Cook source, and human review of the remaining candidate links remain unresolved. U0 and G-US stay PENDING; no real US model training or international implementation is unlocked.

The next dependency-ready task is a separately frozen **offline** Cook-primary/Additional-PIN comparison using the existing private bytes. It must retain duplicate, zero, one and multiple parcel states, use a conservative PIN format rule, and publish only privacy-safe evidence. This capture must not be rerun. Replay locally from the project root with `& 'runs/u0-illinois-additional-pins-v2-20261003T050600Z/verify_artifacts.ps1'`.
