# U0 OpenML Ames source integration and skip correction

Run ID: `u0-ames-source-integration-v1-20261003T132308Z`  
Protocol: `ames_source_integration_v1`  
Requirement: US02  
Status: **verified engineering source integration; U0 and G-US PENDING**

## Question and correction

The [plan](plan.md) froze a read-only check of the locally available official
OpenML 42165 ARFF. The previous NYC observation run's full suite had one
`RealAmesSourceTests` skip because its test process did not set
`AMES_ARFF_PATH`. That report then described the original source file as a
dependency. This was imprecise: the OpenML ARFF already existed locally. The
**separate legacy `ames.csv`** remains missing from the original repository.
The previous invocation's one skip remains its actual result; this run is a
new test invocation under an explicit source path.

## Inputs and observed checks

The existing Git-ignored `data/raw/openml/house_prices-42165.arff` is 479,052
bytes. Its SHA-256 is
`10db9fe72ed693212a222e39981133ec1b3ee5090d7f2caf2461190a4ad51279`
and MD5 is `d5ca59f8d02b1b1c127034392c0f995f`, matching the
[source card](../../data/source_cards/openml_42165.yaml). The focused test
parsed 1,460 records, verified unique `Id` values and positive `SalePrice`
labels, and passed. No source row, price or prediction was published by this
run.

The [evidence manifest](evidence_manifest.json) pins the tested code commit
`bf0e3bf8b004eb00f98fbdf6461609eb0fa07374`, plan hash, Ames environment
lock hash, source identity and sanitized test-artifact hashes. Only this run
directory was untracked when the tests began; tracked code was clean. The
runtime was local CPython 3.11.6 on Windows. There is no model configuration,
checkpoint, split or feature-policy hash in this source-test run.

| Command, with `AMES_ARFF_PATH` set to the resolved private ARFF | Exit | Observed result |
| --- | ---: | --- |
| `.venv/Scripts/python.exe -m unittest tests.test_ames_smoke.RealAmesSourceTests -q` | 0 | 1 passed, 0 skipped; 0.022 s test time, 1.047 s command wall time; [stderr](focused_stderr.log), [gate](focused_gate.json) |
| `.venv/Scripts/python.exe -m unittest discover -s tests -q` | 0 | 1,172 passed, **0 skipped**; 203.536 s test time, 204.933 s command wall time; [stderr](full_stderr.log), [stdout](full_stdout.log), [gate](full_gate.json) |
| `& 'runs/u0-ames-source-integration-v1-20261003T132308Z/verify_artifacts.ps1'` | 0 | Source hashes, Git exclusion, lock, plan, output hashes and no-skip test result verified; [verification log](verify_artifacts.log) |

The full suite deliberately exercises failure paths in unrelated Cook and
PTAX code, so its stderr contains those expected diagnostic messages before
the final `OK`. Local Windows account paths in the saved stderr are replaced
with `<USER_HOME>`; the test counts and exit evidence are unchanged. An
initial verifier attempt failed because its regular expression did not accept
Windows CRLF line endings. The verifier was corrected and then passed.
The frozen plan's phrase “no model fit” was too broad for a full test suite:
some synthetic unit tests fit engineering models. This run added no
real-market model training and opened no reserved real-market labels.

To repeat the focused source check from the project root in PowerShell after
obtaining the ARFF through the documented source route:

```powershell
$env:AMES_ARFF_PATH = (Resolve-Path 'data/raw/openml/house_prices-42165.arff').Path
& '.venv/Scripts/python.exe' -m unittest tests.test_ames_smoke.RealAmesSourceTests -q
Remove-Item Env:AMES_ARFF_PATH
```

## Boundary and next action

This check verifies the current OpenML engineering fixture and removes the
environment-caused test skip. It does not recreate the original `ames.csv`,
row-level historical predictions or XGBoost checkpoint; the guarded replay
remains unreproduced within its measured tolerance. OpenML's licence field is
`NA`, so use beyond this engineering fixture remains pending rights review.
The historical dataset has no usable as-of availability evidence for G-US.

**Zero modern US sale labels are certified.** U0 and G-US remain PENDING.
Continue qualifying a permitted multi-market transaction source with a
verifiable close-date mapping, publication timing, identity and historical
attributes before any real-market training. See [next_action.md](../../next_action.md).
