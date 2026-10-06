# Next action

Updated: 2026-10-06. Branch: `audit/u0`.

## HCPA OFF runner stops immediately at preflight, 6 October 2026

The [runner preflight](runs/u0-hcpa-off-preflight-v1-20261006/report.md)
passes 13 focused tests with 90% branch-aware runner coverage. The combined
admission and runner regression passes 71 tests with two documented Windows
symlink-creation skips, and Ruff lint and format checks pass. Direct-script and
module invocations returned byte-identical blocked JSON with exit 3. An invalid
argument returned generic stderr and exit 2 without echoing the argument.

No raw row, archive, private ledger, label or model was accessed by the runner;
no output or run reservation was written by it, and no model fit ran. This is
an executable blocked boundary, not a prediction result. Keep HCPA training
blocked until the source-admission and fit-readiness findings clear and a later
reviewed protocol adds the first permitted downstream step.

**Exact local recheck:** `& '.venv/Scripts/python.exe' -m scripts.run_hcpa_off_baseline`

## HCPA source-admission gate is executable and pending, 6 October 2026

The [source-admission verification](runs/u0-hcpa-source-admission-v1-20261006/report.md)
passes 58 focused tests with two Windows symlink-creation skips, 92% branch
coverage, and Ruff checks. Two production CLI invocations returned identical
results: `status=pending`, `source_admitted=false`, and
`model_fit_permitted=false`. The three fit-readiness blockers are pending
semantic feature flags, historical property attributes, and eligibility
rules. No HCPA archive, row, private ledger, model artifact, or model fit was
used.

The v1 validator intentionally cannot admit the source. Send the approved
custodian inquiry through the owner's authenticated mail client. A later
reviewed protocol must authenticate the response, verify all four source
findings, clear the separate fit-readiness gate, and implement an atomic
one-run ledger before the frozen HCPA OFF baseline may run.

**Exact local recheck:** `& '.venv/Scripts/python.exe' -m scripts.hcpa_source_admission`

## HCPA custodian recipient revalidated, 6 October 2026

The [recipient revalidation](runs/u0-hcpa-custodian-revalidation-20261006-v1/report.md)
confirms from current official HCPA sources that Marilyn Martinez is the
Records Custodian and that records requests should use
`martinezm@hcpafl.org`. The earlier recipient is superseded. A plain-text
ready-to-import `.eml` now accompanies the approved Markdown inquiry. The
owner's authenticated mail client must populate its intentionally absent
`From` and `Reply-To` fields before delivery.

The inquiry remains unsent because this workspace has no authenticated mail
surface. Until an authoritative response resolves sale-date meaning,
first-publication history, repeated consideration and permitted commercial
use, do not admit HCPA sales to certified model training. Revalidate the
recipient again immediately before any later send.

## Three-field King ablation rejected, 6 October 2026

The [three-field development ablation](runs/king-three-field-ablation-20261006-v1/report.md)
completed four fixed fits in 22.94 seconds. Adding `yr_renovated`,
`sqft_living15`, and `sqft_lot15` together worsened pooled MdAPE from 8.2750%
to 8.3664% and improved only one of four windows. Keep the log absolute-error
incumbent and do not test these fields individually on the same windows.

The next model-critical task is one fixed OFF baseline on a source whose
point-in-time fields, transaction scope, and use rights have cleared. Until
then, use the saved King bundle for immediate historical research predictions;
do not reopen March-May labels or start another King feature search. G-US
remains **PENDING**.

## Prediction result and latency verified, 6 October 2026

The [batched ACL latency checkpoint](runs/king-batched-acl-latency-20261006-v1/report.md)
removed the measured cold-start bottleneck without bypassing private-directory
checks. Ten complete CLI predictions took 0.95-1.39 seconds (1.28-second
median), all returned the exact same estimate, and all passed the two-second
target. Continue using the resident form for repeated predictions.


The [historical result contract](runs/king-result-contract-20261006-v1/report.md)
now makes the saved estimate's 2015 cutoff, historical freshness, unvalidated
market support, unavailable intervals and evidence limits explicit in both CLI
and form output. New receipts require the exact schema; older hash-valid
receipts remain recoverable for commitment.

Ten fresh CLI timings were 2.00-2.64 seconds (2.40-second median), so the cold
two-second target is currently **not met** despite the earlier faster run.
Keep the model resident in the form for repeated predictions. The next local
performance task is profiling and reducing strict JSON bundle validation time
without weakening checkpoint or schema verification.


The [dependency-free inference checkpoint](runs/king-pure-inference-20261006-v1/report.md)
verified the pinned 250-tree model against XGBoost on 31,285 rows with zero
bitwise mismatches. Five complete CLI predictions took 1.18-1.77 seconds and
all returned **$553,846.97** for the example request. Use
`Launch-KingResearchForm.cmd`; model training is not performed for a request.

The next model-critical task is one fixed OFF baseline on a source whose
point-in-time fields, transaction scope and use rights have cleared. The saved
King predictor remains historical research evidence and G-US is still pending.

