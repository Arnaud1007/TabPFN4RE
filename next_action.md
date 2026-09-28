# Next action

Active milestone: U0 audit. Status: the official Ames engineering smoke and local environment audit are verified; legacy recovery is pending inaccessible inputs. G-US is pending.

## Next dependency-ready task

Begin U1's independent core OFF schema and as-of guards. Specify synthetic fixtures for property, transaction, attribute and listing events before implementation. Keep the `available_at <= origin` rule executable and prohibit target-derived fields. Do not call this U1 accepted until its required T01–T08 checks and full smoke pipeline pass.

Resume from the project root in PowerShell:

```powershell
git switch audit/u0
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
```

The saved U0 baseline and test evidence is in `runs/u0-smoke-20260928T082634Z-ef55636ed896/`. The source ARFF and row-level predictions are local ignored files; a fresh clone must download OpenML 42165 using `data/source_cards/openml_42165.yaml` and verify SHA-256 before replay. No releasable use of this data is asserted.

## Unresolved dependencies

- Accessible legacy repository or local path, original Word specification, original 1,168/292 split membership, XGBoost configuration/predictions and `feature_catalog.csv`. On receipt, recover exact artifacts; do not reconstruct a new split as the original.
- Rights decision for any releasable use of the Ames file; its OpenML licence field is `NA`.
- Multi-market time-stamped US transactions and prospective labels for G-US. ON additionally needs authorised historical listing snapshots.

These block legacy reproduction and the US release gate, but not independent schema and OFF pipeline work. International implementation remains gated on G-US PASS.
