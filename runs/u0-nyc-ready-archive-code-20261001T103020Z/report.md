# NYC generated-archive collector: pre-capture code gate

Status: **verified engineering diagnostic; U0 and G-US pending**.
Requirements: US05, US08, US22, US24. Protocol: [ADR 0042](../../decisions/0042-nyc-ready-rolling-archive-capture.md).

The collector requests one already-generated NYC rolling-sales archive at
version 62 through five fixed GETs. It checks the exact revision metadata and
backend archive identity before requesting the CSV, then checks them again
afterward. Raw CSV and JSON responses can only be stored under ignored,
ACL-protected `data/raw/nyc_dof/`; a manifest is written last. Offline replay
rehashes the saved source responses and rechecks CSV structure. Its output has
counts and hashes, never property values. No archive-generation request is
implemented.

## Observed checks

| Check | Result | Artifact |
| --- | --- | --- |
| Fixed-plan dry run | Five GETs, version 62, 128 MiB and 150,000-row caps | `python scripts/capture_nyc_generated_archive.py plan` |
| Focused synthetic unit/integration suite | 28 passed; exit 0 | `focused_tests.log`, `focused_gate.json` |
| Branch-aware collector coverage | 86%; exceeds the project 80% floor | `coverage.log` |
| Full repository suite with pinned local Ames ARFF | 899 passed in 620.394 s; exit 0 | `full_tests.log`, `full_tests_gate.json` |
| Ruff lint and format | Both exit 0 | `ruff_check.log`, `ruff_format.log`, `lint_gate.json` |
| Dependency consistency | Exit 0 | `pip_check.log` |
| Dependency vulnerability audit | Exit 0; no known vulnerabilities found | `pip_audit.log` |
| Diff whitespace and scoped secret scan | No findings | `git diff --check`; `rg` scoped to the four new code/protocol files |

The tests exercised incomplete archive status, wrong backend identity,
changed metadata, redirects, bad content and size, malformed CSV, byte and row
caps, create-only storage, slow responses, and replay tampering. Python, code
and security reviews found no remaining critical or high issue. The full suite
has diagnostic stderr from tests that deliberately exercise failed paths;
its final result is `OK`.

This gate checks code only. The version-62 CSV has not yet been captured or
qualified. The next command is a unique private `capture` run after this
collector and its tests are committed and pushed. A successful capture may
support a candidate archive vintage, but does not establish per-row first
availability, sale/close-date semantics, rights, dwelling identity or sale
label eligibility. NYC certified labels remain **zero**.
