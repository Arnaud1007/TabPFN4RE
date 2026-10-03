# Frozen offline Cook–PTAX diagnostic plan, v1

Frozen on 2026-10-03 UTC before inspecting PTAX candidate-level rows.

## Inputs and cap

- Cook private 200-row sample manifest SHA-256:
  `130b5169ff81ccbc0a729cba98400f2fb377ff9a25999316aaac1960e38a3cf7`.
- PTAX private one-shot capture: `ptax-link-v1-130b5169ff81ccbc`, whose
  committed public aggregate has response-set SHA-256
  `69d86b7fb9c221dee662d49ebc01b94ef26f5e2862a0c9d26afb887f997cd05a`.
- Reuse the exact 100 selected recent Cook rows, 83 distinct document strings,
  80 captured PTAX declarations and 20 requests. No network request is made.
- Abort before output if either offline verifier fails, input membership differs,
  source hashes differ, an unexpected row field appears or the pair worklist
  exceeds 500 candidate links.

## Exact analysis

Join only identical nonempty document strings. Preserve the three grains:
selected Cook rows, unique document strings and PTAX declarations. Build one
private worklist item per selected Cook row, including zero-candidate rows and
all matched declaration IDs and source hashes. Never discard duplicate deed
rows or allocate one declaration amount among them.

For each candidate relation, record diagnostic states for county, exact PIN,
parcel scope, Line 11/13 versus Cook reported price, recorded-date comparison,
coarse instrument month/year, status/use/instrument code presence and
related-party flag. Validate numeric and date representations; separate
missing, malformed, different and matching values. Use `Decimal` for money.
Do not promote an agreement to an eligible single-home sale or infer missing
flags as false.

Assign private review priority from missing/multiple links, county/PIN
conflict, multi-parcel indicators, price/recorded-date disagreement and
unresolved flags. Preserve raw selected source fields only in the private
worklist, never in the public summary. The reviewer queue is not a completed
manual audit or a training set.

## Storage and public boundary

Create a new ACL-restricted directory under Git-ignored
`data/raw/illinois_ptax203/` before writing. Save a private immutable worklist,
input and output hashes, protocol, source membership and completion manifest;
mark complete last. Limit private output to 512 KiB and fail closed. Do not
overwrite the captured inputs or the Cook review ledger. An offline verifier
must recompute all findings from the pinned captures and compare exact bytes
without network access.

The committed aggregate contains only the protocol, source hashes, previously
published denominators (100 Cook rows, 83 document strings, 80 declarations),
private-worklist SHA-256, reviewer-queue size, zero certified labels, false
historical as-of eligibility and U0/G-US PENDING. It contains no new
match/conflict bucket counts. No document number, PIN, declaration ID, date,
price, row hash, URL or free-text note may enter Git. An internal small count
must not be reconstructible from overlapping public totals.

## Acceptance checks

Synthetic tests specify 0/1/N joins, repeated Cook deed rows, duplicate PTAX
IDs, exact leading-zero and punctuation behavior, county conflict, primary
versus secondary PIN ambiguity, multi-parcel repeated consideration,
Line 11/13 disagreement, related-party and unknown codes, malformed
number/date/currency, public privacy and tampered inputs. Run tests RED, then
GREEN with at least 80% branch-aware coverage for the new module. Re-run
offline replay, Ruff, the full repository suite and security review before
committing and pushing. Skipped mandatory tests fail their gate.

No result from this diagnostic can certify a close date, first public
availability, source reuse for deployment, arm's-length status or a price
label. The next decision is whether to manually attest the linked records and
qualify Additional PINs through a separately registered source plan.
