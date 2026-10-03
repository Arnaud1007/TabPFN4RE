# Illinois Additional PINs v1 capture: rejected

- Date: 2026-10-03 UTC
- Requirements: US02, US05, US06, US07, US24
- Protocol: `illinois-ptax203-additional-pins-v1`
- Status: **FAILED before any row query**; U0 and G-US remain PENDING.

The one-shot collector verified the pinned Cook and PTAX inputs, created an ACL-restricted private run, and made its first official metadata GET. HTTP status was 200, and the response SHA-256 was `25a80a2c9274813cfda7d84ad717562765743fae7a9e33aced92edd7daa829cd`. The v1 parser rejected it because it required the `rowIdentifierColumnId` property to be present with a null value. The actual source metadata **omits the property**. The earlier inventory had displayed a missing-key lookup as null and wrongly described it as an explicit null. No response body was saved for the rejected request, no Additional PIN row query occurred, and there is no completion manifest or valid public aggregate.

The private failure event is retained under Git-ignored `data/raw/illinois_ptax203/ptax-additional-v1-130b5169ff81ccbc/`; its SHA-256 is `9283d315d27294bb1334553571940088d701ffa06d0ad0cd8a417c8b1197c2e6`. The v1 collector code SHA-256 at execution was `d4f4bb632c798f2bed93b43818c425feaeab97cc0f1a15d8330ca2e1454cf352`. Three later **metadata-only** bounded reads confirmed the same response hash and the absent property; none queried a declaration ID or PIN. No v1 retry is permitted.

The corrected interpretation is “no row identifier declared in the observed metadata,” without assuming a unique key. ADR 0060 and a new frozen v2 plan register a create-only run name and the exact absence check before any row retrieval. Zero sale labels are certified; historical availability, transfer scope, closing date and rights questions remain unresolved.
