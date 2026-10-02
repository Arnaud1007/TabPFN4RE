# Draft: NYC DOF rolling-sales source clarification

Status: local draft, not sent. Prepared 2026-09-29; refined 2026-10-03. No response or dataset
permission is implied. Proposed route: the [NYC Open Data contact form](https://www.nyc.gov/opendata/contact-us),
which accepts questions about an existing dataset. Ask the Open Data team to
route technical and use-rights questions to the Department of Finance data
owner as needed.

Dataset: [NYC Citywide Rolling Calendar Sales (`usep-8jbt`)](https://data.cityofnewyork.us/City-Government/NYC-Citywide-Rolling-Calendar-Sales/usep-8jbt)
and the [DOF borough workbook exports](https://www.nyc.gov/site/finance/property/property-rolling-sales-data.page).

## Ready-to-send text

Subject: Rolling Sales data definitions, historical publication, and permitted use

Hello NYC Open Data team,

I am evaluating the Department of Finance Rolling Sales files for a research
project that may later support a commercial residential sale-price prediction
service. Could you please clarify these points or route them to the DOF data
owner?

1. Do rolling-file `SALE DATE` and `SALE PRICE` map directly to items 11
   (Date of Sale / Transfer) and 12 (Full Sale Price) of the NYC RP-5217
   transfer report? If not, what source and event define each column? Does
   either mapping vary by borough, property class, co-op transaction or
   release? In particular, is `SALE DATE` contract signing, closing/title
   conveyance, deed execution, City Register recording, or another date?
2. Is each row's first public availability timestamp retained? Are dated
   row-level releases, publication logs and correction/deletion histories
   available for the rolling file? If so, what is the supported access route?
3. How do rows map to economic transfers and dwellings? In particular, can
   one deed's full `SALE PRICE` appear on several tax lots or units, and
   which published fields identify those cases or a correction? How are
   co-op transfers and multi-parcel or partial-interest transactions sourced?
4. Are the current borough XLSX files and `usep-8jbt` API generated from the
   same underlying release? What publication lag or revision differences
   should be expected when matching rows?
5. Do any DOF-specific terms govern using these records to train and serve a
   commercial automated valuation model, retaining derived features/model
   weights, or showing individual comparable-sale records to users? Please
   identify attribution, redistribution or fee conditions if they apply.
6. For characteristics such as `BUILDING CLASS AT PRESENT`, `GROSS SQUARE
   FEET` and `YEAR BUILT`, are dated historical values, correction histories
   or first publication dates available? Does an older transaction row retain
   values as known then, or can later property updates change those fields?

I can provide the exact retrieval timestamps and a few record examples
through an appropriate channel. A data dictionary or contact for the
responsible data owner would also help.

Thank you.

## Internal reason for the request

The project has preserved a private current CSV snapshot and five current
borough XLSX byte streams. These do not establish first publication, true
closing date, individual-home consideration, historic feature availability or
use-specific rights. No NYC sale row is yet certified for model training.
