# ADR 0030: pinned NYC printer-settings exception for worksheet inspection v2

Date: 2026-09-29
Owner: project implementation
Affected requirements: US05, US07, US08, US22, US23 and US24
Affected protocol: `nyc-borough-worksheet-inspection-v2`; v1 remains frozen
Status: approved for implementation after architecture and security review; code and data gates pending

## Evidence and choice

The [frozen v1 inspection](../runs/u0-nyc-worksheet-inspection-v1-20260929T080639Z/report.md) replayed the five pinned official XLSX files and rejected all five packages. Metadata-only diagnosis identified the same `xl/printerSettings/printerSettings1.bin` member in each. Its decoded size is 5,024 bytes and SHA-256 is `7d3c762f37f75bbe2ff459ab52b55b2e7be8a8603e2ad227248f6d4519a0f96b`. Each package declares a `bin` default content type of `application/vnd.openxmlformats-officedocument.spreadsheetml.printerSettings` and has a worksheet relationship of type `http://schemas.openxmlformats.org/officeDocument/2006/relationships/printerSettings` to that member. These observations do not establish worksheet or transaction correctness.

The same bounded metadata-only check found four internal package-root relationships in each workbook: `officeDocument` to `xl/workbook.xml`, `core-properties` to `docProps/core.xml`, `extended-properties` to `docProps/app.xml` and `custom-properties` to `docProps/custom.xml`. V1 required the root relationship map to contain only `officeDocument`; that would be a second deterministic rejection after the binary exception. The printer-settings relationship's literal target is `../printerSettings/printerSettings1.bin` from `xl/worksheets/sheet1.xml`, resolving inside the ZIP. These document-property parts and printer settings contain no valuation inputs and must not become features.

| Root relationship Type URI | Literal Target |
| --- | --- |
| `http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument` | `xl/workbook.xml` |
| `http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties` | `docProps/core.xml` |
| `http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties` | `docProps/app.xml` |
| `http://schemas.openxmlformats.org/officeDocument/2006/relationships/custom-properties` | `docProps/custom.xml` |

All five ZIP inventories share these 13 members: `[Content_Types].xml`, `_rels/.rels`, `docProps/app.xml`, `docProps/core.xml`, `docProps/custom.xml`, `xl/_rels/workbook.xml.rels`, `xl/printerSettings/printerSettings1.bin`, `xl/sharedStrings.xml`, `xl/styles.xml`, `xl/theme/theme1.xml`, `xl/workbook.xml`, `xl/worksheets/_rels/sheet1.xml.rels` and `xl/worksheets/sheet1.xml`. Manhattan alone also has `xl/calcChain.xml`. These are package metadata observations, not parsed worksheet evidence.

The [Microsoft Printer Settings part documentation](https://learn.microsoft.com/en-us/openspecs/office_file_formats/ms-xlsb/1cdc4cb9-836d-41d6-a5b5-9ac0428f491c) corroborates the named content type and relationship, at-most-one-per-worksheet rule and no-outgoing-relationship rule. That page is for an Office file-format specification; it does not certify these XLSX files, the binary's safety in Excel or any sale-row semantics. This inspector never opens an Excel or printer API.

Alternative A was to keep the blanket `.bin` rejection and leave the official workbooks uninspected. Alternative B was to allow any printer-settings binary by path or MIME. The selected choice is a **byte-pinned, opaque exception** limited to these already captured workbooks. It permits a structural inspection while refusing new or changed binary content until a separately versioned review. This is an engineering decision after observing a failed v1 run; it never changes v1's result.

## V2 acceptance rule

Keep the five outer workbook sizes and SHA-256 hashes, capture replay, protected private storage, same-handle pre/post hash and `fstat`, ZIP/XML/time caps, defused XML settings and redacted output from ADR 0029. Before accepting any `.bin` member, require all of the following:

1. Require the exact 13-member package inventory above, plus only the optional `xl/calcChain.xml`. The outer workbook hashes bind that optional member to Manhattan for this run. Reject every other part or directory entry, including opaque members under an extension other than `.bin`. Within that inventory, require exactly one `.bin` member, compared case-sensitively after the existing ZIP name and casefold-alias checks, and require it to be `xl/printerSettings/printerSettings1.bin`. Its decoded byte count must be 5,024 and its streamed SHA-256 must be the pinned value above. Read through EOF so ZIP CRC is checked; do not extract, decode as a printer structure, render or execute it.
2. The effective content type for that member must be exactly `application/vnd.openxmlformats-officedocument.spreadsheetml.printerSettings`. Require exactly one observed-style `Default Extension="bin"` declaration. Reject every `Override` for the binary member, even one with the same MIME, as well as duplicate/default conflicts or any other binary content type.
3. Across **all** parsed relationships, exactly one incoming reference to the binary member is allowed. It must be an **internal** relationship of type `http://schemas.openxmlformats.org/officeDocument/2006/relationships/printerSettings` from the selected worksheet. Its literal target must be exactly `../printerSettings/printerSettings1.bin` and resolve to the exact member. The single `..` segment is allowed only because it resolves within this pinned package; reject root escape, encoded, absolute, aliased, external, duplicate, wrong-type, wrong-source and extra incoming references. The exact package inventory also excludes any outgoing relationship part for the binary member.
4. Require exactly the four observed internal root relationships in the table, with one of each **full Type URI and literal Target**. Also require each Target to resolve to that same ZIP member under the existing safe path resolver. Reject extra, missing, duplicate-type, alternate-spelled or redirected root entries. Continue v1's generic safe internal target resolution for other relationship parts, while rejecting active types and all external targets; this decision does not add an unrestricted new relationship type.
5. Keep rejecting VBA, OLE, ActiveX, external links, connections, all other `.bin` paths or casing and active content-type declarations. Do not treat document-property or printer-settings members as worksheet inputs or features.

The v2 parser must expose a distinct protocol identifier. It must not overwrite, rerun in place or relabel the v1 private run. New inspection writes to a new protected, create-new directory and is independently replayed. If any condition fails, retain an unqualified/rejected status and the exact source hash. A successful structural result still cannot admit sale labels or historical as-of features.

## Tests and promotion

Write synthetic RED tests before changing the parser. A test-only internal helper may receive an immutable printer-settings size/digest policy for fixture bytes. The production CLI, environment and request schema expose no policy override; `inspect_capture` always uses the hardcoded production pin, separately asserted against captured metadata. Cover one valid fixture member; missing binary; wrong hash, size, path and case; missing, duplicate or conflicting MIME declaration, including a matching `Override`; missing, duplicate, external, root-escaping, aliased, wrong-type, wrong-source or extra incoming relationship; outgoing `.rels`; unknown opaque/extra binary; and preserved active-part rejection. Cover the four valid root relationships and missing, duplicate-type, extra and redirected root entries. Confirm no binary interpretation occurs. Repeat 80%+ branch-aware inspector/parser coverage, the full repository suite, Ruff, dependency checks and independent code/Python/security review.

Only after v2 code is committed and pushed may it inspect the captured workbook cells in a new run. The final report must compare v1 and v2 outcomes without calling a v1 rejection a pass or treating v2 structural qualification as a certified transaction source. Source rights, sale-date meaning, first availability and the 200-record manual audit remain independent blockers for U0/G-US.
