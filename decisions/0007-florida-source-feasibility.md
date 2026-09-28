# ADR 0007: Florida statewide source feasibility

Date: 2026-09-28

Owner: project implementation

Affected requirements: US03, US05, US06, US07, US08, US11, G-US

## Evidence

The [Florida Department of Revenue data portal](https://floridarevenue.com/property/Pages/DataPortal_RequestAssessmentRollGISData.aspx) identifies statewide Sale Data File (SDF) and Name Address Legal (NAL) assessment rolls. It posts the current rolls and says prior SDF files from 2009 and NAL preliminary/final rolls from 2002 are available by request. The portal describes a July preliminary, October initial final and later certified final submission cycle, with publication following state review. This may permit reconstruction of historical source vintages, but no files have been requested or ingested here.

The [2026 submission standards](https://floridarevenue.com/property/Documents/2026FINALCompSubmStd.pdf) define SDF sale price from documentary stamps and sale date as the **year and month of deed execution**, not recording. Codes distinguish qualified, disqualified and pending transfers. Standards direct the full transaction price to appear on each parcel in a multi-parcel arm's-length transfer. Some codes flag consideration that differs from the stamps or is allocated from a package. A sale-file row therefore cannot automatically be a single-home gross-consideration label.

Florida includes a possible Census South source and county-level nonmetro candidates, subject to preselection and sample checks. The public-records basis does not by itself settle product redistribution, individual fields' first availability or precise close-date semantics.

## Decision

Prioritise Florida for U0 qualification because it may fill a missing region and nonmetro coverage with statewide official files, qualification codes and requestable historical roll vintages. Keep it documentation-only until a source-specific permitted-use decision. The SDF's month granularity blocks the exact 90-calendar-day pre-close benchmark by itself. A county clerk or other authoritative dated record may supply that missing information; otherwise only a separately named monthly-origin research protocol is possible.

## Next evidence

Determine whether daily deed/close and first-publication evidence can be linked through a county clerk source without fabricating dates. Establish the applicable use terms for the selected counties and files. If authorised, obtain a small historical SDF/NAL sample including at least one prior preliminary/final vintage, hash every original file, audit 200 stratified records, and verify parcel joins, multi-parcel price repetition, qualification flags and area semantics before any model training. External data requests require explicit owner authorisation before sending them.
