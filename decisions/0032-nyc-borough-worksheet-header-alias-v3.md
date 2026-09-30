# ADR 0032: exact NYC borough worksheet header alias for v3 inspection

Date: 2026-09-30
Owner: project implementation
Affected requirements: US05, US07, US08, US22, US23, US24
New protocol: `nyc-borough-worksheet-inspection-v3`
Status: frozen design for implementation; code and source run pending

## Evidence and choice

The [v2 worksheet result](../runs/u0-nyc-worksheet-inspection-v2-20260929T091128Z/report.md) rejected all five byte-pinned borough workbooks under its exact 21-column API-header rule. The separately versioned [verified header diagnosis](../runs/u0-nyc-header-diagnostic-v1-verified-20260930T075500Z/report.md) found a unique 21-cell candidate at source and physical row 5 in each workbook. Each candidate has 20 exact positional matches, no header formulas or extra cells, and the same raw fingerprint `4f8efb3fe379c1adb05938d397271d6c38002b6c2fdbe2224b3c4aa68d529e95`. Protected candidate vectors are identical across boroughs. The only position-wise difference from the pinned rolling API header is column G: workbook `EASEMENT`, API `EASE-MENT`. The diagnostic did not parse sale rows, dates or prices.

Alternative A is to keep the v2 exact-name rule; it correctly records a failure but prevents inspection of the observed official worksheet structure. Alternative B is to normalize punctuation or fuzzy-match headers; that could admit unreviewed schema changes. Choose an **exact, byte-pinned, one-position alias** for a new protocol. This decision does not retroactively change v1 or v2 outcomes. It does not certify a transaction, historical availability or reuse right.

## V3 qualification rule

Use only the five captured XLSX hashes and capture manifest from `official-exports-20260929T033558Z-62ad417fb39f`. Retain all v2 ZIP inventory, opaque pinned printer-settings, MIME, relationship, XML safety, decoded-size, row/cell/string, 180-second, ACL, reparse/hard-link, same-handle pre/post hash and offline replay controls. Reject changed bytes. Do not open Excel or a network service, execute formulas or extract package parts to a filesystem.

Require physical and source worksheet row 5 to contain the 21 ordered, trimmed column names. Positions A:F and H:U must equal the pinned API header exactly. Position G must equal `EASEMENT` exactly. Reject missing or extra nonempty header cells, formulas, duplicate coordinates, a differently positioned header, any other spelling or case, and an extra complete candidate in the first 25 rows. Check both the full raw vector and its pinned fingerprint. Map only the **header name** at G to canonical `EASE-MENT`; never modify its row values, infer an easement status or use this metadata as a predictive input. Preserve the original header name and source column position in lineage.

Continue streaming the worksheet to EOF with bounded defused XML and ZIP CRC validation. Count physical rows, preamble rows and nonempty post-header rows separately. Parse column U as a sale-date candidate under the v2 date-system and 2025-09-01 through 2026-08-31 period rules. Report date minimum/maximum, missing or unparseable dates, out-of-period dates, repeated raw or API-style headers, nonempty cells beyond U, and formulas by preamble/header/data zone. Require at least one data row and zero date, repeated-header, extra-cell or formula violations for **worksheet structural qualification**. A formula anywhere in the worksheet, including preamble or beyond U, blocks qualification; do not infer its harmlessness from location. Manhattan's v2 formula count of one is unresolved and may keep it unqualified.

Never interpret column T as a verified sale consideration or count a physical/data row as an eligible economic transfer in this protocol. Public output contains borough-level counts, safe status/reason categories, source hashes, header fingerprints and date range only. It contains no header strings, address, apartment identifier, sale price, row ID or raw sale cell. Every aggregate retains `label_status: unqualified`, `sale_labels_certified: 0`, and separate `worksheet_qualified_count`. A package, malformed-tail, timeout or integrity failure is not silently dropped; incomplete runs have no valid aggregate.

Create a new protected, exclusive private run with intent, result, redacted public projection and hash manifest. Independently recompute both private and public canonical JSON from the same pinned files for replay. Record code commit, dirty-tree status, both relevant lock hashes, exact commands, tests, timings and failures. Do not overwrite the v1/v2 inspections or either header-diagnostic run. Push reviewed code before opening the workbook cells under v3.

## Tests and promotion

Write synthetic RED tests before implementation. Cover exact G alias acceptance and rejection of case, whitespace-internal, punctuation, moved-position or second-column variants; source/physical row-5 and pinned fingerprint checks; a second plausible header; missing A:U coordinates, duplicate/nonmonotone rows and cells, extra cells, inline/shared strings, and a repeated header. Test formulas in preamble, header, data and beyond U, including cached-value nonuse. Test valid and invalid ISO, US text and Excel serial dates, 1900/1904 systems, boundaries and out-of-period values. Carry forward v2 package/ZIP/XML/hash/ACL/no-overwrite/timeout/redaction/replay tests. Confirm v1/v2 replay outputs remain unchanged. Require 80%+ branch-aware coverage for new modules, the full suite without mandatory skips, Ruff, dependency and security checks, and independent code/Python/security review.

Only a passed v3 **worksheet structure** gate unlocks a separately frozen same-publisher row comparison and manual source review. Rights, actual close-date meaning, first row availability, transfer/parcel/unit identity and the 200-record NYC manual audit are independent requirements. No v3 outcome can by itself admit training labels or satisfy U0 or G-US.
