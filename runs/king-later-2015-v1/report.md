# King County later-period research result

Date: 2026-10-05. Protocol: `king_later_2015_research_v1`. Result:
**completed historical research diagnostic**. U0 and G-US remain PENDING.
The frozen procedure is [ADR 0096](../../decisions/0096-king-later-period-research-check.md),
committed before scoring at `a9d9d714fd0db1e619361e6935af43361aec6e86`.

The saved XGBoost checkpoint and ZIP-median rule were applied without refitting
or tuning to all 4,752 eligible sales dated 1 March through 27 May 2015. Each
method returned 4,752 estimates, with no abstentions or failures. The
aggregate [scorecards](scorecards.json) were copied from the private run. The
[manifest](manifest.json) pins source, split, feature policy, configuration,
checkpoint, runtime and output hashes. Row-level prices and predictions remain
under Git-ignored `data/raw/king-benchmark/king-later-2015-v1/`.

| Measure | Earlier Jan-Feb validation | Later Mar-May XGBoost | Later ZIP median |
| --- | ---: | ---: | ---: |
| Sales scored | 2,228 | 4,752 | 4,752 |
| Median absolute percentage error | 8.90% | **10.52%** | 20.00% |
| Within 10% | 55.25% | **47.94%** | 25.38% |
| P90 absolute percentage error | 29.28% | **26.98%** | 53.38% |
| Median signed percentage error | -2.46% | **-6.99%** | -5.17% |

The earlier column is the XGBoost development score that selected the model;
the later score does not change that frozen choice. The 1.62 percentage-point
rise in MdAPE and stronger negative bias are signals for later source and
market-period diagnosis. No cause is established by this comparison. No
prediction intervals or uncertainty intervals were fitted for this research
fixture.

## Execution and verification

- From the clean, pushed code commit, ran
  `$env:PYTHONPATH = (Resolve-Path -LiteralPath 'src').Path` followed by
  `& 'data/raw/legacy-replay/.venv/Scripts/python.exe' -m scripts.run_king_historical_later`.
  Exit code 0; observed wall time 10.58 seconds, including startup, parsing,
  inference, scoring and private artifact writing.
- The exclusive private opening record predates the completion timestamp.
  The run is consumed; invoking the one-use scorer again is prohibited.
- Verified SHA-256 of both private outputs against the manifest. Independently
  recomputed MdAPE, within-10%, type-7 P90 APE and median signed error from
  4,752 distinct private rows for both methods; all matched the scorecards
  within `1e-12`. Every row date is inside the declared later interval.
- Before opening: seven focused tests passed in both the project and model
  environments, Ruff check/format passed, and the pinned dependency audit
  found no known vulnerabilities. The full suite passed **1,352 tests** with
  **92% package statement coverage** when scikit-learn was appended after the
  project environment. [Test details](test_gate.json) retain earlier
  environment-only failures rather than treating them as model failures.

The passing full-suite command from the project root was:

```powershell
$env:PYTHONPATH = (Resolve-Path -LiteralPath 'src').Path
$env:AMES_ARFF_PATH = (Resolve-Path -LiteralPath 'data/raw/openml/house_prices-42165.arff').Path
@'
import site
import unittest
from pathlib import Path
import coverage
site.addsitedir(str(Path('data/raw/legacy-replay/.venv/Lib/site-packages').resolve()))
run = coverage.Coverage(source=['tabpfn4realestate'])
run.start()
suite = unittest.defaultTestLoader.discover('tests')
result = unittest.TextTestRunner(verbosity=0).run(suite)
run.stop()
run.save()
raise SystemExit(0 if result.wasSuccessful() else 1)
'@ | & '.venv/Scripts/python.exe' -
```

## Claim boundary and next work

The earlier runner had already parsed the later sale prices while checking
the OpenML file. The source has no verified pre-sale feature vintages,
per-record publication times, arm's-length status or original use rights.
This is a retrospective sale-date check, **not** an untouched final test,
90-day pre-sale estimate, current valuation or US release. The proposed G-US
error thresholds are not met here, and this cohort cannot certify that gate
even if they were.

Keep the working historical prediction CLI available. The next model fit
depends on qualifying a source with verified origin-time inputs and
single-home sold-price labels. Continue prospective source capture where
historical vintages cannot be established.
