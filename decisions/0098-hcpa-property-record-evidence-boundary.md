# ADR 0098: HCPA property-record evidence boundary

Date: 2026-10-05  
Status: accepted for source audit only

## Decision

Recognize an exact official HCPA parcel-result URL as
`hcpa_property_record` evidence. The validator requires HTTPS, the exact
`gis.hcpafl.org` host, the `/PropertySearch/` path, no credentials, port or
query, and a parcel-result fragment.

This evidence may support only facts displayed directly on that page:
transaction-row identity within HCPA, parcel/unit identity, property class and
the displayed qualified/unqualified classification. It cannot establish deed
execution, recording or closing dates; consideration scope; multi-parcel
allocation; reason-code meaning; or reuse rights.

## Reason

The official page supplies useful corroboration that the frozen source row is
attached to the expected parcel and residential class. Rejecting that evidence
would discard a concrete source-quality check. Treating it as a deed, closing
record or rights document would overstate what the page proves.

## Consequence

One additional sampled row has a complete attested rubric, while its critical
target-semantics findings remain unknown. HCPA stays excluded from certified
90-day training until the shared date, consideration and rights questions are
resolved.
