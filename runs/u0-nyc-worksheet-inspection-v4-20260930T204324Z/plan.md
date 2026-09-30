# NYC worksheet v4: frozen private inspection plan

This plan was recorded before the v4 runner opened the protected borough workbooks. Protocol: `nyc-borough-worksheet-inspection-v4` under [ADR 0039](../../decisions/0039-nyc-manhattan-preamble-formula-v4.md).

- Reviewed code commit: `80af77fdd4faafedafd7c0e85ecd3bf0d100a078`, pushed to `origin/audit/u0` before private v4 execution.
- Source: `data/raw/nyc_dof/official-exports-20260929T033558Z-62ad417fb39f`, manifest SHA-256 `e29928b44a1b1f733219dac86b8d7e18704bf8c301b458afc2bf1a53895bb9e2`.
- Manhattan workbook SHA-256: `8903566fa59c9ce4c2b427ce24e268cc448d8c04f8c779839df942f29a05397a`.
- Required protected formula diagnostic: `data/raw/nyc_dof/manhattan-formula-v1-20260930T201602Z-6d714e014144`, replayed before this run. Its result and private fingerprints must not enter Git.
- Create-only output: `data/raw/nyc_dof/worksheet-inspection-v4-20260930T204324Z-417da725ab3d`.
- Environment lock: `locks/nyc-worksheet-v3-environment.json`, SHA-256 `4fd04ef826afdb752074590bdb535b3f34e4c57c38391a0d6f49c6187da608b3`.
- Execute `./.venv/Scripts/python.exe scripts/inspect_nyc_dof_borough_exports_v4.py inspect <source> <output>`, then the same command with `replay`.

Pre-run checks: 12 focused synthetic tests passed; branch-aware coverage was 82% for the runner and 89% for the core. The Python 3.11 full suite passed 841 tests with no skips and its [log](../u0-nyc-worksheet-v4-code-20260930T203800Z/full_suite.log) is retained. Ruff, `pip check`, scoped `pip-audit`, code/Python/security review, and the unchanged v3 artifact replay passed. These checks do not predict the v4 outcome.

Acceptance is five structurally qualified worksheets only if the frozen v4 inspection and offline replay pass. V3 remains four qualified and Manhattan unqualified under its own rule. V4 does not certify sale labels; `sale_labels_certified` must remain zero. Any failure stays in a create-only incomplete run. Rights, actual sale-date and first-availability semantics, economic-transfer identity and 190 remaining NYC source-review rubrics remain independent U0 blockers.
