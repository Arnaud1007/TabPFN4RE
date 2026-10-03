# MyDec interactive document-number form check

Run ID: `u0-mydec-document-form-interactive-v3-20261003T153202Z`
Date: 2026-10-03
Requirements: US02, US05, US07, US24
Status: **public document-number form verified; no declaration queried**

## Objective and method

Revisit the [v2 headless access failure](../u0-mydec-document-form-v2-20261003T144507Z/report.md) in a normal interactive browser. The [official IDOR guidance](https://tax.illinois.gov/localgovernments/property/property-transfer-tax-declarations-and-mydec.html) says recorded declarations can be searched without a login. The browser opened the [official MyDec site](https://mytax.illinois.gov/MyDec/), clicked its public declaration-search link, selected “Document Number Search”, and read the settled accessibility and DOM states. No PIN, document number, address, login, payment or search was submitted.

The first state immediately after the tab click still showed “PIN Search” selected. The following state, after navigation to `/#3`, showed “Document Number Search” selected with `aria-selected=true`, a “Search by Document Number” heading, Document Number and County fields, and a disabled Search button. [Observation metadata](observation.json) retains only public form labels and state, never a property value.

## Interpretation

This resolves the narrow form-access question left open by v2. A browser automation check must wait for the selected-tab state after the click; an immediate post-click read can see the previous tab. It does not prove that an exact document-number query will return a declaration or that the portal allows bulk access. The v1/v2 headless observations remain valid records of what those attempts saw; they are not retroactively converted into successful queries.

The next bounded step is to freeze one existing Cook/PTAX lead under a private one-query plan, using an exact document number and county already present in the existing private source sample. Before entering any identifier, verify its provenance and handling, ensure the result capture stays Git-ignored, and define a no-retry limit. A filed declaration would corroborate its own submitted fields; it would not establish a deed, closing date, one-home consideration, first publication or rights for a released model.

Local verification: Python 3.14 parsed the observation JSON, source-card YAML and requirement-map YAML and checked the zero-query, zero-label and four evidence-link assertions (exit 0). `git diff --check` passed (exit 0). The project environment's `pip-audit --local --progress-spinner off` reported no known vulnerabilities in audited distributions (exit 0; unpublished local editable package skipped). The full repository suite was not rerun for this browser-only documentation change.

**Identifiers entered: 0. Queries: 0. Declarations opened: 0. Certified sale labels: 0. U0 and G-US: PENDING.** No model training or test-label opening occurred.
