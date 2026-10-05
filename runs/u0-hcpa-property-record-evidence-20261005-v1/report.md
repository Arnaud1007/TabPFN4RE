# HCPA official property-record evidence checkpoint

Date: 2026-10-05
Milestone: U0 source audit
Gate: HCPA certified training remains blocked; G-US remains **PENDING**

## Result

The audit workflow now recognizes narrowly validated official HCPA parcel
pages. The first additional single-family sample review matched the frozen
source row to the official parcel and sale-history display. The page explicitly
reported a single-family property and agreed with the source qualification
label.

The private append-only ledger now contains three entries covering two unique
sample records. Both records have complete reviewer-attested rubrics; 198 of
200 records remain unreviewed. The post-append private ledger SHA-256 is
`b37ab8a906a60f7ef103be3b6a228360e729c80811b43e4cef50a5fa36846ac1`.

## Evidence boundary

The page does not establish:

- an exact closing, deed-execution or recording date;
- whether consideration covers exactly one property;
- multi-parcel allocation or concessions;
- the source reason-code meaning;
- commercial AVM or derived-product permission;
- historical availability at a prediction origin.

The reviewed row remains ineligible for certified training. No address, owner,
folio, PIN, document number, property-record URL or private ledger content is
tracked in this checkpoint.

## Verification

- 32 review and evidence-policy tests passed with 88% branch coverage of the review module.
- Ruff formatting and lint passed.
- Unsafe schemes, external and suffix-spoof hosts, credentials, unrelated HCPA
  pages and malformed routes were rejected.
- Transaction timing, consideration and rights dimensions rejected the new
  evidence type as insufficient.
- Aggregate replay reported 2 complete, 0 partial and 198 unreviewed records.

## Next action

Continue the stratified 200-record audit using official pages for bounded
identity checks. Keep unresolved deed and source-wide semantics unknown while
the custodian inquiry remains undelivered.
