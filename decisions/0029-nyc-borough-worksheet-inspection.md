# ADR 0029: bounded offline NYC borough worksheet inspection

Date: 2026-09-29
Owner: project implementation
Affected requirements: US05, US07, US08, US22 and US24
Protocol version: `nyc-borough-worksheet-inspection-v1`
Status: approved for implementation before opening workbook cells; metadata-only workbook check completed

## Context and decision

The successful [v2 capture](../runs/u0-nyc-official-export-v2-captured-20260929T033558Z/report.md)
preserves five current Department of Finance XLSX responses. Its ZIP checks
did not inspect worksheet names, headers, row counts or sale dates. This
decision authorizes **offline inspection of those pinned bytes only** to
decide whether each borough file is structurally suitable for a later,
separately specified comparison with the pinned rolling API CSV. It does not
admit a transaction label, establish a first-publication date or decide
commercial reuse rights.

The input set is exactly the five workbooks and hashes in the capture
manifest, with a total of 8,094,187 compressed bytes. The expected
advertised sale-date period is 2025-09-01 through 2026-08-31, inclusive;
this is a hypothesis to check, not an observed property of the sheets. The
expected column sequence is the pinned 21-column schema in
`scripts/profile_nyc_rolling_snapshot.py`, including `SALE DATE` and
`SALE PRICE`. Its UTF-8 SHA-256 over the 21 names joined by ASCII unit
separator is `66e69917e7320aa14485b0f6a3eee7b6ae1fc7b4632d93134a5ca53f326feb65`.
A differing header or date range is evidence to investigate;
neither is silently repaired.

A bounded read of `xl/workbook.xml` metadata, without opening worksheet
cells, observed one borough-named sheet per file and no `date1904` attribute.
This is a design observation only. The inspected XML was at most 2,481 bytes
per file; it does not prove worksheet structure or period.

## Parsing boundary

Run the capture replay before inspection. Use no network calls, Excel
application, macros, formula calculation, external links, image decoding or
archive extraction. Preserve the original XLSX files byte-for-byte. Parse
only workbook, workbook relationships, shared strings, all relationship XML
and the referenced worksheet XML. Reject any external relationship. Resolve
worksheet targets only to normalized members inside the same ZIP. For every
relationship target, reject a URL scheme, absolute or UNC path, backslash,
control character and percent encoding. Resolve permitted relative paths
using POSIX ZIP-member semantics against the source part, and reject a path
that escapes the package root or fails to identify exactly one existing
member. Never hand a relationship target to a filesystem or URL opener.
Reject VBA, OLE, ActiveX, external-link and connection parts or references,
even if the parser would otherwise ignore them. Reject
multiple data sheets, missing or duplicate relationships, ambiguous sheet
targets and a workbook using an unsupported cell representation.

At use, verify the exact workbook size and SHA-256 from the captured private
manifest immediately before and after parsing using the same open file
handle, with the ZIP reader bound to that handle. Reject symlink/reparse or
hard-link substitutions and verify the private directory ACL before opening.
If a hash changes, publish no qualified result. This detects ordinary
concurrent modification under the trusted-local-process threat boundary;
it does not claim protection from an adversary with the same user privilege.

