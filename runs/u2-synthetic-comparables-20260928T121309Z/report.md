# U2 synthetic comparable engineering report

Run ID: `u2-synthetic-comparables-20260928T121309Z`

Code commit: `31e838684ef203b57df1e82a3f772a208345060e`

Status: **verified engineering increment; U2 and G-US remain pending**

Requirements: US06, US08, US10, US23

## Objective and changes

Extend the existing as-of comparable filter with deterministic geographic retrieval and a price-per-living-area baseline on synthetic US records. The implementation adds validated paired coordinates to `Property`, immutable retrieval settings, sale-time property-version checks, radius expansion, a low-count support flag and a weighted-median price-per-square-foot estimate. The priced result is bound to the subject version, origin and source snapshot. No official county rows were ingested or used for a model score.

## Commands and observed results

The exact commands, durations, exit codes and log hashes are in `test_gate.json`. The launcher is `run_gate.ps1` in this directory. The Ames ARFF path was set to the ignored local file so the unrelated Ames tests could execute. The manifest records the file's SHA-256; it is **not** a comparable-sales dataset.

| Check | Observed result | Evidence |
| --- | --- | --- |
| Python 3.11 unittest suite under coverage | 145 passed, 0 skipped, exit 0 | `tests.log` |
| Statement coverage | 90.02% of the current package, exit 0 | `coverage_report.log`, `coverage.json` |
| Ruff lint | Passed, exit 0 | `lint.log` |
| Ruff formatting | Passed, exit 0 | `format.log` |
| Artifact hash check | All five command logs matched the manifest | `test_gate.json` |

The targeted comparable suite has 14 synthetic cases. It checks future/late sales, target-price-independent ranking, deterministic ties, sparse and expanded radii, a hand-checkable weighted median, unavailable property versions, context binding, post-sale area changes, and repeated sales of a neighboring property. Independent code, Python and security re-reviews found no remaining high-severity issue. The Python reviewer noted that the preliminary `supported` field is based on count and radius alone; physical similarity must be calibrated before release.

## Failed attempts and limitations

Two earlier gate launchers are preserved as **incomplete** at `runs/u2-synthetic-comparables-20260928T121100Z/` and `runs/u2-synthetic-comparables-20260928T121221Z/`. They failed in PowerShell output/status handling and have no valid complete manifest. Their failures were not counted as a passing gate. The successful manifest records `dirty_tree: true` because the gate artifacts themselves were untracked during execution; the tested code was at the stated commit.

These tests prove synthetic behavior only. No living-area or geometry source has passed a historical as-of audit; no 50-query real comparable audit, development-fitted scales, 5/10/20 and 6/12/24 comparison, age adjustment, uncertainty interval, geographic barrier handling or performance evaluation exists. The reported 90% coverage is code coverage, not prediction-interval coverage. U0 legacy recovery, U2 source qualification and G-US remain **pending**.

## Next action

Follow `next_action.md`: qualify a Florida daily dated transaction/availability route and a safe historical attribute source, then audit an authorised real sample before any temporal comparable model comparison. Continue synthetic foundation work only within the explicit engineering scope.
