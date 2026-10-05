# U0 HCPA frozen-sample review progress, 5 October 2026

Status: **one complete rubric with nine unknown findings; source admission and G-US PENDING**.
Requirements: US02, US05, US07, US24. The frozen 200-row sample and its
original SHA-256 remain unchanged.

## Reviewed evidence and actual result

I revisited the one sample row that already had a [partial HCPA–Clerk index
comparison](../u0-hcpa-clerk-spotcheck-20260928T171047Z/report.md). A fresh
read-only local check matched every retained HCPA field back to the frozen
sample, matched the instrument number and decimal sale amount to the saved
Clerk observation, confirmed the HCPA `S_DATE` precedes the Clerk recording
date, and confirmed that the displayed legal description identifies a
condominium. This is outside the initial single-family product cohort. No
private document number, price, parcel, address or row ordinal is published.

The private review ledger, governed by the [ledger protocol](../../decisions/0014-hcpa-review-ledger.md), now
contains a superseding reviewer-attested entry covering all 14 rubric
dimensions. Nine conclusions are **unknown**: deed execution and closing
dates, unit linkage, one-property price scope, multi-parcel consideration,
duplicate status, qualification and reason-code corroboration, and reuse
rights. The checked sample and index lack critical closing, unit and scope
evidence; evidence quality is low. “Complete” means that the rubric was
answered, **not** that this record is a valid arm's-length label.

The [aggregate summary](summary.json) reports 1 complete review, 0 partial
reviews and 199 untouched sampled rows. The private entry SHA-256 is
`486d8ad115d29f73d9ff46d35c18e7bcffe6904387ccf97c8cf261cad9adf623`;
the new ledger SHA-256 is
`ff7a5495e78e23a6d4b95f2da55aa730de802b8f42401a6c692d9d6b30b21577`.
The [summary replay](summary_replay.json) is byte-identical. No label or
attribute entered a modelling layer.

## Access and security boundary

The [Clerk's official daily index](https://publicrec.hillsclerk.com/OfficialRecords/DailyIndexes/)
is available through a browser-backed read route but currently covers only
one row of the frozen sample, the row reviewed here. The Clerk's
[historical public search](https://publicaccess.hillsclerk.com/oripublicaccess/)
returned no extractable lines through web retrieval; a bounded direct GET
timed out after eight seconds, and this session had no browser surface.
These are access-route observations, not proof that older instruments do not
exist. No deed image or independent closing record was inspected.

Before adding the private revision, I found that `data/raw/hcpa` inherited
broad workspace permissions. I restricted that directory to the current user,
System and Administrators with the existing local ACL helper, verified the
directory policy, and checked that the frozen sample now inherits those
restricted entries. No source file was removed or changed.

The parent directories retain broader workspace permissions, including
delete-child rights. The private-file ACL check does not remove that residual
local-process risk; the ledger protocol assumes trusted local processes.

The focused review tests passed with 29 tests and 28 subtests. The project venv
has no pytest installation. A first attempt with system pytest also failed
before collection because an unrelated global PostgreSQL plugin could not load
`libpq`; disabling plugin autoload let the focused suite run. The full suite
was not rerun for this source-record-only checkpoint. JSON/YAML parsing, the
three private hashes, byte-identical aggregate replay and `git diff --check`
passed.

## Gate and next action

This review does not qualify `S_DATE`, per-record publication time,
one-dwelling consideration or commercial use. The 200-record source audit
remains 199 records short. Seek an authorised historical Clerk index or deed
route and the HCPA custodian's answers from the prepared inquiry; retain
unknowns until actual evidence arrives. Keep the saved King model available
as historical research. No 90-day HCPA training, model promotion or G-US
claim follows from this one completed rubric.
