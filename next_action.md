# Next action

Updated: 2026-10-03. Branch: `audit/u0`.

## Active state

**U0 is pending; G-US is pending; zero modern US sale labels are certified.**
The legacy Ames split and saved aggregate scores were recovered, but the
original CSV, feature catalogue, row predictions, checkpoint and historical
runtime are missing. The guarded development replay did not reproduce the old
XGBoost scores; the old holdout is retrospective. See [migration_report.md](migration_report.md)
and the [legacy replay report](runs/u0-legacy-replay-20260928T145000Z/report.md).

U1 T01-T08 and a 200-row Ames OFF smoke flow are engineering checks, not a
real-market release. An earlier full suite passed 1,115 tests at the
[Cook staging checkpoint](runs/u0-cook-source-staging-v1-20261003T055304Z/report.md).
The [synthetic T12 holdout ledger](runs/u1-synthetic-holdout-ledger-20261003T111210Z/report.md)
has a crash/replay fixture and a recorded 1,126-test passing suite. It has not
opened any real-market labels and is not a certification runner.
The [synthetic chronology bridge](runs/u3-synthetic-chronological-plan-20261003T113906Z/report.md)
has a later 1,136-test passing suite and verifies training-label maturity at
one UTC fit cutoff per window across pinned source-local zones. It is still
an engineering contract, not a certified real-market split.
The [synthetic OFF bundle v2](runs/u1-synthetic-off-bundle-v2-20261003T122750Z/report.md)
passed a 1,151-test suite with no skips. Its serving JSON omits training row
IDs, requires a separately trusted digest, and remains uncertified; it does
not establish a real-market model or accepted U6 release.
The [NYC observation history](runs/u0-nyc-observation-history-v1-20261003T125727Z/report.md)
records the September and October source captures as two distinct private,
replayable inventory events. Their row-representation multisets are equal;
this does not establish first public availability. Its exact test result is
in the linked report.
The [OpenML Ames source integration rerun](runs/u0-ames-source-integration-v1-20261003T132308Z/report.md)
passed 1,172 full-suite tests with zero skips after explicitly setting
`AMES_ARFF_PATH` to the already available, hash-verified ARFF. This corrects
the earlier interpretation of the one skipped test: the missing legacy file
is `ames.csv`, not the OpenML ARFF. The fixture remains engineering-only.
No real-market model training, final calibration or certification test has begun.
ON mode and international implementation remain locked by the specification.

## Next dependency-ready work

1. **Cook source audit:** identify an authorised route to an authoritative
   deed/parcel instrument and clarify `sale_date`, first public availability,
   multi-parcel consideration, characteristic vintages and dataset-specific
   reuse rights. The [Cook source card](data/source_cards/cook_county_parcel_sales.yaml)
   and [private staging report](runs/u0-cook-source-staging-v1-20261003T055304Z/report.md)
   describe the frozen 200-row queue. One manual rubric is complete, one is
   partial and 198 are untouched. The Cook inquiry is an
   [unsent draft](data/requests/cook_county_sales_inquiry_draft.md); its proposed
   sender/signature change is awaiting the owner's answer. Do not send it
   without that answer.
2. The [Treasurer property portal](decisions/0065-cook-property-portal-discovery-route.md)
   is a possible lead to a recent Clerk document, but its display is explicitly
   **not an official record**. No private PIN has been submitted. A proposed
   one-PIN lookup is awaiting the owner's answer; no purchase or bulk lookup is
   authorised. The in-app browser was unavailable on 2026-10-03. If that route
   remains inaccessible, use official publisher documentation or another
   authorised instrument route.
3. **NYC source audit:** obtain one official instrument for the already frozen
   ACRIS sample lead through a permitted single-document route, or retain a
   bounded access-failure record. Only then freeze a format-specific v2
   comparison under [ADR 0040](decisions/0040-nyc-instrument-and-date-evidence-boundary.md).
   Obtain publisher-backed first-publication, `SALE DATE` to close/contract
   mapping, transfer/unit and rights evidence; finish the private 200-record
   manual review when independent instruments are available. The
   [October repeat capture](runs/u0-nyc-rolling-resnapshot-v1-20261003T101029Z/report.md)
   is byte-identical to the September rolling CSV (82,345 source rows) and
   now has a [two-event private ledger](decisions/0070-nyc-source-observation-history.md)
   with no later row-representation difference and no certified label. The NYC
   [inquiry draft](data/requests/nyc_dof_rolling_sales_inquiry_draft.md)
   remains unsent. No repeat capture should be mistaken for a historical
   per-row availability timestamp.
4. Continue [US source qualification](data/acquisition_backlog.md) if the Cook
   and NYC evidence routes remain inaccessible. New York State Sales Web
   outside NYC is now a [documented candidate](decisions/0066-nys-salesweb-source-feasibility.md)
   for Northeast metro and nonmetro cohorts. Its
   [current static UI asset check](runs/u0-nys-salesweb-ui-v1-20261003T115547Z/report.md)
   found labels for sale, contract, deed, initial-load and last-update dates,
   but did not verify the Excel export or first public availability. The
   [official ORPTS quarterly-report guidance](decisions/0071-nys-orpts-report-date-price-boundary.md)
   maps report Sale Date to transfer date and distinguishes deed recording;
   it also documents concession and parcel-correction risks. The current
   Sales Web export mapping remains unverified. Verify
   its current export, historical availability and reuse terms before
   requesting property rows.
   Its [custodian inquiry](data/requests/nys_salesweb_inquiry_draft.md) is
   an unsent draft.
   HCPA, Florida DOR and King County have separate unresolved identity, time
   and rights issues. Select eight metros across four Census regions plus two
   nonmetro strata before final tuning. No source's raw row count substitutes
   for an eligible single-home transaction cohort.

## Hard blockers to downstream training and release

- A verified gross recorded single-home sale target, a true close-date mapping,
  first availability at each historical origin, and source-specific permitted use.
- Manual audits and joins that resolve property/unit identity, duplicate
  economic transfers and multi-parcel consideration without multiplying labels.
- Historical feature vintages and mature chronological development,
  calibration, untouched test and prospective shadow cohorts. G-US also needs
  the specified market coverage, sample floors, accuracy, interval and service
  gates. See [requirements.yaml](requirements.yaml).
- Missing legacy artifacts limit exact historical reproduction. Do not reopen
  the retrospective Ames holdout as an untouched test.

## Integrity replay commands

From the project root in PowerShell:

```powershell
git switch audit/u0
git status --short
& 'runs/u0-cook-source-staging-v1-20261003T055304Z/verify_artifacts.ps1'
& 'runs/u0-illinois-additional-pin-offline-v3-20261003T053506Z/verify_artifacts.ps1'
& 'runs/u0-nyc-rolling-resnapshot-v1-20261003T101029Z/verify_artifacts.ps1'
& 'runs/u0-nyc-observation-history-v1-20261003T125727Z/verify_artifacts.ps1'
& 'runs/u0-ames-source-integration-v1-20261003T132308Z/verify_artifacts.ps1'
Get-Content data/acquisition_backlog.md
Get-Content data/requests/cook_county_sales_inquiry_draft.md
```

The replay commands require the authorised, Git-ignored private raw files from
these runs. A fresh clone must obtain them through the documented source route
and verify hashes; a missing private file is a dependency, not a passing replay.

After replay, the next source-evidence action is the Cook authorised
instrument route in item 1, or the NYC single-document route in item 3.
Neither has a runnable retrieval command until the access method is verified;
record an access failure if that remains the observed result.