## Resident prediction latency measured, 6 October 2026

The [resident-latency checkpoint](runs/king-resident-latency-20261006-v1/report.md)
loaded the hash-pinned absolute-error model once and issued 100 predictions.
Cold loading took 19.96 seconds on this run, while resident p95 prediction
latency was 1.27 ms and all estimates were identical. Keep the model resident
inside the local form and avoid per-click model loading or retraining.

Double-click `Launch-KingResearchForm.cmd`, wait for the one-time loading state
to clear, then make repeated predictions. Cold startup remains an optimization
target; the measured delay is variable Windows/NumPy/XGBoost loading rather
than model creation.

## HCPA adjacent parcel corrections verified, 6 October 2026

The [adjacent-release comparison](runs/u0-hcpa-parcel-release-diff-20261006-v1/report.md)
verified 531,612 rows from the exact 2 October and 5 October parcel archives.
Geometry and schema were unchanged, but 104 DBF records changed, including
embedded sale dates/prices, assessed values, tax values and one PIN. This is
direct evidence that later parcel releases cannot be backfilled into earlier
valuation origins without leakage.

Keep capturing new exact releases with `--new-only`. The immediate usable
prediction result remains the saved King research model; HCPA training stays
blocked until target semantics and permitted use are established.

## New HCPA parcel release captured, 6 October 2026

The [new-release checkpoint](runs/u0-hcpa-new-release-20261006-v1/report.md)
used the clean-commit `--new-only` workflow against the official listing. It
skipped unchanged All Sales bytes and captured only `parcels_10_05_2026.zip`.
The private three-event ledger verifies its 155,508,715 bytes and classifies it
as a new parcel release. Twenty-seven focused tests passed.

This adds prospective property-source history without retraining. It still
creates zero certified sale labels and does not resolve sale-date semantics,
one-home consideration or commercial model-use rights. Run the same command
when checking for later official releases; it will avoid duplicate downloads.

## HCPA prospective release ledger, 6 October 2026

The [prospective ledger checkpoint](runs/u0-hcpa-prospective-ledger-20261006-v1/report.md)
registered the two accepted exact-byte HCPA captures in independent parcel and
All Sales chains. Nineteen focused tests passed with 86% branch coverage on
the new ledger and changed capture path. Future capture commands now append
new, repeated or corrected observations automatically and recover interrupted
registration without a stale-lock dead end.

This establishes this workspace's first-seen evidence from 5 October onward;
it does not resolve closing-date meaning, one-home consideration, historical
publication or commercial model-use rights. Keep the fast saved King predictor
as the immediate runnable result. Capture HCPA again only when a new official
release appears, and train one fixed HCPA OFF baseline only after source
semantics, rights and matured prospective labels clear.

## HCPA retrospective no-go, 6 October 2026

The [bounded HCPA review](runs/u0-hcpa-review-batch-20261006-v1/report.md)
added nine strict official-property-record reviews, bringing the frozen sample
to 12 complete and 188 unreviewed. Seven new records corroborated all four
supported identity/classification fields; two did not expose the sampled sale
row. Every completed review still lacks closing-date, one-home consideration,
publication-history and reuse evidence.

[ADR 0104](decisions/0104-hcpa-retrospective-source-admission-no-go.md) stops
the remaining row reviews until authoritative source-wide evidence arrives.
Do not fit a retrospective HCPA model. Continue exact prospective release
captures; when semantics and rights clear, run one frozen absolute-error OFF
baseline without another architecture search.

## Faster saved prediction model, 6 October 2026

The [King absolute-error serving bundle](runs/king-absolute-error-serving-20261006-v1/report.md)
is built and runnable. One fixed fit on 16,849 pre-March rows completed in
about 14 seconds, and the saved model returned **$553,846.97** for the example
request. Future predictions load this checkpoint without training. The public
manifest is an exact hash-matched copy of the private bundle manifest, and the
save/reload probe matched exactly.

Double-click `Launch-KingResearchForm.cmd` to use this selected model. The
[default-launcher checkpoint](runs/king-default-launcher-20261006-v1/report.md)
verified the pinned path, manifest, CLI-equivalent output and 43 focused tests.

Use this absolute-error bundle for immediate historical research predictions.
Do not run another model search until a source clears point-in-time, transaction
scope and use-rights checks. The next model-critical task remains one fixed OFF
baseline on a qualified source or a newly matured prospective cohort. G-US is
still pending.

## Fast absolute-error result, 6 October 2026

The [King log absolute-error screen](runs/king-log-absolute-error-development-20261006-v1/report.md)
completed four fixed fits in 25 seconds. Changing only the log-price objective
from squared to absolute error improved pooled MdAPE from 8.56% to 8.27%,
improved all four windows and raised within-10 accuracy from 56.25% to 57.34%.
Use log absolute error as the preferred candidate in the next qualified
point-in-time experiment. Do not attach it to serving or reopen March-May for
selection; source timing, transaction scope and rights remain unresolved.

