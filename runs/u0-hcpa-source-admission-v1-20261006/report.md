# HCPA source-admission gate verification

Run ID: `u0-hcpa-source-admission-v1-20261006`  
Status: **verified PENDING; source not admitted; no model fit permitted**

## Result

The new bounded gate converts the prior HCPA no-go into an executable pending
decision. The production CLI returned the same byte-for-byte JSON result on
two invocations:

- `status=pending`
- `source_admitted=false`
- `model_fit_permitted=false`
- `fit_readiness_status=blocked`
- blockers: pending semantic feature flags, historical property attributes,
  and eligibility rules

This is readiness plumbing, not source acceptance. It does not change ADR
0104's conclusion and does not authorize an HCPA fit, serving, or accuracy
claim.

## Fixed boundary

[ADR 0109](../../decisions/0109-hcpa-off-baseline-readiness.md) restricts the
production command to the exact admission record and frozen policy. The
validator permits bounded decision/evidence metadata only. It rejects raw or
row paths, archive-like formats, JSONL ledgers, links, reparse points, hard
links, unexpected schemas, and changed hashes. Its production CLI accepts no
path arguments and imports no training library.

The v1 protocol rejects every `admitted` representation unconditionally with
`authoritative_acceptance_not_implemented`. A future version must authenticate
the accepting authority and verify all four source findings. Admission alone
will still be insufficient: a separate fit-readiness authorization must clear
the three current blockers, and the future runner must atomically reserve the
one declared fit in a run ledger.

No HCPA archive, sale row, private review ledger, or model artifact was an
input to this evidence run. No model was fitted. The checked admission record
contains no row evidence and all four findings remain `unknown`.

## Verification

| Check | Observed result |
|---|---|
| Focused branch suite | 58 passed, 2 skipped, exit 0 |
| Skips | Windows could not create the file or directory symlink fixtures; the remaining link, reparse, hard-link, path, snapshot and fail-closed tests ran |
| Branch coverage | 92% for `scripts/hcpa_source_admission.py` |
| Ruff lint | Passed |
| Ruff format check | Passed; two files already formatted |
| Production CLI, twice | Exit 0; identical SHA-256 `8c3d8b36d220004f3a6a8b279e98926b3673fc0b7967c847bf6c81efe1410cd6` |

Commands, versions, exit codes, and output paths are recorded in
[test_gate.json](test_gate.json). The [manifest](manifest.json) binds the
implementation, tests, decision, admission record, policy, and public logs.

## Exact artifacts

| Artifact | SHA-256 |
|---|---|
| `scripts/hcpa_source_admission.py` | `fd835a5ac8162e826a1c63d961f13d4b9a2f9cf69fb16885b163d0548b30dd8d` |
| `tests/test_hcpa_source_admission.py` | `6d90a224c80c941d335f532b5c3ea3e5f82450c3efe37e83250dfc990f2aa954` |
| `decisions/0109-hcpa-off-baseline-readiness.md` | `12b422f03ee193e23c5d4289da51f0891f217abe860da12effff0e38a59c2ea3` |
| `data/source_admission/hcpa_allsales_v1.json` | `f03f69f2cb8b660c2e80dbc89630a4346278fdbaf5deb2752e307cc34771a320` |
| `data/model_policies/hcpa_off_absolute_error_v1.json` | `d397c7a07dc82d11ad629465acb17be99d98d54cdffd0d0835f57420e9f5f49d` |

## Requirement effect and next action

This evidence advances US05 source admission controls and U0/U2 evidence
under US24. Both requirements remain planned because the HCPA source is not
admitted. US17 is unchanged because this run performed no model experiment.

Send the already approved custodian inquiry. When an authenticated response
arrives, preserve it as bounded evidence, review rights and semantics, and
design a new acceptance protocol. Only after source admission and the separate
fit-readiness gate pass should the project implement the atomic one-run ledger
and execute the single frozen OFF baseline fit.

