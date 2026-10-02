# U0 migration audit

Date: 2026-09-28. Branch: `audit/u0`. This is an evidence inventory, not a model or release report.

## Provenance and scope

The owner supplied the Part I–III version 2.0 specification in the conversation, dated 27 September 2026. Its original Word file and the earlier specification are not present in this project. The named legacy repository is `github.com/Arnaud1007/tabular-fm-housing-poc`. An initial Git read returned `Repository not found`; after the owner granted private access, the same URL became accessible on 28 September 2026. Commit `60580b6f4350a70617c6edf45d2b95ac53ebec0b` was cloned read-only under Git-ignored `data/raw/legacy-repo/`. The clone was clean at artifact copy. A targeted home-workspace scan found no separate original Word document or `feature_catalog.csv`; a complete search of all local drives has not been performed.

Before modifications, `TabPFN4RealEstate` contained only an untracked README and `.gitignore`, with no commits or remotes. Their SHA-256 values were `c4819e8b8a931cb046006aa009745c4d0b9f9b8caf2b83e0841c0cf9b4b89a04` and `d4934d006f4e6a0569750e48ee35408094ccc413a012cf4f648b53e16e7a5752`, respectively. The starter files were preserved in commit `e00ac7f` on the isolated audit branch.

## Required input inventory

| Input | Status | Evidence and consequence |
| --- | --- | --- |
| Legacy repository and history | Available, privately | Initially inaccessible; the later read-only clone is at `data/raw/legacy-repo/`, commit `60580b6`. It is excluded from this project's Git history. |
| Original Word and earlier specification | Unavailable | Owner confirmed the requested legacy artifacts are unavailable. Only the pasted v2 text is available; earlier protocol changes cannot be checked against an original artifact. |
| OpenML Ames dataset 42165 | Available as a separately fetched engineering fixture | Official metadata names `house_prices` v1 and `SalePrice`; source card records URL and checksums. An unchanged local copy is at `data/raw/openml/house_prices-42165.arff`, ignored by Git. |
| Original 1,168/292 membership | Recovered | `data/legacy/holdout_ids.csv` contains 292 unique zero-based row indices. Its exact order and set match the legacy seed-42 80/20 split; the complement contains 1,168 development rows. Original holdout label exposure is unknown. |
| Historical XGBoost settings and aggregate metrics | Partly recovered | Both scripts and saved development fold/mean metrics are available; the original `ames.csv`, row-level predictions, run-time versions and checkpoint are missing. The repository lock gives an environment approximation, not proof of the historical runtime. |
| `feature_catalog.csv` | Unavailable | Claimed 500 entries, policy counts and formulas are unverified. F172, F349 and F350 remain forbidden by the supplied specification. |
| Previous environment lock and checkpoints | Lock recovered; checkpoints missing | `uv.lock` is present at source commit `60580b6` (SHA-256 `a165ac8d49bfa7d2b4d42f46db2d6e33883fe78662df0cee9846828ba2a2aa6f`); actual historical installed versions and fitted checkpoints are unrecorded. |
| Local hardware | Available | See the measured inventory below. |
| Current US multi-market transactions and historical listing snapshots | Missing | G-US and ON mode cannot be certified from Ames. Acquisition and rights are separate dependencies. |

## Verified Ames source facts

OpenML metadata: <https://www.openml.org/api/v1/json/data/42165>. Download: <https://openml.org/data/v1/download/21754539/house_prices.arff>. The fetched 479,052-byte file has MD5 `d5ca59f8d02b1b1c127034392c0f995f`, matching metadata, and SHA-256 `10db9fe72ed693212a222e39981133ec1b3ee5090d7f2caf2461190a4ad51279`.

The ARFF has 81 attributes, beginning with `Id` and ending with `SalePrice`, and 1,460 data rows of width 81. All 1,460 targets are present and positive; all `Id` values are unique. Sale prices range from 34,900 to 755,000. There are 6,965 `?` cells across the file. These checks establish file identity and a minimal source schema, not real-world historical availability or eligibility. OpenML's licence field is `NA`; releasable use and redistribution rights remain unresolved. The raw file is not committed.

## Measured local environment

| Item | Observation |
| --- | --- |
| Computer | Dell Inspiron 16 Plus 7620 |
| CPU | Intel Core i7-12700H, 14 cores, 20 logical processors |
| RAM | 31.69 GiB reported physical memory |
| GPU | NVIDIA GeForce RTX 3060 Laptop GPU, 6,144 MiB VRAM (`nvidia-smi`) |
| NVIDIA driver | 596.08 (`nvidia-smi`) |
| C: free space at audit | 58.18 GiB; this is a changing value |
| Python | 3.11.6 installed; 3.14.0 is the default `python` command |
| Python 3.11 packages checked | `numpy`, `pandas`, `sklearn` present; `xgboost` and `pytest` absent |

The earlier 8 GB GPU claim is incompatible with the measured 6 GB VRAM. No training capacity claim follows from package installation or this inventory.

## Legacy-to-current protocol map