## Fast comparable result, 6 October 2026

The [King comparable residual screen](runs/king-comparable-development-20261006-v1/report.md)
completed in about 30 seconds on 5,108 rolling development sales. Chronological
out of fold comparable residuals worsened pooled MdAPE from 8.56% to 9.10% and
improved none of four windows. Keep the fixed XGBoost and do not tune this
comparable configuration against the same windows. The source cannot resolve
duplicate economic transfers or point in time availability, so the screen does
not satisfy US10 and cannot support promotion or G-US.

## Fast interval result, 5 October 2026

The [King historical interval checkpoint](runs/king-historical-intervals-20261005-v1/report.md)
reused saved predictions and completed without retraining. Calibration used
1,875 March sales and evaluation used 2,877 April-May sales. Coverage passed at
78.24% for the 80% interval and 88.53% for the 90% interval. Mean 90% relative
width was 54.45%, above the 40% utility cap, so the interval configuration is
rejected and will not be attached to the prediction form. Do not tune against
the consumed April-May labels. The next interval attempt requires a new
development mechanism and a fresh later evaluation cohort.

## Fast prediction research result, 5 October 2026

The [King rolling recency checkpoint](runs/king-rolling-development-20261005-v1/report.md)
scored 5,108 November-February historical sales in four chronological windows.
The fixed XGBoost model achieved 8.56% pooled MdAPE and 56.25% within 10%. The
single predeclared 180-day recency challenger reached 8.63% MdAPE, improved only
1 of 4 windows and was rejected. Keep the fixed model; do not spend more time
on recency weighting without a new error mechanism. The result remains
retrospective research because source timing and rights are unresolved.

## Private HCPA review checkpoint, 5 October 2026

The [second property-record review checkpoint](runs/u0-hcpa-property-record-candidate-20261005-v2/report.md)
now binds the exact official PDF digest in the private append-only ledger. A
generated full-cohort check proves exactly one of 200 frozen sample rows matched
all four supported fields and that this row was not among the two previously
reviewed records. The audit is 3 of 200 complete; 197 remain unreviewed.

**Next review action:** continue the stratified review while seeking authoritative
closing-date, consideration-scope, historical-availability and commercial-use
evidence. HCPA remains excluded from certified training and G-US remains pending.

## Immediate prediction checkpoint, 5 October 2026

The [one-action enrollment checkpoint](runs/king-prospective-enrollment-20261005-v1/report.md)
adds **Predict + record** to the King form. One click reuses the loaded model,
writes the private receipt and publishes the privacy-safe commitment. A failed
commitment is restored after restart and retried without making another
prediction. The saved-model integration returned `$542,149.79`; this remains a
2015 historical research estimate and G-US remains pending.

The [commitment recovery checkpoint](runs/king-commitment-recovery-20261005-v1/report.md)
processed the one pending synthetic v2 receipt without another prediction.
The verified startup scan now reports zero pending current-format receipts.

The [local receipt checkpoint](runs/king-prospective-receipt-20261005-v1/report.md)
proves that committed code can create an access-restricted, create-only receipt
without printing property inputs. Receipt format v2 now adds a private 256-bit
nonce, retains exact raw request bytes, uses a random private ID and supports a
[privacy-safe public commitment](runs/king-prospective-commitments-v1/report.md).
The public artifact omits property inputs, price, request and response hashes,
enrollment hash, private ID and prediction time. This synthetic workflow has no
future outcome and its workstation clock is not independently trusted. Next,
enroll real properties before outcomes are known, publish their nonce-hardened
commitments promptly and wait for qualifying sales to mature.

The [King County local form](runs/king-form-20261005-v1/report.md) now gives a
historical research estimate from the saved model without training. Its
synthetic example displays `$542,150`. The live verification recorded an
0.078-second form construction, a 14.953-second model-ready time, a 0.110-second
first prediction and a 0.079-second repeated prediction on this workstation.
The window stays responsive during loading and the verified model is loaded
once per application session. These observations do not establish the final
application's p95 latency target. The form and CLI share the same guarded
prediction service. Editing an input clears the prior estimate. The private
model bundle is still needed locally.

**Exact form command:** `$env:PYTHONPATH = "$(Resolve-Path -LiteralPath '.');$(Resolve-Path -LiteralPath 'src')"; & 'data/raw/legacy-replay/.venv/Scripts/python.exe' -m scripts.king_research_form --bundle data/raw/king-benchmark/king-absolute-error-serving-20261006-v1 --manifest-sha256 50ca467e61a52752e5ff9082297eeff1b294ef761aec383c8c7d2537c027941d`.

**Next model-critical action:** qualify a source with provable pre-origin inputs,
one-home arm's-length sale labels and permitted use, then run one fixed OFF
baseline. Do not promote the King historical predictor to current or 90-day
service; G-US remains pending. Continue HCPA source review and exact-byte
prospective captures while that source gate is unresolved.

## HCPA source-review checkpoint, 5 October 2026