Use a pinned XML parser with DTD, entity and external references forbidden.
The installed `defusedxml` package is not yet a declared project dependency;
the dedicated [requirements lock](../locks/nyc-workbook-requirements.txt)
pins version 0.7.1 to the [published wheel hash](https://pypi.org/pypi/defusedxml/0.7.1/json).
Install from that lock before implementation runs. Its official API
exposes `iterparse(..., forbid_dtd=True, forbid_entities=True,
forbid_external=True)`; tests must exercise those settings. Microsoft Open
XML documentation describes shared-string indices and the workbook's
`date1904` switch. These are parsing rules, not evidence about the five
captured files. [defusedxml](https://github.com/tiran/defusedxml/blob/main/defusedxml/ElementTree.py),
[shared strings](https://learn.microsoft.com/en-us/office/open-xml/spreadsheet/working-with-the-shared-string-table),
[date1904](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.spreadsheet.workbookproperties.date1904),
[Open XML workbook property default](https://mailman.vse.cz/pipermail/sc34wg4/attachments/20100427/00129e1d/attachment-0001.pdf).

Retain the v2 ZIP safety caps and add explicit inspection limits: 32 MiB
decoded worksheet XML per file, 4 MiB shared strings, 1 MiB for each other
parsed XML member, 150,000 physical rows, 64 cells per row, 100,000 shared
strings, 512 characters per string and 180 seconds elapsed for the five-file
inspection. Reject an input when a limit is exceeded. Stream XML and clear
completed row elements; do not load a worksheet tree in memory. Bound all
cell-reference indices to A through BL and reject duplicate coordinates.
The parser records safe failure categories, not raw cell text, in public
reports.

## Schema and period decision

One physical row means one `<row>` element in worksheet XML; an empty row
element counts toward the first-25-row search and the 150,000-row cap.
Reject duplicate or nonmonotone row numbers. Inspect at most the first 25
physical rows for one header row. Permit only
trimmed surrounding whitespace in header cells; after trimming, require the
exact ordered 21-column sequence. Reject duplicate or missing headers,
additional nonempty header cells and multiple candidate header rows. Count
every nonempty row after the header as a data row. Empty trailing rows do
not become sales. Unexpected nonempty notes or footer rows count as invalid
data, rather than being dropped to make a clean result. Rows before the
header are preamble, recorded as a count and not treated as sales. Any
nonempty data cell beyond the 21 approved columns blocks qualification;
hidden or extra cells cannot be silently discarded.
A repeated header later in the sheet is recorded as an anomaly and blocks
period qualification.

Read `SALE DATE` only from the registered column. Accept unambiguous
`MM/DD/YYYY` and ISO `YYYY-MM-DD` text, or an integral finite Excel serial.
Read `workbookPr@date1904` when present; use the documented 1900 default
when absent and record that defaulting decision. For the 1900 system reject
serial 60 and values before 61; for the 1904 system require nonnegative
integral serials. Reject fractional or ambiguous dates. Record min/max dates,
unparseable/missing and out-of-period counts separately. A qualified
borough requires one sheet, exact header, at least one data row, zero
unparseable/missing/out-of-period dates, zero formulas in the 21 audited
columns and no rejected package or XML condition. Formula presence is
reported without reading a cached formula result. No sale price is parsed
or used to decide this phase.

The public result may contain borough names, approved schema fingerprint,
sheet count, physical/data-row counts, date minima/maxima and safe anomaly
counts. Raw header text, row values, addresses, apartment identifiers,
prices and reviewer notes remain in a protected Git-ignored artifact. An
unexpected header is represented publicly by a fingerprint and mismatch
status, not echoed. Every outcome, including failure, remains attached to
the original five hashes. A complete result for one borough does not imply
all five qualify.

## Execution and acceptance

Write synthetic tests first for valid shared strings, text and serial dates;
preamble and blank rows; header mismatch/duplication; extra sheet; external
relationship; DTD/entity; formula and cached-value traps; corrupt or
oversized members; row/cell/string/time caps; wrong captured hash; private
ACL failure; relationship traversal, UNC, backslash and percent encoding;
active OOXML parts; symlink/reparse/hard-link inputs; post-read hash changes;
and no-overwrite output. Require at least 80% branch-aware
coverage for the inspector. Test that public output never includes
unregistered cell text or direct identifiers. Run the full repository suite,
Ruff and dependency checks, then independent code and security reviews.

Commit and push the reviewed inspector and pinned environment **before**
opening these workbooks through it. Run once to an ignored, protected,
create-new private directory with an intent, detailed result and hash
manifest. Publish a tracked aggregate, verifier, test gate and report. An
offline replay must re-read the pinned workbook bytes and recompute the
aggregate. It makes no network call and does not overwrite the original
inspection. If a workbook fails, keep its bytes
and status; revise the protocol under a new version rather than editing the
input or pretending the period matched.

Same-publisher row comparison begins only under another frozen protocol.
Agreement between two DOF extracts cannot independently prove transaction
truth, closing-date meaning, historical as-of availability or reuse rights.
U0 and G-US remain pending.
