# ADR 0088: Prediction-first Ames prototype

Date: 2026-10-04
Owner: Arnaud
Status: adopted execution order; prototype work planned

## Problem and evidence

Three days of source qualification and synthetic controls have not produced a
usable new model result for the owner. The source audit is necessary for G-US,
but it is not a prerequisite for a clearly labelled Ames engineering prototype.
The existing 200-row Ames smoke run made 40 reserved-row median predictions in
0.906 seconds, with 23.9331% MdAPE and 17.5% within 10%. This is a weak
engineering baseline, not a US service result. The separate five-fold legacy
development replay took 5.106 seconds for 1,168 rows, although it included raw
`Id` and did not reproduce the historical XGBoost score. It cannot be promoted.

Evidence: `runs/u0-smoke-20260928T082634Z-ef55636ed896/` and
`runs/u0-legacy-replay-20260928T145000Z/`.

## Decision

Deliver visible, reproducible historical Ames predictions first. Keep the
strict temporal US qualification as a separate track. Prototype evidence may
show that the model pipeline works; it does not advance U0 or G-US acceptance.
Do not start another source investigation until the first prototype scorecard
and example prediction are available, except to resolve a direct blocker to
that deliverable.

## Timeboxed execution

1. **Available now:** expose the existing median run's aggregate metrics and
   explain its 40-row denominator and historical scope. This is already
   implemented and verified; it is not the desired final model.
2. **Next working session, target 90 minutes:** make a distinct
   `ames_dev_prototype_v1` experiment on the recovered 1,168 development rows.
   Test first. Skip the 292 legacy holdout ARFF data lines before parsing
   prices, using the pinned membership and source hashes from the guarded
   replay. Compare a fold-trained median with one fixed XGBoost setup,
   excluding raw `Id`, `SalePrice`, `MoSold`, `YrSold`, `SaleType`,
   `SaleCondition`, and any other known post-sale or target-derived field.
   Fit imputers and categorical encoders inside each of the five
   development folds. Cap fitting and debugging at 60 minutes of local compute;
   if the environment stalls, report the exact failure and the working median
   result rather than broadening the search. Save private row predictions and
   a public aggregate scorecard with MdAPE, within-10%, P90 APE, signed bias,
   sample count, runtime, code/environment/data/split hashes and limitations.
3. **Following working session, target 60 minutes:** fit the chosen prototype
   configuration on development rows only and expose a local CLI prediction
   for a complete Ames-style property request. Show one actual example output,
   the input fields, model version and explicit prototype status. Add a CLI
   versus direct-model consistency test and a reserved-ID fit guard. Persist
   the model and preprocessing together. No interval will be displayed until
   a disjoint calibration cohort has been defined and tested.
4. **After the prototype checkpoint:** resume qualified US source acquisition,
   as-of feature construction, temporal evaluation and calibration under the
   existing U0–U8 gates. The Ames result cannot support a 90-day future-sale,
   multi-market or national accuracy claim. TabPFN enters only after checkpoint
   rights and hardware feasibility are verified; it does not delay the first
   prediction result.

## Acceptance and stop rule

The prototype checkpoint is complete when the paired development predictions,
aggregate scorecard, one CLI example and relevant tests are saved with exact
replay commands. This is an engineering checkpoint, not an accepted U0 or US
release. Stop model search after the fixed comparison; choose any extension
from measured errors rather than trying architectures indefinitely. Push the
verified checkpoint to `https://github.com/Arnaud1007/TabPFN4RE.git` as the
owner requested.

The remaining G-US blockers stay in `next_action.md` and `migration_report.md`:
qualified modern transactions, historical availability, source rights,
multi-market coverage and a prospective shadow cohort.
