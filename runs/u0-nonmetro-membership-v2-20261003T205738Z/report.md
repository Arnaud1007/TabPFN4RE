# U0 candidate nonmetro county membership

Run ID: `u0-nonmetro-membership-v2-20261003T205738Z`  
Verification code commit: `85ce6b331416349e43987e56062002240494d5b7`  
Geography implementation commit: `ad9205bdbc1806f840ebfbe74d71cf96b86f0da7`  
Requirements addressed: US01, US05, US24  
Status: **candidate geography verified; U0 and G-US PENDING**

## Objective and result

Complete the two proposed nonmetro county sets in the pre-tuning
[US market candidate map](../../data/us_market_candidates.json). The July
2023 [Census delineation workbook](https://www2.census.gov/programs-surveys/metro-micro/geographies/reference-files/2023/delineation-files/list1_2023.xlsx)
lists metropolitan and micropolitan assignments but omits counties outside
both. We joined it to the official [2023 Census county Gazetteer](https://www.census.gov/geographies/reference-files/2023/geo/gazetter-file.html)
universes for New York and Florida and subtracted every metropolitan county.
The definition retains micropolitan counties. [ADR 0086](../../decisions/0086-pinned-nonmetro-county-membership.md)
records the choice and alternatives.

The [validator result](candidate_validation.json) reports 62 counties in the
New York universe and **25 proposed nonmetro counties**, plus 67 counties in
Florida and **22 proposed nonmetro counties**. It verifies the eight existing
metro candidates across all four Census regions and the two nonmetro lists.
All three exact official input files were independently hash-pinned and
checked before parsing; the [run configuration](run_config.json) records
their digests. The pure validation function reports only consistency with
supplied universes; the CLI reports `PASS_CANDIDATE_GEOGRAPHY_ONLY` after
checking the official file hashes.

This is candidate geography, not an admitted service area. The result reports
zero supported markets, zero certified sale labels and G-US `PENDING`.
Neither statewide feed has passed rights, target semantics, first-availability,
historical-attribute or eligible-sample checks. The existing eight metro
sources also remain candidate-only and several cover only part of a CBSA.

## Executed checks

The pinned-source CLI exited zero. Twenty-three focused tests pass, with
**84% branch-aware coverage** of the validator. The [focused log](focused_retry.log),
[coverage](coverage_retry.log), [candidate result](candidate_validation.json)
and [command gate](focused_gate.json) contain the actual output. Ruff check and format and dependency checks pass
at the contemporary [speed verification run](../u1-local-date-fit-speed-v1-20261003T220221Z/check_records.json).

The initial full-suite attempt failed in the PowerShell harness when an
expected negative-test stderr message was treated as a terminating shell
error. It did not write a test verdict; the empty [attempt log](full_suite.log)
and [failure record](attempt1_failure.json) are retained. The retry used
nonterminating native stderr handling and exited zero: **1,287 tests passed,
zero skips**, in 749.554 seconds of test time and 750.577 seconds of wall
time. The [sanitized log](full_suite_retry.log) includes expected negative
fixture messages and ends in `OK`; the [gate](full_suite_gate.json) records
the exact command, exit code, duration, test count, verified local Ames ARFF
hash and log hash. An earlier 1,277-test suite belongs to the previous
candidate-map version and was not substituted for this one.

## Continuation

Continue source qualification and manually audited transfer identities,
prices, first availability and historical attributes in U0. Do not use the
candidate map to train on real sales or claim G-US coverage. The exact
dependency-ready tasks and resume commands are in [next_action.md](../../next_action.md).
