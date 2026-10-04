# ADR 0089: Fixed 12-input Ames prediction profile

Date: 2026-10-04
Owner: Arnaud
Status: adopted before scoring; historical engineering prototype only

## Decision

Add a `manual12` profile to the existing Ames development prototype. Its exact
inputs, in request order, are `GrLivArea`, `OverallQual`, `Neighborhood`,
`YearBuilt`, `TotalBsmtSF`, `GarageCars`, `FullBath`, `BedroomAbvGr`, `LotArea`,
`OverallCond`, `KitchenQual` and `Fireplaces`. This is a fixed engineering
choice based on common property facts and the ability to enter them locally;
the fields were selected before viewing this profile's errors. Quality and
condition use the historical Ames 1-10 definitions; `Neighborhood` uses Ames
codes. Those definitions limit direct use outside this dataset.
Living area, basement area and lot area are square feet; rooms, baths,
fireplaces and garage capacity are counts. Manual requests reject negative
physical quantities, noninteger counts and invalid year/rating values.

Use the checksum-pinned source, recovered 1,168-row development partition,
292-row unopened holdout, same five folds, same fold-local preprocessing and
fixed XGBoost configuration as the full-feature prototype. Give the profile a
separate protocol and exact feature-schema check. Keep old full-feature
bundles loadable. Fit the serving bundle only on development rows.

## Evaluation and promotion

Save paired row-level predictions privately and publish aggregate MdAPE,
within-10%, P90 absolute percentage error, signed bias and runtime. Compare
against the existing full-feature development scorecard on identical rows and
folds. Report the accuracy cost of easier data entry, even if the 12-input
model is worse. The synthetic request is a serving check, not an accuracy
observation. No legacy holdout result, future-sale accuracy, calibrated
interval or G-US claim follows from this experiment.

Require the full source leakage guard, exact input schema, split-hash equality,
zero reserved-row overlap, bundle hash validation and CLI/direct prediction
parity. An executable local CLI with a 12-field request is the deliverable.
Further feature changes require a new protocol and development comparison.

## Alternatives

Entering all 75 fields is cumbersome. Filling 63 absent fields in the old
model would change its information set without measuring the resulting error.
A new model trained and evaluated with the same 12 fields gives a measured
trade-off while leaving the original artifact intact.
