# ADR 0076: Keep Sales Web price and availability semantics unresolved

Date: 2026-10-03
Owner: project implementation
Status: verified UI observation; source admission pending
Affected requirements: US03, US05, US07, US08, US24
Affected protocols: none

## Evidence and alternatives

The official live Sales Web detail view states that its “Personal property” amount is included in the sale price, while the indexed older dictionary describes a sale-price field after subtracting personal property. The [run observation](../runs/u0-nys-salesweb-detail-help-v1-20261003T152306Z/observation.json) records the exact help text and UI keys without any property values. The [current bounded CSV](../runs/u0-nys-salesweb-export-v1-20261003T150117Z/report.md) has `sale_price`, `personal_prop` and `load_dt` headers but no official mapping from these headers to the rendered detail fields.

The UI also defines “Sale loaded to database” as initial entry or loading by New York State. It does not call that date first public publication. Treating the help text as proof of a gross price or treating the database-load date as a public-availability timestamp would resolve the ambiguity without evidence.

## Decision

Keep the export as a private schema-audit candidate only. Do not subtract or add `personal_prop` to `sale_price`, admit a gross consideration target, or use `load_dt` as first public availability until current publisher guidance and record-level evidence resolve the field mappings. Correct the unsent custodian inquiry to mention the observed CSV and ask about the contradiction. Certified labels remain zero; U0 and G-US remain PENDING.
