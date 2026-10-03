# MyDec document-number search form, no query

Protocol: `mydec_document_form_v1`

Date: 2026-10-03

Requirements: US02, US05, US07, US24

The verified public search-view DOM SHA-256 is
`af2d9dc49d5158f08cdda786c214c888dec12ee312a521f768ad88115b468589`.
Its visible tabs include `Document Number Search`. The specific form fields
have not been inspected. Use the same protected, isolated browser profile to
reopen MyDec, click the public declaration-search link, then click only the
`Document Number Search` tab. Save the resulting DOM, capture time and hash
under Git-ignored `data/raw/illinois_mydec/document-form-v1-20261003T144257Z/`.

Do not enter or submit a document number, PIN, address, login or challenge.
Stop if the tab is absent or disabled. Publish only field-label evidence and
access limits. This is not a record query and cannot certify a sale label.
