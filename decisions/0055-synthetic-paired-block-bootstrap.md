# ADR 0055: synthetic paired block-bootstrap comparison

Date: 2026-10-03
Owner: project implementation
Status: adopted for synthetic engineering; real-data protocol pending
Requirements: US12, US13, US22, US23, US24

## Decision

Join baseline and challenger saved predictions by exact canonical row IDs,
using outcome-free row metadata supplied separately. Require the same USD
actual, positive predicted prices and successful estimate status for every
row. Any absent, extra, failed or abstained prediction stops this comparison;
the service-coverage scorecard must report those cases separately. This
comparison's point-error denominator is the complete **common successful
pair** cohort, not an automatically certified pre-abstention cohort.

Each metadata row declares a market, geographic block and temporal block
chosen on development data. Make each `(market, geography, time)` cell one
atomic unit. If a property appears in multiple cells, merge those cells into
one connected resampling component. Reject a property crossing markets.
Sample whole components with replacement within each market, preserving
repeat properties and at least one sample from every declared market. Hash
the split, block-plan fingerprint, all paired rows, block labels and resolved
component membership. Input ordering does not change the hash or draws.

Use 5,000 draws and seed 42 for the registered comparison. Smaller draw
counts are diagnostic tests only. Report challenger-minus-baseline differences
in MdAPE, within-10 share, signed median percentage bias, absolute median
bias and P90 APE, all in fractional units. Report both pooled sale-weighted
and equal-market averages. Use the shared metrics' inclusive within-10 rule
and type-7 quantile convention. Percentile 95% intervals use type-7 2.5% and
97.5% quantiles over paired block replicates. A negative MdAPE difference
favours the challenger; this module does not itself promote a model.

Fewer than 20 independent components overall or fewer than two in any market
means `INCONCLUSIVE` with no reported interval. This is a conservative
engineering floor for this synthetic protocol, not a statistical theorem.
The implementation caps input at 100,000 rows and bounds the worst-case
resampled row work at 100 million row-draws; larger comparisons need a
versioned, profiled implementation. The caps are operational limits, not
accuracy filters.
Even with enough components, block-shape sensitivity, four-window development
consistency, cost and tail noninferiority remain separate release decisions.

## Alternatives and limits

Independent row resampling was rejected because repeat sales and nearby/time
related sales would be treated as independent. Assigning each property to its
first block was rejected because it would conceal cross-block dependence.
Connected components can grow large; that loss of independent units is
reported rather than hidden. Pooling markets in one resampling bag was
rejected because it could omit a smaller market in a replicate.

The module accepts declared block IDs and hashes; it cannot prove their
boundaries were chosen before validation outcomes or that their geography is
correct. The current implementation is **synthetic-only** and cannot satisfy
real US13 or G-US evidence. Real comparison requires source-backed cohort,
frozen block design, at least four temporal development windows, saved paired
predictions, sensitivity analyses and an untouched final protocol.

## Measured local cost

The data-free probe in `runs/u3-synthetic-paired-20261003T023000Z/` measured
36.535 seconds for 10,000 synthetic rows, 10,000 independent components, two
markets and 100 draws on this host. Scaling that wall time by 50 gives roughly
30 minutes for 5,000 draws, **as an extrapolation only**. No full-size 5,000-draw
run or real-data performance is claimed. The probe is kept separately from
acceptance metrics and must be repeated on the intended hardware before a
cost-constrained real comparison.
