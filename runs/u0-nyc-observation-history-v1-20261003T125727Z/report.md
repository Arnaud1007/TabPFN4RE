# U0 NYC rolling source observation history

Run ID: `u0-nyc-observation-history-v1-20261003T125727Z`  
Protocol: `nyc-observation-v1`  
Requirements: US05, US08, US22, US24  
Status: **verified source inventory only; U0 and G-US PENDING**

**Correction, 2026-10-03:** The OpenML ARFF was already present; the one skip
below resulted from an unset `AMES_ARFF_PATH`. The unavailable historical
file is the separate legacy `ames.csv`. See the
[versioned source-integration rerun](../u0-ames-source-integration-v1-20261003T132308Z/report.md).

## Question, inputs and provenance

The [frozen local plan](plan.md) limits this run to the 28 September and
3 October 2026 NYC `usep-8jbt` captures, in that order. The raw files were
already present under Git-ignored `data/raw/nyc_dof/`; this run made no network
request. Each is 10,397,977 bytes, 82,345 parsed rows and has the same
SHA-256 `84c06057c52a2822f982cd98fb77ef7edf2c14134d00f46b073d2e4b762b2ef2`.

The first ledger entries were written while the implementation worktree was
under review. The implementation and plan were then committed as
`410b6523daa528565af7505845f92abc65a9e9ed`, and that exact code replayed
both entries without changing them. The [evidence manifest](evidence_manifest.json)
pins the code commit, lock hash, plan/configuration hash, source and capture
hashes, private observation hashes and non-model fields. There is no split,
feature policy, model configuration or checkpoint in this source-only run.

## Observed result

| Check | 28 September capture | 3 October capture |
| --- | ---: | ---: |
| Project-known-by time, UTC | 2026-09-28 22:55:43.929203 | 2026-10-03 10:13:06.833850 |
| Parsed source rows | 82,345 | 82,345 |
| Added row-representation occurrences | `100_plus` from empty ledger | `zero` |
| Removed row-representation occurrences | `zero` | `zero` |
| Replay | [first_replay.json](first_replay.json) | [second_replay.json](second_replay.json) |

The two private capture entries have distinct times and hashes. The later
snapshot's complete-row multiset equals the earlier one. The public JSON
contains no address, price, unit, row ordinal or row-level fingerprint. The
private entries contain capture-level metadata only. Exact source row counts
describe the files, not unique transactions or eligible homes.

## Commands and checks

Commands were run from the project root with the local Python 3.11.6
environment in `.venv` and the lock pinned by the evidence manifest. The
PowerShell `*>` logs include native-stderr formatting labels; command exit
codes and the test runner's final lines determine the results. The full-suite
log replaces the local Windows account path with `<USER_HOME>` before Git
publication; test output and the final count are otherwise retained.

| Command | Observed result and artifact |
| --- | --- |
| `python -m unittest tests.test_nyc_observation_history -q` | Exit 0; 21 passed, 0 skipped, 2.427 s test time; [log](focused_tests.log) |
| `python -m coverage run --branch --source=tabpfn4realestate.data.nyc_observation_history -m unittest tests.test_nyc_observation_history -q` then `python -m coverage report -m` | Exit 0; 21 passed and 81% branch-aware module coverage; [test log](coverage_tests.log), [coverage report](coverage_report.log) |
| `python -m ruff check src/tabpfn4realestate/data/nyc_observation_history.py tests/test_nyc_observation_history.py` | Exit 0; all checks passed; [log](ruff.log) |
| `python -m pip_audit --skip-editable` | Exit 0; no known vulnerabilities in audited installed packages; editable local project was skipped by the audit tool; [log](pip_audit.log) |
| `python -m unittest discover -s tests -q` | Exit 0; 1,172 tests ran in 203.683 s, one skipped; [log](full_tests.log) |
| `& 'runs/u0-nyc-observation-history-v1-20261003T125727Z/verify_artifacts.ps1'` | Exit 0; pinned hashes, ignored private paths, two entries and saved public summaries verified in about 4.4 s; [log](verify_artifacts.log) |

The sole full-suite skip was `RealAmesSourceTests`, because `AMES_ARFF_PATH`
was unset for that process. The OpenML ARFF was present; the separate legacy
`ames.csv` remains missing. That skipped source check is not counted as passed
in this historical run. The new ledger's 21 tests had no skips.
`git diff --check` was clean.

## Decision, failures and limits

The initial design persisted per-row fingerprints. Review rejected that
design because it retained sensitive address-and-price-derived identifiers;
the accepted version computes them in memory and persists only capture-level
metadata. A first `pip-audit` invocation incorrectly used a nonexistent
`requirements-lock.txt`; a second used `--disable-pip` without `-r` and was
rejected by the tool. The logged `--skip-editable` audit above is the valid
dependency check. These failed invocations are not evidence of vulnerabilities.

This observation method is accepted for source inventory. Its local absolute
manifest paths make the private ledger nonportable, and each append rechecks
the whole private history. A stale lock requires inspection. Before a longer
capture programme, constrain the generic CLI's ledger root and add explicit
relocation and retention rules. These issues do not turn the two current
captures into certified historical vintages.

**Zero sale labels are certified.** Neither capture proves first public
availability for an individual row, `SALE DATE` as close date, transfer or
unit identity, historical feature vintages, or permitted commercial reuse.
No real-market model training, calibration, test opening or international work
was performed. Next: obtain publisher/instrument evidence and complete the
private source audit described in [next_action.md](../../next_action.md).
