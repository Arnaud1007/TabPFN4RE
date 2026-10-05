# King commitment recovery checkpoint

Status: **verified synthetic recovery; not certification**  
Date: 2026-10-05

The application startup scan found one uncommitted current-format private
receipt alongside a retained legacy v1 receipt. The commit-only recovery path
validated the current private receipt, published its privacy-safe commitment
and completed without making another prediction.

## Result

- Pending current receipts before recovery: `1`
- Public commitment ID: `844a9affc0e74649e28b2241`
- Pending current receipts after recovery: `0`
- Public artifact SHA-256:
  `c56883798988276c9270e7515c6040da12b74db03ef35d1852245cd21e9f98ac`
- G-US: `PENDING`

The public artifact contains no property inputs, prediction amount, enrollment
reference, private receipt ID, request hash, response hash or privacy nonce.
Its placeholder model and commit identities show that this is a synthetic test
receipt. It is evidence for crash recovery only.

## Verification

The current implementation reopened and validated the private receipt and
canonical public commitment. A second startup scan returned zero pending v2
receipts. The retained known v1 receipt did not block discovery.

This checkpoint does not create a current valuation, a prospective sale
outcome or accuracy evidence.
