# ADR 0016: HCPA current parcel linkage check

Date: 2026-09-28

Owner: project implementation

Affected requirements: US05, US06, US07 and US24

## Evidence and question

The frozen 200-record All Sales sample is pinned to SHA-256
`2f26728c37f8218d1bb79ee75e4082fb918665eb2cb4cc287feba7f6250aaec9`.
The 2026-09-25 current parcel ZIP is pinned to SHA-256
`968901f963b6424d89ecba757d8c9d6e1117acb3e2228a0d9885461da9c2e3c8`.
The prior code-table audit inspected only its `parcel_dor_names.dbf`. The
current `parcel.dbf` header advertises 531,612 rows in an 894,705,078-byte
member, with `PIN` C(25), `FOLIO` C(20), `DOR_C` C(16), `tUNITS`, `tBLDGS`,
`HEAT_AR` and up to three recent sale references. All Sales uses `PIN` C(29)
and `FOLIO` C(10). The widths are a reason to inspect exact trimmed values,
not a reason to cast identifiers to numbers or assume stable historical
identity. No parcel rows have been accepted into the project schema.

The question is whether the sampled sale entries can be linked to a unique
*current* parcel record and what identity or physical-scope questions that
link raises for manual review. This is an audit of join mechanics, not a
historical feature assembly or an eligibility decision.

## Fixed protocol before viewing matches

Read only the required DBF fields from the pinned ZIP. Keep raw identifiers
private. Trim surrounding DBF padding; preserve leading zeros and do not
guess a replacement `PIN` or `FOLIO`. Treat the source's `CONFID` folio
redaction marker as unavailable. Require both nonblank identifiers to
agree for a high-confidence current-parcel candidate. A one-key candidate is
an identity lead, not an accepted join. Label it a one-key lead when only one
identifier finds a candidate. Reserve identifier conflict for evidence that
PIN and FOLIO point to different candidates, or that an exact pair has
additional contradictory candidates. Track zero, one and multiple exact
matches; retain conflicts and duplicate keys as ambiguity. Do not select
whichever candidate looks most like the expected property.

On uniquely matched sample entries, compare raw All Sales `DOR_CODE` with
current parcel `DOR_C`. Count agreement, disagreement and missing codes
separately. Summarise `tUNITS` and `tBLDGS` as count clues, retaining unknown
and invalid values separately from zero. Classify `HEAT_AR` as zero,
positive, unknown or invalid area; a positive fraction is valid area. Compare
available `SALE1/2/3_DOC` references with the sample's `DOC_NUM` only as a
document-link lead; missing or all-blank source references produce unknown,
not a proven nonmatch. A match does not resolve price or date meaning. Report
all quantities for the full
edge-enriched sample and separately for the 36 rows previously flagged in
repeated instrument-number groups. These are sample counts, not population
prevalence estimates.

The matching rule and 200-record sample were fixed before the scan. After
the first aggregate scan, Python review found that a one-key lead was labelled
as a conflict and that area and blank sale-reference categories could be
misleading. The category definitions above were corrected before the tracked
run was frozen. The zero exact-match result and all source rows remain
unchanged. The rejected aggregate is retained in the tracked run for
traceability; preliminary row-level flags remain under ignored raw storage.

Use synthetic fixtures before reading the real archive to test missing IDs,
duplicate parcel keys, conflicting one-key candidates, invalid DBF structure,
and output containment. The source ZIP and sample checksums must match before
any result is accepted. Refuse silent row duplication or an unexplained DBF
row-count mismatch. Keep row-level matches, source prices, addresses and
identifiers only under Git-ignored `data/raw/hcpa/`; the tracked run contains
aggregate counts, source hashes, commands, test results and limitations.

## Alternatives and decision

Joining on one identifier would cover more rows but can silently choose a
wrong parcel when identifiers are absent or reused. Joining on an address
would add unstable unit and formatting assumptions. The two-key conservative
join is chosen for this source-quality audit; incomplete keys remain visible
for manual investigation. No low-match-rate threshold is defined as proof of
source failure, because the current parcel stock may omit or revise properties
from older sales.

This 2026 file cannot certify the parcel state, field value or public
availability at an earlier valuation origin. It cannot prove one dwelling per
parcel, one economic transfer per DBF row, a true closing date, arm's-length
consideration, or product reuse rights. Any historical model requires dated
vintages and source-specific permission. The 200-record manual review remains
the downstream decision step.
