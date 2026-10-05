# U0 HCPA exact-byte prospective capture, 5 October 2026

Status: **source observation verified; historical 90-day qualification NO-GO; G-US PENDING**.
Requirements: US02, US05, US08, US22, US24. Code commit at capture:
`34e36bdd208b450b9e37e1b3ad9a136177c3a20b`, with a clean working tree.

## Actual observations

The fixed [HCPA public download page](https://downloads.hcpafl.org/Default.aspx)
served both ZIPs through its ASP.NET file table. The capture fetched a fresh
listing, bound each exact filename to its postback control, and required the
response's `Content-Disposition` filename to match. It saved raw bytes and the
listing HTML under restricted, Git-ignored local storage. The tracked
[parcel manifest](parcels_manifest.json) and [All Sales manifest](allsales_manifest.json)
contain no row-level data.

| File | Capture completed UTC | Bytes | SHA-256 |
| --- | --- | ---: | --- |
| `parcels_10_02_2026.zip` | 2026-10-05 09:12:00 | 155,508,869 | `1443f2068fe52d8d04d0d91da047a25b2868ec090f47a95cbac9c44d313c1f39` |
| `allsales_09_18_2026.zip` | 2026-10-05 09:14:57 | 71,234,943 | `847854d9139fe3811506991d3c41d961581a92a648bb661c4bd9d166591366c7` |

Independent `Get-FileHash -Algorithm SHA256` checks matched both saved ZIPs and
listing HTML hashes in the manifests. The All Sales ZIP also matches the exact
copy first downloaded on 28 September. The capture checks response identity,
ZIP magic and byte limits; it **does not** certify ZIP member structure,
property identity, label validity or first publication date. The new parcel
ZIP has not been ingested or structurally audited.

The first parcel attempt at 08:55 UTC used code without the response-filename
check. Its bytes matched the later capture, but it is not the provenance run.
The clean-commit 09:08–09:12 capture above is the accepted source observation.

## Checks and source decision

The [gate record](test_gate.json) records 12 focused listing/release tests,
Ruff lint and format, a dependency audit with no known vulnerabilities, the
two live captures, and independent hash checks. Code, Python and security
reviewers rechecked the capture after fixes. No full engineering-suite rerun
was made for this source-only checkpoint; the prior full-suite result remains
separate evidence.

These bytes were observed on 5 October, so they cannot establish that this
exact parcel version was available at any earlier prediction origin. A 90-day
origin beginning on 5 October can only be assessed on later sales after the
horizon and source lag mature. As of this report, there are **zero** such
matured labels. The older 2025 parcel archive remains blocked by
[ADR 0095](../../decisions/0095-hcpa-archive-listing-asof-boundary.md): its
listing was archived in April, but no contemporaneous checksum or exact bytes
have been recovered in the current project evidence.

Separate All Sales blockers remain: `S_DATE` is documented only as a sale
date, record-level first availability and one-dwelling consideration are
unverified, the 200-record manual audit has zero completed rubrics, and
commercial AVM/redistribution rights have not been established. The
[custodian inquiry](../../data/requests/hcpa_all_sales_inquiry_draft.md) is
ready for the owner to send but delivery is unverified. No HCPA model is
trained or promoted on these files. This single county cannot satisfy the
multi-market G-US coverage requirement.

## Next runnable work

Complete source review on the frozen HCPA sample, obtain the custodian's
field/rights answers through the authorised channel, and continue exact
source captures when new releases appear. Keep the working King historical
research predictor available. If an earlier exact parcel release and sale
semantics become verifiable, run one fixed OFF baseline on eligible matured
sales; otherwise wait for genuinely prospective HCPA outcomes without
relabeling old data as untouched.
