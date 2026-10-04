# HCPA download listing observation

Date: 2026-10-04. Status: **observed, not source-qualified**. Requirements:
US05 and US08. U0 and G-US remain **PENDING**.

A direct read-only GET of the [official HCPA public downloads page](https://downloads.hcpafl.org/Default.aspx)
saved 24,064 HTML bytes at the Git-ignored path in
[observation.json](observation.json). Its SHA-256 matched the observation
record. At local capture time 19:44:12 UTC, the page listed
`allsales_09_18_2026.zip` (68 MB; displayed update September 18) and
`parcels_10_02_2026.zip` (148 MB; displayed update October 2).

The All Sales **filename** matches the September 28 source card. Its bytes
were not re-downloaded, so this observation does not establish byte identity
or an official publication timestamp. The parcel listing changed from the
September 25, 2026 parcel archive previously inspected; it does not establish
an attribute vintage for any historical sale. The raw HTML remains private
and unchanged.

The official Clerk [daily index directory](https://publicrec.hillsclerk.com/OfficialRecords/DailyIndexes/)
listed its `readme.txt`, but a read-only web fetch and a separate 20-second
local GET both timed out on 2026-10-04. No readme or D-file layout was admitted
as an adapter contract. The local GET raised a timeout and wrote no file; the
earlier PowerShell diagnostic command printed a misleading empty byte/hash
line after its nonterminating error. This report records the fetch as **failed**.

Observed command for the successful capture, from the repository root:

```powershell
$ErrorActionPreference = 'Stop'
Invoke-WebRequest -Uri 'https://downloads.hcpafl.org/Default.aspx' -OutFile 'data/raw/hcpa/downloads_page_20261004.html' -TimeoutSec 20
Get-FileHash -Algorithm SHA256 -LiteralPath 'data/raw/hcpa/downloads_page_20261004.html'
```

Verification read the saved HTML and found one listed All Sales file and one
listed parcel ZIP matching the names in the observation record. No model was
trained, no new HCPA transaction label was certified, and no page listing was
treated as an individual record's `available_at` date.

Next, retain repeated dated observations to bound prospective publication
changes. Source qualification still needs the custodian's `S_DATE`, first
publication, repeated-consideration and permitted-use answers, plus the
manual transaction audit. The prepared
[inquiry](../../data/requests/hcpa_all_sales_inquiry_draft.md) remains an
owner handoff with delivery unverified.
