# HCPA private property-record candidate checkpoint

Date: 2026-10-05  
Milestone: U0 source audit  
Gate: HCPA certified training remains blocked; G-US remains **PENDING**

## Result

A hash-pinned official property-record PDF was compared offline with the frozen
200-record HCPA sample. Exactly one private sample row matched on document
identity, parcel identity, the narrowly allowlisted single-family class and the
qualification display. The other 199 rows produced no identity match.

The private result is a create-only **candidate**. It is explicitly un-attested,
was not appended to the review ledger and is not model eligible. The public
[aggregate](aggregate.json) contains only the frozen cohort hash and four state
counts. It omits the property PDF hash and size, record ordinal, observation
time, identifiers, price, address and private paths.

The existing private review ledger was not modified. Its SHA-256 remains
`b37ab8a906a60f7ef103be3b6a228360e729c80811b43e4cef50a5fa36846ac1`,
so the accepted audit count remains 2 complete and 198 unreviewed.

## Evidence boundary

This candidate does not establish closing, deed-execution or recording dates;
one-property consideration; arm's-length status; historical availability; or
commercial and derived-product reuse rights. Those facts remain unknown. No
training row was admitted and no model was fitted.

## Verification

- 50 related tests passed.
- The two changed modules achieved 88% combined branch coverage.
- Ruff format, Ruff lint and `git diff --check` passed.
- The private candidate replayed to the committed aggregate exactly.
- Code, Python and security reviews were required before commit.
- Aggregate SHA-256:
  `8683300357f239e740792c254fda929bc2d31f46afc4b9169c7b3071939412b1`.

## Next action

Have a reviewer inspect the private candidate alongside the official page and
the required Clerk evidence or documented access attempt. Only a separate,
attested ledger revision may advance the completed-review count. Continue to
keep date, consideration, historical availability and rights findings unknown
until their source-wide questions are resolved.
