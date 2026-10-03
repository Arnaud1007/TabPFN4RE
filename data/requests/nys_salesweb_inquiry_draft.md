# New York State Sales Web source inquiry (unsent)

To: ORPTS.Sales@tax.ny.gov
Subject: Sales Web export fields, publication history and research use

Hello ORPTS Data Management Unit,

I am evaluating Sales Web as a source for a historical residential sale-price
prediction research project. No Sales Web property records have been downloaded
or used for model training. Could you point me to the current export dictionary
or clarify the following?

1. Does the Municipal Data Portal offer a state or county bulk export or API,
   or only Excel downloads of search results? Are there request limits or
   restrictions on automated weekly archival snapshots?
2. Do current export fields retain the meanings in the older SalesWeb data
   dictionary? In particular, what do `sale_date`, `sale_price`,
   `personal_prop`, contract date, deed-recorded date, arm's-length flags,
   parcel count and condition codes mean in the current export?
   Does the older `1950-01-01` missing-contract-date sentinel still apply,
   and are class-at-sale and last-roll-class fields distinguished?
3. Does `sale_date` come directly from RP-5217 item 12 for every included
   transfer? How are corrections to the transfer date and consideration
   represented, and can the original values be recovered?
4. Is there a reliable record-level first-publication or public-correction
   timestamp? Does `load_date` refer to the public Sales Web release, or only
   an internal database? Are dated historical exports available?
5. What are the terms for private internal AVM research, subsequent
   commercial predictions, automated downloads, publication of aggregate
   findings and redistribution of raw rows or derived model outputs? We would
   exclude buyer, seller, attorney and preparer identities from research
   extracts.
6. What stable key identifies one economic transfer when a deed covers
   multiple parcels or municipalities? Are parcel rows repeated in downloads,
   and which fields identify a single existing one-family home at the time of
   sale?

A link to the current documentation or the appropriate custodian would be
very helpful.

Thank you,

Arnaud

---

Status: **unsent**. The official general-sales contact is listed in the
[ORPTS contact guidance](https://www.tax.ny.gov/research/property/assess/sales/tipssalesrpt.htm).
Confirm the sender and signature before delivery. No external message was sent.
