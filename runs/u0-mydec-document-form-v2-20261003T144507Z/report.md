# MyDec document-number tab access check

Protocol: `mydec_document_form_v2`

Date: 2026-10-03

Requirements: US02, US05, US07, US24

Status: **document-number form unverified; U0 PENDING; G-US PENDING**

The [v1 frozen plan](../u0-mydec-document-form-v1-20261003T144257Z/plan.md)
used the already verified public MyDec search view and clicked its `Document
Number Search` text. The browser action returned successfully, but the
captured DOM still marked `PIN Search` as selected and `Document Number
Search` as not selected. The v1 DOM SHA-256 is
`bea4f756cc045917ce45f102efe7ae3c83bd5a5c8aa2a3a27daa736897577b87`.

The [v2 frozen retry](plan.md) targeted the element with role `tab`, clicked
once and checked `aria-selected`. It remained `false`; the DOM likewise
marked the document tab not selected. The v2 DOM SHA-256 is
`835c70259707f9a94e56cc955029ce6ea049df76c5d6e57ce6a49036d2815343`.
Both protected captures passed ACL, byte-hash and no-query verification. The
private capture-manifest SHA-256 values are
`1e87b56aa13b756f73d61ab0e5dbfd0ad93b847b83f7332648f4e9deda039cbe`
and `d8a3d24fa03c1b365184b4ddaae68e500f54a3e1e7321b852cd2b5ef2db1d246`.
No document number, PIN, address, login or search was submitted. The
[evidence manifest](evidence_manifest.json) records the pre-commit dirty
tree, environment snapshot, plans and private capture hashes. The
[test gate](test_gate.json) records the attempted actions and failed selected
state. The private DOMs and browser profile remain Git-ignored.

This is an automation/access limitation, not proof that the public form is
unavailable to a person using a normal browser. It also does not change the
already verified public PIN search-view observation. A one-declaration
document-number comparison must wait until the document tab is independently
seen selected, or an official alternative query route is verified. No new
sale label, closing-date rule, first-publication evidence or reuse decision
exists. Cook certified sale labels remain **zero**.
