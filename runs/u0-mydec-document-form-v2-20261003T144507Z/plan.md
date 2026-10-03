# MyDec document tab retry with selected-state check

Protocol: `mydec_document_form_v2`

Date: 2026-10-03

Requirements: US02, US05, US07, US24

The v1 click call completed, but its saved DOM SHA-256
`bea4f756cc045917ce45f102efe7ae3c83bd5a5c8aa2a3a27daa736897577b87`
still marked `PIN Search` as selected and `Document Number Search` as not
selected. Thus v1 did **not** verify the document-number form.

Make one bounded retry in the same isolated browser profile. Reopen the
public declaration search, target the element with role `tab` and name
`Document Number Search`, click once, and require its `aria-selected` value
to become `true`. Save a DOM and private manifest even if selection fails.
Do not enter or submit any property identifier, login or challenge. After
this retry, stop and retain the exact result. Public reporting must not claim
the document-number form is reachable unless the selected state and field
labels both support it.