The [official property-record evidence checkpoint](runs/u0-hcpa-property-record-evidence-20261005-v1/report.md)
adds a strict official-page evidence type and completes one additional
single-family rubric. The audit is now 2 of 200 complete. Parcel identity,
property class and the displayed qualification label agree, but exact date,
consideration scope, reason-code meaning, historical availability and use
rights remain unresolved. HCPA is still excluded from certified training.

The [root documentation audit](runs/u0-hcpa-root-documentation-20261005-v1/report.md)
captured the official `_Documentation.doc` exactly and found a general
redistribution permission with a condition that HCPA references be removed
from the final product. Because this is titled parcel-layer documentation, its
scope for the standalone All Sales ZIP is not explicit. It also confirms Clerk
receipt followed by HCPA review and names multi-parcel, barter/trade and title
transfers as unqualified examples. It does not clear commercial AVM use,
define `S_DATE` as closing date, identify per-row first publication, or prove
one-home price scope. The source is therefore still excluded from certified
90-day training; the custodian inquiry is now narrower.

The [frozen-sample review](runs/u0-hcpa-review-progress-20261005-v1/report.md)
now has one reviewer-attested complete rubric, with nine unknown findings;
199 of 200 sampled records remain unreviewed. The checked deed-index evidence
describes a condominium outside the initial single-family cohort. It does not
establish closing date, one-home consideration, publication timing or reuse
rights. HCPA is still excluded from certified 90-day training. The private
review ledger and source ZIPs remain Git-ignored with restricted local access.

**Exact resume command:** `& '.venv/Scripts/python.exe' -m scripts.review_hcpa_sample summary data/raw/hcpa/audit-sample-20260928-888226e.jsonl data/raw/hcpa/review-ledger-20260928.jsonl - runs/u0-hcpa-review-progress-20261005-v1/summary_next.json --sample-sha256 2f26728c37f8218d1bb79ee75e4082fb918665eb2cb4cc287feba7f6250aaec9`. Review further rows only against accessible official records; retain unresolved facts as unknown and append revisions through the ledger CLI.

## Exact HCPA source captures, 5 October 2026

The [prospective capture report](runs/u0-hcpa-prospective-captures-20261005-v1/report.md)
records clean-commit, exact-byte downloads of the October 2 parcel ZIP and
September 18 All Sales ZIP, with independent SHA-256 checks. These are source
observations, not a 90-day model result. The current exact parcel bytes were
first observed today; there are no matured sales at origins using them. The
older 2025 parcel ZIP still lacks a contemporaneous exact-byte checksum.

**Next runnable source work:** Use the frozen 200-row HCPA review sample and
private ledger to complete source rubrics, preserving unknowns; have the
owner send the revised custodian inquiry for `S_DATE`, price scope, release
history and commercial model-use terms. Continue exact-byte capture when a
new official release
appears. If historical provenance and labels clear, fit one fixed OFF
baseline; otherwise keep the verified King historical research predictor
available while prospective outcomes mature. Do not rerun the HCPA listing
capture merely to repeat the same filename observation.

## Prediction results reset, 5 October 2026

**Immediate result, verified today:** The saved King County model returned
`$542,149.79` for the synthetic [15-field request](examples/king-research-request.json)
in a verified replay, without retraining. Its response is marked
`historical_research_only`; it represents a 2015 research setting, not a
current home valuation. Run the command in the King prediction section below.
The existing Ames 12-field form is available for a simpler interactive demo.
The King development validation score was 8.90% MdAPE on 2,228 sales; this
is not evidence of current-market accuracy. The frozen later-period
[research check](runs/king-later-2015-v1/report.md) scored 4,752 March-May
2015 sales at 10.52% MdAPE and 47.94% within 10%. Neither cohort certifies
the 90-day or US release task.

**Short delivery plan:** Keep the saved King predictor as the immediate
prediction result. For a different historical King property, copy the
15-field example JSON, replace its property facts, and run the same pinned
command; no new training is needed. The development and later-period
scorecards are the measured accuracy evidence for this historical model.
Timebox the next 90-day OFF source qualification to two working hours. If its
pre-origin data, single-home sale labels or permitted use cannot be
established, record a no-go and capture new sources prospectively. Train just
one fixed baseline within the following working day if a candidate clears
those checks. Do not delay the runnable historical predictor for further
model searches or imply a date for G-US certification.

