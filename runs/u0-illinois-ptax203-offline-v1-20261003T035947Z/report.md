# U0 Cook–Illinois PTAX-203 offline linkage diagnostic

Run ID: `u0-illinois-ptax203-offline-v1-20261003T035947Z`  
Code commit: `8a8c6c35fd1c6bd54b0e8e806ba631d29fc569c0`  
Requirements: US02, US03, US05, US06, US07, US08, US24  
Status: **offline diagnostic verified; U0 and G-US PENDING**

## Objective and observed result

The [frozen plan](plan.md) registered an exact-document, no-network diagnostic before candidate-level inspection. It reuses the verified [Cook source sample](../u0-cook-sales-sample-20261003T004123Z/report.md) and [official PTAX-203 capture](../u0-illinois-ptax203-link-v1-20261003T032248Z/report.md). Their pinned inputs contain 100 selected recent Cook rows, 83 document strings and 80 PTAX declarations. The code retains zero, one and multiple candidate relationships and creates one private review item per selected Cook row. It never allocates a declaration-level consideration to a home or treats a candidate link as a sale label.

The [public aggregate](aggregate.json) reports the input hashes, a 100-item review queue, the private worklist hash, zero certified labels and PENDING gates. The private, Git-ignored worklist is 189,576 bytes; its completion manifest is 395 bytes. It contains the row-level diagnostics and review priorities under an ACL-restricted directory. No new match, conflict or small-cell counts, identifiers, prices or dates were published.

## Interpretation and blockers

Cook PIN and PTAX primary-PIN fields have different raw representations in this capture. Version 1 keeps exact strings and flags unresolved identity; it does not silently normalize a match. The captured PTAX `line_3_additional_pins` is a Boolean indicator, not a secondary-PIN list. Its [separate official candidate view](../../data/source_cards/illinois_idor_ptax203.yaml) has not been acquired or qualified. County, parcel scope, Line 11/13 consideration, recorded dates, coarse instrument month, related-party flag and unqualified codes are private review prompts, not eligibility decisions.

The existing Cook ledger remains one complete rubric, one partial and 198 untouched. This 100-item diagnostic queue is **not** 100 completed manual audits. Source-specific commercial use, one-home transfer scope, closing-date meaning, first row availability and historical property-attribute vintages remain unresolved. No real 90-day as-of benchmark or model training is justified; U0 and G-US remain **PENDING**.

## Checks, failure retained and recovery

The first offline invocation failed at the frozen denominator check because the loader passed all 200 Cook sample rows rather than the selected 100. It created neither a private diagnostic nor a public aggregate. A mixed-year synthetic test was added, the loader was corrected to preserve the exact frozen `(document, row ID)` membership, and the same pinned inputs then passed a read-only bounds check. The corrected one-time run completed in 8.59 seconds. Its [replay command](verify_artifacts.ps1) recomputes the worklist from both captures and compares exact private bytes and the committed public aggregate without network access; it passed.

Fifteen focused synthetic tests passed at 85% branch-aware coverage; [coverage details](coverage.json) and the [gate record](test_gate.json) preserve the numbers and commands. Ruff lint and format checks passed. The full repository suite passed 1,067 tests in 179.247 seconds, with one local Ames integration test skipped because `AMES_ARFF_PATH` was unset; that exact test then passed separately with the verified local OpenML file and no skip. `pip check` passed, and `pip-audit` found no known vulnerability in auditable installed packages; the local project package has no PyPI lookup. Independent code, Python and security re-reviews found no remaining blocking finding.

From the project root, replay the private evidence with:

```powershell
& 'runs/u0-illinois-ptax203-offline-v1-20261003T035947Z/verify_artifacts.ps1'
```

The [test gate](test_gate.json) pins the code commit, environment lock, plan, Cook source snapshot, PTAX response set, private worklist and public aggregate hashes. Split, feature-policy and checkpoint identities are inapplicable to this source-only run. A fresh clone needs authorised local copies of the two ignored captures; it cannot reconstruct this private review queue from Git alone.

## Next action

Review the private queue against source instruments and the separate Additional PINs source under a new bounded plan. Obtain publisher evidence for close-date semantics, first publication and commercial rights. Record each completed manual rubric independently; do not promote a price label from the current diagnostic.
