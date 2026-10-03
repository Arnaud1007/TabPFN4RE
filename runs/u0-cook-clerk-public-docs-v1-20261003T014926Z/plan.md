# U0 Cook Clerk public-document capture plan

Run ID: `u0-cook-clerk-public-docs-v1-20261003T014926Z`  
Owner: project implementation  
Requirements: US02, US05, US07, US08  
Status before capture: planned

## Question

Can the official Clerk's public documentation identify a usable route for
checking recorded instruments, execution versus recording dates and fees,
without implying that the Assessor's current parcel rows have historical
first-publication evidence or commercial-use rights?

## Bounded inputs and method

Capture only the following official URLs once, using read-only GETs, with a
15-second timeout per URL. Preserve response bytes and HTTP status, content
type, retrieval time and SHA-256 in a new Git-ignored, ACL-restricted directory
under `data/raw/cook_county/`. Abort if a response exceeds 1 MiB or is not
HTML/PDF. Do not request a property row, person, deed image, paid document or
subscription.

1. `https://www.cookcountyclerkil.gov/recordings/search-recordings`
2. `https://www.cookcountyclerkil.gov/publication/transfer-list-license-agreement-summary`
3. `https://www.cookcountyclerkil.gov/recordings/recording-fees`
4. `https://www.cookcountyclerkil.gov/recordings/recording-faqs`

Use the installed `pdftotext` only for private inspection of the saved PDF.
The public report may include URL, status, type, byte count, digest and a
short paraphrase of relevant terms. Do not commit raw HTML/PDF or extracted
text. Verify the source bytes and run report before updating the source card
and decision record.

## Interpretation rule

A published route or paid data product is a feasibility lead, not an obtained
record or permission to use it. Do not treat execution date as contract or
closing date. The current Assessor feed remains ineligible for the primary
90-day close-origin benchmark unless row-level identity, time and rights are
separately established. No model training or gate change follows this capture.
