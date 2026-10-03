# Read-only review record

Run ID: `u3-synthetic-local-date-off-v1-20261003`  
Reviewed code commit: `30f8e3cd7da25df7a32ab827adc2bfb31e13af7b`

This file records the reviewers' findings and the corresponding code changes.
The reviews were read-only agent inspections in the working session; their
full dialogue is not an independently archived artifact. Reproduce the
conclusions with the linked tests and code commit.

| Review | Finding | Resolution or limit |
| --- | --- | --- |
| Python model review | Changing a training label left the old model identity unchanged; direct construction could return a negative price. | `training_rows_sha256` now binds accepted label facts and feature snapshots; `__post_init__` validates price, hashes, IDs and cutoff. Both have regression tests. |
| Security review | A supplied source digest was compared with the supplied schedule digest, without hashing source bytes. The source contract included unused manifest sources. | Source-byte verification remains a documented real-data blocker. Prediction sources now come from used label and feature lineage sources, with a regression test. |
| Code review | Two economic transfers could share one source/deed ID and both train. Local feature hashes omitted the assembler policy version. | Both RED tests reproduced the gaps; fit now rejects duplicate `(source_id, transaction_id)` and the local hash includes `LOCAL_DATE_ASSEMBLER_POLICY_VERSION`. |
| Final code review | Rechecked both fixes and the as-of boundary, DST, maturity and exact-UTC compatibility paths. | No remaining critical or high issue reported. The caller-declared source digest stays synthetic-only. |

The final [test gate](test_gate.json) and [full-suite log](full_suite.log)
capture 1,244 passing tests with zero skips. This review is evidence for the
engineering fixture, not acceptance of U0, U3 or G-US.