| When | Deliverable | Done when |
| --- | --- | --- |
| Now, done | Replay the saved King model on the synthetic 15-field request | Numeric output and historical scope are visible in one command |
| Done: King later-period research | Applied the frozen model to every March-May 2015 row without refitting | [4,752-row scorecard](runs/king-later-2015-v1/report.md): 10.52% XGBoost MdAPE, 47.94% within 10%; research only |
| Done: Indiana source decision | Published the 200-row audit queue, inspected 20 extreme low-price records, and checked assessment timing | [No-go decision](decisions/0094-indiana-assessment-asof-no-go.md): 20 inspected, none confirmed arm's-length; no pre-origin assessment vintage established |
| Done: Hillsborough source decision | Checked independent 2025/2026 archived listings and the exact local ZIP hash | [ADR 0095](decisions/0095-hcpa-archive-listing-asof-boundary.md): listed by April 2026, exact local bytes only verified in September; HCPA 90-day historical model remains blocked |
| Next source action | Obtain a dated exact parcel release or begin prospective captures, and resolve All Sales close-date, transaction scope and use terms | One source with defensible origin-time inputs and sale labels before the next fixed model fit |
| If a source passes | Fit one fixed OFF baseline on matured labels and pre-origin fields, then save chronological predictions and a scorecard | Reproducible errors, bias, tails, coverage and source timing; no architecture search |
| Later | Complete the source audit, calibrate intervals and reserve future outcomes | Only a passed gate supports a market release claim |

The immediate prediction is already working. Model fitting is fast: the
Indiana two-model comparison took 36.32 seconds end to end. The delay is
proving which fields were available before a sale, validating transaction
labels and obtaining an untouched future evaluation cohort. The 200-row queue
is not a completed manual audit. Pause additional model families, new markets,
post-hoc slices and nonessential documentation while these prediction
deliverables are open. Push each accepted checkpoint to `origin/audit/u0`.

**Source continuation:** Seek a contemporaneous checksum or publisher
release history for the 2025 parcel archive. The [archived listing
check](runs/u0-hcpa-wayback-20261005-v1/report.md) shows the filename in an
April 2026 capture, but does not date our September ZIP bytes. Resolve All
Sales date, price scope and reuse questions before a 90-day baseline.

To capture a newly listed exact ZIP from the project root, use
`& '.venv/Scripts/python.exe' -m scripts.capture_hcpa_release parcels <exact-listed-filename>`
or substitute `allsales` and its exact filename. The command rejects a changed
listing or mismatched response filename and stores the bytes under ignored
private storage. It does not itself qualify the data for modelling.

## Prediction-first reset after three days

**New October 4 result:** The fixed [Indiana assessment-snapshot diagnostic](runs/indiana-assessment-diagnostic-v1/report.md)
trained two models on the same 65,490 sales and scored the same 71,054 later
sales in 36.32 seconds. Adding assessed values and neighborhood lowered MdAPE
from 30.79% to 15.19% and raised within-10% accuracy from 15.44% to 36.57%.
This is development evidence only: the fields were observed in later downloaded
sale-disclosure snapshots, with unknown pre-sale availability and possible
post-sale revisions. The result is not a current-home prediction service.

**Next runnable source task:** Establish an assessment vintage actually
published before the selected prediction origin, then check whether parcel
linkage and historical coverage reproduce the signal. The public Marion
Gateway PARCEL ZIP matched 18,650 of 19,664 unique nonempty 2024 sale parcel
IDs but contains no `IMPROVE`/`DWELLING` building fields; stop using it as a
planned living-area source. Independently complete the 200-record Indiana
sale/transfer audit. If dated assessment or building attributes are not
available, keep this diagnostic unpromoted and change source. Do not rescore
2025 as if it were an untouched certification test.

To replay the fixed diagnostic from a clean committed tree with pinned private
archives, choose a **new** ignored output directory:

```powershell
$env:PYTHONPATH = (Resolve-Path -LiteralPath 'src').Path
& 'data/raw/legacy-replay/.venv/Scripts/python.exe' -m scripts.indiana_assessment_diagnostic --source-2024 data/raw/indiana_sdf/SDF_2024.zip --source-2025 data/raw/indiana_sdf/SDF_2025.zip --output data/raw/indiana_sdf/benchmarks/my-new-assessment-run
```

The historical King County request command below already returns an estimate
without retraining. Its saved January-February 2015 development validation
score is 8.90% MdAPE on 2,228 sales. This is the current usable research
predictor, not a current-home or G-US release.

**Done:** The [fixed Indiana 2024-to-2025 comparison](runs/indiana-sdf-20261004-v1/report.md)
scored 71,054 later sales in 24.46 seconds end to end. Its three-input tree
model had 30.79% MdAPE; the county/ZIP median did better at 28.68%. Neither
is a useful current-home valuation or a G-US result. The 2025 cohort is now
consumed development evidence. Do not tune against it and call it untouched.
The large recorded price and acreage extremes remain unaudited.

**Remaining quality task:** audit at least 200 stratified Indiana
transactions, including extreme amounts and ambiguous identities, and qualify
historically dated building-size, age and condition fields if available. Keep
the existing King historical request interface available while this source
work proceeds. A future test for an improved Indiana model requires a new
untouched period and verified information timing.

To replay the fixed historical comparison from a clean committed tree, use a
new private output directory:

```powershell
$env:PYTHONPATH = (Resolve-Path -LiteralPath 'src').Path
& 'data/raw/legacy-replay/.venv/Scripts/python.exe' -m scripts.run_indiana_historical_benchmark --source-2024 data/raw/indiana_sdf/SDF_2024.zip --source-2025 data/raw/indiana_sdf/SDF_2025.zip --output data/raw/indiana_sdf/benchmarks/my-indiana-replay
```

