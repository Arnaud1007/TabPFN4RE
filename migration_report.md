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

## U0 status and next dependency

The available source schema permits a separately labelled engineering smoke baseline. The legacy split, runs, feature catalogue and old specification are unavailable, so legacy reproduction remains **PENDING**. The historical holdout's exposure status is unknown and it cannot certify a release. No US accuracy, calibration, or coverage result is claimed.

Next: complete a small reproducible Ames smoke run using a new engineering split; request the accessible legacy repository and artifacts; then update this audit with exact hashes and recovered facts. Continue core OFF foundations without treating missing optional catalogue entries as evidence or substituting a newly invented legacy split. The smoke run must use the copied source above and save a manifest; no score is reported until that command is executed.
