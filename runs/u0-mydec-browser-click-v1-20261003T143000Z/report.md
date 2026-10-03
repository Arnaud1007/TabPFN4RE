# Illinois MyDec public search access

Protocol: `mydec_public_browser_click_v1`  
Date: 2026-10-03  
Requirements: US02, US05, US07, US24  
Status: **verified public search view; U0 PENDING; G-US PENDING**

The [IDOR MyDec guidance](https://tax.illinois.gov/localgovernments/property/property-transfer-tax-declarations-and-mydec.html)
documents a no-login recorded-declaration search. The
[data-file guidance](https://tax.illinois.gov/localgovernments/property/mydecdatafiles.html)
states that IDOR has not verified the declarations' accuracy. The
[first plan](../u0-mydec-public-access-v1-20261003T142501Z/plan.md)
captured both official pages and a rendered public landing page. The
[second plan](../u0-mydec-search-entry-v1-20261003T142900Z/plan.md)
tested direct navigation to the observed internal hash; it returned the
landing view. The [final frozen plan](plan.md) used a real browser click.

That click reached the public **PIN Search** view, with visible **Document
Number Search** and **Address Search** options. The field labels **Primary
PIN** and **County** appeared. The browser started and the public link click
completed; no property identifier, login or search was submitted. The initial
literal-heading heuristic in the private browser manifest returned false
because this view uses “PIN Search,” not “Declaration Search.” A create-only
inspection record parsed the captured DOM and established the correct view.

The captured public landing DOM SHA-256 is
`f6f4fd9a6d11c18419b52834f94ad8c5c9495a64e237e08e8ae9b89f20e6f193`;
the two IDOR guidance-page SHA-256 values are
`8e429e419a80383d7a263fc43c2ce4f1199bb1bd2666b5452b02b84b69f9e414`
and `b063b5668875b3d6414a4ced1c2ee1003bdb217c216ffaef0e55cf4957bcc4ed`;
the browser-click DOM SHA-256 is
`af2d9dc49d5158f08cdda786c214c888dec12ee312a521f768ad88115b468589`.
The three protected run directories passed ACL and byte-hash verification.
The [evidence manifest](evidence_manifest.json) records the pre-commit dirty
tree, runtime snapshot, plan hashes and private capture hashes; no modelling
data snapshot, split, feature policy or checkpoint exists for this access
probe. The [test gate](test_gate.json) records the bounded actions and observed
results. Session-scoped links, DOMs, cookies, browser profiles and any
property data remain outside Git. The browser tools also retained isolated
local profiles beyond the frozen plans' intended HTML/metadata artifacts;
the [deviation record](deviation.md) describes their protected state and a
policy-rejected cleanup attempt.

This improves the Cook evidence route but does not verify a particular
declaration, deed, true close date, first public availability or reuse right.
Cook has **zero certified sale labels**. The next source action is to freeze
one already sampled document-number lead for a bounded lookup, then compare
only actually displayed declaration fields against the protected Cook/PTAX
observations. A result must remain audit-only until an authoritative
instrument, timing and scope are independently resolved.
