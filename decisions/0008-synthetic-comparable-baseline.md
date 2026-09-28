# ADR 0008: Synthetic comparable retrieval baseline

Date: 2026-09-28

Owner: project implementation

Affected requirements: US06, US08, US10, US23

## Alternatives and evidence

The U1 comparable filter already rejects future and late-published sales, wrong property classes, disallowed transfers and known duplicate economic transfers. A simple price-per-area baseline can be tested with synthetic WGS84 locations and living areas before a real source qualifies. Distance ranking by an unknown target price was rejected because it would leak the answer. Learned retrieval and area-adjusted sale prices require training data and valid temporal folds that are not yet available.

The RED synthetic suite initially failed at a missing retrieval API. A first implementation passed nine tests. Independent code, Python and security reviews found three integrity gaps: missing area bypassed subject validation, a later subject version could be passed to pricing, and a post-sale comparable area could alter a historical price-per-area. New failing tests reproduced these cases; the corrected implementation and fourteen targeted tests then passed. The complete test suite and lint were rerun before the code commit. Exact gate evidence is recorded separately in `runs/`.

## Decision

Use a frozen configuration to rank eligible sales by geographic distance, sale recency and living-area difference, with deterministic ties. Keep only the latest eligible sale per neighboring property. Expand radius under the registered 12-month window until the minimum count is reached or the final radius is exhausted. The preliminary point estimate is the weighted median USD per square foot times subject living area. The priced result binds the exact subject version, origin and source snapshot. Candidate property versions dated after their sale are excluded.

This is an engineering baseline, not a certified model. The default scales, 5-neighbor cap, 3-neighbor minimum and 2/10/30 km radii are synthetic starting values, not market-validated settings. The `supported` field currently means only that the count threshold is met inside a radius. It does **not** establish physical similarity, prediction quality or release support. No age adjustment, price-area fit, local market trend, uncertainty interval or observed US source is present.

## Promotion dependencies

Before real-data acceptance, derive retrieval scales and physical-similarity/support thresholds from development-only folds; compare 5/10/20 neighbors and 6/12/24-month windows; add age/condition and geography constraints where source semantics support them; audit 50 real queries; and test sparse and source-dropout cohorts. A source snapshot needs a content hash and dated property versions. Evaluate the price-per-area baseline against area-adjusted and residual-correction variants on identical valid cohorts. No current source card proves the historical timing required for those experiments.
