# ADR 0103: King absolute-error serving refit

## Status

Accepted for one bounded private refit and research-only serving bundle.

## Context

ADR 0102 selected `xgboost_log_absolute_error` on four November 2014 through
February 2015 rolling development windows. It reduced pooled development
MdAPE from 8.56% to 8.27%, improved MdAPE in all four windows, and met the
registered useful-gain rule. Its four fold models are development evidence,
not a single artifact suitable for the existing local prediction command.

The source still lacks historical publication times, attribute vintages,
arm's-length flags, original-source commercial-use clearance, and a certified
90-day origin. This refit cannot promote the model, open March through May
labels, or support a current valuation claim.

## Decision

Bind the refit to the committed ADR 0102 manifest and aggregate by exact
SHA-256. Require the selected candidate, four improved windows, 16,849
eligible rows, and zero March through May labels parsed or scored. Require a
clean committed worktree and the exact Python, NumPy, and XGBoost versions in
the hash-pinned dependency lock before fitting.

Run a separate staging command against the pinned full ARFF. The staging
command reuses the selective pre-March reader, which inspects only identifier
and date prefixes for later rows and fully parses only the 16,861 rows before
1 March 2015. It applies the frozen target-blind eligibility policy, requires
exactly 16,849 eligible rows and the 12 known future-year-built quarantines,
and atomically writes a canonical JSON-lines training artifact plus manifest
under the private root. The stage manifest binds source, cutoff, schema,
membership, quarantine and artifact hashes.

The model builder accepts only that private stage directory and its expected
manifest SHA-256. It has no full-ARFF argument or full-source reader. It opens
only the staged manifest and pre-March artifact, revalidates every row,
membership hash, eligibility rule, source identity and cutoff, then fits
exactly one XGBoost model with the ADR 0102 configuration:

```text
objective: reg:absoluteerror
training cutoff, exclusive: 2015-03-01
fit count: 1
```

The final model configuration is an immutable literal independent of the
legacy model configuration. The selection manifest must contain that exact
model dictionary, including depth, seed and objective. Before publication,
save the fitted model, reload it through a new XGBoost instance, and compare
both instances on a deterministic eight-row training-only probe batch. Require
finite equivalent predictions under declared absolute and relative tolerances.
Record probe and prediction hashes, tolerances and maximum differences in the
summary and manifest. A failed reload or comparison prevents publication and
does not satisfy T10.

Write the model, ordered feature names, candidate declaration, summary, and
manifest atomically into a new ACL-checked directory directly below the
private King benchmark root. The manifest binds the source, training
membership, quarantine counts, selection evidence, dependency lock, runtime,
resolved configuration, feature policy, checkpoint, code commit, and every
output hash. It explicitly records zero March through May labels parsed and
scored. If verification after the atomic rename fails, retain the renamed
directory as failed-run evidence; do not recursively delete a path whose
identity has not been re-established.

The prediction loader dispatches explicitly between the legacy bundle, whose
manifest has no bundle protocol field, and this protocol. Legacy validation,
response keys, reference period, capture and display remain unchanged.
The new bundle loads only when the caller SHA-256, private manifest SHA-256,
and immutable public registry manifest at
`runs/king-absolute-error-serving-20261006-v1/manifest.json` are identical.
The loader validates exact outputs and aggregate size, runtime, code-commit
shape, training membership, stage identity, configuration, summary and zero
later-label counters. Responses additionally expose bundle protocol,
objective, exclusive training cutoff, training period, selection period, the
median-like point semantics of log absolute-error loss, and the intended
90-day conditional-sale target. They use an unambiguous rolling-development
reference period. The form and capture validator dispatch on the exact
`bundle_protocol` and reject hybrid schemas. Loading the new predictor also
verifies the active Python, NumPy, XGBoost, platform and machine values before
model deserialization.

## Evidence boundary

The resulting artifact is a faster local research predictor only. Its final
refit has no disjoint performance estimate. Do not parse or score the frozen
March through May labels, attach the rejected historical intervals, claim the
ADR 0102 development score as final-refit accuracy, certify a 90-day origin,
offer King County service, claim commercial eligibility, or advance G-US.
