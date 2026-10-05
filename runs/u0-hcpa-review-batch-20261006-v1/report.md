# HCPA bounded review and retrospective admission decision

Date: 2026-10-06  
Milestone: U0 source audit  
Status: checkpoint **PASS**; retrospective source admission **NO-GO**; G-US **PENDING**

## Result

Ten previously unreviewed, qualified, detached single-family sample rows were
selected without publishing their identifiers. Their official HCPA property
PDFs were captured into ignored private storage. Nine records passed the strict
evidence URL contract and were appended to the private review ledger; one was
retained privately but rejected by that contract.

Seven appended records corroborated document identity, parcel identity,
single-family class and displayed qualification. Two corroborated parcel and
class but the current property record did not expose the sampled sale row, so
document identity and qualification remained unknown.

The ledger now contains 12 complete reviews and 188 unreviewed sample rows.
All 12 retain unknown closing-date semantics, price scope, multi-parcel
allocation, reason-code meaning and reuse rights. No row is model eligible.

## Decision

[ADR 0104](../../decisions/0104-hcpa-retrospective-source-admission-no-go.md)
stops further retrospective row review until authoritative source-wide evidence
arrives. The already approved custodian inquiry remains unsent because no
authenticated mail surface is connected. Exact future release capture remains
active so first observation and correction history can be established
prospectively.

The official [download page](https://downloads.hcpafl.org/Default.aspx) exposes
the current dated files, and the official [contact page](https://www.hcpafl.org/Contact-Us/Email-Us-Feedback)
provides email, telephone and live-chat routes. Neither page resolves the four
admission questions.

## Evidence and privacy

- Private ledger SHA-256:
  `29d4d53fbf688483bb939f355dc710eb750678837ced6b8499554eeb4f578782`.
- Frozen sample: 200 rows; 12 complete; 188 unreviewed.
- No PDF, property identifier, address, price, document number, private review
  entry or row-level match is committed.
- The rejected evidence route was not weakened to increase the review count.

This checkpoint does not establish a historical 90-day origin, a qualified
sale label, commercial permission, model accuracy or market coverage.
