# ADR 0004: Synthetic OFF baseline and transfer-level split identity

Date: 2026-09-28

Owner: project implementation
Affected protocol: U1 synthetic engineering only; no real-world certification version

## Context and alternatives

The low-level feature validator could accept caller-supplied definitions, and a raw source transaction ID could identify one feed's copy of a sale while another feed's copy entered a different split. We considered trusting declared feature definitions and source-scoped raw IDs, or binding fit to the existing as-of assembler and a canonical economic-transfer key.

## Decision

`GuardedOffMedian.fit` constructs OFF snapshots from canonical inputs, validates the application-owned core feature list and per-feature lineage, and rejects reserved economic transfers. It requires a simulated training cutoff; both closing and first label availability must precede it. The fitted model stores that cutoff and rejects earlier prediction origins. The point estimate is the median of eligible training sale prices. This is an engineering baseline, not a claim of US accuracy.

The partition key is `Transaction.economic_transfer_id`, so source copies of one transfer remain in one split. Raw `(source_id, transaction_id)` is retained in the source record for traceability. A conflicting duplicate must be quarantined during canonicalisation.

## Evidence and limits

The U1 synthetic gate in `runs/u1-canaries-20260928T113723Z/` passed T01–T08 canaries and a 200-row synthetic flow. The 160 training labels mature before the 40 reserved prediction origins. The full local suite passed 131 tests at 89% statement coverage. This does not verify source factual correctness, historical vintages, data rights, a real US temporal split, market accuracy or the G-US gate.

An approved name and lineage timestamp cannot detect a dishonest upstream source that copies a sale outcome into a legitimate field such as condition. Source audits and adapter-level provenance remain required. The current comparable filter reconciles every visible transaction per query; U2 must canonicalise and index larger source tables before real-scale retrieval.
