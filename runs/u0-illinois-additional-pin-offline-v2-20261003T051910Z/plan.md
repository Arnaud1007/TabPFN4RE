# Frozen Cook / Additional PIN offline diagnostic plan, v2

Frozen 2026-10-03 UTC **before** any Cook-to-Additional-PIN relation was computed. ADR 0062 rejects the unexecuted v1 plan because of one mistyped input hash. This v2 plan adopts all comparison states, tests, caps, private/public fields and no-label boundaries in [ADR 0061](../../decisions/0061-illinois-additional-pin-offline-triage.md) and the [v1 plan](../u0-illinois-additional-pin-offline-v1-20261003T051508Z/plan.md), with only these versioned corrections:

- Protocol: `illinois-additional-pin-offline-v2`.
- Create-only private directory: `data/raw/illinois_ptax203/ptax-additional-offline-v2-130b5169ff81ccbc/`.
- Prior Cook/PTAX private worklist SHA-256: **`7981f32fe1970afcb2c20768271c5c0c58dc05ff9a3905fe94981aeef9f8ac8e`**, verified directly against the unchanged local file and the committed prior public aggregate. Require both checks before writing output or computing comparisons.
- Unchanged Cook capture SHA-256: `130b5169ff81ccbc0a729cba98400f2fb377ff9a25999316aaac1960e38a3cf7`.
- Unchanged PTAX response-set SHA-256: `69d86b7fb9c221dee662d49ebc01b94ef26f5e2862a0c9d26afb887f997cd05a`.
- Unchanged Additional PIN response-set SHA-256: `5b9d230f76f66d33b024009ee1c81aec18d5318b0cd5c748752ddf4300fba013`.

The exact document and declaration joins, strict PIN tokens, `PT`/`ROW only` states, duplicate observation ordinals, 100 Cook items, ≤500 candidate/observation references, 1 MiB private worklist cap, create-only completion-last persistence, byte-identical replay and fixed privacy-safe public aggregate remain as registered in v1. No new data request is authorised. A v2 failure remains a failed run rather than a reason to mutate these frozen rules.
