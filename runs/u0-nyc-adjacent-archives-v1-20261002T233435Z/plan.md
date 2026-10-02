# Frozen run plan: NYC adjacent archive representations

Run ID: `archive-adjacent-v1-20261002T233435Z-6db0ca9ec142`
Protocol: `nyc-adjacent-archives-v1`, defined by [ADR 0048](../../decisions/0048-nyc-adjacent-archive-concordance-v1.md).
Status before execution: planned. Requirements: US05, US06, US08, US22, US23, US24.

Run one offline comparison of the immutable NYC rolling-sales version-61 and
version-62 captures. The runner pins their public/private manifests, exact CSV
SHA-256 values, byte counts and row counts from ADR 0048. It uses the unchanged
strict archive parser and compares all 21 trimmed fields as multisets, then
compares a second tier with only sale-date representation normalized. It writes
protected create-only aggregate artifacts beneath
`data/raw/nyc_dof/archive-adjacent-v1-20261002T233435Z-6db0ca9ec142/`.

Before opening either CSV: commit and push the reviewed runner, tests, lock,
ADR and this plan to `origin/audit/u0`; verify the remote ref equals the clean
local HEAD and the private output directory does not exist. Record the exact
code commit, environment lock hash, helper hashes, source hashes and
configuration hash in the intent. The runner must make no network request.

From the project root, execute exactly once:

```powershell
.\.venv\Scripts\python.exe scripts/compare_nyc_adjacent_archives_v1.py compare data/raw/nyc_dof/archive-adjacent-v1-20261002T233435Z-6db0ca9ec142
```

If it fails, retain the incomplete directory; do not reuse the ID. If it
succeeds, run offline replay against that directory, independently verify
private hashes and publish only the intent provenance, fixed-denominator
bucketed public projection, test gate and report. No source row, address,
unit, price, date, ordinal or per-row fingerprint may enter Git.

The run is source inventory only. Matching rows cannot certify economic
transfer identity, first availability, DOF sale-date semantics, rights,
historical features or model labels. `sale_labels_certified=0`,
`historical_asof_eligible=false`; U0, U3 and G-US remain PENDING.
