# Illinois MyDec public declaration route: access check

Protocol: `mydec_public_access_v1`  
Date: 2026-10-03  
Requirements: US02, US05, US07, US24  
Status: frozen before the recorded capture below; exploratory page reads preceded this plan.

## Question

Can this environment open the Illinois Department of Revenue's public MyDec
recorded-declaration search without a login or property-specific request?
The [IDOR MyDec guidance](https://tax.illinois.gov/localgovernments/property/property-transfer-tax-declarations-and-mydec.html)
says a public search exists. The
[IDOR data-file guidance](https://tax.illinois.gov/localgovernments/property/mydecdatafiles.html)
says the open declaration files are updated weekly and IDOR has not verified
the accuracy of their contents. A MyDec view could corroborate a filed
declaration, but cannot independently prove a deed, close date, first public
availability or dwelling-level consideration.

## Bounded check

1. Save only the two public IDOR guidance pages and the MyDec public landing
   DOM with acquisition time, URL, byte length and SHA-256 in Git-ignored
   `data/raw/illinois_mydec/public-access-v1-20261003T142501Z/`.
2. Use one isolated local headless Chrome profile for the MyDec landing page.
   Do not log in, solve a challenge, submit a PIN, address or document number,
   request an individual declaration, download a form, or accept paid terms.
3. Record whether the no-login public search entry is visible. If only a login
   page or an access failure appears, record that precise outcome and stop.
4. Publish only a bounded route report, hashes and next evidence condition.
   No source row, party, property identifier, session cookie or browser profile
   may enter Git.

This is a source-access audit. It creates no sale label, temporal split, model
prediction or certification result. Existing Cook and PTAX captures remain
unchanged.
