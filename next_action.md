# Next action

Active milestone: U0 remains pending access to the owner's private legacy repository. The owner confirmed the requested legacy split, XGBoost results and feature catalogue are unavailable. U1 engineering checks T01–T08 and a 200-row Ames OFF smoke flow are verified, but U1 cannot be accepted before U0. Synthetic U2 comparable retrieval and U3 temporal-fold guards are verified engineering increments, not accepted real-data milestones. The synthetic protocol remains `us_synthetic_rolling_v2`; a separate `us_local_date_90d_v1` calendar-date visibility helper is now tested under ADR 0011. G-US is pending; international work is locked.

## Next dependency-ready task

When repository access is granted, run a read-only inventory of `github.com/Arnaud1007/tabular-fm-housing-poc` in an isolated checkout and update `migration_report.md`. Do not reconstruct absent legacy split or result artifacts as originals. Independently, continue U0 source qualification from `data/acquisition_backlog.md`: verify Hillsborough HCPA `S_DATE` against true close/deed semantics, first publication date and the right to use its data; determine whether stable dated snapshots can be collected. Florida DOR SDF remains a statewide linkage candidate but has year/month-only sale dates. NYC, Cook County and King County have distinct timing and join dependencies. Do not train a real-world temporal model until source timing and label eligibility are demonstrated.

The read-only HCPA aggregate source scan in `runs/u0-hcpa-profile-20260928T133100Z/` reconciles 2,453,187 raw DBF records but establishes no eligible residential cohort. Before an adapter, perform the 200-record source audit, confirm document/parcel uniqueness, define a rights decision and recover historical availability snapshots. An unchanged source ZIP is kept under Git-ignored `data/raw/hcpa/`; it is not part of the releasable canonical data layer.

Resume from the project root in PowerShell:

```powershell
git switch audit/u0
$env:AMES_ARFF_PATH = (Resolve-Path 'data/raw/openml/house_prices-42165.arff').Path
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
```

Latest complete engineering gate: `runs/u3-local-calendar-20260928T133000Z/test_gate.json` (188 tests, 0 skipped, 90.65% statement coverage). Its report records the current changes and limits. A prior local-calendar gate launcher produced invalid coverage metadata and is preserved as failed under `runs/u3-local-calendar-20260928T132430Z/`. Earlier synthetic fold evidence remains immutable at `runs/u3-synthetic-utc-20260928T125610Z/` and `runs/u3-synthetic-temporal-20260928T123500Z/`. The local Ames ARFF is ignored by Git; a fresh clone must download OpenML 42165 using `data/source_cards/openml_42165.yaml` and verify SHA-256 before replay. For deterministic Windows timezone rules, run `.\.venv\Scripts\python.exe -m pip install --require-hashes -r locks/local-date-requirements.txt` before tests. No releasable use of the Ames file is asserted.

## Unresolved dependencies

- Access to the owner-confirmed private legacy repository. The original Word specification, 1,168/292 split membership, XGBoost configuration/predictions and `feature_catalog.csv` were confirmed unavailable. Recover any genuinely present facts after access; do not reconstruct a new split as the original.
- Rights decision for any releasable use of the Ames file; its OpenML licence field is `NA`.
- Multi-market time-stamped US transactions and prospective labels for G-US. ON additionally needs authorised historical listing snapshots.
- For Cook County specifically, dataset-level reuse rights, exact transaction/close-date semantics, historical field availability and a safe parcel-to-building join. Current API metadata lacks these proofs.
- For NYC, dataset-level reuse decision, historical publication snapshots or defensible first-availability reconstruction, close-date semantics, and tax-lot/unit identity audit. Current annualized and rolling extracts are not enough for a certified as-of backtest.
- For King County, an authorised Assessor data route, source-specific rights, close-date and availability evidence, and multi-parcel/multi-building reconciliation. The documented GIS derivatives are marked Not Public.
- For Florida, verified close-date semantics, historical NAL/SDF and county publication availability, source-specific reuse decisions, and deed/parcel reconciliation. Hillsborough HCPA offers a documented sale-date field but its assessor entry can lag weeks and historical first availability is unknown. Prior DOR rolls are available by request, but no request has been sent.
- For comparable pricing, source geometry with as-of dates, a development-fitted similarity/support rule, 50 audited real queries and the full US10 variant comparison. The current `supported` count is not a release support claim; see ADR 0008.
- For temporal certification, verified close and first-availability dates, complete historical vintages, rolling/calibration/test cohorts and reserved-label enforcement. The separate `us_local_date_90d_v1` helper supplies calendar-date and availability rules but is not connected to a qualified real source or certification fold; see ADRs 0009–0011.

These block legacy reproduction and the US release gate, but not U0 source feasibility work. No model was trained on a modern multi-market US cohort.
