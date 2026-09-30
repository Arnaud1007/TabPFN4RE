# NYC Manhattan preamble formula: frozen private diagnostic plan

Protocol: `nyc-manhattan-formula-diagnostic-v1` under [ADR 0038](../../decisions/0038-nyc-manhattan-preamble-formula-diagnostic.md). This plan is recorded before the new diagnostic reads the pinned workbook.

- Reviewed code: `dc9cf39c0789df8ac758048c926846e9beea2603`, pushed to `origin/audit/u0` before workbook inspection.
- Source capture: `data/raw/nyc_dof/official-exports-20260929T033558Z-62ad417fb39f`; manifest SHA-256 `e29928b44a1b1f733219dac86b8d7e18704bf8c301b458afc2bf1a53895bb9e2`.
- Manhattan XLSX SHA-256: `8903566fa59c9ce4c2b427ce24e268cc448d8c04f8c779839df942f29a05397a`.
- Private output: `data/raw/nyc_dof/manhattan-formula-v1-20260930T201602Z-6d714e014144`, create only.
- Environment lock: `locks/nyc-worksheet-v3-environment.json`, SHA-256 `4fd04ef826afdb752074590bdb535b3f34e4c57c38391a0d6f49c6187da608b3`.
- Commands: `./.venv/Scripts/python.exe scripts/diagnose_nyc_manhattan_formula_v1.py diagnose <source> <private-output>`, then the same command with `replay`.
- Expected public projection is fixed: protocol, `private_only_v1`, completion, `v3_worksheet_qualified=false`, `sale_labels_certified=0`. The diagnostic does not change v3 qualification, admit transaction rows or open test labels.

Pre-run checks: 14 focused tests passed; branch-aware coverage was 82% for the runner and 83% for the XML reader. The full Python 3.11 suite passed 829 tests with one optional integration skip; its [log](../u0-nyc-manhattan-formula-code-20260930T201000Z/full_suite.log) is retained. Ruff check and format, `pip check`, and scoped `pip-audit` passed. Code, Python and security reviewers found no unresolved critical issue. The CLI now explicitly handles defused XML failures, and strict private-path rejection is tested. These are engineering checks, not a source or U0 gate pass.

Keep the private result and its hashes under ignored, ACL-protected storage. The public report may give only the fixed projection and non-sensitive source/code hashes. If the run fails, retain its incomplete intent and diagnose the failure under a new run ID. Do not loosen v3 based on this plan.
