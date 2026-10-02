# U0 legacy lock marker audit

Date: 2026-10-03. Protocol: `ames_legacy_lock_markers_v1`. Requirements: US02, US22, US24. Status: **bounded environment diagnostic verified; U0 and G-US PENDING**.

## Objective and inputs

[ADR 0045](../../decisions/0045-legacy-lock-marker-audit.md) froze a read-only check of the recovered legacy `uv.lock` against the installed package snapshot from guarded Ames replay v9. The target markers were Windows (`win32`) and Python 3.11.6. The input lock SHA-256 is `a165ac8d49bfa7d2b4d42f46db2d6e33883fe78662df0cee9846828ba2a2aa6f`; the v9 environment snapshot SHA-256 is `348f41fe53681d972a683f71014c13933d052f5eaaa1f6a18be571dc47bcd01c`. The public [aggregate](aggregate.json) records the exact comparison, decision hash and code commit `09f9b4f19a7fafdea01811ee510fcafb119fb315`.

## Observed result

All **9 of 9** compared package versions selected by the lock's Windows Python 3.11.6 resolution markers match the v9 replay's installed versions:

| Package | Selected and installed version |
| --- | --- |
| NumPy | 2.4.6 |
| pandas | 3.0.5 |
| SciPy | 1.17.1 |
| scikit-learn | 1.9.1 |
| XGBoost | 3.2.0 |
| joblib | 1.6.0 |
| threadpoolctl | 3.6.0 |
| python-dateutil | 2.9.0.post0 |
| tzdata | 2026.3 |

The one-off audit read only the lock and saved environment snapshot. It did not fit a model or access source rows, predictions or reserved holdout labels. **Archived XGBoost scores remain not reproduced** by the guarded development replay. The original `ames.csv`, actual historical installed runtime, row-level predictions and checkpoint are missing. Lock agreement with replay v9 does not prove what was installed for the historical run or identify the cause of its score difference. No sale labels were certified.

## Verification and next action

An initial read-only verification checked marker selections against the aggregate and the lock hash (exit 0, 0.306 seconds), but did not independently inspect the saved v9 environment file. The extended read-only command below was then executed from the project root with exit code 0 and observed duration 0.339 seconds. It checks the selected and recorded installed versions against the actual v9 JSON file and verifies all three input hashes. It printed `PASS: nine marker selections, replay environment, and input hashes reproduce aggregate`. The run has no model-fit command or full test gate; its only output artifacts are the public aggregate and this report.

```powershell
.venv\Scripts\python.exe -c "import tomllib,json,hashlib; from pathlib import Path; from packaging.markers import Marker,default_environment; p=Path('data/raw/legacy-repo/uv.lock'); q=Path('runs/u0-legacy-replay-20260928T145000Z/v9/environment_packages.json'); r=Path('decisions/0045-legacy-lock-marker-audit.md'); d=tomllib.loads(p.read_text(encoding='utf-8')); e=json.loads(q.read_text(encoding='utf-8')); a=json.loads(Path('runs/u0-legacy-lock-markers-v1-20261002T221026Z/aggregate.json').read_text(encoding='utf-8')); names=set(a['packages']); selected={}; env=default_environment(); env.update(python_full_version='3.11.6',python_version='3.11',sys_platform='win32'); [(selected.setdefault(x['name'],[]).append(x['version'])) for x in d['package'] if x['name'] in names and (not x.get('resolution-markers') or any(Marker(m).evaluate(environment=env) for m in x['resolution-markers']))]; assert len(names)==9; assert all(selected[n]==[a['packages'][n]['lock_selected']]==[a['packages'][n]['replay_installed']]==[e[n]] and a['packages'][n]['matches'] for n in names); assert hashlib.sha256(p.read_bytes()).hexdigest()==a['legacy_lock_sha256']; assert hashlib.sha256(q.read_bytes()).hexdigest()==a['prior_environment_sha256']; assert hashlib.sha256(r.read_bytes()).hexdigest()==a['decision_sha256']; print('PASS: nine marker selections, replay environment, and input hashes reproduce aggregate')"
```

Do not rerun the Ames model solely on a higher version visible elsewhere in the multi-environment lock. Continue U0 source qualification and preserve the archived-score discrepancy until the missing original data or historical runtime can be recovered. This result does not change NYC source rights, date semantics, first-availability or transfer identity; U0 and G-US remain pending.
