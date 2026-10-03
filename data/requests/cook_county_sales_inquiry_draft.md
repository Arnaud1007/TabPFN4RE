# Cook County parcel sales and characteristics: inquiry draft (unsent)

To: assessor.data@cookcountyil.gov
Subject: Clarification of Parcel Sales dates, transfer scope, publication history and reuse

Hello Cook County Assessor Data Department,

I am evaluating the public Parcel Sales (`wvhk-k5uv`) and Single and Multi-Family Improvement Characteristics (`x54s-btds`) datasets for a research project on historical residential sale-price prediction. I have captured a small private audit sample, but have not admitted any records as verified model labels. Could you clarify these points or direct me to the relevant documentation?

1. The Parcel Sales metadata describes `sale_date` as the date recorded, rather than executed. Is a contract, closing, execution or conveyance date available through an official source that can be linked by document number and PIN? How are `is_mydec_date` replacements defined?
2. Is there a dated archive or change log that shows when each sale row and each characteristic value first became publicly available, including late additions and corrections? Can older portal extracts be obtained with reliable publication dates?
3. The dataset description's 2023 update says deed, price and recency filters were removed, while a later note says the sales remain filtered. Which rule applies to the current extract, and how do the `sale_filter_*` flags relate to source rows?
4. For `is_multisale = TRUE`, is the full `sale_price` repeated on every parcel row? What identifies one economic transfer, and when, if ever, is consideration allocated to a dwelling? Is `doc_no` unique for non-multisales across all vintages?
5. What are the meanings and correction histories of `sale_type`, `deed_type`, `mydec_deed_type` and any arm's-length flags? Are concessions recorded separately from gross consideration?
6. In the characteristics dataset, does a historical `year` row contain values as published in that tax year, or can it reflect later corrections? Is a publication date available for each PIN/year/card version?
7. Please clarify any dataset-specific conditions for private internal AVM research, subsequent commercial prediction use, and publication of aggregate findings or derived model outputs. I do not plan to redistribute raw rows, names or images.

Thank you for any guidance. A link to an existing technical note or the right custodian would be helpful.

Arnaud

---

Status: **unsent**. This draft is a local project artifact. No external message has been dispatched.
