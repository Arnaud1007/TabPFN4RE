# Draft: HCPA All Sales source clarification

Status: ready-to-import local draft; not sent. Prepared 2026-09-28 and recipient
revalidated 2026-10-06. The project owner approved sending it, then chose a
ready-to-send email handoff because no authenticated mail account or mail
window is available in this workspace. Delivery by the owner is unverified.
The `.eml` intentionally omits `From` and `Reply-To`; the sending mail client
must populate them from the owner's authenticated account before delivery.

To: martinezm@hcpafl.org. The current
[official records-custodian notice](https://www.hcpafl.org/Portals/HCPAFL/RecordsCustodianforHCPA_Marilyn.pdf?ver=2023-04-29-105106-420)
names Marilyn Martinez and directs HCPA records requests to this address. The
[official directors page](https://www.hcpafl.org/Links/HCPA-Directors) lists
her as Director of Administrative Services and Records Custodian. The
[official feedback page](https://hcpafl.org/Contact-Us/Email-Us-Feedback)
lists `custserv@hcpafl.org` for general questions, concerns or comments; it is
retained as a fallback and is not the addressee of this records inquiry.

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
4. The general disclaimer in the root `_Documentation.doc` says users may
   redistribute "this data," modified or unmodified, if all HCPA references
   are removed from the final product. Does that permission cover the
   standalone All Sales ZIP as well as the parcel layer, and does it cover
   training and serving a commercial automated valuation model? Please
   distinguish raw records, derived features or model weights, and display of
   individual comparable-sale records. Are there additional fees or conditions?

I can supply the exact public archive name and a small number of record
examples through a suitable channel if they would help resolve the field
definitions. I would appreciate any current data dictionary, release schedule,
and applicable use terms.

Thank you.

## Local evidence behind the questions

- [HCPA public downloads](https://downloads.hcpafl.org/Default.aspx) list a
  dated All Sales ZIP; the embedded `allsales.doc` describes `S_DATE` only as
  the date of sale and warns that entry can lag Clerk receipt and review.
- The root `_Documentation.doc`, captured and hashed on 5 October 2026,
  contains a redistribution permission with an HCPA-reference-removal
  condition and independently describes Clerk receipt followed by HCPA
  review. It does not expressly define the permission's scope for the
  standalone All Sales ZIP or commercial model use.
- [HCPA terms](https://www.hcpafl.org/Terms) reserve ungranted rights and do
  not state a dataset-specific commercial AVM permission.
- [HCPA Maps & Data](https://www.hcpafl.org/Downloads/Maps-Data) lists paid
  data request products, but does not establish historical All Sales vintages.
- The local U0 audit currently treats these questions as unresolved and does
  not train a releasable model on this source.

## Recipient provenance

The recipient was revalidated against the three official HCPA sources above
on 6 October 2026. The earlier `shepherdw@hcpafl.org` recipient is superseded
and must not be used for this draft. The matching plain-text email artifact is
`data/requests/hcpa_all_sales_inquiry.eml`. No authenticated mail surface was
available, so neither draft was sent.
