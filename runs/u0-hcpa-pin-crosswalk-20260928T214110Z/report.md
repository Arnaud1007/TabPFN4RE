# U0 HCPA disjoint PIN crosswalk audit

Run ID: `u0-hcpa-pin-crosswalk-20260928T214110Z`. Requirements addressed:
US05, US06, US07 and US24. Status: empirical identifier-format evidence;
**no automatic parcel join is authorised**. U0 and G-US remain pending.

## Fixed inputs and method

[ADR 0017](../../decisions/0017-hcpa-pin-crosswalk-validation.md) froze the
ASCII PIN guard, candidate segment permutation, 99% distinct-control rule
and the ten-cell disjoint sampling design before this audit. The [sample
selection run](../u0-hcpa-pin-validation-sample-20260928T211600Z/report.md)
committed the new 1,000-row sample SHA-256
`35c52bc969980cb0e1cabb698a70754825774f0ddc09e6b1417cdc21dc1ad3f9`
before either parcel comparison. Its old 200-row discovery sample was
excluded. The validator enforces both hashes in its normal 1,000-row mode.

The 2025 archive SHA-256 is
`2c575a9d7f47a0a3d20527f3c2c5bfa88cb9fbdb9f27dfe3fce59d3edec8260c`;
its parcel DBF has PIN `C29`, FOLIO `C10`, STRAP `C22` and 527,723 active
rows. The 2026 current archive SHA-256 is
`968901f963b6424d89ecba757d8c9d6e1117acb3e2228a0d9885461da9c2e3c8`;
its parcel DBF has PIN `C25`, FOLIO `C20` and 531,612 active rows. These are
separate vintages. Neither archive date proves first availability at a
historical valuation origin.

## Observed results

The [aggregate](aggregate.json) includes every selected sale row and all ten
100-row date/`QU` cells. The 2025 exact raw PIN+FOLIO comparison finds one
parcel row for **984/1,000** sale rows, no multiple exact matches and 16 with
no exact match. The 984 exact rows represent **983 distinct `(PIN, FOLIO)`
controls** with nonblank STRAP; the frozen conversion agrees with STRAP in
**983/983 distinct controls** and 984/984 sale rows. The sample has 999
distinct source identities, so repeated sales are not counted as independent
controls or transformed-key collisions.

For the 2026 archive, every sample row has one FOLIO lead. Of those, 994
parcel rows have nonblank PIN, and the candidate conversion agrees in
**994/994**. The other six have blank current parcel PIN and are excluded
from that agreement denominator, not imputed. There are no observed
transformed-key collisions, duplicate exact matches or PIN/FOLIO conflicts
under this validator's categories. There are 16 missing 2025 exact controls,
including six FOLIO-only leads. The [aggregate gap breakdown](gap_breakdown.json)
shows that unmatched 2025 rows occur in several date bands; their causes
remain unverified. The six blank 2026 PINs also span several date bands.
Five of those six also lack a 2025 exact control; this overlap is a review
priority, not an inferred reason for either source gap.
This deliberate date/qualification stratification is not a county-wide
match-rate estimate.

The numeric format criterion in ADR 0017 is met **on this sample**. The
aggregate's `automatic_join_status` is `BLOCKED`: the publisher has not
confirmed that this permutation is a stable source contract, and first
publication, rights, property-level sale scope and eligibility are unresolved.
No raw FOLIO lead or transformed match becomes an eligible modelling row.

## Execution and reproducibility

The exact command, pinned hashes, exit codes, durations, private flags hash
and immutable artifact hashes are in [test_gate.json](test_gate.json) and
[manifest.json](manifest.json). The first real scan exited 0 in 5.980 seconds.
A second invocation with distinct output paths exited 0 in 13.126 seconds.
The two aggregate files are byte identical, SHA-256
`00589ab40082ca48828c7420fdb2f122637722a001750c53d4e399a8288bc541`;
the two ignored private flag files are byte identical, SHA-256
`add23b60b5d8cb1793d06a8f5a26f2c3c45f8863d44cbf521c33284ff18f2d79`.
No row-level identifier, price, address or reviewer note is tracked. The
source audit uses the reviewed code committed at `6d46b4e`; its synthetic
checks and 338-test full suite are recorded in the [preceding gate](../u0-hcpa-pin-validation-sample-20260928T211600Z/test_gate.json).

The audit writes private flags and the aggregate separately. If it crashes
between writes, an absent aggregate means the run is incomplete; retain
the orphan private file as failed evidence and replay the identical pinned
configuration to new output paths. This crash path was reviewed but not
triggered against the real archives.

## Next action and blockers

Investigate the 16 missing 2025 controls and six blank current PINs through
private source review; preserve both groups in the audit denominator. Seek
publisher confirmation of the format mapping and source-specific commercial
reuse rights. Complete the 200-record manual sale/parcel/Clerk review: zero
rubrics are complete. Establish actual sale-date meaning, transaction scope,
first availability and historical parcel vintages before building any
certified as-of feature or modern US model. The prepared custodian inquiry
remains unsent; the owner requested a ready-to-send email because no mail
account was connected in this workspace.
