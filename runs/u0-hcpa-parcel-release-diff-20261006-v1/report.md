# HCPA consecutive parcel release comparison, 6 October 2026

Status: **verified aggregate correction evidence; source remains unqualified; G-US PENDING**.
Requirements: US05, US08, US22, US24.

## Result

The exact 2 October and 5 October 2026 HCPA parcel archives were compared from hash-verified in-memory snapshots using implementation commit `2d0738e`. Both exports contain **531,612** DBF rows with the same schema. Their SHP and SHX members are byte-identical, which makes record-order comparison defensible for this adjacent-release diagnostic.

Of 531,612 parcel records, **531,508 were byte-identical across all DBF fields** and **104 changed**. No deletion-marker change occurred. The changed fields include five `SALE1_PRC` rows, six `SALE1_DATE` rows, five `SALE2_PRC` rows, five `SALE3_PRC` rows, 68 `JUST` rows, 75 `TAX_VAL` rows and one `PIN` row. The complete privacy-safe field counts and source/geometry hashes are in [aggregate.json](aggregate.json).

No parcel identifier, owner, address, price value or row-level hash is tracked in this evidence directory.

## Verification

- Nine focused tests passed with 80% branch coverage.
- Ruff and format checks passed.
- Code, Python and security reviews approved the implementation after archive integrity, decompression budgets and input-overwrite protections were added.
- The clean-commit live comparison exited zero.
- Archive SHA-256 values match the append-only private observation ledger.

## Interpretation

This is direct evidence that the publisher can revise parcel, assessment and embedded recent-sale attributes between adjacent releases while retaining the same parcel geometry and row count. Certified historical features must therefore bind to exact captured bytes and cannot treat a later parcel archive as if it were available at an earlier valuation origin.

This comparison does not establish the meaning or first-publication date of embedded sale fields, arm's-length eligibility, commercial model-use rights, or certified transaction labels. It does not unlock HCPA model training or G-US.