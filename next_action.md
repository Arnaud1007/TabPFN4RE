# Next action

Active milestone: U0 remains pending source qualification and missing historical artifacts. The private legacy repository is accessible at commit `60580b6`; its original 292 holdout indices and saved development scores are preserved in `data/legacy/`. The guarded development-only replay is complete, repeatable and excludes reserved labels, but **does not reproduce archived XGBoost scores**; see `runs/u0-legacy-replay-20260928T145000Z/report.md`. The original Word file, feature catalogue, `ames.csv`, historical installed versions, row-level predictions and checkpoint remain unavailable. The holdout exposure history is unknown, so it is retrospective. U1 engineering checks T01–T08 and a 200-row Ames OFF smoke flow are verified, but U1 cannot be accepted before U0. Synthetic U2 comparable retrieval and U3 temporal-fold guards are engineering increments, not accepted real-data milestones. G-US is pending; international work is locked.

## Next dependency-ready task

Continue U0 source qualification from `data/acquisition_backlog.md`. The frozen HCPA sample protocol is `decisions/0013-hcpa-manual-audit-sample.md`, and `runs/u0-hcpa-audit-sample-20260928T160539Z/` records a verified, private 200-record selection from the pinned archive. **No full manual review rubric has been completed.** `data/source_cards/hillsborough_clerk_official_records.yaml` documents the official instrument search and recent daily index route. One direct sampled lookup timed out; a second sampled instrument partially matched a recent official daily index row, as recorded in `runs/u0-hcpa-clerk-spotcheck-20260928T171047Z/`. Review the 200 against HCPA and, where accessible, Clerk evidence using the protocol's rubric; preserve unknown answers and keep row-level material under Git-ignored `data/raw/hcpa/`. Then verify HCPA `S_DATE` against true close/deed semantics, first publication date and the right to use its data; determine whether stable dated snapshots can be collected. The [public download page](https://downloads.hcpafl.org/) carries an All Rights Reserved footer but no dataset-specific permission statement; do not infer commercial or redistribution rights from download access. Florida DOR SDF remains a statewide linkage candidate but has year/month-only sale dates. NYC, Cook County and King County have distinct timing and join dependencies. Do not train a real-world temporal model until source timing and label eligibility are demonstrated.

The read-only HCPA aggregate source scan in `runs/u0-hcpa-profile-20260928T133100Z/` reconciles 2,453,187 raw DBF records but establishes no eligible residential cohort. The mechanical sample selected 200 distinct rows and its ten cell populations reconcile to the same total; this is not the 200-record manual source audit. Before an adapter, complete the review, confirm document/parcel uniqueness, define a rights decision and recover historical availability snapshots. An unchanged source ZIP and the row-level sample are kept under Git-ignored `data/raw/hcpa/`; neither is part of the releasable canonical data layer.

Resume from the project root in PowerShell:

```powershell
git switch audit/u0
$env:AMES_ARFF_PATH = (Resolve-Path 'data/raw/openml/house_prices-42165.arff').Path
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
Get-Content data/source_cards/hillsborough_hcpa_allsales.yaml
Get-Content runs/u0-hcpa-audit-sample-20260928T160539Z/report.md
Get-Content runs/u0-hcpa-clerk-spotcheck-20260928T171047Z/report.md
Get-Content runs/u0-legacy-replay-20260928T145000Z/report.md
```

Latest complete engineering gate: `runs/u0-hcpa-audit-sample-20260928T160539Z/test_gate.json` (216 tests, 0 skipped, 91% core package statement coverage; 10 sampler tests and 84% sampler statement coverage; Ruff and pinned dependency audit clean). The prior legacy replay gate is `runs/u0-legacy-replay-20260928T145000Z/test_gate.json`; its `report.md` records the failed historical XGBoost reproduction and missing inputs. Earlier synthetic fold evidence remains immutable. The local Ames ARFF and private clone are ignored by Git; a fresh clone must obtain OpenML 42165 using `data/source_cards/openml_42165.yaml`, verify SHA-256, and obtain authorised access to the pinned private repository commit for legacy replay. For deterministic Windows timezone rules, run `.\.venv\Scripts\python.exe -m pip install --require-hashes -r locks/local-date-requirements.txt` before tests. No releasable use of the Ames file is asserted.

## Unresolved dependencies

- The original Word specification, `feature_catalog.csv`, source `ames.csv`, historical run environment, row-level predictions and checkpoint remain unavailable. The private repository, exact split membership, scripts, lock and aggregate development scores are recovered. The development-only replay did not match historical XGBoost scores; investigate only if the missing original CSV or run environment can be recovered, and never use the retrospective holdout for selection.
- Rights decision for any releasable use of the Ames file; its OpenML licence field is `NA`.
- Multi-market time-stamped US transactions and prospective labels for G-US. ON additionally needs authorised historical listing snapshots.
- For Cook County specifically, dataset-level reuse rights, exact transaction/close-date semantics, historical field availability and a safe parcel-to-building join. Current API metadata lacks these proofs.
- For NYC, dataset-level reuse decision, historical publication snapshots or defensible first-availability reconstruction, close-date semantics, and tax-lot/unit identity audit. Current annualized and rolling extracts are not enough for a certified as-of backtest.
- For King County, an authorised Assessor data route, source-specific rights, close-date and availability evidence, and multi-parcel/multi-building reconciliation. The documented GIS derivatives are marked Not Public.
- For Florida, verified close-date semantics, historical NAL/SDF and county publication availability, source-specific reuse decisions, and deed/parcel reconciliation. Hillsborough HCPA offers a documented sale-date field but its assessor entry can lag weeks and historical first availability is unknown. Prior DOR rolls are available by request, but no request has been sent.
- For comparable pricing, source geometry with as-of dates, a development-fitted similarity/support rule, 50 audited real queries and the full US10 variant comparison. The current `supported` count is not a release support claim; see ADR 0008.
- For temporal certification, verified close and first-availability dates, complete historical vintages, rolling/calibration/test cohorts and reserved-label enforcement. The separate `us_local_date_90d_v1` helper supplies calendar-date and availability rules but is not connected to a qualified real source or certification fold; see ADRs 0009–0011.

These limit exact historical reproduction and block the US release gate, but not U0 source feasibility work. No model was trained on a modern multi-market US cohort.
