# ADR 0039: byte-pinned Manhattan preamble exception in worksheet v4

Date: 2026-09-30
Owner: project implementation
Status: frozen before v4 code and private workbook execution
Protocol: `nyc-borough-worksheet-inspection-v4`
Requirements: US05, US07, US08, US22, US23, US24

## Evidence and decision

The immutable [v3 worksheet run](../runs/u0-nyc-worksheet-inspection-v3-20260930T092659Z/report.md) qualified four boroughs structurally and rejected Manhattan because of exactly one preamble formula. The [private v1 formula diagnostic](../runs/u0-nyc-manhattan-formula-v1-20260930T201602Z/report.md) passed an offline replay against the exact pinned source and preserved the formula privately. Its review supports discarding this preamble cell entirely; it provides no sale-label, source-freshness, or historical-availability evidence. Formula content, position, attributes, cached-value status and their fingerprints remain out of public artifacts.

Alternative A keeps v3 as the sole rule. It retains a valid rejection but leaves the official Manhattan worksheet unavailable for later source comparison. Alternative B permits any preamble formula. It could admit a changed workbook or unreviewed formula. Choose a **Manhattan-only exception for the exact captured workbook and exact privately replayed formula**. Other boroughs retain all v3 rules. V1–v3 code, results and decisions remain immutable.

## Frozen v4 rule

Use only capture `official-exports-20260929T033558Z-62ad417fb39f`, manifest SHA-256 `e29928b44a1b1f733219dac86b8d7e18704bf8c301b458afc2bf1a53895bb9e2`, and Manhattan XLSX SHA-256 `8903566fa59c9ce4c2b427ce24e268cc448d8c04f8c779839df942f29a05397a`. A changed source requires a new decision. Before v4 inspection, replay the protected v1 diagnostic from `manhattan-formula-v1-20260930T201602Z-6d714e014144` and load its canonical private formula record. A missing, tampered or incomplete diagnostic blocks v4.

For each borough, run the unchanged v3 package, header, row, date, XML/ZIP and EOF inspection on the same hash-checked file handle. Bronx, Brooklyn, Queens and Staten Island pass v4 only if their v3 worksheet result qualifies without exceptions. Manhattan must have exactly four preamble rows, the exact pinned row-5 header, at least one post-header data row, exactly one preamble formula, zero header/data formulas, and zero other structural, extra-cell, repeated-header or date violations. Privately extract the single preamble formula under the v1 bounds and require byte-equivalent parsed metadata to the replayed private record. The only v3 failure permitted for Manhattan is that formula. Any other formula, changed position, changed metadata, changed workbook bytes or malformed tail fails.

The formula and its cached value are never evaluated, returned as model inputs, used as an availability or freshness timestamp, or published. V4 may mark a **worksheet structure** qualified; it never interprets the sale-consideration column, admits a transaction row, or certifies a sale label. Every result retains `label_status: unqualified` and `sale_labels_certified: 0`.

The runner uses the existing private-root ACL, no-reparse, hard-link, source-hash, same-handle pre/post hash, 180-second cap, create-only intent, redacted public projection and byte-identical offline replay controls. An incomplete run cannot publish a pass. Preserve v3 replay as a regression check. Do not report five structural passes unless all five files pass this frozen v4 run.

## Acceptance and limits

Write synthetic RED tests before implementation. Cover the exact Manhattan exception, changed private formula, duplicate/preamble/header/data/beyond-column formulas, changed header/date/extra cells, cached-value redaction, non-Manhattan strictness, changed source bytes, missing or tampered diagnostic, path confinement, no overwrite, failed intent, replay tampering and v3 regression. Require at least 80% branch-aware coverage for each new Python module, Ruff, the full suite, dependency checks and code/Python/security reviews. Commit and push reviewed code before running v4 on the protected source. Publish a new run with actual commands, hashes and a verifier, keeping the private formula and its result fingerprint out of Git.

Rights, actual close-date meaning, first row availability, economic-transfer and unit identity, and the 200-record manual audit remain independent U0 blockers. A v4 structural pass would certify zero labels and cannot unlock model training or G-US.
