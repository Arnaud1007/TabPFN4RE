# U0 NYC ACRIS bounded linkage pilot: incomplete

Run ID: `u0-nyc-acris-pilot-20260929T003102Z`  
Status: **INCOMPLETE**; U0 and G-US **PENDING**  
Code commit at execution: `d51fb533100c5b42960d9d2eb90a499388fd7a68`  
Requirements: US04, US05, US06, US07, US08, US22, US23, US24

## Objective and frozen scope

[ADR 0022](../../decisions/0022-nyc-acris-linkage-pilot.md) froze one sampled
rolling-sales row from each of NYC boroughs 1-4 before any sampled ACRIS row
lookup. The pinned private CSV and 200-row sample ledger matched their recorded
SHA-256 hashes. All four selected rows had complete numeric borough/block/lot
components. The collector used only the official NYC Open Data Master and
Legals APIs, with the registered request, response-size and result caps. Raw
rows, identifiers, query URLs and the selected sample remain under Git-ignored
`data/raw/nyc_dof/`.

## Observed attempt

The live command exited 1 after 3 HTTP requests in 3.491 seconds. The first
BBL lookup returned 27 Legals rows representing 24 distinct document IDs.
One Master row was retrieved for the first document. Its linked Legals lookup
hit the registered 100-row cap, so the collector stopped with the sanitized
`saturated` failure category. Two valid responses were saved privately and
hashed in [aggregate.json](aggregate.json). The third response body was **not**
saved because validation rejected it before persistence; the saturation
classification is the observed process result, not independently replayable
from the two saved responses. No limits were widened and no replacement row
was selected. A later invocation replayed the incomplete state and also exited
1, without creating another response file.

**No selected transaction was matched or manually reviewed. No sale price,
closing date, first availability time, or commercial reuse right was
established.** The result does not admit NYC data to training or the 90-day
as-of benchmark. The first BBL's 24 distinct documents also shows why a
50-request ceiling may be too small if every document needs Master and linked
Legals evidence; that is a capacity observation, not a reason to silently
change the frozen protocol.

## Checks and evidence

[test_gate.json](test_gate.json) records the actual live/replay exits and eight
successful checks. The collector's 25 focused synthetic tests passed with
86% branch-enabled coverage. The full repository suite passed 419 tests with
one optional OpenML integration skip and no mandatory skips. Ruff lint and
format, `pip check`, and the scoped pinned-dependency audit passed. The
code-table failure messages in the full-suite log come from expected negative
fixtures; the suite exit code was 0. The
[manifest](manifest.json) records code, environment, configuration, source,
sample and private response hashes. Run
`& 'runs/u0-nyc-acris-pilot-20260929T003102Z/verify_artifacts.ps1'` from the
project root to recheck the saved private evidence and tracked files.

## Decision and next action

Keep `nyc-acris-pilot-v1` failed and immutable. Before another sampled lookup,
review the first BBL's document-type mix privately and register a new protocol
with a justified candidate rule, response caps and request budget. Preserve
the original four selected rows and disclose that this pilot exposed source
structure. A future collector should save bounded invalid/saturated responses
privately before returning a failure, so the failure itself can be replayed.
Continue the independent 200-record manual rubric and source-rights/date
questions; this pilot completed zero rubrics. Do not train or certify NYC data.
