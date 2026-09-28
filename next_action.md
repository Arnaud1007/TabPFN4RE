# Next action

Active milestone: U0 remains pending recovery of the owner's legacy project artifacts. U1 engineering checks T01–T08 and a 200-row synthetic OFF flow are verified, but U1 cannot be accepted before U0. G-US is pending; international work is locked.

## Next dependency-ready task

Continue U0 source feasibility: verify official Cook County residential sale and characteristic sources, exact release/version, permitted use, historical availability and identifier linkage. Record a source card and an acquisition decision. If those pass, prepare a small manually audited adapter fixture without treating current assessor attributes as historical. Do not train a real-world temporal model until source timing and label eligibility are demonstrated.

Resume from the project root in PowerShell:

```powershell
git switch audit/u0
$env:AMES_ARFF_PATH = (Resolve-Path 'data/raw/openml/house_prices-42165.arff').Path
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
```

Latest complete gate: `runs/u1-canaries-20260928T113723Z/test_gate.json` (131 tests, 89% statement coverage). The prior capture `runs/u1-canaries-20260928T113634Z/` is incomplete and preserved. The local ARFF is ignored by Git; a fresh clone must download OpenML 42165 using `data/source_cards/openml_42165.yaml` and verify SHA-256 before replay. No releasable use of that file is asserted.

## Unresolved dependencies

- Accessible legacy repository or local path, original Word specification, original 1,168/292 split membership, XGBoost configuration/predictions and `feature_catalog.csv`. On receipt, recover exact artifacts; do not reconstruct a new split as the original.
- Rights decision for any releasable use of the Ames file; its OpenML licence field is `NA`.
- Multi-market time-stamped US transactions and prospective labels for G-US. ON additionally needs authorised historical listing snapshots.

These block legacy reproduction and the US release gate, but not U0 source feasibility work. No model was trained on a modern multi-market US cohort.
