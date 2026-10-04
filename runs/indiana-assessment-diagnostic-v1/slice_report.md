# Indiana assessment-snapshot error slices

Date: 2026-10-05. Protocol:
`indiana_sdf_snapshot_assessment_posthoc_slices_v1`. Status: **verified
development diagnostic; U0 and G-US pending**. Requirement US20 has partial
diagnostic evidence only. This report is computed from [slices.json](slices.json),
whose SHA-256 is
`0ff509d5576ada70f586e4b937f522c9072b8dd6a58762d50411a0a5d39d4de4`.

## Result

All **71,054** saved 2025 sales remain in the overall denominator. The
assessment-snapshot model had lower absolute dollar error than the fixed
three-input XGBoost on **50,648 sales (71.28%)**. Its overall 15.19% MdAPE
replays the [original diagnostic](report.md) exactly.

Price bands use 2024 training-sale cutoffs of $117,000, $185,000, $250,000
and $343,000, with a sale exactly at a cutoff assigned to the lower band.
Each 2025 sale is grouped by its **realised** price; these
bands are retrospective error analysis, not pre-sale routing features.

| Realised price band | Sales | Assessment MdAPE | Three-input MdAPE | Assessment within 10% | Assessment P90 APE |
| --- | ---: | ---: | ---: | ---: | ---: |
| Up to $117,000 | 12,737 | **51.62%** | 98.75% | 11.30% | 257.64% |
| $117,000–$185,000 | 13,256 | 21.19% | 25.17% | 25.02% | 55.53% |
| $185,000–$250,000 | 13,647 | 13.44% | 17.37% | 39.74% | 39.05% |
| $250,000–$343,000 | 14,577 | 9.63% | 24.47% | 51.37% | 30.19% |
| Over $343,000 | 16,837 | 10.15% | 39.89% | 49.39% | 31.56% |

All **56 counties with at least 200 sales** had lower MdAPE with the
assessment-snapshot model than with the three-input model. The weakest of
these still had **39.82% MdAPE** on 327 sales. Another 35 counties had fewer
than 200 sales, totalling 4,309; they remain in the overall score but have no
county scorecard. Assessment fields were both positive on 70,464 rows (15.15%
MdAPE) and had at least one zero on 590 (21.23% MdAPE). No row in this fixed
cohort had a missing assessment value. Groups under 200 disclose counts only.

## Interpretation and next task

The gain is broad across the counties with enough rows, but the lowest price
band has very poor accuracy and tail error. Prioritise the 200-record
stratified source audit, especially low-price transfers, price meaning,
multi-property or partial-interest transactions, and area/identity errors.
Separately verify the assessment vintage and first availability before using
these fields in a 90-day OFF model. The 2025 rows were already consumed
development data. This post-hoc analysis does not validate a current-home
prediction or qualify the model for release.

## Evidence and checks

The analysis was executed from clean code commit
`ac0870367a391ec6b36f1b56d1e300a649a488b3` using the pinned 2024 and
2025 SDF ZIPs and hash-verified private predictions. It checked split
membership, every saved row's ID, date and actual price, and replayed the
original overall scorecards before publishing aggregate-only JSON. The five
price-band counts and three assessment-state counts each sum to 71,054; the
56 scored-county rows plus 4,309 small-county rows also sum to 71,054.
Three focused tests, Ruff, the locked dependency audit and the CLI run passed;
see [slice_test_gate.json](slice_test_gate.json). The previous project-wide
suite passed 1,320 tests with 92% package coverage before this diagnostic
script was added; it was not rerun for this slice-only checkpoint.

From the repository root, with authorised private source ZIPs and the
original private prediction artifact in place, run:

```powershell
$env:PYTHONPATH = (Resolve-Path -LiteralPath 'src').Path
& 'data/raw/legacy-replay/.venv/Scripts/python.exe' -m scripts.indiana_assessment_slices --source-2024 data/raw/indiana_sdf/SDF_2024.zip --source-2025 data/raw/indiana_sdf/SDF_2025.zip --output runs/indiana-assessment-diagnostic-v1/slices.json
```

The output is create-only. For a new run, use a new protocol and file path;
do not overwrite this evidence.
