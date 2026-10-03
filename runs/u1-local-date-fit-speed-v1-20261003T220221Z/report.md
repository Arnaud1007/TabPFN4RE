# Synthetic calendar model fit speed

Run ID: `u1-local-date-fit-speed-v1-20261003T220221Z`  
Optimized code commit: `85ce6b331416349e43987e56062002240494d5b7`  
Requirements addressed: US11, US22, US24  
Status: **engineering optimization verified; U0 and G-US PENDING**

## Hypothesis and change

Profiling the existing 204-row synthetic OFF calendar fit/replay/score test
identified repeated loading and parsing of the same pinned `tzdata` zone file.
The date assembler called that loader thousands of times in the test. Cache
successful immutable `ZoneInfo` objects in a bounded 64-key LRU cache while
checking the zone key and frozen `tzdata` version on every request. The first
test-first run failed because the cache helper did not yet exist. No date,
model, feature, split or target semantics changed.

## Measured result

Three fresh Python 3.11.6 processes ran the same test before and after the
change on this machine. Each timing includes test setup, two fits, replay,
prediction and scoring, so it is an end-to-end synthetic path measurement.

| State | Wall seconds | Median |
| --- | --- | ---: |
| Before, code `ad9205b` | 3.0792, 2.5185, 2.5363 | 2.5363 s |
| After, optimized source hash `c3d63139635de20f707826272b70e5b836e168b75a2918af4bd42e9b5838d26b` | 0.5235, 0.5123, 0.5093 | 0.5123 s |

The measured median is **4.95 times faster**, or about 79.8% less wall time,
for this fixture. [Before](before.json) and [after](after.json) preserve all
three timings and the exact command. The latter was captured before the
optimized code commit, so it records a dirty tree; the source hash matches
the committed version. This is not a TabPFN training benchmark or evidence
that real-market model creation has the same speedup. There are still zero
certified modern sale labels and no real-market model fit.

## Verification and limits

The [check record](check_records.json) contains commands, exit codes,
durations and log hashes. Forty-two focused tests pass, with **89% branch-aware
coverage** of the changed date module. Ruff check and format, `pip check`,
and `pip-audit --skip-editable` exit zero. Code, Python and security reviewers
[reported no blocking finding](review_evidence.md). The broader project suite passed **1,287 tests
with zero skips**; its [gate](../u0-nonmetro-membership-v2-20261003T205738Z/full_suite_gate.json)
is recorded in the contemporaneous nonmetro run.

The bounded cache can parse one zone twice on simultaneous cold misses; this
affects only performance. The installed pinned wheel and version check are
part of the [run configuration](run_config.json). A zone file changed in
place without a version change is outside this immutable dependency model.
No price accuracy or service-area result was produced in this run.
