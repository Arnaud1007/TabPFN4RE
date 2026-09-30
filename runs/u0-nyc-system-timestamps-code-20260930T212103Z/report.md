# NYC row-system-timestamp probe: code gate

Status: **verified engineering diagnostic; U0 and G-US pending**.

The fixed probe in `scripts/probe_nyc_system_timestamps.py` requests only
current-view aggregate counts and minimum/maximum Socrata system timestamps
for the NYC rolling and annualized sale views. ADR 0041 freezes the question,
request plan, validation and interpretation before the official capture. Raw
metadata can contain cached property examples, so capture files are written
only into a Git-ignored directory with a checked private ACL. The public
projection contains no individual property row. No sale label is certified.

## Checks

| Check | Observed result | Evidence |
| --- | --- | --- |
| Focused unit and offline integration tests | 30 passed | `focused_tests_final.log` |
| Branch-aware probe coverage | 89% | `coverage.log` |
| Full repository suite | 871 passed in 202.792 s; exit 0 | `full_tests.log`, `full_tests_gate.json` |
| Ruff check | exit 0 | `ruff_check_final.log` |
| Ruff format check | exit 0 | `ruff_format_final.log` |
| Dependency consistency | exit 0 | `pip_check.log` |
| Dependency vulnerability audit | exit 0; no known vulnerabilities found | `pip_audit.log` |
| Diff whitespace | exit 0 | `git diff --check` |

An initial Ruff format check failed while the test file was still being
edited. That failed output is retained in `ruff_format.log`; the completed
file passed the final check. The focused tests were written first and recorded
their expected failures before the implementation changes.

This is a code gate only. The official six-request capture, raw hash check and
offline replay follow after this code is committed and pushed. Current portal
row-instance timestamps cannot establish a sale's historical first public
availability, even if the capture succeeds. Source rights, close-date meaning,
transfer/unit identity and the remaining 190 manual review rubrics remain
open. The next command after pushing is:

```powershell
.\.venv\Scripts\python.exe scripts/probe_nyc_system_timestamps.py capture data/raw/nyc_dof/system-timestamps-v1-<unique-UTC-id>
```