## Immediate prediction delivery plan

1. **Done:** Train and score the 12-field historical Ames model. The saved
   development scorecard and synthetic example are linked below.
2. **Done:** The local 12-field entry form passed form-versus-CLI parity,
   invalid-input checks and the 1,302-test project suite. Its runnable launch
   command is below and its [evidence](runs/ames-manual-form-20261004-v1/report.md)
   is recorded. This gives a usable historical prediction workflow immediately.
3. **Done:** A fixed King County historical research comparison trained and
   scored in 6.46 seconds end to end. On 2,228 Januaryâ€“February 2015
   validation sales, XGBoost reached 8.90% MdAPE and 55.25% within 10%; the
   ZIP-code median reached 21.20% and 25.18%. See the
   [run report](runs/king-historical-20261004-v1/report.md). This is a
   validation-selected development result, with no verified pre-sale
   information dates and no G-US credit.
4. **Done:** The local [King research prediction command](runs/king-serving-20261004-v1/report.md)
   reuses the saved model with a 15-field JSON request and no retraining. Its
   synthetic example returns $542,149.79 for the 2015 historical reference
   period. It is not a present-day valuation.
5. **Done:** The [frozen King March-May research check](runs/king-later-2015-v1/report.md)
   scored all 4,752 later sales once. XGBoost reached 10.52% MdAPE and 47.94%
   within 10%; the ZIP median reached 20.00% and 25.38%. Resolve an official
   source's target, first-availability and reuse-rights questions before the
   next 90-day model fit. Do not describe these scores as US release accuracy.

The [October 4 HCPA listing capture](runs/u0-hcpa-listing-20261004T194412Z/report.md)
adds an observed publication checkpoint: the All Sales filename remained dated
September 18 while the parcel filename advanced to October 2. Further HCPA
listing capture is lower priority than prediction validation. A listing date
does not establish individual sale availability.

Form launch command from the project root on this workstation:

```powershell
$env:PYTHONPATH = (Resolve-Path -LiteralPath 'src').Path
& 'data/raw/legacy-replay/.venv/Scripts/python.exe' -m scripts.ames_manual12_form --bundle data/raw/ames-prototype/manual12-20261004-v1 --bundle-sha256 1505ab1806202b9ca9626bbe5c92c4ef4f7393ef90680994ba8113b0f392a4f4
```

## Prediction checkpoints completed (ADR 0088 and ADR 0089)

The [12-field Ames checkpoint](runs/ames-manual12-20261004-v1/report.md)
provides a quicker manual input path on clean commit `104d571`: 6.81% MdAPE,
66.78% within 10%, and a 2.923-second development run. Its score is paired
with the full-feature model on the exact same 1,168 rows and folds. The
12-field model trades 1.17 percentage points of median error for a much
smaller request. U0 and G-US remain pending.

The [Ames prototype checkpoint](runs/ames-dev-prototype-20261004-v1/report.md)
is implemented and verified on the clean commit `cd2f4221`: 1,168 paired
development-fold predictions, XGBoost 5.64% MdAPE and 71.32% within 10%,
median baseline 24.83% and 21.32%. A full-feature local CLI example and
trusted bundle SHA are recorded there. The 292-row legacy holdout was not
opened. This is historical engineering evidence, not U0 acceptance or a
future-sale US result.

Immediate runnable 12-field prediction command from the project root:

```powershell
$env:PYTHONPATH = (Resolve-Path -LiteralPath 'src').Path
& 'data/raw/legacy-replay/.venv/Scripts/python.exe' -m scripts.ames_dev_prototype predict --bundle data/raw/ames-prototype/manual12-20261004-v1 --request examples/ames-manual12-request.json --bundle-sha256 1505ab1806202b9ca9626bbe5c92c4ef4f7393ef90680994ba8113b0f392a4f4
```

After the form checkpoint, replay the prototype contract from the project root:

```powershell
$env:PYTHONPATH = (Resolve-Path -LiteralPath 'src').Path
& 'data/raw/legacy-replay/.venv/Scripts/python.exe' -m unittest discover -s prototype_tests -q
```

Keep the private bundle outside Git. Resume the U0 source qualifications below
where authoritative access is available; Cook and NYC retrieval
commands remain unavailable pending the specific source/rights evidence
listed there. Do not reopen the legacy holdout. Real US evaluation remains
the release-critical path.

## Active state

