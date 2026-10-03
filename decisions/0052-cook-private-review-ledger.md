# ADR 0052: private Cook County source-review ledger

Date: 2026-10-03

Owner: project implementation

Affected requirements: US02, US05, US07, US08, US22, US23 and US24

Protocol: `cook-source-review-v1`

Status: implementation decision; acceptance requires executable evidence

## Context and alternatives

[ADR 0051](0051-cook-sales-private-audit-sample.md) froze a private,
200-row, stratified Parcel Sales capture. Its verified manifest SHA-256 is
`130b5169ff81ccbc0a729cba98400f2fb377ff9a25999316aaac1960e38a3cf7`.
The sample manifest contains ordered row identifiers, and its 20 row-page
responses contain the selected values. These are source observations, not
verified dwelling transfers. The current public aggregate records zero manual
rubrics and zero certified sale labels.

Editing the capture to add review notes would change its identity. A public
spreadsheet would expose PINs, prices and document numbers. Reusing the HCPA or
NYC ledger unchanged would also import source-specific identity and evidence
rules. Keep the capture immutable and add a Cook-specific, private review
history using the established local file controls.

## Frozen inputs and storage

The v1 tool runs offline against exactly the pinned capture. It first replays
the capture verifier, checks the manifest hash and reconstructs 1-based
ordinals in the order of `sample_row_ids`. The ordinal, the capture hash and a
canonical hash of the selected row bind every review entry. Duplicate or
reordered row identifiers fail before initialization or append.
The official capture metadata is pinned separately at SHA-256
`c967e289fdd1a45319b1efdedf38276c670b1cdb0e11e5466e95e31731119dce`;
a review citing the published sale-price field label and description must reference
those captured bytes, not an arbitrary HTTPS page.

Initialize a new `data/raw/cook_county/manual-review-v1/` directory containing
a private worklist, an empty JSONL review ledger and a manifest with a unique
ledger ID. The worklist carries the selected source values and audit-priority
flags; its hash is fixed in the review manifest. This directory and all review
entries remain Git-ignored. The directory must have a verified restricted ACL
on Windows or owner-only permissions elsewhere. Existing or incomplete
initialization is preserved for inspection, never overwritten or inferred to
be an empty ledger.

Append under an exclusive lock and an expected prior-ledger SHA-256. Validate
the entire prior history, unique entry IDs, contiguous per-ordinal revisions
and exact supersession links. Write a complete new ledger image with fsync and
atomic same-directory replacement. A crash or truncated history is an error;
the `summary` action can replay a successful append whose output was lost.
Static symlinks, junction redirection and hard-linked private files are
rejected. As with the shared private-file helper, trusted same-privilege local
processes are assumed; a malicious concurrent directory swap is outside this
tool's protection.

## Evidence and rubric boundary

Each private entry has a reviewer code, UTC review time, status (`partial` or
`complete`), attestation, evidence observations, and dimension findings.
Evidence IDs are unique. An `unknown` finding cites checked evidence and
states the concrete limitation. Evidence observation and attempted-access
times cannot follow the review time. The reviewed time and pinned-row
observation cannot predate the captured run's completion, and the reviewed
time cannot predate the private review ledger's creation. A missing or
unstructured Clerk access attempt cannot count as a completed rubric.

The sole affirmative v1 rubric finding is the **published-row price state**:
positive, zero or invalid, checked against the pinned raw field and cited with
the source row and official field label/description. It says nothing about gross
dwelling consideration, arm's-length sale or eligibility. All identity,
property/unit, economic-transfer, repeated-consideration, recorded-versus-
closing, first-publication, characteristic-vintage, arm's-length, correction
and evidence-quality findings remain `unknown` in v1. A generic URL or a
self-declared `recorded_instrument` evidence kind cannot turn those into
affirmative findings. Later source-artifact verification and semantic
comparisons require a separately versioned protocol, following the
[NYC evidence boundary](0027-nyc-ledger-evidence-boundary.md).

`complete` measures reviewer-attested effort: a full rubric, pinned source
observation, official field-label/description check, and a structured, relevant
unavailable-access attempt for a recorded instrument. A self-declared
instrument URL does not qualify in v1; a locally verified instrument-artifact
route requires a versioned extension. An unknown answer may remain
after a complete review. Neither `complete` nor any source flag certifies a
sale label, historical feature, 90-day origin, data right or released model.
The verified capture's `is_multisale` and repeated document numbers set review
priority only; they do not prove the economic transfer count.

## Public output and acceptance

Only the 200 denominator, reviewed/partial/complete/untouched counts, hashes,
fixed protocol identity and zero certified-label status may enter a public
summary. No row identifier, ordinal, PIN, document number, price, finding,
reviewer code, evidence URL or free-text note may be logged or committed.
Small interim finding cells are suppressed entirely. A later full audit may
publish sufficiently supported aggregates under a separate disclosure rule.

Write synthetic RED tests before the ledger implementation. The gate includes
capture provenance and completion time, wrong order and ordinal, false affirmative findings,
incomplete attestation, unstructured attempts, compare-and-swap, revisions,
truncated history, ACL and path controls, public-output privacy, replay,
branch-aware coverage, the full test suite, lint and dependency checks. Push
reviewed code before initializing the real ledger. The first real run may
create the private worklist and record a partial review, but it must retain
zero certified labels and U0/G-US pending. The 200 manual rubrics, independent
instrument checks, closing and availability evidence and source rights are
still required for a later qualification decision.
