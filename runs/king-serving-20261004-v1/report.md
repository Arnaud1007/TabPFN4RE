# King historical research prediction command

Date: 2026-10-04. Scope: **historical King County research only**. U0 and
G-US remain **PENDING**. This checkpoint adds a request interface to the
already-fitted [King validation model](../king-historical-20261004-v1/report.md);
it does not retrain or rescore the model.

## Result

The [synthetic 15-field request](../../examples/king-research-request.json)
returned **$542,149.7940648721**. The machine output is preserved in
[example_prediction.json](example_prediction.json). The response identifies
the January–February 2015 reference period, the model and manifest hashes,
and `certified_90_day_origin: false`. It contains no asking price or sale
price input.

The saved checkpoint has manifest SHA-256
`32c11c3ac12e69126d2e1b2b58ab9eb5403a001836cfeb102442b234fef7cbe9`
and model SHA-256
`cead625a3b87d73f46fdf740bfb366b9ff3b17d52434011a63e0ca91849f0033`.
The serving implementation and tests are committed at
`247c5ce2de27adab3b2f45a40d64376b43399340`.
Its original clean training-code commit is
`3df798b6689a2aa2f6732cb93b065ad5493eda41`. Source, split, dependency
lock, configuration and feature-policy hashes remain in its private manifest.

The model's earlier development validation measured 8.90% MdAPE and 55.25%
within 10% on 2,228 January–February 2015 sales. Those numbers are copied
from the [saved validation scorecard](../king-historical-20261004-v1/validation_summary.json),
not scores for the synthetic request. No later March–May cohort was scored.

## Checks

- Four focused unit tests passed: input boundaries, feature order, log-price
  conversion and bundle tamper rejection.
- One local saved-checkpoint integration test passed in the pinned Python 3.11
  environment. It compared a validation row with its archived prediction to a
  declared $0.10 tolerance and checked CLI/library equality. The one-off
  replay difference observed before that test was $0.040028.
- The CLI produced the saved synthetic output and returned a clear nonzero
  status for a bad manifest hash. A final cold CLI invocation took 3.1114
  seconds on this workstation, including Python startup and bundle checking.
  Ruff checks and formatting passed.
- The pinned dependency audit reported no known vulnerabilities.
- The full project suite passed **1,320 tests in 227.611 seconds**, with
  **92% package coverage** and no skipped tests. The exact commands and
  results are recorded in [test_gate.json](test_gate.json).

The private bundle, raw source, validation rows and property-level values
remain outside Git.

## Run

From the repository root on the existing workstation:

```powershell
$env:PYTHONPATH = (Resolve-Path -LiteralPath 'src').Path
& 'data/raw/legacy-replay/.venv/Scripts/python.exe' -m scripts.king_research_predict --bundle data/raw/king-benchmark/king-validation-20261004-v1 --manifest-sha256 32c11c3ac12e69126d2e1b2b58ab9eb5403a001836cfeb102442b234fef7cbe9 --request examples/king-research-request.json
```

Edit only the [request file](../../examples/king-research-request.json) to
try another hypothetical King County house. The private model bundle is not
in Git; a fresh clone must reproduce the historical benchmark first and use
its newly saved manifest hash.

## Limits and next action

The underlying data do not establish what was knowable 90 days before a
sale, current-market behaviour, arm's-length status or source reuse rights.
The command has no calibrated interval. It must not be used as a current
valuation or US release. The next prediction-critical task is to qualify
one contemporary transaction source's label, first availability, historical
attributes and permitted use, then run a small as-of OFF baseline if it passes.
