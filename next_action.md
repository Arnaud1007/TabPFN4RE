# Next action

Active milestones: U0 legacy recovery is pending inaccessible inputs; independent U1 work is in progress. The Ames smoke, synthetic canonical/as-of contract, training guards, split validator and shared US point scorecard are verified. U1 and G-US are pending.

## Next dependency-ready task

Complete U1's remaining acceptance wiring in test-first order: T03 must reject future or late-published sales from the deterministic comparable candidate set; T04 must reject target copies and forbidden F172/F349/F350 fields at the model-fit boundary, including derived dependencies. Then run a small synthetic end-to-end flow through canonicalisation, as-of assembly, guarded fit, prediction and the shared scorecard, preserving row IDs and hashes. Do not mark U1 accepted until these checks and its applicable integration tests pass.

Resume from the project root in PowerShell:

```powershell
git switch audit/u0
$env:AMES_ARFF_PATH = (Resolve-Path 'data/raw/openml/house_prices-42165.arff').Path
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
```

The U0 baseline is in `runs/u0-smoke-20260928T082634Z-ef55636ed896/`; the U1 foundation gates are in `runs/u1-foundation-20260928T091610Z/` and `runs/u1-integrity-20260928T093259Z/`. The source ARFF and row-level predictions are local ignored files; a fresh clone must download OpenML 42165 using `data/source_cards/openml_42165.yaml` and verify SHA-256 before replay. No releasable use of this data is asserted.

## Unresolved dependencies

- Accessible legacy repository or local path, original Word specification, original 1,168/292 split membership, XGBoost configuration/predictions and `feature_catalog.csv`. On receipt, recover exact artifacts; do not reconstruct a new split as the original.
- Rights decision for any releasable use of the Ames file; its OpenML licence field is `NA`.
- Multi-market time-stamped US transactions and prospective labels for G-US. ON additionally needs authorised historical listing snapshots.

These block legacy reproduction and the US release gate, but not the remaining independent U1 checks. International implementation remains gated on G-US PASS.
