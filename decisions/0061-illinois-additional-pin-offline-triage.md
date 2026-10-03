# ADR 0061: offline Additional PIN triage without label promotion

- Date: 2026-10-03
- Owner: project implementation
- Requirements: US02, US03, US05, US06, US07, US08, US24
- Protocol: `illinois-additional-pin-offline-v1`
- Status: approved for private source-review triage only

## Decision

Replay the frozen Cook, PTAX and Additional PIN captures and the prior Cook/PTAX offline worklist. Join Additional observations to declarations by **exact** `declaration_id`; retain the Cook-row, exact-document, declaration and Additional-observation grains separately. Preserve every duplicate observation with an ordinal and source-row hash. Do not create independent price labels for repeated deed rows or additional parcels.

For comparison only, accept a Cook PIN as 14 ASCII digits or the exact display grouping `NN-NN-NNN-NNN-NNNN`. Retain leading zeros. Apply the same rule to PTAX primary and Additional PINs; mark all other punctuation or whitespace as unknown/malformed. A valid raw-string equality is `raw_exact`; equality after removing only those four predeclared hyphens is `display_equivalent`, a weaker review lead. Recognise uppercase `PT` immediately before a valid PIN or with one intervening ASCII space as `part_parcel`; an equal 14-digit base is only `part_parcel_lead`. Recognise `ROW only` case-insensitively as `right_of_way` without a PIN. Missing and malformed stay distinct. Do not strip arbitrary text, trim spaces or convert numeric values to strings.

Compare the Cook PIN independently with the primary PIN and with **each** Additional observation. Retain raw source values in the pinned capture and reference their ordinals and hashes from a new ACL-restricted private worklist. Retain observation counts, distinct raw PIN counts, exact duplicate five-field rows, and all comparison states; do not copy one Additional source row into several apparent independent records. Preserve zero/one/multiple declaration links, repeated Cook document rows, PTAX Line 2/3, Cook multi-parcel flags, and their contradictions. A zero Additional-row observation only means no row was returned in the frozen snapshot. `split_parcel` and lot-size text remain uninterpreted source observations. Prior price and date diagnostics stay at declaration grain and are not recomputed into labels.

Publish only pinned source/worklist hashes, the already disclosed 100 Cook-row, 83 document and 80 declaration denominators, zero certified labels, false historical as-of eligibility and PENDING gates. No new match count, conflict bucket, Additional-row count, PIN, declaration ID, price, date, exact query URL or free-text note enters Git. A separate reviewer must assess any identity lead against independent source instruments. The existing Cook review ledger and earlier worklist remain untouched.

## Evidence boundary

[IDOR's PTAX instructions](https://tax.illinois.gov/localgovernments/property/general-information/ptax-203_instructions.html) permit `PT` for part-parcel and `ROW only` for right-of-way without a PIN; [Cook Assessor guidance](https://www.cookcountyassessoril.gov/quick-information/where-do-i-find-my-pin) describes a 14-digit PIN. These support only the diagnostic token classes above. [IDOR's MyDec page](https://tax.illinois.gov/localgovernments/property/mydecdatafiles.html) states that declaration accuracy has not been verified. A PIN lead, equal consideration or matching recorded date does not establish a single-home arm's-length sale, close date, first public availability or commercial-use rights. No US training or G-US promotion follows from this diagnostic.

The [frozen plan](../runs/u0-illinois-additional-pin-offline-v1-20261003T051508Z/plan.md) fixes exact inputs, format rule, output caps, replay and privacy before computing any cross-source matches. A changed comparison rule needs a new protocol, not a revision to this result.
