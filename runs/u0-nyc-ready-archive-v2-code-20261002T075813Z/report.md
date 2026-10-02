# NYC ready archive v2: pre-capture code gate

Status: **verified engineering diagnostic; U0 and G-US pending**. Requirements:
US05, US08, US22 and US24. Protocol: [ADR 0043](../../decisions/0043-nyc-ready-archive-status-v2.md).

The first live v1 attempt is preserved as [FAILED_STATUS_SCHEMA](../u0-nyc-ready-archive-v1-failed-20261001T104628Z/report.md): two metadata GETs completed and the CSV was never requested. V2 accepts the observed six-field `done` response only for the pinned backend dataset, version and storage locations. The collector still uses five fixed GETs, a private create-only run directory and bounded responses. A v2 live archive has **not** been requested by this code gate.

## Observed checks

| Check | Result | Evidence |
| --- | --- | --- |
| Fixed-plan dry run | Five GETs for dataset `usep-8jbt`, version 62; 128 MiB and 150,000-row caps | `python scripts/capture_nyc_generated_archive.py plan` |
| Completed repository suite before final test-only fixture | 901 tests, exit 0, 520.854 seconds, with pinned local Ames ARFF | `full_tests_before_v1_fixture.log`, `full_tests_before_v1_fixture_gate.json` |
| Final focused suite, including the valid two-field v1 rejection | 31 tests, exit 0 | `coverage_final_tests.log`, `coverage_final_gate.json` |
| Branch-aware collector coverage | 86%; above the project 80% floor | `coverage_final.log` |
| Ruff lint, format and dependency consistency | All exit 0 | `lint_gate.json`, `ruff_check.log`, `ruff_format.log`, `pip_check.log` |
| Pinned `tzdata` vulnerability audit | Exit 0; no known vulnerabilities | `pip_audit_final_gate.json`, `pip_audit_final.log` |
| Preserved failed v1 run | Two private response hashes match; no CSV or collector manifest | [v1 verifier](../u0-nyc-ready-archive-v1-failed-20261001T104628Z/verify_artifacts.ps1) |

The tests cover the exact observed status, a valid legacy two-field response, malformed fields, changed status after download, archive identity, response limits, private storage, CSV validation and offline replay. Code, Python and security reviewers found no remaining critical, high or medium issues. `git diff --check` passed; a scoped token/secret-pattern scan found no match in the changed code, tests, decision or v1 failure artifacts.

Saved logs were encoded as UTF-8 and their local user-home path prefix was
replaced with `<USER_HOME>` for the public repository. Exit codes, test counts,
diagnostics and gate decisions were retained.

## Attempts that were not accepted as gates

The first coverage invocation used a path as a module source filter and collected no data (`coverage_gate.json`). A corrected 30-test run passed (`coverage_gate_v2.json`), then the final 31-test run refreshed coverage after the extra fixture. A full-suite rerun after that fixture lost its unified-exec process handle; no Python test process or exit record remained, so its partial log is retained as `full_tests_interrupted.log` and is **not** counted as a pass. The earlier complete 901-test run and the final 31-test focused run are reported separately. One pip-audit attempt failed while creating a temporary virtual environment; the final audit used the pinned one-package requirement with `--disable-pip --no-deps` and passed. These failures were not converted into successful results.

This gate validates collector code, not NYC sale labels. A successful archive capture would establish a candidate dated vintage, but not per-row first publication, transaction scope, close-date meaning, rights or dwelling identity. NYC certified labels: **0**. U0 and G-US: **PENDING**. The next step is to commit and push this reviewed v2 collector, verify a clean tree, then run one new unique private capture and offline replay.
