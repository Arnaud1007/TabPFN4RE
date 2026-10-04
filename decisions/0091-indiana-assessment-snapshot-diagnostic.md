# ADR 0091: Fast disclosure-snapshot assessment diagnostic

Date: 2026-10-04
Owner: Arnaud
Status: adopted before this diagnostic run
Protocol: `indiana_sdf_snapshot_assessment_retrospective_diagnostic_v1`

## Decision

Run one additional Indiana development comparison on the **same 65,490
training and 71,054 validation economic sales** as ADR 0090. The 2025 labels
have already been inspected; they are development data for this question, not
an untouched test. Fit the original county, ZIP and acreage XGBoost again and
an otherwise identically configured XGBoost that additionally receives
`SALEPARCEL.P2_2_AV_Land`, `P2_3_AV_Improvement` and county-scoped
`P2_7_Neighborhood_Code`. Keep the county/ZIP median for reference. Both
assessment amounts use whole-dollar format 12.0, `log1p` for modelling and
explicit missing indicators. All category vocabulary fits on 2024 rows only.
Save paired 2025 row-level predictions privately and generate metrics from that
file. Retain positive but extreme consideration amounts in the fixed cohort.

This diagnostic asks whether tax assessment and local neighborhood information
carry useful signal. The values are observed in later retrieved archives and
may include post-sale revisions. It **does not** establish that the fields were
available 90 days before sale or that a current-home predictor may use them. An assessed
value is a property feature in this experiment, never a substitute sale label.
The model cannot be promoted from this run, regardless of its score.

## Source check and rejected shortcut

The official [Gateway download page](https://gateway.ifionline.org/public/download.aspx)
offers county `PARCEL` files. The retrieved property-file documentation says
this public download consists of PARCEL, tax bill, adjustment and personal
property files. The separate `IMPROVE` and `DWELLING` files described in the
[DLGF format specification](https://www.in.gov/dlgf/files/50-IAC-26-File-Formats.pdf)
were not in the Marion 2023 ZIP. That public download therefore does not
currently supply the requested building size, year built or condition.

The Marion 2023 PARCEL ZIP was retrieved privately and checksum pinned as
`b4e32805a21c38fab0bd9b6825946ec1e8d87ce412dbce5ffc27d44fbabd0eae`.
A source-only format check found 343,629 parcel records. Among 19,664 unique
nonempty parcel IDs linked to Marion 2024 sale forms, 18,650 (94.84%) had an
exact 18-digit match in that PARCEL file. These are join-key observations, not
audited home links or permitted historical features. The ZIP header reports
an April 2025 creation date, so this extract cannot certify what was available
at a 2024 prediction origin. The Gateway file is **not used** in this model.

## Stop and follow-up

Stop after the registered paired run and report the result even if the model
is worse. Do not tune further on the same 2025 score while describing it as
independent evidence. A deployable 90-day OFF system still needs verified
historical assessment vintages or other dated property attributes, audited
sale labels, permitted use and a new untouched future cohort. The existing
King 2015 research predictor remains the current runnable example.
