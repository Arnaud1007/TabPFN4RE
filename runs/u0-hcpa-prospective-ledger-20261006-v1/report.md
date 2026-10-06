# HCPA prospective release ledger checkpoint, 6 October 2026

Status: **implemented and verified; source qualification remains blocked; G-US PENDING**.
Requirements: US02, US05, US08, US22, US24.
Implementation commit: `3dce229736506d558b2ff948af7fc313847f1e83`.

## Result

The private append-only observation ledger now contains **2** verified exact-byte observations: one parcel release and one All Sales release. Both are classified `first_observation` for their independent source-family chains. The ledger SHA-256 is `a8ce7c4d2a191a6f9d92a73c783a476f4dcce6d82dc7c97a93d9027a136e177d`.

The ledger validates completed capture manifests against their saved ZIP size and SHA-256, preserves a global hash chain and per-family predecessor chain, and classifies unchanged downloads, new releases, renamed identical bytes, and same-filename corrections. Capture and ledger writes use OS advisory locks. Interrupted registration leaves a recoverable `.ledger_pending` state; stale lock files do not retain ownership.

The earlier 08:58 parcel attempt was not imported because its older manifest lacks the accepted listing evidence. No raw rows, archive members, parcel identifiers, addresses or prices are present in this tracked report or [aggregate summary](summary.json).

## Verification

- 19 focused unit and integration tests passed.
- Branch coverage: 86% for the new ledger module and 86% for the capture module.
- Ruff lint and format checks passed.
- Python compile checks passed.
- Code, Python and security reviews found no remaining commit-blocking issue.
- Both private ZIP digests and byte counts were recomputed during registration.
- The broader suite ran 1,517 tests in the lightweight environment: 1,508 passed, two skipped and seven lacked optional NumPy/scikit-learn dependencies.
- Those exact seven dependency-bearing tests then passed in the pinned model environment. See [test_gate.json](test_gate.json).

The chain detects accidental alteration within the trusted private workspace. Its hashes are not an external signature or write-once archive.

## Evidence boundary and next action

These observations prove when this workspace first captured the exact files. They do not prove earlier public availability, closing-date semantics, one-home consideration, arm's-length eligibility or commercial model-use rights. Certified sale labels remain zero.

Run `python -m scripts.capture_hcpa_release <family> <exact-listed-filename>` only when the official page lists a new release. The command will resume pending registration, capture exact bytes and append the observation automatically. Do not train an HCPA price model until the source-wide semantic and rights blockers are resolved and labels observed after the prospective origin have matured.
