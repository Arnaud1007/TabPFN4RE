# Douglas County Assessor source inquiry (unsent)

To: assessors@douglas.co.us
Subject: Property Sales download: price/date definitions, historical versions and permitted use

Hello Douglas County Assessor team,

I am evaluating your [Property Sales and Property Improvements downloads](https://www.douglasco.gov/assessor/data-downloads/) for residential sale-price research that may later support a commercial prediction service. I have checked the public file descriptions but have not downloaded property records. Could you help clarify the following, or direct me to the data custodian?

1. Do the [County Open Data Guidelines](https://www.douglasco.gov/documents/open-data-guidelines.pdf/) apply to these direct Assessor text downloads? May a minimized extract excluding `Grantor`, `Grantee`, owner names and addresses be used for internal model research, later commercial predictions, and publication of aggregate results without redistributing raw rows? Is a separate agreement needed?
2. The published [TD-1000 transfer declaration](https://www.douglasco.gov/documents/transfer-declaration-form_-rev-10-18.pdf/) asks separately for closing and contract dates, total price including personal property, and contracted price when different; it also states the completed declaration is confidential. Which event, if any, supplies the public download's `Sale_Date`? Does `Sale_Price` retain gross total consideration, exclude personal property, use an assessor adjustment, or follow another rule? The [mass-appraisal description](https://www.douglasco.gov/assessor/mass-appraisal/) describes screening and adjustments for assessment; do those affect the downloadable field? Please describe concessions, nominal or non-arm's-length deeds, and later price corrections without disclosing any confidential declaration.
3. Can one `Recording_No` or deed appear on several `Account_No` rows? If a transfer covers several parcels or dwellings, does each row repeat the whole consideration? Is there a documented key for one economic transfer and a way to distinguish a single dwelling from a package sale?
4. Are dated historical copies, change logs or record-level first-publication times available for sales and improvement attributes? When do new sales first appear in the download, and do corrections replace prior values? Since the public page says "active accounts only," are records removed when accounts become inactive or are renumbered?
5. How should `Account_No` and `Building_ID` be joined when one account has multiple improvements? What does `Built_as_SF` measure, and can building area, condition and remodel information be recovered as they were known at a past valuation date?
6. Is there a data dictionary for `Deed_Type`, property class and the relevant flags, plus a documented refresh schedule? If the needed historical extract requires a paid custom report, please describe the scope and quote separately; this email does not authorize a purchase.

Links or written definitions are especially useful because the project needs to audit records as they were available before a sale, not merely read today's database snapshot. I would not use party identities as model inputs.

Thank you,

Arnaud

---

Status: **unsent draft**. Contact address is printed in the Assessor's [2026 official form](https://www.douglasco.gov/documents/senior-exemption-long-form-instructions.pdf/); the [current contact page](https://www.douglasco.gov/assessor/contact-us/) also offers the Assessor contact route. No external message or paid request was made.
