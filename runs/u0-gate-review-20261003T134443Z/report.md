# U0 milestone gate review

Review ID: `u0-gate-review-20261003T134443Z`  
Date: 2026-10-03  
Reviewed commit: `a4b9d59633a60443c36382a9ab616dcd4597113b`  
Requirements: US02, US24; dependent boundaries US05, US11, G-US  
Decision: **U0 PENDING; G-US PENDING**

## Objective and method

Consolidate existing U0 evidence against the supplied acceptance text without
rerunning historical models, opening reserved labels or acquiring property
records. This is an evidence review, not a new accuracy experiment. Read the
migration report, original artifact provenance, guarded replay comparison,
official Ames integration run, source cards and Ames smoke report. Check their
existence and SHA-256 hashes; inspect the current Git commit and clean tree.
The review used read-only PowerShell `Get-Content`, `Get-FileHash`,
`git rev-parse HEAD` and `git status --short --branch`; all exited 0.

| Checked artifact | SHA-256 |
| --- | --- |
| [`migration_report.md`](../../migration_report.md) | `e1585be4712ffbb075fb5d87dbdaa2d15c7d56a1e2641de96448357e5ab801af` |
| [`data/legacy/provenance.json`](../../data/legacy/provenance.json) | `5a6a0cead127b3337667eea3c3fb3364dbc20edfa8beb9b24543f0db688f863e` |
| [`comparison.json`](../u0-legacy-replay-20260928T145000Z/comparison.json) | `82ddf65a0d02c6125bcc1d260945c3c70363484e7285dcfaf6ee14f799eec467` |
| [Ames integration manifest](../u0-ames-source-integration-v1-20261003T132308Z/evidence_manifest.json) | `142e90142cf0dbc2ad4ae5bb78a0421b58ec0298dbe0348a3c330356f40c9944` |
| [Ames smoke manifest](../u0-smoke-20260928T082634Z-ef55636ed896/manifest.json) | `dd2218d69594f86cdad9dab20f20c75fd158e372242ff29907e9feb55b92fe43` |

## Acceptance matrix

| US02/US24 criterion | Result | Evidence and limit |
| --- | --- | --- |
| Read-only inventory, preserved initial tree and isolated branch | Verified | [Migration report](../../migration_report.md) records initial hashes, clean private clone and `audit/u0` branch. |
| OpenML 42165 identity, 1,460 rows, `Id`, `SalePrice` and source hash | Verified | [Source integration run](../u0-ames-source-integration-v1-20261003T132308Z/report.md) checked the 479,052-byte ARFF and passed 1,172 tests, zero skipped. Engineering fixture only. |
| Original 1,168/292 split membership | Verified | [Provenance](../../data/legacy/provenance.json) and [migration report](../../migration_report.md) recover the original indices and complement. Prior exposure is unknown; holdout is retrospective. |
| Historical XGBoost parameters, metrics, predictions, versions and reproduction | **Failed reproduction; partial recovery** | [Replay report](../u0-legacy-replay-20260928T145000Z/report.md) and `comparison.json`: saved mean MAE $15,624.4750; replay $15,499.7416; maximum fold difference $653.3657. Original CSV, row predictions, checkpoint and actual runtime are unavailable. [Lock audit](../u0-legacy-lock-markers-v1-20261002T221026Z/report.md) cannot prove the runtime. |
| Companion feature catalogue | Missing, tracked | Not present in legacy repo or targeted workspace scan. Named forbidden fields remain blocked; absence does not stop independent foundation work. |
| CPU, RAM, GPU, VRAM, driver and disk inventory | Verified at audit time | [Migration report](../../migration_report.md) records i7-12700H, 31.69 GiB RAM, RTX 3060 with 6 GiB VRAM and driver 596.08. Free disk is time-varying. |
| Rights/source dependency inventory | Verified as inventory | [Source cards](../../data/source_cards/) state unresolved releasable rights, target semantics and publication timing. No source is certified for modern temporal training. |
| Post-schema small baseline and distinct protocol | Verified as engineering evidence | [Ames smoke](../u0-smoke-20260928T082634Z-ef55636ed896/report.md) used 200 rows, produced 40 saved predictions and labelled the score non-certifying. |
| Consolidated acceptance decision | **PENDING** | This report and [ADR 0072](../../decisions/0072-u0-legacy-replay-acceptance-boundary.md) record the open criterion; no exception is adopted. |

The replay failure is not an accuracy comparison between models. The six
corrected-parser local runs were repeatable, but the missing original CSV and
runtime prevent assigning a cause to the mismatch. The current
`requirements.yaml` entries for US02 and US24 remain `planned` because the
milestone is not accepted. No score was transcribed as a G-US result.

## Downstream state and next action

The Cook and NYC manual source reviews and first-publication, close-date,
identity, historical-vintage and permitted-use checks are U2/G-US
dependencies. They are not additional U0 acceptance criteria. **Zero modern
US sale labels are certified.** The US release needs frozen eight-metro/four-
region and two-nonmetro scope, 10,000 matured final sales and an actual future
shadow cohort; none is established by this review.

If original `ames.csv` or historical predictions become available, register a
new development-only replay before executing it. Meanwhile continue the
source-qualification tasks and exact resume instructions in
[`next_action.md`](../../next_action.md). This review changed no model,
dataset, split, feature policy or test protocol, so no new test run is claimed.
