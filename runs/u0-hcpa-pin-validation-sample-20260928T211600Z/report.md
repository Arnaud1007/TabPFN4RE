# U0 HCPA disjoint PIN validation sample

Run ID: `u0-hcpa-pin-validation-sample-20260928T211600Z`.
Requirements addressed: US05, US06, US07, US24. Status: the **sample
selection** is verified; PIN mapping has not been evaluated by this run.
U0 and G-US remain pending.

## Objective and protocol

[ADR 0017](../../decisions/0017-hcpa-pin-crosswalk-validation.md) froze the
five sale-date bands crossed with `Q/U`, 100 new records per cell, the
SHA-256 ranking formula and seed 43, and exclusion of every ordinal in the
earlier 200-record audit sample before this selection. The same ADR recorded
the candidate PIN conversion and ASCII guard before inspecting this disjoint
sample. The selector reads the pinned unchanged All Sales ZIP, validates the
source DBF, and publishes only the [aggregate selection manifest](sample_manifest.json).
The 1,000 row-level identifiers are stored under ignored `data/raw/hcpa/`.
The source file, manual review records and private sample are not included in
Git.

## Actual result

The source header and scan reconcile 2,453,187 DBF records. All 200 earlier
sample ordinals were found and excluded. Each of the ten cells has 100 newly
selected records; the total is 1,000. The private sample SHA-256 is
`35c52bc969980cb0e1cabb698a70754825774f0ddc09e6b1417cdc21dc1ad3f9`.
The aggregate manifest SHA-256 is
`5248e21e21b41eec2e0ab97881ec619bf82f3669f76f35beacfadeb5e7756267`.
An independent invocation into separate paths produced byte-identical private
sample and aggregate manifest. Neither invocation tested the PIN conversion.

## Commands and checks

From the project root in PowerShell, the accepted selection command was:

```powershell
.\.venv\Scripts\python.exe scripts/select_hcpa_pin_validation_sample.py `
  data/raw/hcpa/allsales_09_18_2026.zip `
  data/raw/hcpa/audit-sample-20260928-888226e.jsonl `
  data/raw/hcpa/pin-validation-sample-20260928-v1.jsonl `
  runs/u0-hcpa-pin-validation-sample-20260928T211600Z/sample_manifest.json
```

The replay used the same inputs and distinct outputs
`data/raw/hcpa/pin-validation-sample-20260928-v1-replay.jsonl` and
`data/raw/hcpa/pin-validation-sample-20260928-v1-replay-manifest.json`.
Both exited 0; exact wall-clock durations were not recorded. A further replay
after formatting the selector also produced the same two hashes. The
[test gate](test_gate.json) records 11 selector and 19 synthetic crosswalk
tests, 338 full-suite tests with no skips, 83% selector, 87% crosswalk and
88% package branch-aware coverage, lint, formatting and scoped dependency
checks. The full-suite log includes expected error messages from negative
fixtures; its exit code was zero. This selection does not prove source rights, historical availability,
transaction scope, sale-date meaning or dwelling eligibility.

## Failed attempt and recovery

The first real scan exited 1 before writing output because the initial
selector assumed every selected DBF field had type `C`. HCPA `S_DATE` has DBF
type `D`. A synthetic failure fixture was added, then the guard was corrected
before the accepted scan. No sample was selected by the failed invocation.
The first formatting check found two files to reformat. Formatting was
applied, the final formatting check passed, and a fresh source replay
reproduced the frozen hashes.

The two-file output is no-overwrite, but a process crash after writing the
private sample and before linking the public manifest can leave an incomplete
run. The operator must retain that orphan as failed evidence, inspect its hash,
and rerun the same pinned configuration to **new** private/public paths. A
manifest is a completed selection only when its sample path exists with the
recorded hash, all ten quotas and source/exclusion hashes reconcile. No
partial run is silently resumed or treated as a frozen sample. This crash
path was reviewed but has not been exercised on the real source.

## Next action

Review and run the separately tested crosswalk auditor against exactly this
frozen sample hash and the pinned 2025 and 2026 parcel archives. Report
distinct-control agreement, ambiguities and failures before considering a
format rule. Keep every historical-as-of, rights and sale-eligibility gate
blocked. Independently, complete the 200-record manual source audit; it
still has zero complete rubrics.
