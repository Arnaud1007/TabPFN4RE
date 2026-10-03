# U0 pre-tuning US market candidate map

Run ID: `u0-us-market-scope-v1-20261003T201219Z`  
Code commit: `412d05e`  
Requirements addressed: US01, US05, US24  
Status: **candidate geography verified; U0 and G-US PENDING**

## Objective and observed evidence

Name a proposed comparison set before real-market model tuning. The
[candidate manifest](../../data/us_market_candidates.json) contains eight
distinct metropolitan CBSAs, two in each Census region, and two separately
named proposed nonmetro strata. It lists the currently identified source
cards and the gap between each source footprint and its whole CBSA. The
[decision](../../decisions/0085-us-market-candidates-before-tuning.md) defines
change control before a later service-area freeze.

The official [Census July 2023 delineation workbook](https://www2.census.gov/programs-surveys/metro-micro/geographies/reference-files/2023/delineation-files/list1_2023.xlsx)
was retrieved as 143,798 bytes with SHA-256
`952c4b1e78acbb54e6ec9412434b7602fedacbf021736351a63c181bdb753629`.
The [validator](../../scripts/validate_us_market_scope.py) independently pins
that digest, parses the exact bytes it hashed, and checks each proposed CBSA
name, metropolitan classification, county count and proposed source-county
membership. It checks two candidate metros per Census region, source-card
paths and candidate-only statuses. The [validation result](candidate_validation.json)
reports **8 metro candidates, 2 nonmetro candidates, 0 supported markets,
0 certified sale labels and G-US PENDING**. Nonmetro county membership remains
unverified because the manifest records rules, not a frozen county list.

The selected source families span NYC DOF, NYS Sales Web, Cook County,
Illinois PTAX, Hillsborough HCPA, Florida DOR, Douglas County and King County.
They are candidates with unresolved rights, price/transfer meaning, close
date, first availability and historical attributes. Several named CBSAs
extend beyond the identified county source. Recent price direction, density,
stock and sample floors were not measured in this run; their proposed
contrasts are hypotheses, not a passed diversity audit.

## Executed checks

| Check | Observed result | Evidence |
| --- | --- | --- |
| Pinned-workbook candidate validation | Exit 0; eight metros, two per region; two nonmetro candidates; zero supported markets | [validation](candidate_validation.json), [command gate](validation_gate.json) |
| Focused tests with branch coverage | 15 passed; 84% validator coverage | [focused log](focused.log), [coverage](coverage.log), [commands](focused_gate.json) |
| Full Python 3.11 suite with verified local Ames ARFF | Exit 0; **1,277 tests, zero skips**; 913.683 s test time, 919.791 s wall time | [full log](full_suite.log), [command gate](full_suite_gate.json) |
| Ruff check and format check | Both exit 0 | [check](ruff_check.log), [format](ruff_format.log) |
| Dependency and vulnerability checks | `pip check` and `pip-audit --skip-editable` exit 0 | [dependency](pip_check.log), [audit](pip_audit.log) |
| Code, Python and security reviews | Final review found no pre-push blocker after fixes | [review record](review_evidence.md) |

The full suite used `.venv/Scripts/python.exe -m coverage run --branch
--source=tabpfn4realestate -m unittest discover -s tests -p test_*.py -q`
with `AMES_ARFF_PATH` set to the locally verified OpenML ARFF, SHA-256
`10db9fe72ed693212a222e39981133ec1b3ee5090d7f2caf2461190a4ad51279`.
Its log includes expected text from deliberate failure fixtures and ends in
`OK`. The saved log is UTF-8 with local account paths redacted. The
[test gate](test_gate.json) stores commands, exit codes, durations and hashes.
The repository's [Git attributes](../../.gitattributes) preserve the exact
line endings of the hashed planning files across checkouts.
The [run configuration](run_config.json) distinguishes the Census geography
reference hash from a sale-data snapshot: no sale-data, split, feature-policy
or model checkpoint hash exists for this source-planning task.

The initial test-first run failed because the validator module was absent.
Two later invalid-input tests exposed non-explicit error handling, which was
fixed before the passing suite. Review found a hash/parse reopen race and
unbounded manifest reading; both were corrected before this gate.

## Limits and next action

This result does **not** pass the eight-metro/two-nonmetro G-US coverage gate.
No eligible transaction population, final test, calibration, shadow cohort,
model accuracy or service coverage was assessed. A candidate may be replaced
only in a versioned pre-tuning decision; no failing final-test market may be
removed retroactively. Continue the [U0 source audit](../../next_action.md)
and measure source coverage and market variation from eligible historical
data before freezing a supported service area.
