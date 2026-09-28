# U1 synthetic integrity increment

Run ID: `u1-canaries-20260928T113723Z`

Code commit: `01eebfed08d793e824d68443f13137ba5270f801`

Requirements touched: US06, US08, US09, US10, US11, US12, US14, US22, US23, US24
Status: T01–T08 synthetic checks **verified**; U1 **PENDING**; G-US **PENDING**

## Objective and completed changes

Add an as-of comparable candidate filter, known forbidden-feature canaries, and a guarded OFF median baseline whose fit path uses an application-owned feature registry. Fit checks canonical transfer-level split membership, source inclusion, label eligibility, 90-day origin alignment and label maturity. Prediction rejects origins before the fitted training cutoff. A 200-row synthetic flow fits 160 matured labels and predicts 40 later reserved rows before their outcomes are supplied to scoring.

## Commands and observed results

`test_gate.json` records the exact commands, exit codes, durations, code and source hashes, environment lock hash, output logs and their hashes. The Python 3.11 suite passed **131 tests** with **89% statement coverage**; Ruff lint and format checks passed. The synthetic median was 179,500 USD and all 40 reserved rows reached the shared scorecard. That number and any synthetic error are fixture behaviour, not empirical housing performance. Code, Python and security reviews found no remaining high or medium issue in this increment after the temporal fixture was corrected.

## Failed attempts and limitations

RED canaries exposed cross-feed transfer conflicts, forbidden feature aliases, relabelled reserved transactions, unmatured training labels, duplicate economic transfers, invalid model construction and prediction before model training. The first gate capture, `runs/u1-canaries-20260928T113634Z/`, is retained as incomplete: PowerShell treated unittest stderr as a terminating error before the capture script wrote complete evidence. The successful rerun used the same committed code and corrected log capture.

The comparable function is currently an auditable eligibility filter; it does not rank by distance, adjust prices or yield an estimate. It scans all visible transactions per query and needs a canonical indexed store before large US use. The fixed feature list does not prove upstream source facts are honest. No modern multi-market US labels, source rights, calibration cohort or prospective outcomes were evaluated. U0 legacy artifacts remain missing, so U1 cannot be accepted as a sequential milestone yet.

## Next action

Verify rights and historical availability for the first larger official US source, register its source card, and build a small audited adapter fixture. Resume details and unresolved dependencies are in `next_action.md`.
