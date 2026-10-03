# Frozen Illinois Additional PINs capture plan, v2

Frozen 2026-10-03 UTC after v1 rejected its first metadata response and **before any Additional PIN row query**. Use [v1's full plan](../u0-illinois-additional-pins-v1-20261003T044111Z/plan.md), except for the following explicit corrections. The v1 private run and failure event remain untouched.

- Protocol is `illinois-ptax203-additional-pins-v2` and create-only private run is `ptax-additional-v2-130b5169ff81ccbc`.
- The official metadata response SHA-256 `25a80a2c9274813cfda7d84ad717562765743fae7a9e33aced92edd7daa829cd` **omits** `rowIdentifierColumnId`; it does not contain an explicit null. Require the property to remain absent in both v2 metadata snapshots. No unique row identifier is declared.
- Compare the five field names, numeric column IDs and data types between initial and final metadata. The observed mapping is `declaration_id` 610418722 text, `pin` 610418723 text, `lot_size_or_acreage` 610418724 text, `lot_size_units` 610418725 text and `split_parcel` 610418727 text. Require this mapping in both snapshots. The version markers remain `rowsUpdatedAt=1790506807` and `viewLastModified=1789611867`.
- Derive the exact same 80 declaration IDs only from the previously verified Cook/PTAX private bytes. Retain eight batches of ten, count/row pairs, two metadata requests, 18 GET maximum, the same caps, no retries/redirects/proxies/credentials, and a private create-only artifact set. No v1 run reuse is allowed.
- A successful v2 capture still publishes only the v1 plan's fixed safe aggregate and certifies zero sale labels. A failure leaves an incomplete private run and no valid aggregate. An offline Cook-PIN comparison requires another frozen version and cannot be folded into this capture.

Test the corrected absence contract, metadata drift, duplicate/nonfinite JSON rejection, no-proxy transport, private replay and output allowlist on synthetic data before v2's first request. Review, full suite and security checks precede the one-shot v2 capture.