**U0 is pending; G-US is pending; zero modern US sale labels are certified.**
The [King historical research run](runs/king-historical-20261004-v1/report.md)
compares two models on an old sale-date validation period. It does not resolve
as-of feature availability, original rights, or the US release gate. Its
March-May 2015 prices were parsed in the original validation run and then
scored once in the [later-period research check](runs/king-later-2015-v1/report.md).
They are consumed research labels, not process-isolated certification labels.
The [synthetic calendar fit speed run](runs/u1-local-date-fit-speed-v1-20261003T220221Z/report.md)
measured a 4.95-fold reduction in median wall time for its 204-row fit,
replay and score test after caching pinned time zones. This is engineering
speed evidence, not a real-market or TabPFN training result. The associated
full project suite passed 1,287 tests with zero skips. Continue U0
source qualification before modern US transaction model training.
The [version 2 candidate map](data/us_market_candidates.json) now derives
New York's 25 and Florida's 22 proposed nonmetro counties from pinned official
2023 Census county lists minus every metropolitan county in the pinned July
2023 delineation. [ADR 0086](decisions/0086-pinned-nonmetro-county-membership.md)
records the definition and limits. This verifies candidate geography only;
neither statewide feed has an eligible sale cohort or supported service area.
The [pre-tuning US market candidate map](data/us_market_candidates.json)
now names eight metros across four Census regions and two separate proposed
nonmetro strata, checked against a pinned Census delineation workbook. It is
an inventory with zero supported markets. Several source footprints cover
only part of a metro, and market variation still needs qualified data.
[ADR 0085](decisions/0085-us-market-candidates-before-tuning.md)
requires a versioned replacement before final tuning if a candidate fails.
The [synthetic capture byte-binding run](runs/u3-synthetic-capture-binding-v1-20261003T193616Z/report.md)
now replays a guarded OFF median from the exact five-row generated training
file it hashed, with reserved prices absent. Its full suite passed 1,262 tests
with zero skips and 81% branch-aware coverage across the two touched model
modules. This verifies engineering provenance for a synthetic fixture only;
no real sale source, rights, first-publication rule or economic-transfer
meaning has been certified. Continue U0 source qualification before real-data
training; U3 and G-US remain pending.
The [synthetic local-date publication v2 decision](decisions/0082-source-local-feature-publication-v2.md)
now permits typed date-only first publication for property and attribute facts
and typed prior-sale dates in a separate OFF feature policy. It keeps source
zones and precision in lineage, rejects future and duplicate sale facts, and
does not change the exact-UTC or local-date v1 policy. This is synthetic
engineering work; a real source still needs verified first-availability dates,
rights, semantics and independently hashed raw artifacts. Continue the U0
source audit before any real-data training.
The [synthetic source-local date OFF bridge](runs/u3-synthetic-local-date-off-v1-20261003/report.md)
now joins date-only sale labels to 90-calendar-date origins, timestamped
as-of features and a guarded median fit under the frozen synthetic maturity
plan. Its final suite passed 1,244 tests with zero skips and 89% combined
branch-aware coverage of the four touched production modules. The recorded
source digest is still a fixture declaration, not a verified raw-source hash.
Date-only publication now has a typed synthetic contract but no verified
real-source adapter. U3 has
not been accepted and no real-market labels were trained.
The [synthetic property-history selector](runs/u1-synthetic-property-history-v1-20261003T164855Z/report.md)
now resolves structural versions at valuation time and comparable sale time,
with separate information cutoffs, late-publication tests and deterministic
copy reconciliation. Its checks are engineering evidence only. A real adapter
still has to prove recoverable historical versions and first availability.
The [consolidated U0 gate review](runs/u0-gate-review-20261003T134443Z/report.md)
records the verified inventory and the failed historical XGBoost reproduction.
[ADR 0072](decisions/0072-u0-legacy-replay-acceptance-boundary.md) keeps the
mandatory criterion open; no acceptance exception has been adopted.
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
The [synthetic effective-version check](runs/u1-synthetic-validity-v1-20261003T160514Z/report.md)
passed a later 1,201-test full suite with zero skips and 88% branch-aware
coverage of its three touched production modules. It requires dated end
publication, closes identical source observation copies, and fails on
unresolved overlapping corrections. The assembler still receives one
preselected property version and has no certified real-source history.
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
The [Cook private source-quality funnel](runs/u2-cook-quality-v1-20261003T135237Z/report.md)
replayed the pinned 200 parcel observations, wrote private fixed-code findings
and count partitions, and passed 1,185 full-suite tests with zero skips.
Its public aggregate contains no new small-cell counts. Every observation
remains audit-only, with zero certified sale labels.
No certified real-market model training, final calibration or certification
test has begun. The King research-only comparison is separate.
ON mode and international implementation remain locked by the specification.

## Next dependency-ready work

