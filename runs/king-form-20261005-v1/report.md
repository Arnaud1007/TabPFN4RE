# King County historical research form

Date: 2026-10-05. Status: **implemented and verified for historical research**.
U0 and G-US remain **PENDING**.

## Objective and result

This checkpoint makes an already-fitted King County model usable through a
local 15-field desktop form. It removes training from the path to a prediction:
the application verifies and loads the saved private bundle, validates the
request, and calls the same prediction service as the JSON CLI.

The checked-in synthetic request produced **$542,149.7940648721** in the
machine response and **$542,150** in the rounded form display. The result is a
historical January-February 2015 research estimate. It is not a current
valuation, a 90-day prediction, or a calibrated interval.

## Changes

- Added `scripts/king_research_form.py`, a local Tkinter form with all 15
  required inputs, a synthetic example, field-specific errors, and permanent
  scope text.
- Reused `scripts/king_research_predict.py` for bundle verification, input
  validation, encoding, and model inference.
- Move checkpoint loading and inference to worker threads so the window stays
  responsive. Inputs and actions are locked until the model or result is ready.
- Verify and deserialize the checkpoint once at application startup, then
  reuse that loaded model for every prediction in the session.
- Clear a displayed estimate whenever an input changes, preventing the old
  result from appearing to describe edited values.
- Added unit and hidden-window integration tests, plus a live verifier against
  the private saved checkpoint.

## Verification

The focused form and prediction suite passed **23 tests**. Branch coverage was
**86%** across the two serving modules (form 85%, prediction service 88%). Ruff
lint and formatting checks passed. Independent code, Python, security, and
accessibility reviews were run; no code or security blocker remains.

The optimized live verifier passed under `python -O`, proving that its checks
are not removed with assertions. Its saved run constructed the form in
**0.078 seconds**, made the model ready after **14.953 seconds**, and recorded a
**0.110-second first prediction** and a **0.079-second repeated prediction**.
The prior implementation loaded the checkpoint after each click; observed
completion ranged from 8.547 to 51.469 seconds. The main-flow integration test
proves that the form is created and disabled before model loading completes;
the live result proves model reuse and fast clicks after readiness. One run
does not establish the application's p95 latency target.

A broad lightweight-environment run executed **1,373 tests** and reported two
errors because that environment did not contain `scikit-learn`. Both affected
Indiana encoder tests passed in the pinned Python 3.11 model environment. The
failure was therefore an environment dependency mismatch, not a failure in
the form or model implementation.

The programmatic association between each visual field label and its Tk entry
still needs verification with the target Windows screen reader. Keyboard
focus, Enter submission, modal result/error announcements, and post-result
invalidation have executable coverage.

Commands, exit codes, and exact observed results are in
[`test_gate.json`](test_gate.json). The aggregate live result is in
[`live_result.json`](live_result.json); it contains no property input or
private row data.

## Run

From the repository root on this workstation:

```powershell
$env:PYTHONPATH = "$(Resolve-Path -LiteralPath '.');$(Resolve-Path -LiteralPath 'src')"
& 'data/raw/legacy-replay/.venv/Scripts/python.exe' -m scripts.king_research_form --bundle data/raw/king-benchmark/king-validation-20261004-v1 --manifest-sha256 32c11c3ac12e69126d2e1b2b58ab9eb5403a001836cfeb102442b234fef7cbe9
```

Choose **Load synthetic example**, then **Predict**, or replace the fields with
a hypothetical King County house. The private model bundle and raw source data
remain outside Git.

## Scope and next action

The underlying source does not prove which property facts were available 90
days before sale, arm's-length status, current-market validity, or permitted
production use. The measured historical development and later-period errors
remain in the King benchmark reports. This form does not change those limits.

The next model-critical action is to qualify one contemporary source with
provable pre-origin attributes, one-home arm's-length labels, and permitted
use, then train one fixed OFF baseline. HCPA remains blocked from certified
training while date semantics, transaction scope, release history, rights,
and most of the frozen manual audit remain unresolved.
