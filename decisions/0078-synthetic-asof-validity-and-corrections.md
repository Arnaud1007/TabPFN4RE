# ADR 0078: Versioned effective dates in synthetic OFF snapshots

Date: 2026-10-03
Owner: project implementation
Status: implemented engineering contract; real-source admission pending
Affected requirements: US06, US08, US22, US23, US24
Affected protocol: `synthetic_off_asof_v2`; synthetic input schema fingerprint v2

## Evidence and alternatives

The first U1 canonical records had `observed_at` and `available_at`, but no
effective interval. The assembler accepted a supplied property record whose
state had expired and selected the latest attribute observation even if its
validity ended before the valuation origin. Merely adding `valid_to` would let
later corrections rewrite an earlier backtest. Filtering each version alone
would also leave an older open copy active after a later published end.

The alternatives were to use observation order as implicit validity, attach an
undated end, or require an effective interval with separately evidenced end
availability. The first two cannot distinguish physical state from when the
source made a correction known. The [synthetic RED/GREEN run](../runs/u1-synthetic-validity-v1-20261003T160514Z/report.md)
tests the chosen contract and its ambiguity cases.

## Decision

`Property` and `Attribute` may carry `valid_from`, `valid_to` and
`valid_to_available_at`. The interval is half-open, with `observed_at` as the
default start when no explicit `valid_from` exists. A stated end requires its
own availability timestamp. The assembler applies the end only after both the
record and its end have become available by the source cutoff; historical
snapshots exclude future disclosure even if the physical end was earlier.

For attributes, identical source observations are reconciled before effective
time filtering. A disclosed end closes their earlier open copies. Conflicting
ends, a later open copy that could retract a known end, and unresolved overlap
between an expired correction and an active observation fail with a diagnostic.
No value is guessed. The assembler policy and synthetic bundle input schema
fingerprints changed, so an old bundle cannot be loaded under this contract.

The current API receives one already selected `Property`; it checks that
version's validity but does not prove that a source supplied every property
revision. A real adapter must resolve the complete property history and
publish its version lineage before this can support a certified historical
prediction. No real-market label, score or release gate is accepted here.
