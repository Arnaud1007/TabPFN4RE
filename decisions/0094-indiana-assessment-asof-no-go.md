# ADR 0094: Do not promote Indiana disclosure assessments to a 90-day model

Date: 2026-10-05. Owner: Arnaud. Status: adopted for the current source
snapshot. Affected protocol: `indiana_sdf_snapshot_assessment_retrospective_diagnostic_v1`.

## Evidence

The pinned 2025 disclosure archive is a later, revisable source snapshot.
[STATS Indiana](https://www.stats.indiana.edu/about/sdf.asp) says county
assessors can correct historical submissions. The [DLGF form
instructions](https://www.in.gov/dlgf/files/Sales-Disclosure-Form-Instructions.pdf)
describe `P2_2_AV_Land` and `P2_3_AV_Improvement` as the assessor's most
recent values when processing the sale form. No evidence currently dates
those exact values before an origin 90 days before the sale. The available
Marion 2023-assessment PARCEL copy was created on 19 April 2025; its nominal
assessment year does not establish earlier public availability.

The targeted [audit queue](../runs/indiana-assessment-diagnostic-v1/audit_sample_manifest.json)
selected 200 eligible 2025 sales without using model errors. The first
[private-ledger review](../runs/indiana-assessment-diagnostic-v1/audit_review_first20.json)
inspected 20 deliberately extreme low-price records: ten assessor notes
indicate nonmarket consideration or invalidity, and ten remain unresolved
despite very low stated prices. Ten of these 20 were marked valid for
trending. None has an independent conveyance cross-check or a confirmed
arm's-length eligibility decision. This edge-enriched review cannot estimate
the defect rate of the full cohort. The remaining 180 selected records are
unreviewed, and the broader US07 source audit remains incomplete.

## Decision

Keep the 15.19% MdAPE assessment result as a **retrospective development
diagnostic** on its unchanged 71,054-row denominator. Do not serve it as a
current valuation, train a certified 90-day OFF model with these assessment
fields, or count it toward G-US. `P2_16_Valid_Trending` remains a post-sale
review field, never a predictor or a filter applied to the published score.

Reconsider only after obtaining a source snapshot or publisher evidence that
dates each assessment input before the chosen origin, plus a broader audited
label cohort. Any changed eligibility rule or model needs a new data version
and an untouched later evaluation period.

## Alternatives rejected

- Removing flagged or low-price 2025 rows after observing errors would change
  the existing score's denominator and would not establish eligibility.
- Treating an assessment-year label or later downloaded value as its
  first-availability date would create a false historical feature.
- More model tuning on the same consumed 2025 cohort would not resolve either
  the availability or label problem.

The saved King County command remains the runnable historical research
predictor while a better-dated source is qualified.