1. **Cook source audit:** identify an authorised route to an authoritative
   deed/parcel instrument and clarify `sale_date`, first public availability,
   multi-parcel consideration, characteristic vintages and dataset-specific
   reuse rights. The [Cook source card](data/source_cards/cook_county_parcel_sales.yaml)
   and [private staging report](runs/u0-cook-source-staging-v1-20261003T055304Z/report.md)
   describe the frozen 200-row queue. One manual rubric is complete, one is
   partial and 198 are untouched. The
   [private quality audit](runs/u2-cook-quality-v1-20261003T135237Z/report.md)
   now provides fixed review reasons for all 200 rows without changing their
   eligibility or order. The [MyDec public search access check](runs/u0-mydec-browser-click-v1-20261003T143000Z/report.md)
   reached the no-login declaration search view without submitting a PIN,
   document number or address. The [document-number tab check](runs/u0-mydec-document-form-v2-20261003T144507Z/report.md)
   left that tab unselected in two headless attempts. A later
   [interactive check](runs/u0-mydec-document-form-interactive-v3-20261003T153202Z/report.md)
   observed the exact document-number form after navigation settled, with no
   identifier or query submitted. The
   [one-document plan](runs/u0-mydec-one-document-v1-20261003T153741Z/plan.md)
   now freezes one existing private lead, provenance, handling and a one-query
   cap; no identifier has been entered. Obtain action-time confirmation before
   entering that exact document number into the official MyDec browser form.
   Continue
   to seek the
   authoritative Clerk instrument and publisher date/rights clarification.
   [ADR 0087](decisions/0087-cook-sale-validation-version-boundary.md)
   records the Assessor's separate, internally versioned sale-validation
   flags and its reported 2026 rerun after omitted 2025 sales were added.
   Ask whether historical flag vintages and late-sale publication logs can be
   obtained under suitable terms; neither has been admitted as an input.
   Use the private quality findings to prioritize independent checks. The
   Cook inquiry is an
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
   outside NYC is a [documented candidate](decisions/0066-nys-salesweb-source-feasibility.md)
   for Northeast metro and nonmetro cohorts. The
   [bounded current export check](runs/u0-nys-salesweb-export-v1-20261003T150117Z/report.md)
   verified a private 25-row CSV with 78 header fields, including sale,
   contract, deed, initial-load and update dates. This resolves the current
   format/header question left by the static UI audit, but no row is certified.
   The [live detail-page help audit](runs/u0-nys-salesweb-detail-help-v1-20261003T152306Z/report.md)
   exposed a price-basis conflict: current help says personal property is
   included in sale price, while the older dictionary describes a net price.
   It also defines initial database loading without establishing first public
   availability. The [current UI/CSV concordance check](runs/u0-nys-salesweb-ui-csv-concordance-v1-20261003T163610Z/report.md)
   matched all 25 bounded search rows on six displayed fields and four detail
   pages on 12 fields each. The detail page leaves a zero price blank even
   though the result table and CSV show zero. A 2025 sale date with a 2026
   deed and database-load date demonstrates why sale date is not availability.
   These checks do not resolve price basis, first publication or reuse rights.
   The [custodian draft](data/requests/nys_salesweb_inquiry_draft.md)
   now asks about the exact current CSV mapping.
   The [official ORPTS quarterly-report guidance](decisions/0071-nys-orpts-report-date-price-boundary.md)
   maps report Sale Date to transfer date and distinguishes deed recording;
   it also documents concession and parcel-correction risks. The current
   CSV's date/price meanings, historical public availability and reuse terms
   remain unverified. Register a 200-record stratified audit only after those
   access and rights questions are resolved.
   Its [custodian inquiry](data/requests/nys_salesweb_inquiry_draft.md) is
   an unsent draft.
   HCPA and Florida DOR have separate unresolved identity, time and rights
   issues. The [Douglas County, Colorado metadata check](runs/u0-douglas-co-source-feasibility-v1-20261003T172000Z/report.md)
   found direct parcel-sale and improvement downloads, but only current
   active-account coverage. Confirm whether County portal reuse guidance
   applies to these files, and obtain gross-price, close-date, first-publication,
   transfer-scope and historical-vintage definitions before row acquisition.
   The [Assessor inquiry draft](data/requests/douglas_county_assessor_source_inquiry_draft.md)
   collects these questions; it has not been sent or used to order a paid report.
   [ADR 0083](decisions/0083-douglas-confidential-declaration-field-boundary.md)
   records that the official confidential TD-1000 form has distinct closing,
   contract and total-price fields, while the public download has no published
   mapping to them. The revised inquiry asks for that mapping without seeking
   confidential declarations. Do not infer a close date or gross target from
   the form.
   The other Western candidate's
   [King County access review](runs/u0-king-rights-v1-20261003T154623Z/report.md)
   found a required Assessor download acknowledgment and separate eSales
   commercial-content restriction. No acknowledgment was accepted; the
   [King inquiry](data/requests/king_county_assessor_source_inquiry_draft.md)
   remains unsent. Seek a source-specific use decision for either Western
   candidate before acquisition. Select eight metros across four Census regions plus two
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
.\.venv\Scripts\python.exe -m unittest tests.test_asof_version_validity -q
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_property_version_selection.py -q
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_u2_comparables.py -q
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_local_date_*.py -q
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
The typed date-only publication and synthetic capture byte-binding engineering
tasks have been verified. Their next dependency is a real source with
independently hashed raw bytes, permitted use, true target and availability
semantics, and an audited property/unit mapping. The candidate market map
does not open a real-data fit or substitute for those U0 checks.
