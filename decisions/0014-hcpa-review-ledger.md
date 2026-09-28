# ADR 0014: Private HCPA source-review ledger

Date: 2026-09-28

Owner: project implementation

Affected protocol: `hcpa-audit-v1` sample selection; new `hcpa-review-v1` review ledger

Affected requirements: US02, US05, US07, US22, US23, US24

## Alternatives and evidence

The frozen 200-record HCPA sample in ADR 0013 has property and instrument
identifiers. Editing its `manual_review` placeholders would change its SHA-256
and make the selection artifact difficult to replay. A public spreadsheet would
expose row-level details and could lose rejected or corrected findings.

The first official Clerk index comparison in
[`runs/u0-hcpa-clerk-spotcheck-20260928T171047Z/`](../runs/u0-hcpa-clerk-spotcheck-20260928T171047Z/report.md)
matched an instrument and numeric amount but did not verify the unit, close
date, consideration scope or use rights. It is a partial review, not a completed
rubric or model label.

## Decision

Keep the sample unchanged. Store each source-review revision in a JSONL ledger
under Git-ignored `data/raw/hcpa/`, tied to the exact sample hash and ordinal.
Each entry includes dated evidence references, explicit findings and unknown
states, a reviewer code, and a revision link. Corrections add a new entry;
the latest entry for an ordinal determines the current review status.

`scripts/review_hcpa_sample.py` validates entries and produces only aggregate
counts and hashes in tracked `runs/`. It writes a complete new ledger image to
a same-directory temporary file, syncs it, then atomically replaces the prior
image. Exact-entry CLI retries can recover a missing aggregate summary after
the ledger commit; a changed duplicate is rejected. A crash-truncated or
invalid ledger is never silently repaired. A stale lock needs verified manual
recovery using its recorded PID, host and creation time.

`complete_records` means **reviewer-attested rubric completion**. Unknown
answers are permitted when the checked evidence cannot resolve a fact. This
count does not independently verify source truth, data rights, label
eligibility or historical availability. A partial entry cannot increment it.

## Threat and access boundary

The script rejects static symlinks, junction redirection and hard-linked
private files. It assumes trusted local processes control `data/raw/hcpa/`
while it runs; same-privilege concurrent directory swaps are outside this
local audit tool's protection. Keep row-level files out of Git and restrict
workspace access accordingly. No external records request or paid access is
performed by this decision.

## Acceptance and current outcome

The [ledger run](../runs/u0-hcpa-review-ledger-20260928T174512Z/report.md)
records 29 focused tests, a full engineering suite with zero skips, lint,
format, dependency audit, private-path checks, a one-entry partial review and
byte-identical summary replay. The one review does not complete the 200-record
manual audit. HCPA `S_DATE`, historical publication, transaction scope and
reuse rights remain unresolved.