| Legacy claim in supplied v2 text | Current requirement | Migration decision |
| --- | --- | --- |
| Ames data and 1,168/292 holdout | US02, US11 | Original saved membership is recovered. Its exposure history is unknown, so it is retrospective and cannot certify a release. Keep a separate future certification cohort. |
| Historical XGBoost result | US02, US14 | Original configuration and aggregate development scores are recovered; predictions and checkpoint are absent. Replay on development rows only and report version/data limits. Compare additional model families later. |
| 500-feature catalogue and three named forbidden fields | US09, US08 | Verify CSV counts and formulas when obtained; keep named fields blocked in the meantime. |
| 8 GB GPU planning assumption | US02, US15, US22 | Replace with measured 6 GB VRAM for safe profiling. |
| Final holdout tie-breaking | US13 | Freeze the model using development evidence before a new final test. |
| Random Ames folds as release evidence | US11, G-US | The actual legacy script uses one shuffled five-fold CV, not the 3 × 5-fold protocol described in v2. Retain it only as retrospective engineering evidence; certification needs temporal, geographic and prospective US evidence. |

## U0 engineering evidence and next dependency

The separate engineering smoke run `u0-smoke-20260928T082634Z-ef55636ed896` completed on commit `7d224e711ef52fa7adbf0a4cfd52a5dd9e0afa11` with the official source checksum above. Its protocol is `ames_engineering_v1`: the first 200 source rows, with 160 development and 40 reserved rows under seed 42. The median-price baseline produced 40 saved predictions. The saved metrics are MdAPE `0.2393308080808081` (23.93%) and within-10% `0.175` (17.5%). The run manifest records the source, split, policy, environment, configuration, checkpoint and prediction hashes. It declares `certification_eligible: false`. Raw source and row-level predictions remain local and ignored by Git because source redistribution permission is unresolved.

The Python 3.11 test gate on that commit passed 33 tests with no skips and 90% measured statement coverage; Ruff lint passed. The commands, exits, timing and output are in the same run directory. The small baseline is evidence that source parsing, split preservation, prediction and artifact creation work. It is not the recovered 1,168/292 holdout, a real-world temporal result, or evidence for G-US.

This paragraph documented the initial state before private access was granted. The legacy split and aggregate development scores were subsequently recovered, as described below. The feature catalogue, old specification, row-level predictions and fitted checkpoint remain unavailable. The historical holdout's exposure status is unknown and it cannot certify a release. US coverage, calibration and prospective accuracy remain unmeasured.

The synthetic rolling-origin helper was versioned from `us_synthetic_rolling_v1` to `us_synthetic_rolling_v2` after a repeated-hour timestamp audit. V2 compares instants in UTC and uses an exact 90-day UTC engineering horizon; it rejects real-protocol IDs. V1 gate evidence remains unchanged. Neither version is a source-local 90-calendar-day certification protocol; ADR 0010 and the later gate report record the distinction.

## Additional U0 source feasibility audit

