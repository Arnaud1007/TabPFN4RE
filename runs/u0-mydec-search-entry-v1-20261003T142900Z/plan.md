# Illinois MyDec public search-entry check

Protocol: `mydec_public_search_entry_v1`  
Date: 2026-10-03  
Requirements: US02, US05, US07, US24  
Status: frozen before search-entry navigation.

The protected public-home capture from
`u0-mydec-public-access-v1-20261003T142501Z` has SHA-256
`f6f4fd9a6d11c18419b52834f94ad8c5c9495a64e237e08e8ae9b89f20e6f193`.
It exposes one enabled internal link labelled “Search for Illinois, Cook
County, and City of Chicago Real Estate Transfer Declarations.” This does not
show whether the search form itself is reachable.

Make **one** read-only headless-browser navigation to that observed internal
link in the same isolated profile. Store the resulting DOM, time, byte length
and hash only under Git-ignored, ACL-restricted
`data/raw/illinois_mydec/search-entry-v1-20261003T142900Z/`.
Do not submit a PIN, document number, address, declaration ID, login, challenge
or purchase. If the link fails to resolve or the form is unavailable, record
the exact outcome and stop. Publish only a bounded access report. This check
cannot establish a deed, closing date, first publication, rights or a verified
home-sale label.
