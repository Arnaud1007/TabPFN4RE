# New York State Sales Web UI and CSV concordance

Run ID: `u0-nys-salesweb-ui-csv-concordance-v1-20261003T163610Z`  
Observed: 2026-10-03 UTC  
Status: **current export mapping checked; source admission pending**  
Requirements: US03, US05, US07, US08, US24

## Objective and population

Reopen the official [Sales Web](https://pad.tax.ny.gov/) public search using
Albany County, all municipalities, and sale date 2025-08-01 through 2025-08-01.
Compare its rendered 25-row result table with the already frozen private
25-row, 78-column `SaleswebExtract.csv` from the
[export audit](../u0-nys-salesweb-export-v1-20261003T150117Z/report.md).
The CSV SHA-256 is
`5548b290ac36772070799800dfc7f875bdaf04c1599aaa169562b43ec6f9b355`.
No private property identifier was entered into the portal. The public
result links for four records were opened to compare detail fields. This is
a current-format check, not a random sample or a historical as-of audit.

## Observed comparison

The result view displayed `1 - 25 of 25`. The CSV has 25 rows. For every
rendered row, the following ordered fields were normalized and compared as a
sorted set: SWIS code, property class **on roll**, sale date, displayed sale
price, deed book and deed page. The rendering converted `08/01/2025` to
`2025-08-01` and stripped dollar signs and commas from price. Both sides
produced the same SHA-256:

`cf40e18f96fab9c7af28af359d34dfeac568d63cb7c0f7b4fc997e227a7f726c`

All 25 book/page pairs are distinct in this bounded set. Matching hashes
show exact concordance for those six current-view fields under this
normalization. They do not prove that book/page is a unique economic-transfer
key generally, that the source itself is correct, or that the export is
stable across future revisions.

Four linked detail pages were then checked: an ordinary class-210 transfer,
a zero-price class-230 transfer, a one-dollar class-210 transfer with a
later deed, and a high-value class-414 transfer. For each page, 12 fields
were compared to its CSV row: SWIS code, deed book/page, deed date,
contract date, sale date, price, personal-property amount, parcel count,
class **at sale**, database-load date and last-update date. Date displays
were normalized to ISO dates. The UI leaves a zero sale price blank in its
detail view although the search table displays `$0` and CSV contains `0`;
the detail comparison normalized that blank to the CSV zero. A missing
contract date was blank on both sides. The four normalized detail rows
matched, with SHA-256:

`3d05c28ff76995f4298f9db644ea35ae034ca38953b6f8c613a8d3609f431c1f`

One nominal-price record has a 2025 sale date but a 2026 deed date and
2026 database-load date. This directly demonstrates that the sale-date
field cannot stand in for source availability. The displayed database-load
date has been matched to `load_dt` for these four current rows, but the
portal does not say that it is their first **public** availability.

## Reproduction and limits

The six-field canonical line is
`swis_cd|prop_class_last_roll|sale_dte|sale_price|book|page`; sort 25 lines
lexicographically and SHA-256 their UTF-8 text joined by `\n` with no final
newline. The 12-field detail line uses the CSV fields
`swis_cd|book|page|deed_dte|contract_dt|sale_dte|sale_price|personal_prop|nbr_of_parcels|prop_class_at_sale|load_dt|last_fm_dt`.
For the detail UI comparison only, display blank price on the zero-price
page maps to CSV `0`. The four private deed book/page pairs used for detail
checks remain in the Git-ignored raw CSV; they are not published here.
A future replay must reopen the live
portal, not treat these hashes as an immutable state of the publisher.

The current help text and legacy dictionary still conflict about whether
personal property is included in the exported price. All 25 bounded CSV
rows have zero `personal_prop`, so this check cannot resolve that conflict.
The UI/CSV agreement also does not certify gross consideration, closing
semantics, first publication, corrected history, single-home identity,
reuse rights, or historical attributes. The 200-record stratified audit
has not begun. **Certified sale labels: 0. U0 and G-US: PENDING.** No model
training, calibration, final test or international implementation occurred.

## Verification and next action

The local Python 3.11 project environment recomputed both CSV hashes from
the pinned raw file: 25 six-field rows, 25 distinct book/page pairs, and
four 12-field detail rows matched the UI-side hashes above (exit 0).
The four-page comparison was visually observed in the official browser UI;
this run did not create an automated UI test. The command output contains
only aggregate values and hashes. Python 3.14 parsed the source card and
requirement map and checked five evidence links, the zero-label boundary,
the raw CSV hash and the 25-row comparison hash (exit 0). `git diff --check`
passed and `git check-ignore` confirmed the raw CSV remains ignored (both
exit 0). The project environment's `pip-audit --local --progress-spinner off`
found no known vulnerabilities in auditable packages (exit 0; the local
editable project package was skipped). No model test suite is claimed for
this documentation-only source check.

Obtain publisher confirmation of sale-price basis, the CSV field meanings,
first public availability and permitted reuse. The
[custodian inquiry](../../data/requests/nys_salesweb_inquiry_draft.md)
remains an unsent draft. Then register the 200-record audit under a frozen
protocol; do not promote these 25 rows to training labels.
