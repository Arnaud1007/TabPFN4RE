# ADR 0096: Score the frozen King later period once for research

Date: 2026-10-05. Owner: Arnaud. Status: adopted before later-period scoring.
Protocol: `king_later_2015_research_v1`. Requirements informed: US11, US12,
US13, US23. This is not a G-US certification protocol.

## Decision and fixed inputs

The 14,621 sales before 2015 trained the existing model. The 2,228 January-
February 2015 sales selected XGBoost over the ZIP median. Score both frozen
predictors once on all 4,752 eligible March-May 2015 sales in the existing
[split](../runs/king-historical-20261004-v1/split_manifest.json). Do not refit,
tune, change features, abstain after observing errors or use the later scores
to select a new champion.

Freeze the OpenML source SHA-256 `25817379c3f06c584ca61eb2413a8368af72fc5548848a0ceb9bb4a885e90401`,
split SHA-256 `55cfef3afd7e51c3f85b0ddc8af0c272f62a615c178bc509d04ba327aa009a75`,
bundle manifest SHA-256 `32c11c3ac12e69126d2e1b2b58ab9eb5403a001836cfeb102442b234fef7cbe9`
and XGBoost checkpoint SHA-256 `cead625a3b87d73f46fdf740bfb366b9ff3b17d52434011a63e0ca91849f0033`.
Use the common metric engine for MdAPE, within-10%, P90 APE, signed bias and
all-row coverage. Store row-level prices and predictions only in ignored
private storage; commit aggregate results and their evidence hashes.
Use the original NumPy exponentiation of model log outputs. Pin NumPy 2.4.6
and XGBoost 3.2.0; record their observed versions, Python version, dependency
lock hash, feature-policy hash and model-configuration hash with the run.

The runner must commit a one-use opening intent before it parses the source.
An interrupted opening consumes this research cohort under this protocol; a
second model cannot silently reuse it. Save the prediction file before
computing metrics. The code and this decision must be committed before the
opening run.

## Interpretation limit

The previous validation runner parsed the entire OpenML file, including the
later prices, while checking its source and split. The later cohort has not
been scored or used for model selection, but its labels were not technically
inaccessible. The uploader supplies sale dates without verified contract,
closing or recording semantics, individual label availability, historical
property-attribute vintages, arm's-length flags or original rights. Therefore
the result is a **retrospective later-period research diagnostic**, not an
untouched final test, a 90-day pre-sale prediction or a current King County
service. G-US remains PENDING regardless of its score.

This additional diagnostic is authorised to answer whether development
performance persists in later historical sales. It does not replace source
qualification, calibration or a genuinely prospective test.
