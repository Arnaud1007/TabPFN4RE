# U0 Hillsborough All Sales review-sample checkpoint

Run ID: `u0-hcpa-audit-sample-20260928T160539Z`

Requirements: US02, US05, US06, US07, US08
Status: sample selected; **manual source audit pending**; U0 and G-US pending

## Objective and changes

The [frozen protocol](../../decisions/0013-hcpa-manual-audit-sample.md)
defines 20 rows in each of ten sale-date/`QU` cells, including unusual source
records. The [sampler](../../scripts/sample_hcpa_audit.py) streams the pinned
DBF from its unchanged ZIP, validates the source hash and DBF structure, and
keeps at most bounded candidate heaps. It writes only a local Git-ignored
JSONL review file containing source identifiers and codes, with no grantor,
grantee, street or subdivision fields. The tracked
[selection manifest](sample_manifest.json) contains aggregate counts and the
private file's hash. The [run manifest](manifest.json) records the exact
commit, script/environment/protocol hashes, hardware and command.

HCPA's embedded `allsales.doc` defines `S_DATE` only as a date of sale, `QU`
as qualified or unqualified, and `DOC_NUM` as a Clerk instrument number. It
does not prove that `S_DATE` is the close date or when a given transaction
first became available. The [official HCPA download page](https://downloads.hcpafl.org/Default.aspx)
does not establish product redistribution rights. These remain source
qualification blockers, independent of the sample's mechanical integrity.

## Observed output

The command below exited 0 after 23.756 seconds. It selected 200 distinct
DBF record ordinals, 20 per cell. The ten cell populations sum to the
2,453,187 active records in the earlier aggregate profile. The broad `edge`
screen flags 1,666,333 source entries, of which 147 are in the selected
sample. An edge flag is a review priority, **not** a label rejection or an
arm's-length decision.

The private JSONL has 200 lines, 200 unique ordinals, no unexpected fields and
SHA-256 `2f26728c37f8218d1bb79ee75e4082fb918665eb2cb4cc287feba7f6250aaec9`.
Git ignores its path. No row-level identifiers, dates, amounts or reviewer
notes are committed. The independent aggregate integrity check matched the
sample hash and population total. The review slots are blank; **zero source
records have been manually verified**.

```powershell
.\.venv\Scripts\python.exe scripts/sample_hcpa_audit.py `
  data/raw/hcpa/allsales_09_18_2026.zip `
  data/raw/hcpa/audit-sample-20260928-888226e.jsonl `
  runs/u0-hcpa-audit-sample-20260928T160539Z/sample_manifest.json
```

The command is deliberately no-overwrite. To verify this completed selection,
hash the existing private JSONL and compare it with `sample_manifest.json`;
do not rerun into the same path or treat a newly drawn sample as the frozen
one.

## Engineering checks and review

The [gate record](test_gate.json) records 10 synthetic sampler tests, 216 full
engineering tests, Ruff lint and format, the pinned dependency audit, and
aggregate sample validation. All exited 0. Sampler statement coverage is 84%;
core package statement coverage is 91%. Code, Python and security reviewers
raised edge-count and private-path guard findings; both were fixed and all
three re-reviews approved the final sampler before the real archive run.

## Failed attempts and unresolved defects

The test-first RED checkpoints intentionally failed before their implementation.
No real archive sampling command failed. There has been no manual comparison
with the HCPA property record or Clerk instrument yet, so transaction scope,
economic duplicates, property class, `QU` correctness, `S_DATE` semantics and
field accuracy remain unverified. A second authorised publisher is required
for cross-feed duplicate testing. Historical first availability and reuse
permission remain unresolved. None of these entries is eligible for a
certified 90-day as-of training or test cohort.

## Next action

Review the 200 private records under `data/raw/hcpa/` against available
source evidence using the rubric in ADR 0013. Preserve unknown answers and
publish only aggregate findings and a reviewed evidence hash. In parallel,
resolve the meaning of `S_DATE`, obtain a defensible first-availability trail
and determine the source-specific use right before any model ingestion.
