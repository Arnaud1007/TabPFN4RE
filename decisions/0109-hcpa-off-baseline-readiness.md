# ADR 0109: Freeze the HCPA OFF baseline behind source admission

## Status

Accepted as a pending, executable admission gate. No HCPA model fit is
authorised by this decision.

## Context

ADR 0104 stopped retrospective HCPA admission because the available source
material did not establish closing-date semantics, historical first
availability, one-home consideration and deterministic transaction handling,
or the rights needed for model training and use. Those are source-wide
questions. Reading more private sale rows cannot resolve them.

The next model experiment should be ready to run promptly if authoritative
answers arrive. This validator keeps its own result blocked when presented
with a merely plausible archive. The future HCPA runner must consume a later
admission and fit-readiness authorization at its fit boundary, atomically
reserve its single run ID, and reject direct or replayed bypasses. This gate
must inspect only bounded, pinned, non-row decision and evidence files. It
must never inspect the HCPA archive, sample, review ledger, or sale rows.

## Decision

Maintain `data/source_admission/hcpa_allsales_v1.json` as the exact admission
record. It has four typed findings:

1. `closing_date_semantics`
2. `historical_availability`
3. `transaction_grouping_and_exclusion`
4. `use_rights`

This first gate validates only `pending` and `rejected` metadata. It rejects
`admitted` and `admitted: true` unconditionally with
`authoritative_acceptance_not_implemented`. File hashes prove byte integrity;
they do not prove that arbitrary text is authoritative or true. A later,
separately reviewed version must authenticate the accepting authority before
it can admit the source.

That later acceptance design must require all four findings to be verified. It
must also require an affirmative conclusion that `S_DATE` is the closing date,
a conservative availability method, deterministic transaction grouping and
exclusion, and permission for research training, commercial training,
commercial serving, and derived model artifacts. Comparable display is an
independent permission and may remain false without blocking the point model.

The validator rejects unknown schemas, duplicate JSON keys, missing or unknown
evidence hashes, duplicate evidence artifacts, path traversal, links, reparse
points, hard links, non-regular files, archive-like inputs, and oversized
inputs. Evidence is hashed from the same bounded file-descriptor snapshot that
is accepted. Parent component identities are checked before and after each
read. This defends against accidental replacement and ordinary redirection; a
malicious same-privilege process racing filesystem operations remains outside
the local validator's security boundary. Evidence is restricted to
`data/source_evidence/hcpa/`, plus this exact decision file.

The production CLI accepts no input paths. It validates only the exact
committed admission and policy paths. Lower-level path-taking functions exist
for isolated tests and do not expand the production interface.

Freeze `data/model_policies/hcpa_off_absolute_error_v1.json` before admission.
It declares exactly one future OFF fit using the already selected XGBoost
`reg:absoluteerror` configuration. Source admission does not permit that fit:
the semantic feature flags, historical property attributes and eligibility
rules must pass a separate fit-readiness gate first. The policy binds the exact
admission-record bytes. It is a declaration; the validator imports no training
library and performs no fit. The future runner and run ledger, rather than this
metadata validator, must enforce the declared one-fit constraint.

## Consequences

The initial admission record is `pending`; therefore model fitting and serving
are disallowed. New evidence changes the record only through an explicit,
reviewable update with exact hashes. Raw HCPA data remains outside this
validator. G-US, U2 source admission, and any commercial or accuracy claim
remain pending.
