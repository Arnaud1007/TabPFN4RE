# U0 Cook Clerk public-document source audit

Run ID: `u0-cook-clerk-public-docs-v1-20261003T014926Z`  
Baseline code commit: `da87a4d2583d8acf0a5cf09cc9bbeb5f3f9f459a`  
Requirements: US02, US05, US07, US08, US24  
Status: **four official documents captured and replayed; U0 and G-US PENDING**

## Question and method

The [frozen plan](plan.md) limited this run to four generic official Clerk
pages/documents. Read-only GETs returned HTTP 200 for all four. The
[capture manifest](capture_manifest.json) records exact URLs, UTC times,
durations, content types, byte counts and SHA-256 hashes. The original bytes
and a one-page PDF preview remain in an ACL-restricted, Git-ignored private
directory. No property-specific record, party name, PIN value, deed image or paid product was
requested. The [technical verification](verification.json) and
[saved output](verify.log) report exit 0; the verifier checks the four byte
hashes, frozen plan/manifest, file sizes and private ACL.
The one-line verification output was transcoded from PowerShell's UTF-16
capture to UTF-8 with normalized line endings for Git review; the pinned log
hash is of the saved UTF-8 file.

The capture used Windows PowerShell `Invoke-WebRequest` once per URL in the
manifest, inside a loop with `$doc.url` set to that exact URL and `$path` set
to the corresponding new file in the protected directory:

```powershell
$response = Invoke-WebRequest -Uri $doc.url -TimeoutSec 15 -UseBasicParsing -OutFile $path -PassThru
```

The loop also timed each request, checked the response type and 1 MiB file
cap, hashed each saved file with `Get-FileHash -Algorithm SHA256`, and wrote
the resulting [manifest](capture_manifest.json). The separate exploratory
portal probe used `Invoke-WebRequest -Uri
'https://crs.cookcountyclerkil.gov/Search' -TimeoutSec 15
-UseBasicParsing`; it returned 403 and saved no property data. The four GET
durations and the replay command's exit code/duration are in the manifest and
[verification record](verification.json). The exact expanded private file
paths were deliberately omitted from public artifacts.

## Findings

The [Clerk's recording-search page](https://www.cookcountyclerkil.gov/recordings/search-recordings)
links to a separate public search site and describes searches by address,
PIN, parties and indexed detail. The captured page is a route description,
not a matched result for a sampled Assessor row.

The one-page
[Transfer List License Agreement Summary](https://www.cookcountyclerkil.gov/publication/transfer-list-license-agreement-summary)
offers monthly deed-transfer indexing data that includes document number,
consideration, PIN, execution date and recording date. It states a USD 400
annual fee and a license agreement. It does **not** identify a contract or
closing date or establish when an index row first became available. The
document also cautions that address data is outside the Clerk's own index.
The PDF was extracted with isolated `pypdf 6.1.0`; despite cross-reference
warnings, the single page rendered legibly with isolated `PyMuPDF 1.26.3`
and was visually inspected. Both tools were installed only under ignored
private capture storage, leaving the project environment lock unchanged.

The [fee page](https://www.cookcountyclerkil.gov/recordings/recording-fees)
lists USD 5 for a non-certified electronic copy and an additional card charge
for online purchases. The [FAQ](https://www.cookcountyclerkil.gov/recordings/recording-faqs)
says online purchase applies to post-1985 recorded documents and describes
separate corrective instruments/affidavits. A corrected Assessor row therefore
cannot be assumed to have a one-to-one replacement document without a
row-specific audit.

An exploratory direct shell request to the separate recording-search endpoint
returned HTTP 403; this was outside the four-URL capture and did not retrieve
a property result. Browser control was unavailable in this session. The
MiKTeX `pdftotext` launcher was also unconfigured, so the isolated PDF tools
above were used. These access observations do not establish general portal
availability or source semantics.

## Decision and next action

[ADR 0053](../../decisions/0053-cook-clerk-date-and-access-route.md) keeps the
Assessor rows in a private audit and records the Clerk transfer list as an
unacquired, paid candidate. No USD 400 license or USD 5 document was bought;
no terms were accepted. An execution date is not automatically a closing
date, and these pages do not provide historical row-availability evidence.
The Cook source audit still has one partial and zero complete manual rubrics,
zero certified sale labels, and no eligible primary 90-day close-origin rows.

Continue the private manual review and seek a permitted, row-specific Clerk
route or custodian clarification of date, consideration, correction, first
publication and use rights. A monetary acquisition needs its own budget and
rights decision. No model training or international work is unlocked.

Replay from the project root, with the authorized private capture present:

```powershell
& 'runs/u0-cook-clerk-public-docs-v1-20261003T014926Z/verify_artifacts.ps1'
```
