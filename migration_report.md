# U0 migration audit

Date: 2026-09-28. Branch: `audit/u0`. This is an evidence inventory, not a model or release report.

## Provenance and scope

The owner supplied the Part I–III version 2.0 specification in the conversation, dated 27 September 2026. Its original Word file and the earlier specification are not present in this project. The named legacy repository is `github.com/Arnaud1007/tabular-fm-housing-poc`. A public Git read of that URL returned `Repository not found` (exit 128) on 28 September 2026; this does not distinguish a private repository from a missing or renamed one. A targeted scan of top-level projects under `Desktop/Coding_projects` found no linked clone. A complete search of all local drives has not been performed.

Before modifications, `TabPFN4RealEstate` contained only an untracked README and `.gitignore`, with no commits or remotes. Their SHA-256 values were `c4819e8b8a931cb046006aa009745c4d0b9f9b8caf2b83e0841c0cf9b4b89a04` and `d4934d006f4e6a0569750e48ee35408094ccc413a012cf4f648b53e16e7a5752`, respectively. The starter files were preserved in commit `e00ac7f` on the isolated audit branch.

## Required input inventory

| Input | Status | Evidence and consequence |
| --- | --- | --- |
| Legacy repository and history | Missing or inaccessible | URL returned 404/exit 128; no local remote found in targeted scan. Request an accessible path. |
| Original Word and earlier specification | Missing | Only the pasted v2 text is available. Earlier protocol changes cannot be checked against its actual artifact. |
| OpenML Ames dataset 42165 | Available as a separately fetched engineering fixture | Official metadata names `house_prices` v1 and `SalePrice`; source card records URL and checksums. An unchanged local copy is at `data/raw/openml/house_prices-42165.arff`, ignored by Git. |
| Original 1,168/292 membership | Missing | No split artifact found. Any new split must have a new ID and must never be called the original holdout. |
| Historical XGBoost settings, versions, predictions and metrics | Missing | Reproduction and numerical tolerance cannot yet be measured. |
| `feature_catalog.csv` | Missing | Claimed 500 entries, policy counts and formulas are unverified. F172, F349 and F350 remain forbidden by the supplied specification. |
| Previous environment lock and checkpoints | Missing | Legacy execution environment and checkpoint identity cannot be reconstructed. |
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
| Ames data and 1,168/292 holdout | US02, US11 | Recover exact membership if provided; otherwise label any observed historical score retrospective and create a distinct future certification cohort. |
| Historical XGBoost result | US02, US14 | Recover exact configuration and predictions before reproduction claims; compare additional mandatory model families later. |
| 500-feature catalogue and three named forbidden fields | US09, US08 | Verify CSV counts and formulas when obtained; keep named fields blocked in the meantime. |
| 8 GB GPU planning assumption | US02, US15, US22 | Replace with measured 6 GB VRAM for safe profiling. |
| Final holdout tie-breaking | US13 | Freeze the model using development evidence before a new final test. |
| Random Ames folds as release evidence | US11, G-US | Retain only as an engineering protocol; certification needs temporal, geographic and prospective US evidence. |

## U0 engineering evidence and next dependency

The separate engineering smoke run `u0-smoke-20260928T082634Z-ef55636ed896` completed on commit `7d224e711ef52fa7adbf0a4cfd52a5dd9e0afa11` with the official source checksum above. Its protocol is `ames_engineering_v1`: the first 200 source rows, with 160 development and 40 reserved rows under seed 42. The median-price baseline produced 40 saved predictions. The saved metrics are MdAPE `0.2393308080808081` (23.93%) and within-10% `0.175` (17.5%). The run manifest records the source, split, policy, environment, configuration, checkpoint and prediction hashes. It declares `certification_eligible: false`. Raw source and row-level predictions remain local and ignored by Git because source redistribution permission is unresolved.

The Python 3.11 test gate on that commit passed 33 tests with no skips and 90% measured statement coverage; Ruff lint passed. The commands, exits, timing and output are in the same run directory. The small baseline is evidence that source parsing, split preservation, prediction and artifact creation work. It is not the recovered 1,168/292 holdout, a real-world temporal result, or evidence for G-US.

The legacy split, runs, feature catalogue and old specification are unavailable, so legacy reproduction remains **PENDING**. The historical holdout's exposure status is unknown and it cannot certify a release. US coverage, calibration and prospective accuracy remain unmeasured. The next dependent action is to obtain an accessible legacy repository or artifact bundle and recover exact membership and historical predictions. Independent core OFF engineering can continue while that access is pending.

## Additional U0 source feasibility audit

On 28 September 2026, the official Cook County [parcel sales](https://datacatalog.cookcountyil.gov/d/wvhk-k5uv) and [improvement characteristics](https://datacatalog.cookcountyil.gov/d/x54s-btds) metadata were retrieved and hashed. Source cards in `data/source_cards/` record the exact IDs, field semantics, links, local metadata checksums and unresolved rights and timing questions. No property-level source rows were ingested or used for training.

The sales schema describes `sale_date` as recorded rather than executed; older dates may have been truncated to the first of a month, and sales may reach the Assessor months after recording. The characteristics data has one row per building card, not per parcel or dwelling; `char_bldg_sf` is exterior building area. Neither current metadata provides per-record first availability. The metadata licence fields are absent, so commercial use and redistribution are not assumed. ADR 0005 keeps both as candidates and blocks certified historical as-of use until source timing, target semantics, linkage and rights are established.
