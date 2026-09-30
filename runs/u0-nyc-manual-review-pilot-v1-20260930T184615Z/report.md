# NYC source-review pilot: ten protected v1 forms

Run ID: `u0-nyc-manual-review-pilot-v1-20260930T184615Z`  
Status: **verified review effort only; U0 and G-US pending**  
Requirements: US05, US07, US08, US22, US23, US24

## Objective and result

Review the ten frozen rows from the prior protected same-publisher comparison against the NYC source and available official recording indexes. Append findings to the private, revisioned `nyc-source-review-v1` ledger under ADR 0027. The ledger now contains **10 attested complete rubrics out of 200 selected records; 190 remain unreviewed**. Completeness records the review process, not label eligibility. The only affirmative field is the pinned publication's reported price state. All other rubric dimensions remain `unknown`. **Zero sale labels are certified.** No NYC model training or US release gate is unlocked.

The frozen protected evidence manifest records 47 hashed files, including a ten-entry ledger snapshot, ten forms, ten per-review summaries and bounded index-response captures. Its SHA-256 is `018f2a356f9e8a2d3c7a0480410c2316b12d98b20c105dbbb323d3fb5d3288b6`. Later reviews append to the live ledger without changing this run snapshot. The public [aggregate](aggregate.json) contains only overall counts and input hashes. Row identities, prices, exact review findings and protected response bytes remain under Git-ignored `data/raw/nyc_dof/manual-review-v1/`.

## Checks performed and limits

The reviewer inspected the pinned source rows, the official NYC DOF glossary, a same-publisher export comparison and bounded read-only ACRIS or Richmond County index responses where applicable. Index candidates did not establish a matched deed image, dwelling-level economic transfer, consideration scope, close date or first row publication. Dataset-specific commercial/release rights remain pending in the source card. A response to the source clarification draft has not been received. Manhattan's workbook preamble remains a separate structural task.

The first one-off Python lookup failed during import before sending a request. A retry and later bounded GETs succeeded. The one-off request code was not retained as an executable collector; request intents, response bytes and hashes are private, and this verifier supports offline integrity checks. Subsequent review batches should use a checked-in, bounded, tested collector. This run makes no prospective or as-of claim.

## Verification

From the project root, run `& 'runs/u0-nyc-manual-review-pilot-v1-20260930T184615Z/verify_artifacts.ps1'`. It validates the private manifest and captured file hashes, protected ACL, source and sample hashes, ledger against the prior frozen pilot set, all 13 review dimensions, public aggregate regeneration and the public gate. The fresh focused ledger suite ran `python -m unittest discover -s tests -p test_nyc_sample_review.py -q`: **18 tests passed in 42.947 seconds**. The preceding unchanged-code run passed 786 full-suite tests with no skips; that suite was not rerun for this data-only append because local free disk was low. See [test_gate.json](test_gate.json) for exact provenance. The public verifier is the offline replay command for these files.

## Next action

Continue the remaining 190 selected reviews with a reproducible bounded lookup runner. Obtain actual deed/transfer and dated publication evidence, resolve source rights and date semantics, and keep unsupported facts unknown. U0 remains pending; G-US and international implementation remain locked.
