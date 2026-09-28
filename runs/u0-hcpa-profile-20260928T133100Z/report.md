# Hillsborough All Sales aggregate source audit

Run ID: `u0-hcpa-profile-20260928T133100Z`

Status: complete as a **U0 source inventory only**. U2 ingestion and G-US remain pending.

## Objective and source

Inspect the structure and aggregate quality of the official [Hillsborough County Property Appraiser public All Sales archive](https://downloads.hcpafl.org/Default.aspx), retrieved on 28 September 2026. An unchanged SHA-256-verified copy of the exact 68 MB ZIP is kept at the Git-ignored `data/raw/hcpa/allsales_09_18_2026.zip` for local replay. The source SHA-256 in `manifest.json` and the source card identifies it; neither raw rows nor person names are committed.

The archive contains `allsales.dbf` and `allsales.doc`. The documentation calls `S_DATE` a sale date and says assessor entry may take weeks after Clerk receipt and staff review. It does not prove the date is closing or that a historical row was visible by a particular valuation origin. Specific commercial use and redistribution rights are unresolved.

## Actual action and results

The replay command was `.\.venv\Scripts\python.exe runs/u0-hcpa-profile-20260928T133100Z/profile.py C:\Users\tdech\AppData\Local\Temp\hcpa_allsales.zip runs/u0-hcpa-profile-20260928T133100Z/profile.json`. It returned exit code 0 in 56.477 seconds. `manifest.json` records the code commit, dirty-tree state, Python version, environment-lock hash, script hash, source hash, output hash and start/end timestamps. The script checks the exact archive checksum, bounded ZIP/DBF dimensions, row markers, EOF and short category-code formats before emitting aggregate JSON.

For local replay, the Git-ignored `data/raw/hcpa/allsales_09_18_2026.zip` can replace the temporary archive path in that command; its SHA-256 was verified identical. A fresh clone must obtain the source through the official page and verify the recorded SHA-256, if that dated file remains available.

| Observation | Count or value |
| --- | ---: |
| DBF header rows and scanned rows | 2,453,187 each |
| Parseable daily `S_DATE` and positive decimal `S_AMT` | 2,453,187 each |
| Earliest and latest observed sale dates | 1901-12-01 to 2026-09-17 |
| Raw `QU` codes `Q` / `U` | 1,090,999 / 1,362,188 |
| Raw `VI` code `V` | 512,547 |
| Missing `DOC_NUM` | 269,947 |

These are raw file counts. No code is interpreted as arm's length or existing single-family eligibility yet. There is no model training, accuracy result, certified as-of evaluation or release claim.

## Checks, failed attempts and limits

The initial exploratory aggregate is preserved as `profile_initial.json`. A later security-hardened replay produced byte-identical `profile.json`. Independent checks confirmed the output/script/environment hashes in `manifest.json`, the header-versus-scan row count, and that sale-year and qualification-code counts each sum to active rows. Ruff lint passed. Ruff formatting reported style changes for this one-off audit script; no product-code format gate depends on it. The earlier manifest without the environment-lock hash is preserved as `manifest_initial.json`; the current manifest records its metadata revision without changing the executed script or output.

The output contains no row-level IDs, prices, dates, addresses or person names. It is not the required 200-record manual audit. Next, verify `S_DATE` against deed/closing evidence, source rights, economic transfer identity, and dated publication snapshots. Then define a residential eligibility funnel and audit 200 stratified records before any candidate training.
