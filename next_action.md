# Next action

Active milestone: U0 remains pending recovery of the owner's legacy project artifacts. U1 engineering checks T01–T08 and a 200-row synthetic OFF flow are verified, but U1 cannot be accepted before U0. Synthetic U2 comparable retrieval and U3 temporal-fold guards are verified engineering increments, not accepted real-data milestones. The synthetic temporal protocol is now `us_synthetic_rolling_v2` with UTC instant guards; ADR 0010 records the change. G-US is pending; international work is locked.

## Next dependency-ready task

Continue U0 source qualification from `data/acquisition_backlog.md`. Florida DOR is the next candidate: determine whether an official daily deed/close source can be linked to its SDF and whether prior NAL/SDF publication vintages establish as-of attributes. Its year/month-only SDF cannot satisfy the exact 90-day pre-close origin alone. NYC, Cook County and King County have distinct timing, access and join dependencies in ADRs 0005–0006. If a source cannot provide a 90-day pre-close history, register a separate monthly-origin research protocol; do not present it as G-US evidence. Do not train a real-world temporal model until source timing and label eligibility are demonstrated.

Resume from the project root in PowerShell:

```powershell
git switch audit/u0
$env:AMES_ARFF_PATH = (Resolve-Path 'data/raw/openml/house_prices-42165.arff').Path
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
```

Latest complete gate: `runs/u3-synthetic-utc-20260928T125610Z/test_gate.json` (171 tests, 0 skipped, 90.54% statement coverage). The v1 synthetic fold gate remains at `runs/u3-synthetic-temporal-20260928T123500Z/`; its evidence was not rewritten. An earlier U3 evidence launcher failed in PowerShell JSON parsing and is preserved under `runs/u3-synthetic-temporal-20260928T123348Z/`. Two earlier U2 gate launchers are also incomplete and preserved. The local ARFF is ignored by Git; a fresh clone must download OpenML 42165 using `data/source_cards/openml_42165.yaml` and verify SHA-256 before replay. No releasable use of that file is asserted.

## Unresolved dependencies

- Accessible legacy repository or local path, original Word specification, original 1,168/292 split membership, XGBoost configuration/predictions and `feature_catalog.csv`. On receipt, recover exact artifacts; do not reconstruct a new split as the original.
- Rights decision for any releasable use of the Ames file; its OpenML licence field is `NA`.
- Multi-market time-stamped US transactions and prospective labels for G-US. ON additionally needs authorised historical listing snapshots.
- For Cook County specifically, dataset-level reuse rights, exact transaction/close-date semantics, historical field availability and a safe parcel-to-building join. Current API metadata lacks these proofs.
- For NYC, dataset-level reuse decision, historical publication snapshots or defensible first-availability reconstruction, close-date semantics, and tax-lot/unit identity audit. Current annualized and rolling extracts are not enough for a certified as-of backtest.
- For King County, an authorised Assessor data route, source-specific rights, close-date and availability evidence, and multi-parcel/multi-building reconciliation. The documented GIS derivatives are marked Not Public.
- For Florida, a daily close/recording source, historical NAL/SDF availability, source-specific reuse decision, and deed/parcel reconciliation. Prior rolls are available by request, but no request has been sent.
- For comparable pricing, source geometry with as-of dates, a development-fitted similarity/support rule, 50 audited real queries and the full US10 variant comparison. The current `supported` count is not a release support claim; see ADR 0008.
- For temporal certification, an explicit source-local 90-calendar-day origin policy, verified close and first-availability dates, complete historical vintages, rolling/calibration/test cohorts and reserved-label enforcement. The current v2 split enforces 90 UTC days only for synthetic engineering; see ADRs 0009–0010.

These block legacy reproduction and the US release gate, but not U0 source feasibility work. No model was trained on a modern multi-market US cohort.