On 28 September 2026, the official Cook County [parcel sales](https://datacatalog.cookcountyil.gov/d/wvhk-k5uv) and [improvement characteristics](https://datacatalog.cookcountyil.gov/d/x54s-btds) metadata were retrieved and hashed. Source cards in `data/source_cards/` record the exact IDs, field semantics, links, local metadata checksums and unresolved rights and timing questions. No property-level source rows were ingested or used for training.

The sales schema describes `sale_date` as recorded rather than executed; older dates may have been truncated to the first of a month, and sales may reach the Assessor months after recording. The characteristics data has one row per building card, not per parcel or dwelling; `char_bldg_sf` is exterior building area. Neither current metadata provides per-record first availability. The metadata licence fields are absent, so commercial use and redistribution are not assumed. ADR 0005 keeps both as candidates and blocks certified historical as-of use until source timing, target semantics, linkage and rights are established.

On the same date, official NYC DOF rolling and annualized sales API metadata were saved locally and hashed; their source cards preserve the exact IDs and checksums. King County Assessor/GIS descriptions were inspected without accepting download terms or ingesting rows. ADR 0006 and `data/acquisition_backlog.md` record the comparative decision. NYC supplies published transaction prices and longer annual history but not per-row availability or historical attribute vintages; its final-roll attributes must not be mistaken for features available before a sale. King County's sale extract can repeat an economic transfer across parcels, while its building extract can repeat a parcel across buildings. Its documented GIS derivatives are marked Not Public. Both sources remain acquisition candidates, not certified temporal data. At that point in the audit, legacy access and primary 90-day pre-close evidence were missing; legacy access was granted later, as recorded below.

Florida Department of Revenue SDF/NAL documentation was then audited without downloading property rows or sending a records request. ADR 0007 and source cards record its statewide coverage potential, parcel and transfer-code semantics, prior roll request path, and the exact date limitation: the SDF stores deed-execution **year and month**, not a daily close date. Maryland SDAT was retained as a lower-priority backup because its public search forbids automated scraping and a licensed bulk route is unresolved. None of these source discoveries constitutes an accepted U2 data pipeline or a G-US market.

Hillsborough County Property Appraiser's public All Sales archive and embedded `allsales.doc` were inspected in a temporary audit location on 28 September 2026; their hashes and fields are in `data/source_cards/hillsborough_hcpa_allsales.yaml`. The source documents `S_DATE` as “date of sale” and warns that sales enter the assessor system after Clerk receipt and staff review, potentially several weeks later. No historical first-availability stream or verified pre-close date meaning has been established. No property rows were loaded into canonical layers or used for training. This is a promising county-level daily-date candidate, not a qualifying G-US label source.

The [public downloads page](https://downloads.hcpafl.org/) has an "All Rights Reserved" footer but no dataset-specific permission statement. That observation does not resolve commercial or redistribution rights; the HCPA source card keeps releasable use pending.

A read-only aggregate scan of the exact HCPA archive inspected all 2,453,187 DBF records without retaining personal names, property identifiers, row-level prices or addresses. The header count matched the scanned count; all `S_DATE` values parsed as dates and all `S_AMT` values parsed as positive decimals. The raw codes include 1,090,999 `Q` and 1,362,188 `U` records, plus 512,547 `V` records. These are not eligibility counts: code semantics, economic duplicates, property type, arm's-length status, historical availability and close-date meaning remain unaudited. The aggregate output and read-only script are under `runs/u0-hcpa-profile-20260928T133100Z/`.

ADR 0011 and the separately tested `us_local_date_90d_v1` helper define 90 source-local calendar days and conservative date-only availability using pinned `tzdata`. The synthetic fold builder remains isolated from this protocol. No real source has yet passed the close-date, availability, rights and identity checks required to use the helper for certification.

## Recovered legacy evidence after private access

The original commit `60580b6` contains `baseline.py`, `run_experiment.py`, `data.py`, `evaluate.py`, `holdout_ids.csv`, two saved development-score files and a Day 8 mean-metrics file. The four original CSVs were copied byte-for-byte into `data/legacy/`; `data/legacy/provenance.json` records original paths, byte counts and SHA-256 hashes. The source clone is clean and ignored by this repository. The source file `ames.csv` is ignored and was not in the private repository.

The saved `holdout_ids.csv` contains 292 unique zero-based Pandas indices in the original seed-42 `train_test_split(test_size=0.20)` order, ranging from 15 to 1450. The index complement has 1,168 rows. The separately fetched official OpenML ARFF has `Id = row_index + 1` on all 1,460 rows. These checks recover membership, not proof that the original holdout was never opened. The saved holdout is therefore retrospective.

The actual Day 8 script uses a single shuffled five-fold `KFold(n_splits=5, shuffle=True, random_state=42)` on development rows, with fold-local median numeric imputation, most-frequent categorical imputation, one-hot encoding, a mean Dummy regressor and XGBoost (`n_estimators=400`, `max_depth=4`, `learning_rate=0.05`, `subsample=0.8`, `colsample_bytree=0.8`, `random_state=42`, `n_jobs=-1`). It is not the 3 × 5-fold legacy protocol described in the owner-supplied v2 text. The stored Day 8 development means are Dummy MAE $56,318.2323 and XGBoost MAE $15,624.4750; XGBoost RMSE $27,135.6399, RMSLE 0.1271649 and R-squared 0.8737498. These are saved historical aggregates, not a new run, holdout result or G-US score.

The legacy scripts retain raw `Id` as a predictor and have no historical `available_at` controls. `evaluate.py` clips negative predictions for RMSLE. Those behaviours belong only to the retrospective replay; current feature guards and metric rules must not inherit them. The private repository contains no `feature_catalog.csv`, row-level prediction file, fitted model checkpoint or historical execution manifest. Its `uv.lock` pins a plausible Python 3.11 Windows environment, but does not prove what was installed for the saved scores.

The guarded development-only replay is recorded at `runs/u0-legacy-replay-20260928T145000Z/`. It excluded the 292 reserved ARFF rows before parsing prices and used the recovered one-five-fold rules. Six corrected-parser repeats gave identical development predictions. The Dummy folds reproduce the archived metrics exactly; the XGBoost mean MAE is $15,499.7416 against the archived $15,624.4750, with maximum absolute fold MAE difference $653.3657. The archived XGBoost score is therefore **not reproduced**. The original CSV and historical runtime remain missing, so the discrepancy cannot be assigned to one cause. The report preserves rejected parsing attempts, package audit history, final run hashes, complete test evidence and the redacted local prediction policy. U0 remains pending unresolved legacy and source qualification dependencies; none of these scores qualify for G-US.

The later read-only [legacy lock marker audit](runs/u0-legacy-lock-markers-v1-20261002T221026Z/report.md), frozen under [ADR 0045](decisions/0045-legacy-lock-marker-audit.md), evaluated the recovered `uv.lock` for Windows Python 3.11.6. All nine selected numerical/model package versions match those installed for guarded replay v9. The exact package comparison and hashes are in its public aggregate; the report includes an executed independent verification command. This narrows one possible version-mismatch explanation but does **not** establish the actual historical installed environment or reproduce the archived XGBoost scores. The original `ames.csv` remains missing, no new model fit or sale-label certification occurred, and U0 and G-US remain pending.
