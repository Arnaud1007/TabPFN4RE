# ADR 0104: Stop retrospective HCPA admission pending source-wide evidence

## Status

Accepted. HCPA remains the first prospective Florida source candidate, but its
current and historical downloads are not admitted for a certified retrospective
90-day OFF benchmark.

## Context

The frozen HCPA sample now has 12 complete reviewer-attested rubrics. The latest
bounded batch captured ten official property PDFs; nine passed the strict URL
and evidence contract and were appended. Seven of those nine corroborated the
sampled document, parcel, single-family class and qualification. Two current
property records did not expose the sampled sale row, so document identity and
qualification remained unknown.

Every one of the 12 completed rubrics still has unknown closing-date semantics,
one-property consideration scope, multi-parcel allocation, reason-code meaning
and commercial model-use rights. Eleven also lack an exact recording-date
comparison. Reviewing more current property PDFs can measure identity drift,
but cannot answer those source-wide questions.

The official download page currently exposes a dated current All Sales file,
not a versioned row-publication history. HCPA's contact page provides email,
telephone and live chat routes; this workspace has no authenticated mail
surface. The owner-approved inquiry remains ready to send and delivery remains
unverified.

## Decision

Stop the remaining 188 frozen sample reviews unless new authoritative evidence
addresses at least one source-wide blocker. Do not train or certify a
retrospective HCPA model from the current archives. Preserve all private review
evidence and the append-only ledger.

Continue exact prospective capture of newly listed parcel and All Sales files.
A future origin must bind the property snapshot actually observed at that
origin. A transaction label can mature only after a qualifying sale within the
declared 90-day horizon is first observed in a later captured release. Publisher
lag remains measured from those captures; it is never inferred from the sale
date. No model fit begins until sale semantics, transaction scope and permitted
use are resolved.

When those conditions pass, run one frozen `reg:absoluteerror` OFF baseline.
Do not reopen architecture search first.

## Consequences

This is a no-go for retrospective certification, not a rejection of HCPA as a
future source. It prevents a long row-review exercise from delaying predictions
while preserving the path to a prospectively timed Florida cohort. U0 and G-US
remain pending.
