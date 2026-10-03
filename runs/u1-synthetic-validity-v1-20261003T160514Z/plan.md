# Synthetic property and attribute validity check

Run ID: `u1-synthetic-validity-v1-20261003T160514Z`  
Baseline commit: `5f8658f844bbf02db3f23cb721a5263e3ca237ab`  
Requirements: US06, US08, US22, US23, US24  
Status at registration: planned; U0, U1 and G-US remain pending.

## Hypothesis and change

An explicit effective interval and independently dated publication of its end
can prevent an expired property or attribute version from entering a synthetic
OFF snapshot without introducing future corrections into earlier snapshots.
The comparator is the existing `synthetic_off_asof_v1` assembler. Change only
the canonical validity contract, attribute-copy reconciliation, as-of assembly
and synthetic bundle schema fingerprint. No real sale labels or reserved tests
are opened.

## Frozen checks

The RED cases require known expiry to remove an old version, later publication
to preserve earlier values and hashes, overlapping competing observations to
fail, identical source observation copies to reconcile, conflicting end dates
to fail, and exact boundaries and snapshot cutoffs to be honored. Run the
focused suite, full Python 3.11 suite with the pinned local OpenML ARFF path,
Ruff check and format, branch-aware coverage of touched modules, and local
dependency audit. Keep raw source data and any private identifiers outside
Git. If a check fails, retain its actual result and correct the implementation
before a separate final verification.

Acceptance is a passing synthetic test/quality gate with no skipped mandatory
test, no unresolved high review finding and an explicit compatibility bump.
This cannot accept U0/U1 or establish market accuracy.
