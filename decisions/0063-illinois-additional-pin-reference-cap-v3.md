# ADR 0063: version the Additional PIN observation-reference cap

- Date: 2026-10-03
- Owner: project implementation
- Requirements: US02, US03, US05, US06, US07, US08, US24
- Status: approved for local-only v3 diagnostic

The frozen [v2 offline plan](../runs/u0-illinois-additional-pin-offline-v2-20261003T051910Z/plan.md) capped candidate pairs and Additional-observation references separately at 500. Its one real run failed during worklist construction after all pinned inputs passed preflight. No complete private diagnostic or public aggregate was written. The [failure report](../runs/u0-illinois-additional-pin-offline-v2-20261003T051910Z/failed_report.md) records a resource-only diagnostic without disclosing new cross-source counts.

Repeated Cook rows can reference the same captured Additional observation without creating independent labels. The separate reference cap was too low for this valid grain-preserving representation. Raise **only** that resource cap to 5,000 in a new `illinois-additional-pin-offline-v3` protocol. Keep the 500 candidate-pair cap, 1 MiB worklist cap, exact matching states, duplicate preservation, four pinned hashes, create-only private persistence and fixed privacy-safe public allowlist. This is not a change to eligibility or a model-selection threshold.

Freeze the [v3 plan](../runs/u0-illinois-additional-pin-offline-v3-20261003T053506Z/plan.md) before running the real comparison. Use a new private directory. Test both sides of the new cap synthetically, rerun checks and review, then perform one real offline run. A failure remains failed and requires a further version; no source row or sale label is promoted by this decision.
