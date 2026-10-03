# ADR 0064: stage Cook parcel-sale observations without label promotion

- Date: 2026-10-03
- Owner: project implementation
- Requirements: US02, US03, US05, US06, US07, US08, US22, US23, US24
- Protocol: `cook-parcel-source-staging-v1`
- Status: approved for a bounded private source-schema round trip

The frozen 200-row Cook Assessor capture is useful for testing the source adapter, but its `sale_date` is a recording date, its row availability is unknown, and a parcel-sale row is not necessarily one dwelling transfer. The current canonical `Transaction` requires a close instant, availability instant and an economic-transfer identity that this source has not established. [ADR 0051](0051-cook-sales-private-audit-sample.md) and [ADR 0056](0056-cook-socrata-system-timestamp-boundary.md) retain those boundaries.

Create an immutable `CookParcelSaleObservation` separate from `Transaction`. Preserve every selected raw source scalar and the distinction between an omitted field and explicit JSON null. Parse source row ID, 14-character PIN state, published USD price state and recorded local date without converting them to certified property, close-date or first-availability facts. Keep per-row lineage to the pinned capture manifest, exact source-response bytes and a canonical JSON hash of the selected row values. Invalid optional values remain auditable states; an unidentifiable row or unexpected field fails the batch. Repeated document numbers and multi-parcel flags remain review prompts, never independent labels.

Use the existing ACL-checked `_capture_rows()` loader, which replays the original capture and checks its exact 200-row membership. The new runner performs no HTTP request, makes no changes to the frozen capture or review ledger, writes create-only private observations with a completion manifest last, and verifies exact bytes before publishing a fixed allowlist aggregate. The only public facts are input/output hashes, the already disclosed 200-row denominator, zero certified labels, false historical as-of eligibility and PENDING gates. No PIN, document number, price, date, address, row ID, new small-cell count or free-text note enters Git.

This is a source-schema and lineage checkpoint under the [frozen plan](../runs/u0-cook-source-staging-v1-20261003T055304Z/plan.md). It does not qualify a sale label or satisfy U0/US07. A future mapping to canonical `Transaction` requires independent transaction scope, true close date, row-first availability, property identity, arm's-length and rights evidence under a new decision.
