# HCPA second property-record review checkpoint

Date: 2026-10-05  
Milestone: U0 source audit  
Gate: HCPA certified training remains blocked; G-US remains **PENDING**

## Result

An official HCPA print record for one previously unreviewed, sampled
single-family row was downloaded into ignored private storage and pinned by
SHA-256. Offline comparison found exactly one matching frozen sample row and
199 rows with no identity match. The match covered document identity, parcel
identity, property class and the displayed qualification status.

The evidence policy now represents the exact print-record source as
`hcpa_property_record_pdf`. It accepts only the exact official HTTPS host, path
and single strict `pin` query. Like the browser-page evidence, it can support
only the four checks above. It cannot establish dates, consideration scope,
multi-parcel allocation, reason-code meaning or reuse rights.

The official Clerk route was attempted but blocked in this browser environment.
That access limit was recorded privately. A complete reviewer-attested rubric
kept every unresolved transaction and rights dimension unknown. The private
ledger now contains 4 append-only entries covering 3 unique sampled records; 197 remain
unreviewed. No row became model eligible.

## Privacy and public evidence

The tracked [candidate aggregate](aggregate.json) omits the PDF fingerprint,
record ordinal, observation time, identifiers, price, address and private path.
The tracked [review summary](review_summary.json) contains aggregate counts
only. The [selection check](selection_check.json) proves the PDF had exactly one
full four-field match among all 200 sample rows and that the row was absent from
the prior two-record ledger. No private PDF, review entry or ledger bytes are committed.

## Verification

- 67 related tests passed.
- The three changed modules achieved 87% combined branch coverage.
- Ruff format and lint passed.
- A generated full-cohort selection check found 1 full match and 199 nonmatches; the selected row was previously unreviewed.
- The private review entry records the SHA-256 calculated from the inspected PDF.
- Ledger replay reported 3 complete, 0 partial and 197 unreviewed records.
- Candidate aggregate SHA-256:
  `8683300357f239e740792c254fda929bc2d31f46afc4b9169c7b3071939412b1`.
- Review summary SHA-256:
  `4204c033043c09ba256c6ca26e972e46a7a26b1a0e02e65455bae1b0f3aa3fd4`.

## Remaining blocker

HCPA still lacks verified closing-date semantics, one-home consideration scope,
historical per-row availability and commercial model-use terms. Continue the
stratified review, but do not fit the 90-day OFF baseline until those source-wide
questions clear.
