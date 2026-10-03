# New York State Sales Web source inquiry (unsent)

To: ORPTS.Sales@tax.ny.gov
Subject: Sales Web export fields, publication history and research use

Hello ORPTS Data Management Unit,

I am evaluating Sales Web as a source for a historical residential sale-price
prediction research project. I downloaded one bounded 25-row CSV search result
for a private schema audit; none of its records has been used for model training.
Could you point me to the current export dictionary or clarify the following?

1. Does the Municipal Data Portal offer a state or county bulk export or API,
   beyond the observed CSV search-result download? Are there request limits or
   restrictions on automated weekly archival snapshots?
2. Do current export fields retain the meanings in the older SalesWeb data
   dictionary? In particular, what do `sale_dte`, `sale_price`,
   `personal_prop`, contract date, deed-recorded date, arm's-length flags,
   parcel count and condition codes mean in the current export?
   Does the older `1950-01-01` missing-contract-date sentinel still apply,
   and are class-at-sale and last-roll-class fields distinguished?
   The current detail-page help says personal property is included in the sale
   price, while the older dictionary describes a net-of-personal-property
   price. Which interpretation applies to current CSV `sale_price`?
3. The official ORPTS quarterly-report guidance maps its Sale Date to RP-5217
   item 12 and Deed Date to item C2. Do current Sales Web CSV columns use
   those same definitions for every included transfer? How are corrections to
   the transfer date, parcel scope and consideration represented, and can the
   original values be recovered?
4. Is there a reliable record-level first-publication or public-correction
   timestamp? The current detail help describes initial entry or loading by
   New York State; does CSV `load_dt` correspond to that field, and does it
   denote public availability or only an internal database event? Are dated
   historical exports available?
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
