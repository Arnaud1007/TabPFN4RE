# Synthetic OFF median bundle v2: verification report

Run ID: `u1-synthetic-off-bundle-v2-20261003T122750Z`  
Baseline commit: `89a1017d83a11328e610d454aa7e6c6739e52840`; code and test hashes are in [manifest.json](manifest.json).  
Requirements: US14, US22, US23 T10, synthetic engineering scope  
Status: **verified engineering fixture; U0, U6 and G-US PENDING**

## Objective and changes

Make the in-memory synthetic OFF median baseline reloadable without pickle or
plaintext training identifiers. The [v2 bundle](../../src/tabpfn4realestate/models/bundle.py)
publishes strict JSON once and requires a caller-held SHA-256 to load it.
The loaded [serving view](../../src/tabpfn4realestate/models/off_baseline.py)
contains an amount, training cutoff, training count and aggregate feature
hash. The training object retains row IDs for split checks, but the bundle
contains no raw IDs or per-row hashes. Both views use the same as-of
prediction path. [ADR 0069](../../decisions/0069-synthetic-off-bundle-v2.md)
records the alternatives and trust boundary.

## Observed verification

| Check | Evidence | Result |
| --- | --- | --- |
| Bundle behavior | [focused gate](focused_gate.json) and [log](focused_tests.log) | 15 tests, exit 0; save/load prediction and snapshot parity, digest, schema, privacy, no-overwrite and failed-publish cases |
| Full Python 3.11 suite | [test gate](test_gate.json) and [log](full_suite.log) | 1,151 tests, **0 skipped**, exit 0; runner 220.843 s |
| Branch-aware coverage | [touched modules](coverage_touched.log), [full package](coverage_full.log) | Bundle 88%; three touched modules combined 86%; package 89% |
| Ruff lint and format | [verification.json](verification.json), [lint](ruff_check.log), [format](ruff_format.log) | Both exit 0; 144 files formatted |
| Local dependency audit | [audit log](pip_audit.log) | Exit 0; no known vulnerabilities in auditable packages; editable project not on PyPI |

The full suite used the locally verified OpenML Ames ARFF via `AMES_ARFF_PATH`,
so its optional fixture test did not skip. Its PowerShell `Tee-Object` log was
transcoded from UTF-16LE to UTF-8 without changing the text. Expected error
messages from negative source-audit fixtures appear before the final `OK`.
The [environment snapshot](../../locks/u1-off-bundle-v2-environment.json)
records the measured tool versions and its hash is in the run manifest.

During development, RED tests first failed because the bundle module was
absent. Later tests caught an incompatible error message, exposed plaintext
training IDs in the first JSON design, and proved the large-Decimal size
check needed to run before fixed-point formatting. Those intermediate RED
outputs were not retained as gate artifacts; the final passing commands are
the gate evidence. The [review notes](review_notes.md) record the
code, Python and security findings and remaining compatibility limits.

## Limits and next action

The bundle is explicitly `certification_eligible: false`. There is no real
US source cohort, calibrated interval, release ID or production loader. A
feature-assembler semantic change still requires a deliberate policy-version
bump; the current fingerprint and one fixed synthetic snapshot canary do not
prove compatibility for every input. The bundle path and caller-held digest
must be trusted; power-loss durability of the NTFS directory entry has not
been established. No actual sale-price accuracy was evaluated here.

Continue the U0 source rights, close-date, first-availability and identity
work in [next_action.md](../../next_action.md). Design a real release bundle
only after its data, feature and calibration contracts are frozen.
