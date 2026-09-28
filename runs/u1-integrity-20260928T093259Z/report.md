# U1 training and scorecard increment

Run ID: `u1-integrity-20260928T093259Z`
Code commit: `08b2b55` (full hash in `test_gate.json`)
Requirements touched: US11, US12, US22, US23, US24
Status: T05-T08 foundation **verified**; U1 **PENDING**; G-US **PENDING**

## Objective and completed changes

Add fold-scoped training ID guards, a categorical encoder that does not fit validation categories, distinct future-sales and unseen-property split validation, and one point-error scorecard. The scorecard records every eligible row's estimate, failure or abstention status; invalid monetary outputs fail explicitly. Its threshold shares use exact comparisons, and its quantile convention is recorded in ADR 0003.

## Actual commands and observed outputs

`test_gate.json` records the full commands, exits, durations, environment and output hashes. The Python 3.11 run passed 88 tests with zero skips and measured 90% statement coverage. Ruff lint and format checks exited 0. Code, Python and security reviews reported no remaining high or medium finding after the final numeric-bound fix.

This result is executable engineering evidence, not an accuracy score for a US service area. The Ames source-bound tests used the local verified OpenML file; the new guard and metric cases use synthetic rows.

## Failed attempts and next task

The RED tests first exposed mutable split membership, padded IDs, category-code collision, unsupported currency, rounding at the exact 10% boundary, and an extreme Decimal representation. Each was corrected before this recorded gate. No real-world temporal US model was trained. Complete the remaining U1 comparable-time and feature-fit canaries, then a synthetic end-to-end pipeline before assessing U1 acceptance. The legacy artifacts and multi-market US source dependencies remain listed in `next_action.md`.
