# One-document MyDec check preparation

Run ID: `u0-mydec-one-document-v1-20261003T153741Z`
Status: **prepared; query not submitted**
Requirements: US02, US05, US07, US24

The [frozen plan](plan.md) selected one lead from the already verified Cook/PTAX private worklist. The prior offline verifier exited 0 and printed `offline_private_and_public_replay_pass`. A deterministic rule selected one exact-document, one-Cook-row, Cook-county, single-reported-parcel candidate. The exact identifier and declaration identity are only in the ACL-restricted, Git-ignored selection file named in [prepared.json](prepared.json); this report contains no record values.

Local verification confirmed that the plan and environment-snapshot hashes in `prepared.json` match their files, all four requirement links resolve, the private ACL is restricted, the selection file is Git-ignored, and both public and private states record zero identifiers entered and zero searches. The first combined check used the project Python 3.11 environment and exited 1 because that environment does not install PyYAML. A corrected split check used system Python 3.14 with PyYAML for public YAML/JSON (exit 0) and the project Python 3.11 for private ACL and selector checks (exit 0). `git diff --check` exited 0; `pip-audit --local --progress-spinner off` exited 0 with no known vulnerabilities in audited distributions (local unpublished package skipped). No model or full test suite was run for this source-plan preparation.

An independent security review found no critical or high findings. It verified that the private selector is ignored and restricted to the current user, Administrators and SYSTEM, and that no selected record values occur in the public diff. The remaining privacy boundary is the future MyDec submission itself.

The planned browser action still needs action-time confirmation before entering the exact document number into Illinois MyDec. **Identifiers entered: 0. Searches: 0. Declarations opened: 0. Certified sale labels: 0. U0 and G-US: PENDING.**
