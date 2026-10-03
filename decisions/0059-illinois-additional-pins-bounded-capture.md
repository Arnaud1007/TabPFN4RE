# ADR 0059: bounded Illinois PTAX-203 Additional PIN capture

- Date: 2026-10-03
- Owner: project implementation
- Requirements: US02, US05, US06, US07, US24
- Protocol: `illinois-ptax203-additional-pins-v1`
- Status: approved for bounded private source audit only

## Decision

The [official Additional PINs view](https://data.illinois.gov/Government-and-Public-Employees/PTAX-203-Additional-PINs/ay2h-5hx3) is a candidate source for reviewing parcels attached to already captured PTAX-203 declarations. Its five fields are `declaration_id`, `pin`, `lot_size_or_acreage`, `lot_size_units` and `split_parcel`. The verified metadata identifies the Illinois Department of Revenue as the official publisher and records a Public Domain licence, but declares no unique row key. Its description covers additional properties in declarations with multiple properties. The declaration ID is therefore a foreign key and can occur in several rows.

Capture only rows for the 80 declaration IDs in the frozen PTAX response set. First verify the Cook and PTAX private captures and the offline linkage aggregate; then derive the IDs internally without printing them. Query every ID, including those whose PTAX Line 3 additional-PIN indicator is false or absent. Preserve every returned row and exact duplicate; no unique-PIN, unique-declaration or one-home assertion follows from the response. The five source fields are retained to distinguish source observations and scope flags, not to create model features.

Use a single bounded, read-only capture under an ACL-restricted and Git-ignored directory. Public artifacts may expose only fixed prior input denominators, source/protocol hashes, zero certified labels and pending gates. They may not expose new match buckets, small-cell counts, IDs, PINs, lot sizes, prices, dates or request URLs. No party or address fields exist in the five-field view. A failure leaves an incomplete private run, never a valid aggregate.

## Interpretation boundary

An additional PIN may explain why a Cook PIN differs from the PTAX primary PIN. It does not prove a dwelling-level economic transfer or allocate Line 11 declaration consideration among properties. Missing additional rows do not prove a single parcel. [IDOR instructions](https://tax.illinois.gov/localgovernments/property/general-information/ptax-203_instructions.html) allow part-parcel `PT` and ROW-only cases; these need distinct diagnostic states in a later offline review. `split_parcel` text and lot size are source observations, not certified eligibility or model inputs. View-level update timestamps do not establish when an individual row first became public.

The [frozen capture plan](../runs/u0-illinois-additional-pins-v1-20261003T044111Z/plan.md) fixes exact membership, query batches, size and request caps before any Additional PIN row request. It supersedes no earlier frozen capture or diagnostic. A later comparison with Cook PINs requires a separately registered, conservative format rule and its own versioned output. No sale label, 90-day origin, commercial model route or G-US promotion is authorised by this decision.
