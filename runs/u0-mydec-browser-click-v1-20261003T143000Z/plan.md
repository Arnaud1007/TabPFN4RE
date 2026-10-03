# MyDec public search link interaction

Protocol: `mydec_public_browser_click_v1`  
Date: 2026-10-03  
Requirements: US02, US05, US07, US24  
Status: frozen before interaction.

Direct navigation to the public landing page's internal hash returned the
landing page again. This check uses the already installed Playwright Core
1.60.0 with local Chrome 155.0.8059.27 in a new isolated, protected profile.
It will navigate once to `https://mytax.illinois.gov/MyDec/`, click **only**
the observed public link labelled “Search for Illinois, Cook County, and City
of Chicago Real Estate Transfer Declarations,” and inspect the resulting form.

Store the resulting DOM and a private outcome manifest under Git-ignored
`data/raw/illinois_mydec/browser-click-v1-20261003T143000Z/`. Do not fill or
submit any field, authenticate, solve a challenge, purchase, or extract a
declaration. The only public output is whether the form was reachable and
which *field labels* appeared. A failed browser launch or link action ends
this attempt. No sale label or availability rule is established.
