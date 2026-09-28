# Draft: HCPA All Sales source clarification

Status: local draft; not sent. Prepared 2026-09-28. Sending an external request
requires the project owner's explicit authorisation.

Proposed recipient: the HCPA records custodian listed in the
[official custodian notice](https://www.hcpafl.org/Portals/HCPAFL/pdfs/RecordsCustodianforHCPA.pdf).

## Proposed message

Subject: All Sales data definitions, historical releases, and permitted use

Hello,

I am assessing whether the Hillsborough County Property Appraiser's public
All Sales files can support a research and potentially commercial residential
sale-price prediction system. Could you please clarify the following or direct
me to the responsible data and permissions staff?

1. What event does `S_DATE` represent in the All Sales DBF: contractual closing,
   deed execution, Clerk recording, an assessor-entered effective date, or
   another event? Is that meaning consistent across historical releases?
2. Is the date when an individual sale first entered the public All Sales file
   recorded anywhere? Are prior dated ZIP releases, publication logs, correction
   histories, or data dictionaries available, and how can they be requested?
3. Does one All Sales row always represent the entire consideration for one
   parcel, or can a multi-parcel deed repeat the full consideration on each
   parcel? Which fields or rules identify those cases and later corrections?
4. What permissions or agreement govern use of the All Sales data to train and
   serve a commercial automated valuation model? Please distinguish use of
   raw records, derived features or model weights, and display of individual
   comparable-sale records to users. Are there fees or attribution conditions?

I can supply the exact public archive name and a small number of record
examples through a suitable channel if they would help resolve the field
definitions. I would appreciate any current data dictionary, release schedule,
and applicable use terms.

Thank you.

## Local evidence behind the questions

- [HCPA public downloads](https://downloads.hcpafl.org/Default.aspx) list a
  dated All Sales ZIP; the embedded `allsales.doc` describes `S_DATE` only as
  the date of sale and warns that entry can lag Clerk receipt and review.
- [HCPA terms](https://www.hcpafl.org/Terms) reserve ungranted rights and do
  not state a dataset-specific commercial AVM permission.
- [HCPA Maps & Data](https://www.hcpafl.org/Downloads/Maps-Data) lists paid
  data request products, but does not establish historical All Sales vintages.
- The local U0 audit currently treats these questions as unresolved and does
  not train a releasable model on this source.
